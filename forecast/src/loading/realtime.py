"""실시간 수집 로그 → 배차간격(headway) 실측 추출.  [Phase 0]

서버(cron)가 쌓는 실시간 지하철 스냅샷(`data/subway_realtime/*.jsonl`)을 파싱해
역×시간대 **배차간격(초)** 을 산출한다. 결과 `data/realtime_headway.csv` 는
`config.headway_min_at()` 가 읽어 첨두 모형의 '배차/2' 가정을 실측으로 교체한다.

원리: 실시간 도착정보(realtimeStationArrival)는 한 스냅샷에 다가오는 열차 여러 대의
      도착예정초(barvlDt)를 준다. 같은 (호선·역·방향)에서 도착예정초를 정렬해
      **연속 두 대의 차이 = 그 순간의 배차간격** 으로 본다. 스냅샷을 여러 개 모아
      (호선·역·시) 중앙값을 취하면 안정적인 배차 표본이 된다.

실시간 응답은 소급 조회가 안 되므로 서버가 스냅샷을 쌓고, 이 스크립트는 로컬로
내려받은(`scripts/sync_realtime.sh`) jsonl 을 읽는다.

실행:  python -m src.loading.realtime [jsonl_dir]
산출:  data/realtime_headway.csv  (line, station, hour, headway_sec, n_samples)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

from src import config

# 서울 실시간 지하철 subwayId → 호선번호 (1001..1009 = 1~9호선). 광역/경전철은 무시.
SUBWAY_ID_TO_LINE = {f"100{i}": i for i in range(1, 10)}

# 배차간격 유효범위(초). 30초 미만·30분 초과는 노이즈로 버린다.
HEADWAY_MIN_SEC = 30
HEADWAY_MAX_SEC = 1800


def _line_of(subway_id) -> "int | None":
    return SUBWAY_ID_TO_LINE.get(str(subway_id))


def iter_records(jsonl_dir):
    """디렉터리의 모든 *.jsonl 레코드를 하나씩 yield (깨진 줄은 건너뜀)."""
    d = Path(jsonl_dir)
    for fp in sorted(d.glob("*.jsonl")):
        with open(fp, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue


def extract_headway(jsonl_dir) -> pd.DataFrame:
    """도착 스냅샷 → (line, station, dir, daytype, hour, headway_sec) 표본 DF."""
    rows = []
    for rec in iter_records(jsonl_dir):
        if rec.get("service") != "realtimeStationArrival":
            continue
        lst = (rec.get("raw_response") or {}).get("realtimeArrivalList") or []
        try:
            ts = datetime.fromisoformat(rec["collected_at"])
        except (KeyError, ValueError):
            continue
        wd = ts.weekday()
        daytype = "평일" if wd < 5 else ("토요일" if wd == 5 else "일요일")

        # (호선·역·방향)별로 도착예정초를 모은다.
        buckets: dict = {}
        for e in lst:
            ln = _line_of(e.get("subwayId"))
            if ln is None:
                continue
            try:
                eta = int(str(e.get("barvlDt")).strip())
            except (TypeError, ValueError):
                continue
            if eta <= 0:            # 이미 도착/진입(0) 은 간격 계산에서 제외
                continue
            key = (ln, e.get("statnNm"), e.get("updnLine"))
            buckets.setdefault(key, []).append(eta)

        # 연속 두 대의 도착예정초 차이 = 순간 배차간격.
        for (ln, st, dr), etas in buckets.items():
            etas.sort()
            for a, b in zip(etas, etas[1:]):
                gap = b - a
                if HEADWAY_MIN_SEC <= gap <= HEADWAY_MAX_SEC:
                    rows.append((ln, st, dr, daytype, ts.hour, gap))

    return pd.DataFrame(
        rows, columns=["line", "station", "dir", "daytype", "hour", "headway_sec"])


def build_headway_table(jsonl_dir) -> pd.DataFrame:
    """표본 → (line, station, hour) 중앙 배차간격 + 표본수."""
    df = extract_headway(jsonl_dir)
    if df.empty:
        return df
    g = (df.groupby(["line", "station", "hour"], as_index=False)
           .agg(headway_sec=("headway_sec", "median"),
                n_samples=("headway_sec", "size")))
    g["headway_sec"] = g["headway_sec"].round(0).astype(int)
    return g.sort_values(["line", "station", "hour"]).reset_index(drop=True)


def main() -> None:
    jsonl_dir = sys.argv[1] if len(sys.argv) > 1 else str(config.REALTIME_DIR)
    print(f"[realtime] 읽는 중: {jsonl_dir}")
    if not Path(jsonl_dir).exists():
        print(f"  (경로 없음) 먼저 scripts/sync_realtime.sh 로 서버 데이터를 내려받으세요.")
        sys.exit(0)

    table = build_headway_table(jsonl_dir)
    if table.empty:
        print("  배차 표본 없음(수집이 더 쌓여야 함). 산출 생략.")
        return

    config.DATA.mkdir(exist_ok=True)
    table.to_csv(config.REALTIME_HEADWAY_CSV, index=False)
    print(f"  저장: {config.REALTIME_HEADWAY_CSV}  ({len(table)} 행)")
    print(f"  역 {table['station'].nunique()}개 · 표본 합계 {int(table['n_samples'].sum())}건")
    show = table.copy()
    show["headway_min"] = (show["headway_sec"] / 60).round(1)
    print(show.head(20).to_string(index=False))


if __name__ == "__main__":
    main()
