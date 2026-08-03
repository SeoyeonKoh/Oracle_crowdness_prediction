"""계산 타당성 교차검증.

1) 볼륨 sanity: 우리 승하차 합계 vs CARD(OA-12914) 월별 합계 — 규모 정합성
2) 피크 정렬: 유료구역(승강장) 체류 피크시간 vs OA-12928 열차혼잡 피크시간
   두 지표가 같은 첨두시간(출퇴근)에 정렬되면 계산이 상식과 부합.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def volume_sanity(boarding_long: pd.DataFrame, card_monthly: pd.DataFrame) -> pd.DataFrame:
    """월×호선 승차 합계 비교. 반환: month, line, ours, card, ratio."""
    b = boarding_long[boarding_long["io"] == "승차"].copy()
    b["month"] = b["date"].dt.strftime("%Y%m")
    ours = (b.groupby(["month", "line"], as_index=False)["cnt"].sum()
             .rename(columns={"cnt": "ours"}))
    card = card_monthly.rename(columns={"boardings": "card"})[["month", "line", "card"]]
    m = ours.merge(card, on=["month", "line"], how="inner")
    m["ratio"] = m["ours"] / m["card"]
    return m.sort_values(["line", "month"]).reset_index(drop=True)


def peak_alignment(detail: pd.DataFrame, congestion: pd.DataFrame, top_n: int = 15) -> pd.DataFrame:
    """상위 역별 승강장 체류 피크시간 vs 열차혼잡 피크시간 비교.

    detail: 파이프라인 상세 DF(평일만 걸러 들어온다고 가정하지 않음 → 내부에서 평일 사용)
    congestion: load_train_congestion() 결과
    """
    d = detail[detail["daytype"] == "평일"]
    # 역별 총 승강장 체류로 상위 역 선정
    top = (d.groupby(["line", "station"])["occ_platform"].sum()
             .sort_values(ascending=False).head(top_n).index)

    occ_h = (d.groupby(["line", "station", "hour"])["occ_platform"].mean().reset_index())
    cong = congestion[congestion["daytype"] == "평일"]
    cong_h = (cong.groupby(["line", "station", "hour"])["pct"].mean().reset_index())

    rows = []
    for line, station in top:
        o = occ_h[(occ_h.line == line) & (occ_h.station == station)]
        c = cong_h[(cong_h.line == line) & (cong_h.station == station)]
        if o.empty or c.empty:
            continue
        o_peak = int(o.loc[o["occ_platform"].idxmax(), "hour"])
        c_peak = int(c.loc[c["pct"].idxmax(), "hour"])
        # 공통 시간대에서 상관계수
        merged = o.merge(c, on="hour", how="inner")
        corr = (merged["occ_platform"].corr(merged["pct"])
                if len(merged) > 2 else np.nan)
        rows.append({
            "line": line, "station": station,
            "occ_peak_hour": o_peak, "congestion_peak_hour": c_peak,
            "peak_gap_h": abs(o_peak - c_peak), "corr": round(float(corr), 3),
        })
    return pd.DataFrame(rows)
