"""실시간 배차 추출 테스트. (`python3 tests/test_realtime.py` 로도 실행)"""
import json
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.loading import realtime          # noqa: E402


def _snapshot(collected_at, arrivals):
    """arrivals: [(subwayId, statnNm, updnLine, barvlDt), ...] → 도착 스냅샷 레코드."""
    return {
        "source": "seoul_subway_realtime", "collected_at": collected_at,
        "name": "arrival_test", "service": "realtimeStationArrival", "target": "왕십리",
        "raw_response": {"realtimeArrivalList": [
            {"subwayId": sid, "statnNm": st, "updnLine": dr, "barvlDt": str(eta)}
            for (sid, st, dr, eta) in arrivals]},
    }


def _write(tmpdir, records):
    fp = os.path.join(tmpdir, "2026-08-04.jsonl")
    with open(fp, "w", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")
    return tmpdir


def test_headway_from_consecutive_etas():
    """같은 (호선·역·방향)에서 연속 도착예정초 차이 = 배차간격."""
    with tempfile.TemporaryDirectory() as d:
        # 2호선 왕십리 상행: 60s, 240s, 480s → 간격 180, 240
        rec = _snapshot("2026-08-04T08:15:00+09:00",
                        [("1002", "왕십리", "상행", 60),
                         ("1002", "왕십리", "상행", 240),
                         ("1002", "왕십리", "상행", 480)])
        _write(d, [rec])
        df = realtime.extract_headway(d)
        gaps = sorted(df["headway_sec"].tolist())
        assert gaps == [180, 240], gaps
        assert set(df["hour"]) == {8}
        assert set(df["line"]) == {2}


def test_ignores_arrived_and_out_of_range():
    """barvlDt<=0(도착)과 비정상 간격은 제외."""
    with tempfile.TemporaryDirectory() as d:
        rec = _snapshot("2026-08-04T09:00:00+09:00",
                        [("1002", "왕십리", "상행", 0),      # 도착 → 제외
                         ("1002", "왕십리", "상행", 60),
                         ("1002", "왕십리", "상행", 90)])     # 간격 30 (경계, 유효)
        _write(d, [rec])
        df = realtime.extract_headway(d)
        assert df["headway_sec"].tolist() == [30], df["headway_sec"].tolist()


def test_build_table_median():
    """여러 스냅샷 → (line, station, hour) 중앙값 + 표본수."""
    with tempfile.TemporaryDirectory() as d:
        recs = [
            _snapshot("2026-08-04T08:05:00+09:00",
                      [("1002", "왕십리", "상행", 100), ("1002", "왕십리", "상행", 400)]),  # 300
            _snapshot("2026-08-04T08:35:00+09:00",
                      [("1002", "왕십리", "상행", 100), ("1002", "왕십리", "상행", 340)]),  # 240
        ]
        _write(d, recs)
        t = realtime.build_headway_table(d)
        row = t[(t["line"] == 2) & (t["station"] == "왕십리") & (t["hour"] == 8)].iloc[0]
        assert row["n_samples"] == 2
        assert row["headway_sec"] == 270   # median(300,240)


def _run_all():
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    for fn in fns:
        fn()
        print(f"  ✓ {fn.__name__}")
    print(f"통과: {len(fns)}개")


if __name__ == "__main__":
    _run_all()
