"""서버 수집본 → 앱이 읽을 realtime.json 한 개로 가공.

세 가지를 한 파일에 담는다.
  ① headway    배차간격 실측  — subway_realtime 스냅샷의 barvlDt 차분 (src/loading/realtime.py 와 동일 원리)
  ② arrivals   도착정보       — 가장 최근 스냅샷의 도착 예정 열차
  ③ congestion 실시간 혼잡도  — citydata 의 AREA_CONGEST_LVL (지하철 API 에는 없다)

서버에서 실행한다(수집 원본이 서버에 있으므로). pandas 없이 표준 라이브러리만 쓴다.

실행:
  python3 scripts/build_realtime_json.py                 # 기본 위치에 출력
  python3 scripts/build_realtime_json.py --out /tmp/realtime.json
"""

import argparse
import json
import os
import statistics
import sys
from datetime import datetime, timedelta
from glob import glob

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SUBWAY_DIR = os.path.join(ROOT, "data", "subway_realtime")
CITY_DIR = os.path.join(ROOT, "data", "citydata")

# 서울 실시간 지하철 subwayId → 호선번호 (src/loading/realtime.py 와 동일)
LINE_OF = {f"100{i}": i for i in range(1, 10)}

# 배차간격 유효범위(초). 30초 미만·30분 초과는 노이즈.
HEADWAY_MIN_SEC, HEADWAY_MAX_SEC = 30, 1800

# 배차간격을 계산할 때 돌아볼 시간(분). 짧으면 표본 부족, 길면 '지금'이 아니게 된다.
HEADWAY_WINDOW_MIN = 90


def norm_station(name):
    """'건대입구역'(citydata) 과 '건대입구'(지하철 API) 를 같은 키로 맞춘다."""
    s = (name or "").strip()
    return s[:-1] if len(s) > 1 and s.endswith("역") else s


def iter_jsonl(directory, days=2):
    """최근 며칠치 *.jsonl 레코드를 yield (깨진 줄은 건너뜀)."""
    for fp in sorted(glob(os.path.join(directory, "*.jsonl")))[-days:]:
        with open(fp, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def parse_ts(s):
    try:
        return datetime.fromisoformat(s)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------
# ① 배차간격
# ---------------------------------------------------------------

def build_headway(now):
    """(호선, 역)별 최근 배차간격 중앙값(초)."""
    cutoff = now - timedelta(minutes=HEADWAY_WINDOW_MIN)
    samples = {}   # (line, station) -> [gap_sec, ...]

    for rec in iter_jsonl(SUBWAY_DIR):
        if rec.get("service") != "realtimeStationArrival":
            continue
        ts = parse_ts(rec.get("collected_at"))
        if ts is None or ts < cutoff:
            continue
        lst = (rec.get("raw_response") or {}).get("realtimeArrivalList") or []

        # (호선·역·방향)별로 도착예정초를 모아 연속 차이를 배차간격으로 본다.
        buckets = {}
        for e in lst:
            line = LINE_OF.get(str(e.get("subwayId")))
            if line is None:
                continue
            try:
                eta = int(str(e.get("barvlDt")).strip())
            except (TypeError, ValueError):
                continue
            if eta <= 0:          # 이미 도착/진입은 간격 계산에서 제외
                continue
            buckets.setdefault((line, e.get("statnNm"), e.get("updnLine")), []).append(eta)

        for (line, station, _dir), etas in buckets.items():
            etas.sort()
            for a, b in zip(etas, etas[1:]):
                gap = b - a
                if HEADWAY_MIN_SEC <= gap <= HEADWAY_MAX_SEC:
                    samples.setdefault((line, norm_station(station)), []).append(gap)

    out = {}
    for (line, station), gaps in samples.items():
        out[f"{line}|{station}"] = {
            "line": line,
            "station": station,
            "headway_sec": int(round(statistics.median(gaps))),
            "n_samples": len(gaps),
            "window_min": HEADWAY_WINDOW_MIN,
        }
    return out


# ---------------------------------------------------------------
# ② 도착정보
# ---------------------------------------------------------------

def build_arrivals(now):
    """역별 '가장 최근 스냅샷'의 도착 예정 열차 목록."""
    latest = {}    # station -> (ts, [열차...])

    for rec in iter_jsonl(SUBWAY_DIR, days=1):
        if rec.get("service") != "realtimeStationArrival":
            continue
        ts = parse_ts(rec.get("collected_at"))
        if ts is None:
            continue
        station = norm_station(rec.get("target"))
        if station in latest and latest[station][0] >= ts:
            continue

        trains = []
        for e in ((rec.get("raw_response") or {}).get("realtimeArrivalList") or []):
            line = LINE_OF.get(str(e.get("subwayId")))
            if line is None:
                continue
            try:
                eta = int(str(e.get("barvlDt")).strip())
            except (TypeError, ValueError):
                eta = None
            trains.append({
                "line": line,
                "dir": e.get("updnLine"),           # 상행/하행 · 내선/외선
                "dest": e.get("bstatnNm"),          # 종착역
                "eta_sec": eta,
                "msg": e.get("arvlMsg2"),           # "전역 출발", "3분 후" 등
                "current": e.get("arvlMsg3"),       # 현재 위치 역
            })
        trains.sort(key=lambda t: (t["eta_sec"] is None, t["eta_sec"]))
        latest[station] = (ts, trains)

    return {st: {"updated_at": ts.isoformat(), "trains": trains}
            for st, (ts, trains) in latest.items()}


# ---------------------------------------------------------------
# ③ 실시간 혼잡도
# ---------------------------------------------------------------

def build_congestion(now):
    """지점별 최신 실시간 인구·혼잡도 (+ 예보)."""
    latest = {}   # station -> (ts, dict)

    for rec in iter_jsonl(CITY_DIR, days=1):
        ts = parse_ts(rec.get("collected_at"))
        if ts is None or not rec.get("area_nm"):
            continue
        station = norm_station(rec["area_nm"])
        if station in latest and latest[station][0] >= ts:
            continue

        forecast = []
        for f in (rec.get("ppltn_forecast") or [])[:6]:
            forecast.append({
                "time": f.get("FCST_TIME"),
                "level": f.get("FCST_CONGEST_LVL"),
                "ppltn_min": f.get("FCST_PPLTN_MIN"),
                "ppltn_max": f.get("FCST_PPLTN_MAX"),
            })

        latest[station] = (ts, {
            "area_nm": rec["area_nm"],
            "level": rec.get("congest_lvl"),
            "message": rec.get("congest_msg"),
            "ppltn_min": rec.get("ppltn_min"),
            "ppltn_max": rec.get("ppltn_max"),
            "base_time": rec.get("ppltn_base_time"),
            "forecast": forecast,
        })

    return {st: dict(v, updated_at=ts.isoformat()) for st, (ts, v) in latest.items()}


# ---------------------------------------------------------------

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(ROOT, "data", "realtime.json"))
    args = ap.parse_args()

    now = datetime.now().astimezone()
    payload = {
        "generated_at": now.isoformat(),
        "headway": build_headway(now),
        "arrivals": build_arrivals(now),
        "congestion": build_congestion(now),
    }

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))

    size_kb = os.path.getsize(args.out) / 1024
    print(f"[realtime] {args.out}  ({size_kb:.1f} KB)")
    print(f"  배차간격  {len(payload['headway'])} 개 (호선×역)")
    print(f"  도착정보  {len(payload['arrivals'])} 개 역")
    print(f"  혼잡도    {len(payload['congestion'])} 개 지점")
    if not payload["headway"]:
        print("  ⚠ 배차 표본 0 — 수집이 더 쌓여야 합니다", file=sys.stderr)


if __name__ == "__main__":
    main()
