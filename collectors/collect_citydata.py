"""
서울 실시간 도시데이터(citydata) 수집기
==========================================

수집 대상 : 서울 열린데이터광장 - 서울 실시간 도시데이터 (citydata)
필요 인증키 : SEOUL_OPENDATA_GENERAL_KEY (일반 인증키, config/APIkey.py)
저장 위치 : (프로젝트 루트)/data/citydata/YYYY-MM-DD.jsonl
파일 위치 : collectors/ 안. 어디서 실행하든 경로는 파일 기준으로 계산한다.

이 프로젝트는 앞으로 수집기가 여러 개가 된다.
(지하철 도착정보, 서울교통공사 혼잡도정보 등)
그래서 파일명·폴더·변수명에 어느 데이터인지를 모두 드러낸다.

원칙:
  1. 가공하지 않는다. 원본 JSON을 통째로 남긴다.
  2. 실패해도 죽지 않는다. 한 장소가 실패해도 다음 장소로 넘어간다.
  3. 호출 수를 스스로 센다. 하루 한도에 닿으면 그날은 더 호출하지 않는다.

알아둘 것 (매뉴얼 v8.5 기준):
  혼잡도 등급은 '그 장소의 최근 28일 평균 인구 대비 비율'이다.
    여유 50% 이하 / 보통 50~75% / 약간 붐빔 75~100% / 붐빔 100% 초과
  장소끼리 비교할 수 없고, 기준선도 28일 롤링으로 계속 움직인다.
  등급만 저장하면 나중에 다시 계산할 수 없으므로 인구수를 함께 저장한다.

  실시간 인구는 집계 후 15분 뒤에 제공된다. (10:10~10:15 집계분 → 10:30 제공)
  따라서 5분 간격 호출의 실익이 크지 않다.

실행:
  python3 collect_citydata.py

한 번 실행하면 대상 장소를 한 바퀴 돌고 끝난다.
반복 실행은 cron이 담당한다. (README.md 참고)
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import requests

# ============================================================
# 인증키
# ============================================================
# 키는 이 파일에 적지 않는다. config/APIkey.py 에서 읽어온다.
# APIkey.py 는 .gitignore 에 들어 있어 깃허브에 올라가지 않는다.
# 만드는 법은 config/APIkey_example.py 참고.
#
# 이름을 데이터셋이 아니라 '발급처 + 키 종류'로 붙인 이유:
# 열린데이터광장은 데이터셋마다 키를 주지 않는다. 일반 인증키 하나로
# 실시간 도시데이터를 포함한 여러 서울시 OpenAPI를 호출한다.

# 이 파일은 collectors/ 안에 있으므로, 프로젝트 루트는 한 단계 위다.
# 어느 폴더에서 실행해도 동작하도록 모든 경로를 이 기준으로 계산한다.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "config"))

try:
    from APIkey import SEOUL_OPENDATA_GENERAL_KEY
except ImportError:
    SEOUL_OPENDATA_GENERAL_KEY = os.environ.get("SEOUL_OPENDATA_GENERAL_KEY", "")

# ============================================================
# 설정 — 여기만 고치면 된다
# ============================================================

# 수집 대상 장소.
# 장소명 대신 POI 코드로 호출한다. 매뉴얼 표 3-1에 따르면
# AREA_NM 자리에 '핫스팟 장소명 또는 코드명'을 넣을 수 있다.
# 코드를 쓰면 한글 인코딩 문제와 오타 문제가 사라진다.
#
# 아래는 경기도민 유입 관문 환승역 12곳이다. 확정이 아니다.
# 승강기 가동현황이 2주쯤 쌓이면 접근성 취약 역으로 교체를 검토한다.
CITYDATA_TARGET_POIS = [
    ("POI033", "서울역"),                    # 1·4·경의중앙·공항철도
    ("POI029", "사당역"),                    # 2·4 + 광역버스
    ("POI017", "고속터미널역"),               # 3·7·9
    ("POI038", "신도림역"),                  # 1·2
    ("POI119", "잠실역"),                    # 2·8
    ("POI045", "왕십리역"),                  # 2·5·경의중앙·수인분당
    ("POI081", "청량리 제기동 일대 전통시장"),   # 1·경의중앙·경춘·수인분당
    ("POI014", "강남역"),                    # 2·신분당
    ("POI006", "종로·청계 관광특구"),          # 1·3·5 (종로3가)
    ("POI051", "총신대입구(이수)역"),          # 4·7
    ("POI061", "김포공항"),                  # 5·9·공항철도·김포골드
    ("POI043", "연신내역"),                  # 3·6
]

# 이 수집기가 하루에 쓸 수 있는 호출 수.
# 열린데이터광장이 일일 한도를 공개하지 않아 1,000회를 가정하고 여유를 뒀다.
# 나중에 다른 수집기가 같은 키를 쓰게 되면 이 값을 나눠 배분해야 한다.
CITYDATA_MAX_CALLS_PER_DAY = 950

CITYDATA_REQUEST_TIMEOUT_SEC = 20   # 이 시간을 넘기면 포기
CITYDATA_RETRY_COUNT = 1            # 실패 시 재시도 횟수 (폭주 방지로 1회만)

# ============================================================
# 아래부터는 건드릴 일이 거의 없다
# ============================================================

KST = timezone(timedelta(hours=9))

CITYDATA_SOURCE_ID = "seoul_citydata"   # 레코드마다 어느 수집기가 만든 건지 표시
CITYDATA_API_URL = "http://openapi.seoul.go.kr:8088/{key}/json/citydata/1/5/{poi}"

CITYDATA_DIR = os.path.join(PROJECT_ROOT, "data", "citydata")
CITYDATA_COUNTER_PATH = os.path.join(CITYDATA_DIR, "call_counter.json")


def now_kst():
    return datetime.now(KST)


def log(msg):
    print(f"[{now_kst().strftime('%Y-%m-%d %H:%M:%S')}] [citydata] {msg}", flush=True)


# ---------- 호출 수 세기 ----------

def load_citydata_call_count(today):
    try:
        with open(CITYDATA_COUNTER_PATH, encoding="utf-8") as f:
            counter = json.load(f)
        if counter.get("date") == today:
            return int(counter.get("count", 0))
    except Exception:
        pass
    return 0


def save_citydata_call_count(today, count):
    try:
        with open(CITYDATA_COUNTER_PATH, "w", encoding="utf-8") as f:
            json.dump({"source": CITYDATA_SOURCE_ID, "date": today, "count": count}, f)
    except Exception as e:
        log(f"주의: 호출 수 저장 실패 ({e})")


# ---------- API 호출 ----------

def fetch_citydata(poi_code):
    """POI 코드 하나의 도시데이터를 받아온다. 실패하면 예외를 던진다."""
    url = CITYDATA_API_URL.format(key=SEOUL_OPENDATA_GENERAL_KEY, poi=quote(poi_code))
    last_error = None

    for attempt in range(CITYDATA_RETRY_COUNT + 1):
        try:
            res = requests.get(url, timeout=CITYDATA_REQUEST_TIMEOUT_SEC)
            res.raise_for_status()
            return res.json()
        except Exception as e:
            last_error = e
            if attempt < CITYDATA_RETRY_COUNT:
                time.sleep(2)

    raise last_error


def extract_live_ppltn_fields(payload):
    """
    조회·집계에 쓸 핵심 값만 뽑는다.
    구조가 예상과 달라도 None이 들어갈 뿐 오류를 내지 않는다.
    원본은 통째로 저장하므로 여기서 실패해도 데이터는 잃지 않는다.
    """
    citydata = payload.get("CITYDATA") or {}
    ppltn_list = citydata.get("LIVE_PPLTN_STTS") or []
    ppltn = ppltn_list[0] if ppltn_list else {}

    return {
        "area_nm": citydata.get("AREA_NM"),
        "area_cd": citydata.get("AREA_CD"),
        "ppltn_base_time": ppltn.get("PPLTN_TIME"),
        "congest_lvl": ppltn.get("AREA_CONGEST_LVL"),
        "congest_msg": ppltn.get("AREA_CONGEST_MSG"),
        # 등급은 28일 평균 대비 상대값이라 그것만으로는 재계산이 불가능하다.
        # 인구수를 남겨야 나중에 기준을 바꿔 다시 계산할 수 있다.
        "ppltn_min": ppltn.get("AREA_PPLTN_MIN"),
        "ppltn_max": ppltn.get("AREA_PPLTN_MAX"),
        "ppltn_forecast": ppltn.get("FCST_PPLTN"),
    }


def detect_citydata_api_error(payload):
    """정상 응답이면 CITYDATA 블록이 있다. 없으면 오류 메시지를 돌려준다."""
    if payload.get("CITYDATA"):
        return None
    result = payload.get("RESULT") or {}
    code = result.get("RESULT.CODE") or result.get("CODE") or "?"
    msg = result.get("RESULT.MESSAGE") or result.get("MESSAGE") or str(payload)[:200]
    return f"{code} {msg}"


# ---------- 본체 ----------

def main():
    if not SEOUL_OPENDATA_GENERAL_KEY:
        log("중단: 인증키가 없습니다. config/APIkey.py 를 만들고")
        log('       SEOUL_OPENDATA_GENERAL_KEY = "발급받은키"  한 줄을 넣으세요.')
        log("       (config/APIkey_example.py 참고)")
        sys.exit(1)

    os.makedirs(CITYDATA_DIR, exist_ok=True)

    cycle_started_at = now_kst()
    today = cycle_started_at.strftime("%Y-%m-%d")
    calls_used = load_citydata_call_count(today)
    calls_left = CITYDATA_MAX_CALLS_PER_DAY - calls_used

    if calls_left <= 0:
        log(
            f"오늘 호출 한도({CITYDATA_MAX_CALLS_PER_DAY}회)에 도달해 건너뜁니다. "
            f"내일 0시에 초기화됩니다."
        )
        return

    if calls_left < len(CITYDATA_TARGET_POIS):
        log(f"주의: 남은 호출 {calls_left}회. 앞쪽 {calls_left}곳만 수집합니다.")

    out_path = os.path.join(CITYDATA_DIR, f"{today}.jsonl")
    success_count = fail_count = 0

    with open(out_path, "a", encoding="utf-8") as out_file:
        for poi_code, poi_label in CITYDATA_TARGET_POIS:
            if calls_used >= CITYDATA_MAX_CALLS_PER_DAY:
                log("한도 도달로 이번 주기를 중단합니다.")
                break

            calls_used += 1
            try:
                payload = fetch_citydata(poi_code)
            except Exception as e:
                fail_count += 1
                log(f"실패 {poi_label}({poi_code}): {type(e).__name__} {e}")
                continue

            api_error = detect_citydata_api_error(payload)
            if api_error:
                fail_count += 1
                log(f"실패 {poi_label}({poi_code}): API 응답 오류 {api_error}")
                continue

            fields = extract_live_ppltn_fields(payload)
            record = {
                # 어느 수집기가 만든 레코드인지. 나중에 소스를 합칠 때 필요하다.
                "source": CITYDATA_SOURCE_ID,
                # 우리가 호출한 시각
                "collected_at": cycle_started_at.isoformat(),
                # 서울시가 값을 잰 시각 (약 15분 전). 집계는 이 시각 기준으로 한다.
                "ppltn_base_time": fields["ppltn_base_time"],
                "requested_poi_cd": poi_code,
                "area_cd": fields["area_cd"],
                "area_nm": fields["area_nm"],
                "congest_lvl": fields["congest_lvl"],
                "congest_msg": fields["congest_msg"],
                "ppltn_min": fields["ppltn_min"],
                "ppltn_max": fields["ppltn_max"],
                "ppltn_forecast": fields["ppltn_forecast"],
                # 응답 원본 전체. 지하철·버스·날씨 등이 모두 여기 들어 있다.
                "raw_response": payload,
            }
            out_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            success_count += 1
            log(
                f"수집 {poi_label} → {fields['congest_lvl']} "
                f"({fields['ppltn_min']}~{fields['ppltn_max']}명, "
                f"기준시각 {fields['ppltn_base_time']})"
            )

    save_citydata_call_count(today, calls_used)
    elapsed_sec = (now_kst() - cycle_started_at).total_seconds()
    log(
        f"완료: 성공 {success_count} / 실패 {fail_count} / {elapsed_sec:.1f}초 소요 · "
        f"오늘 누적 {calls_used}/{CITYDATA_MAX_CALLS_PER_DAY}회"
    )


if __name__ == "__main__":
    main()