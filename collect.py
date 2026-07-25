"""
서울 실시간 도시데이터 수집기
================================

하는 일:
  설정된 장소들의 실시간 도시데이터를 API로 받아와서, 받은 원본 그대로 파일에 저장한다.

원칙:
  1. 가공하지 않는다. 원본 JSON을 통째로 남긴다.
  2. 실패해도 죽지 않는다. 한 장소가 실패해도 다음 장소로 넘어간다.
  3. 호출 수를 스스로 센다. 하루 한도에 닿으면 그날은 더 호출하지 않는다.

중요 (매뉴얼 v8.5 기준):
  혼잡도 등급은 '그 장소의 최근 28일 평균 인구 대비 비율'로 정해진다.
    여유 50% 이하 / 보통 50~75% / 약간 붐빔 75~100% / 붐빔 100% 초과
  즉 장소끼리 비교할 수 없고, 기준선도 28일 롤링으로 계속 움직인다.
  따라서 등급만 저장하면 나중에 다시 계산할 수 없다. 인구수를 반드시 함께 저장한다.

  또한 실시간 인구는 집계 후 15분 뒤에 제공된다.
  (10:10~10:15 집계분 → 10:30 제공)
  그래서 5분 간격 호출의 실익이 크지 않다. 10분 간격으로 충분하다.

실행:
  python3 collect.py

이 파일은 한 번 실행하면 설정된 장소를 한 바퀴 돌고 끝난다.
반복 실행은 cron이 담당한다 (README.md 참고).
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import requests

# ============================================================
# 설정 — 여기만 고치면 된다
# ============================================================

# 인증키는 이 파일에 직접 적지 않는다.
# 같은 폴더에 secret.py 파일을 만들고 아래 한 줄만 넣는다.
#
#     API_KEY = "발급받은키"
#
# secret.py 는 .gitignore 에 들어 있어 깃허브에 올라가지 않는다.
# 이렇게 해야 코드를 공유해도 키가 새지 않는다.
try:
    from secret import API_KEY
except ImportError:
    API_KEY = os.environ.get("SEOUL_API_KEY", "")

# 수집 대상.
# 장소명 대신 POI 코드로 호출한다. 매뉴얼 표 3-1에 따르면
# AREA_NM 자리에 '핫스팟 장소명 또는 코드명'을 넣을 수 있다.
# 코드를 쓰면 한글 인코딩 문제와 오타 문제가 사라진다.
#
# 아래는 경기도민 유입 관문 환승역 12곳이다.
# 확정이 아니다. 승강기 가동현황이 2주쯤 쌓이면 접근성 취약 역으로 교체를 검토한다.
# 바꿀 때는 이 목록만 고치면 된다. (121장소 목록 원본에서 확인한 실제 코드)
AREAS = [
    ("POI033", "서울역"),                  # 1·4·경의중앙·공항철도
    ("POI029", "사당역"),                  # 2·4 + 광역버스
    ("POI017", "고속터미널역"),             # 3·7·9
    ("POI038", "신도림역"),                # 1·2
    ("POI119", "잠실역"),                  # 2·8
    ("POI045", "왕십리역"),                # 2·5·경의중앙·수인분당
    ("POI081", "청량리 제기동 일대 전통시장"),  # 1·경의중앙·경춘·수인분당
    ("POI014", "강남역"),                  # 2·신분당
    ("POI006", "종로·청계 관광특구"),        # 1·3·5 (종로3가)
    ("POI051", "총신대입구(이수)역"),        # 4·7
    ("POI061", "김포공항"),                # 5·9·공항철도·김포골드
    ("POI043", "연신내역"),                # 3·6
]

# 하루에 이만큼 호출하면 그날은 멈춘다.
# 실제 한도가 공개되어 있지 않아 1,000회를 가정하고 여유를 뒀다.
MAX_CALLS_PER_DAY = 950

# 한 번 호출에 이 시간을 넘기면 포기한다 (초)
TIMEOUT = 20

# 실패 시 다시 시도할 횟수. 폭주 방지를 위해 1회만.
RETRY = 1

# ============================================================
# 아래부터는 건드릴 일이 거의 없다
# ============================================================

KST = timezone(timedelta(hours=9))
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "data")
COUNTER_PATH = os.path.join(DATA_DIR, "call_counter.json")

API_URL = "http://openapi.seoul.go.kr:8088/{key}/json/citydata/1/5/{area}"


def now_kst():
    return datetime.now(KST)


def log(msg):
    print(f"[{now_kst().strftime('%Y-%m-%d %H:%M:%S')}] {msg}", flush=True)


# ---------- 호출 수 세기 ----------

def load_counter(today):
    try:
        with open(COUNTER_PATH, encoding="utf-8") as f:
            c = json.load(f)
        if c.get("date") == today:
            return int(c.get("count", 0))
    except Exception:
        pass
    return 0


def save_counter(today, count):
    try:
        with open(COUNTER_PATH, "w", encoding="utf-8") as f:
            json.dump({"date": today, "count": count}, f)
    except Exception as e:
        log(f"주의: 호출 수 저장 실패 ({e})")


# ---------- API 호출 ----------

def fetch(area_code):
    url = API_URL.format(key=API_KEY, area=quote(area_code))
    last_error = None

    for attempt in range(RETRY + 1):
        try:
            res = requests.get(url, timeout=TIMEOUT)
            res.raise_for_status()
            return res.json()
        except Exception as e:
            last_error = e
            if attempt < RETRY:
                time.sleep(2)

    raise last_error


def extract(payload):
    """
    저장하기 쉽게 핵심 값만 뽑아둔다.
    구조가 예상과 다르면 None이 들어갈 뿐, 오류를 내지 않는다.
    원본은 통째로 저장하므로 여기서 실패해도 데이터는 안 잃는다.
    """
    city = payload.get("CITYDATA") or {}
    ppltn_list = city.get("LIVE_PPLTN_STTS") or []
    ppltn = ppltn_list[0] if ppltn_list else {}

    return {
        "area_nm": city.get("AREA_NM"),
        "area_cd": city.get("AREA_CD"),
        "base_time": ppltn.get("PPLTN_TIME"),
        "congest_lvl": ppltn.get("AREA_CONGEST_LVL"),
        "congest_msg": ppltn.get("AREA_CONGEST_MSG"),
        # 등급은 28일 평균 대비 상대값이라 재계산이 불가능하다.
        # 인구수를 함께 남겨야 나중에 기준을 바꿔 다시 계산할 수 있다.
        "ppltn_min": ppltn.get("AREA_PPLTN_MIN"),
        "ppltn_max": ppltn.get("AREA_PPLTN_MAX"),
        "forecast": ppltn.get("FCST_PPLTN"),
    }


def is_error(payload):
    if payload.get("CITYDATA"):
        return None
    result = payload.get("RESULT") or {}
    code = result.get("RESULT.CODE") or result.get("CODE") or "?"
    msg = result.get("RESULT.MESSAGE") or result.get("MESSAGE") or str(payload)[:200]
    return f"{code} {msg}"


# ---------- 본체 ----------

def main():
    if not API_KEY:
        log("중단: 인증키가 없습니다. 같은 폴더에 secret.py 를 만들고")
        log('       API_KEY = "발급받은키"  한 줄을 넣으세요.')
        sys.exit(1)

    os.makedirs(DATA_DIR, exist_ok=True)

    started = now_kst()
    today = started.strftime("%Y-%m-%d")
    used = load_counter(today)
    remaining = MAX_CALLS_PER_DAY - used

    if remaining <= 0:
        log(f"오늘 호출 한도({MAX_CALLS_PER_DAY}회)에 도달해 건너뜁니다. 내일 0시에 초기화됩니다.")
        return

    if remaining < len(AREAS):
        log(f"주의: 남은 호출 {remaining}회. 앞쪽 {remaining}곳만 수집합니다.")

    out_path = os.path.join(DATA_DIR, f"{today}.jsonl")
    ok = fail = 0

    with open(out_path, "a", encoding="utf-8") as f:
        for code, label in AREAS:
            if used >= MAX_CALLS_PER_DAY:
                log("한도 도달로 이번 주기를 중단합니다.")
                break

            used += 1
            try:
                payload = fetch(code)
            except Exception as e:
                fail += 1
                log(f"실패 {label}({code}): {type(e).__name__} {e}")
                continue

            err = is_error(payload)
            if err:
                fail += 1
                log(f"실패 {label}({code}): API 응답 오류 {err}")
                continue

            core = extract(payload)
            record = {
                "collected_at": started.isoformat(),   # 우리가 호출한 시각
                "base_time": core["base_time"],        # 서울시가 값을 잰 시각 (약 15분 전)
                "requested_cd": code,
                "area_cd": core["area_cd"],
                "area_nm": core["area_nm"],
                "congest_lvl": core["congest_lvl"],
                "congest_msg": core["congest_msg"],
                "ppltn_min": core["ppltn_min"],
                "ppltn_max": core["ppltn_max"],
                "forecast": core["forecast"],
                "raw": payload,                        # 원본 전체
            }
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            ok += 1
            log(
                f"수집 {label} → {core['congest_lvl']} "
                f"({core['ppltn_min']}~{core['ppltn_max']}명, 기준시각 {core['base_time']})"
            )

    save_counter(today, used)
    elapsed = (now_kst() - started).total_seconds()
    log(
        f"완료: 성공 {ok} / 실패 {fail} / {elapsed:.1f}초 소요 · "
        f"오늘 누적 {used}/{MAX_CALLS_PER_DAY}회"
    )


if __name__ == "__main__":
    main()
