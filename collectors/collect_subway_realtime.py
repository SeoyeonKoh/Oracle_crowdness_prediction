"""
실시간 지하철 수집기 (subway_realtime)
==========================================

수집 대상 : 서울 열린데이터광장 - 실시간 지하철 API (swopenapi.seoul.go.kr)
             · realtimePosition       (노선 실시간 열차 위치)
             · realtimeStationArrival (역 실시간 도착정보 = 배차 간격 표본)
필요 인증키 : SEOUL_OPENDATA_SUBWAY_KEY  (일반 인증키와 별개, config/APIkey.py)
저장 위치 : (프로젝트 루트)/data/subway_realtime/YYYY-MM-DD.jsonl
파일 위치 : collectors/ 안. 어디서 실행하든 경로는 파일 기준으로 계산한다.

왜 모으나:
  혼잡 경보 기능의 '배차 간격 표본'과 도착 ETA를 위해서다. 실시간 지하철
  응답은 소급 조회가 불가능하므로 스냅샷을 찍어 쌓는다.

원칙(collect_citydata.py 와 동일):
  1. 가공하지 않는다. 원본 JSON을 통째로 남긴다.
  2. 실패해도 죽지 않는다. 한 호출이 실패해도 다음으로 넘어간다.
  3. 호출 수를 스스로 센다. 하루 한도(일반 키와 별개)에 닿으면 멈춘다.

실행:
  python3 collectors/collect_subway_realtime.py
  (반복은 cron 이 담당 — README 참고)
"""

import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import quote

import requests

# ============================================================
# 인증키 — config/APIkey.py 의 SEOUL_OPENDATA_SUBWAY_KEY
# ============================================================
# ⚠️ 도시데이터의 일반 인증키가 아니다. '실시간 지하철 인증키' 별도 신청분.
#    주소도 swopenapi.seoul.go.kr (일반 API는 openapi.seoul.go.kr)
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(PROJECT_ROOT, "config"))

try:
    from APIkey import SEOUL_OPENDATA_SUBWAY_KEY
except ImportError:
    SEOUL_OPENDATA_SUBWAY_KEY = os.environ.get("SEOUL_OPENDATA_SUBWAY_KEY", "")

# ============================================================
# 설정 — 여기만 고치면 된다
# ============================================================
# (레코드 이름, 서비스, 조회범위, 대상). 대상은 노선명(위치) 또는 역명(도착).
SUBWAY_REALTIME_TARGETS = [
    ("position_2호선", "realtimePosition",       "0/100", "2호선"),
    ("position_4호선", "realtimePosition",       "0/100", "4호선"),
    ("arrival_왕십리", "realtimeStationArrival", "0/20",  "왕십리"),
    ("arrival_동대문", "realtimeStationArrival", "0/20",  "동대문역사문화공원"),
]

# 실시간 지하철 키의 하루 한도(1,000회, 일반 키와 별개)에 여유를 둔 값.
SUBWAY_MAX_CALLS_PER_DAY = 950
SUBWAY_REQUEST_TIMEOUT_SEC = 15
SUBWAY_RETRY_COUNT = 1

# ============================================================
# 아래부터는 건드릴 일이 거의 없다
# ============================================================
KST = timezone(timedelta(hours=9))
SUBWAY_SOURCE_ID = "seoul_subway_realtime"
SUBWAY_API_URL = "http://swopenapi.seoul.go.kr/api/subway/{key}/json/{service}/{rng}/{target}"

SUBWAY_DIR = os.path.join(PROJECT_ROOT, "data", "subway_realtime")
SUBWAY_COUNTER_PATH = os.path.join(SUBWAY_DIR, "call_counter.json")


def now_kst():
    return datetime.now(KST)


def log(msg):
    print(f"[{now_kst().strftime('%Y-%m-%d %H:%M:%S')}] [subway_realtime] {msg}", flush=True)


# ---------- 호출 수 세기 ----------
def load_call_count(today):
    try:
        with open(SUBWAY_COUNTER_PATH, encoding="utf-8") as f:
            counter = json.load(f)
        if counter.get("date") == today:
            return int(counter.get("count", 0))
    except Exception:
        pass
    return 0


def save_call_count(today, count):
    try:
        with open(SUBWAY_COUNTER_PATH, "w", encoding="utf-8") as f:
            json.dump({"source": SUBWAY_SOURCE_ID, "date": today, "count": count}, f)
    except Exception as e:
        log(f"주의: 호출 수 저장 실패 ({e})")


# ---------- API 호출 ----------
def fetch_one(service, rng, target):
    """호출 하나. 실패하면 예외를 던진다."""
    url = SUBWAY_API_URL.format(
        key=quote(SEOUL_OPENDATA_SUBWAY_KEY), service=service,
        rng=rng, target=quote(target))
    last_error = None
    for attempt in range(SUBWAY_RETRY_COUNT + 1):
        try:
            res = requests.get(url, timeout=SUBWAY_REQUEST_TIMEOUT_SEC)
            res.raise_for_status()
            return res.json()
        except Exception as e:
            last_error = e
            if attempt < SUBWAY_RETRY_COUNT:
                time.sleep(2)
    raise last_error


def summarize(payload):
    """응답에서 건수/메시지만 간단히 뽑아 로그용으로 쓴다(원본은 통째로 저장)."""
    try:
        parts = []
        for k, v in payload.items():
            if isinstance(v, list):
                parts.append(f"{k} {len(v)}건")
            elif isinstance(v, dict) and "message" in v:
                parts.append(str(v.get("message"))[:40])
        return " · ".join(parts)
    except Exception:
        return "(요약 실패)"


# ---------- 본체 ----------
def main():
    if not SEOUL_OPENDATA_SUBWAY_KEY:
        log("중단: 인증키가 없습니다. config/APIkey.py 에")
        log('       SEOUL_OPENDATA_SUBWAY_KEY = "발급받은_실시간지하철_키"  를 넣으세요.')
        log("       (config/APIkey_example.py 참고 · 일반 키와 별개 신청)")
        sys.exit(1)

    os.makedirs(SUBWAY_DIR, exist_ok=True)
    started = now_kst()
    today = started.strftime("%Y-%m-%d")
    calls_used = load_call_count(today)

    if calls_used >= SUBWAY_MAX_CALLS_PER_DAY:
        log(f"오늘 호출 한도({SUBWAY_MAX_CALLS_PER_DAY}회) 도달. 건너뜁니다.")
        return

    out_path = os.path.join(SUBWAY_DIR, f"{today}.jsonl")
    ok = fail = 0
    with open(out_path, "a", encoding="utf-8") as out:
        for name, service, rng, target in SUBWAY_REALTIME_TARGETS:
            if calls_used >= SUBWAY_MAX_CALLS_PER_DAY:
                log("한도 도달로 이번 주기를 중단합니다.")
                break
            calls_used += 1
            try:
                payload = fetch_one(service, rng, target)
            except Exception as e:
                fail += 1
                log(f"실패 {name}: {type(e).__name__} {e}")
                continue
            record = {
                "source": SUBWAY_SOURCE_ID,
                "collected_at": started.isoformat(),
                "name": name,
                "service": service,
                "target": target,
                "raw_response": payload,   # 가공 없이 원본 전체
            }
            out.write(json.dumps(record, ensure_ascii=False) + "\n")
            ok += 1
            log(f"수집 {name} · {summarize(payload)}")

    save_call_count(today, calls_used)
    elapsed = (now_kst() - started).total_seconds()
    log(f"완료: 성공 {ok} / 실패 {fail} / {elapsed:.1f}초 · "
        f"오늘 누적 {calls_used}/{SUBWAY_MAX_CALLS_PER_DAY}회 · 저장 {SUBWAY_DIR}")


if __name__ == "__main__":
    main()
