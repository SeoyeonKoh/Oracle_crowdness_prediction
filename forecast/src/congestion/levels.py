"""1-2 4단계 혼잡 등급 — 여유 / 보통 / 주의 / 혼잡.

Phase 1의 절대 LOS 등급은 시간평균 특성상 대부분 A로 포화된다.
서비스에는 '상대적' 혼잡이 더 유용하므로, 밀도(명/㎡)의 데이터 기반 분위수로
4단계를 정의한다(팀 결정: 여유/보통/주의/혼잡).

기본 경계는 평일 승강장 밀도 분위수(p50/p80/p95)에서 도출했고 config처럼 조정 가능.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

LEVELS = ["여유", "보통", "주의", "혼잡"]

# 4단계 = 백분위(%) 구간. 여유 0–50 / 보통 50–80 / 주의 80–95 / 혼잡 95–100.
# 즉 '혼잡도 %'는 그 밀도가 평일 밀도 분포에서 차지하는 백분위수이고,
# 4단계 경계(p50/p80/p95)와 완전히 일관된다.
LEVEL_PCT_BANDS = [50, 80, 95]

# 밀도(명/㎡) 경계 — 평일 승강장 분포 분위수 기반(p50, p80, p95).
# density < b0 → 여유, < b1 → 보통, < b2 → 주의, 그 이상 → 혼잡.
DEFAULT_BREAKS = {
    "platform": [0.02, 0.04, 0.07],
    "concourse": [0.02, 0.04, 0.07],
}


def level_of(density: float, zone: str = "platform",
             breaks: "dict | None" = None) -> str:
    """밀도 → 4단계 라벨."""
    if density is None or (isinstance(density, float) and np.isnan(density)):
        return ""
    b = (breaks or DEFAULT_BREAKS)[zone]
    if density < b[0]:
        return LEVELS[0]
    if density < b[1]:
        return LEVELS[1]
    if density < b[2]:
        return LEVELS[2]
    return LEVELS[3]


def build_pct_table(summary: pd.DataFrame, daytype: str = "평일") -> dict:
    """구역별 백분위수→밀도 표(길이 101). 혼잡도 %의 근거가 되는 경험적 분포.

    table[i] = 평일 밀도 분포의 i퍼센타일 밀도값. (i=0..100)
    """
    out = {}
    for zone, col in [("platform", "density_platform"),
                      ("concourse", "density_concourse")]:
        v = summary[summary["daytype"] == daytype][col].dropna()
        v = v[v >= 0]
        qs = np.linspace(0, 1, 101)
        out[zone] = [round(float(x), 5) for x in np.quantile(v, qs)]
    return out


def percent_of(density: float, table: list) -> "float | None":
    """밀도 → 혼잡도 %(백분위수 0–100). table=build_pct_table 결과의 한 구역."""
    if density is None or (isinstance(density, float) and np.isnan(density)):
        return None
    # table[i]가 density 이하인 최대 i가 곧 백분위
    pct = int(np.searchsorted(table, density, side="right"))
    return float(max(0, min(100, pct)))


def level_from_percent(pct: "float | None") -> str:
    """혼잡도 %(백분위) → 4단계."""
    if pct is None:
        return ""
    if pct >= LEVEL_PCT_BANDS[2]:
        return LEVELS[3]
    if pct >= LEVEL_PCT_BANDS[1]:
        return LEVELS[2]
    if pct >= LEVEL_PCT_BANDS[0]:
        return LEVELS[1]
    return LEVELS[0]


def compute_breaks(summary: pd.DataFrame,
                   quantiles=(0.5, 0.8, 0.95)) -> dict:
    """요약 데이터의 평일 밀도 분위수로 구역별 경계 산출(데이터 기반)."""
    wk = summary[summary["daytype"] == "평일"]
    out = {}
    for zone, col in [("platform", "density_platform"),
                      ("concourse", "density_concourse")]:
        q = wk[col].quantile(list(quantiles))
        out[zone] = [round(float(q.loc[x]), 4) for x in quantiles]
    return out


def add_level(df: pd.DataFrame, breaks: "dict | None" = None) -> pd.DataFrame:
    """density_platform/concourse → level_platform/concourse 컬럼 추가."""
    out = df.copy()
    for zone in ("platform", "concourse"):
        out[f"level_{zone}"] = out[f"density_{zone}"].map(
            lambda d: level_of(d, zone, breaks))
    return out
