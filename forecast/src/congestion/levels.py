"""1-2 4단계 혼잡 등급 — 여유 / 보통 / 주의 / 혼잡.

[PATCH 5] 사용자에게 보여주는 4단계는 '절대' 기준으로 판정한다:
          첨두 밀도(peak_platform ÷ 유효면적)를 만원 밀도(CRUSH) 대비로 등급화.
          경계 = CRUSH의 1/3, 2/3, 1.0 (승강장 0.5/1.0/1.5 명/㎡).
          → 서울 전체가 붐비면 다 같이 '혼잡'이 뜨는, 물리량 기반 등급.
          ⚠️ 경계 분수(1/3·2/3)는 제안값 — 답사 체감 라벨로 검산 후 확정.

[PATCH 6] 기존 분위수(백분위) 체계는 삭제하지 않고 '평소보다 붐빔' 배지의
          판단 근거로 강등한다(busier_badge).

기존 함수(level_of, build_pct_table, percent_of, level_from_percent,
compute_breaks, add_level)는 하위 호환을 위해 전부 유지.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src import config

LEVELS = ["여유", "보통", "주의", "혼잡"]

# ══════════════════════════ [PATCH 5] 절대 등급 ═══════════════════════════

# CRUSH(만원 밀도) 대비 경계 분수. 승강장 CRUSH=1.5 → [0.5, 1.0, 1.5] 명/㎡.
# 참고: Fruin 대기공간(queueing) 기준으로도 1.5명/㎡는 '제약 시작' 구간과 부합.
ABS_BREAK_FRACTIONS = (1 / 3, 2 / 3, 1.0)

# 휠체어 프로필은 더 보수적(= 위험을 크게 잡음 = 더 일찍 '혼잡'으로 판정)이므로
# 임계가 더 낮다. 근거: ADA 휠체어 정지 점유면적(0.93㎡)이 일반 보행자 개인공간의
# 약 2배 → 같은 면적밀도에서 체감 제약이 약 2배. 임계를 절반으로 조인다.
WHEELCHAIR_TIGHTEN = 0.5

PROFILE_TIGHTEN = {"일반": 1.0, "휠체어": WHEELCHAIR_TIGHTEN}


def abs_breaks(zone: str, profile: str = "일반") -> list:
    """구역별 절대 밀도 경계(명/㎡) = CRUSH × 분수 × 프로필 계수."""
    crush = config.CRUSH_DENSITY[zone]
    k = PROFILE_TIGHTEN.get(profile, 1.0)
    return [crush * f * k for f in ABS_BREAK_FRACTIONS]


def abs_break_pcts(profile: str = "일반") -> list:
    """만원 대비 %로 표현한 경계 — 화면이 crushpct(pa/ca)를 그대로 등급화할 수 있다.

    density/CRUSH×100 = crushpct 이므로 경계는 CRUSH와 무관하게 분수×100이 된다.
    → 구역이 달라도 동일한 % 경계를 쓴다(일반 33.3/66.7/100).
    """
    k = PROFILE_TIGHTEN.get(profile, 1.0)
    return [round(f * k * 100, 1) for f in ABS_BREAK_FRACTIONS]


def level_abs(density: float, zone: str = "platform",
              profile: str = "일반") -> str:
    """첨두 밀도(명/㎡) → 절대 4단계 라벨."""
    if density is None or (isinstance(density, float) and np.isnan(density)):
        return ""
    b = abs_breaks(zone, profile)
    if density < b[0]:
        return LEVELS[0]
    if density < b[1]:
        return LEVELS[1]
    if density < b[2]:
        return LEVELS[2]
    return LEVELS[3]


def level_abs_from_pct(pct, zone: str = "platform",
                       profile: str = "일반") -> str:
    """만원 대비 %(crushpct) → 절대 4단계. export 단계에서 쓴다.

    density/CRUSH×100 = pct 이므로 밀도 대신 %로 바로 등급화할 수 있다.
    """
    if pct is None or (isinstance(pct, float) and np.isnan(pct)):
        return ""
    b = abs_break_pcts(profile)
    if pct < b[0]:
        return LEVELS[0]
    if pct < b[1]:
        return LEVELS[1]
    if pct < b[2]:
        return LEVELS[2]
    return LEVELS[3]


def crush_pct(density: float, zone: str = "platform") -> "float | None":
    """만원(CRUSH) 대비 % — '정원 대비'와 같은 의미의 절대 %."""
    if density is None or (isinstance(density, float) and np.isnan(density)):
        return None
    return round(100.0 * density / config.CRUSH_DENSITY[zone], 1)


def add_peak_density(df: pd.DataFrame) -> pd.DataFrame:
    """첨두 인원 → 유효면적 기준 밀도.

    density_peak_platform = peak_platform ÷ (승강장 면적 × 유효면적비율)
    density_eff_concourse = occ_concourse ÷ (대합실 면적 × 유효면적비율)
    (대합실은 열차 펄스가 없어 시간평균을 그대로 쓴다.)
    """
    out = df.copy()
    r = config.EFFECTIVE_AREA_RATIO
    with np.errstate(divide="ignore", invalid="ignore"):
        out["density_peak_platform"] = np.where(
            out["platform_area"] > 0,
            out["peak_platform"] / (out["platform_area"] * r["platform"]),
            np.nan,
        )
        out["density_eff_concourse"] = np.where(
            out["concourse_area"] > 0,
            out["occ_concourse"] / (out["concourse_area"] * r["concourse"]),
            np.nan,
        )
    return out


def add_level_abs(df: pd.DataFrame) -> pd.DataFrame:
    """절대 등급·만원 대비 % 컬럼 추가 (add_peak_density 이후 호출)."""
    out = df.copy()
    out["level_abs_platform"] = out["density_peak_platform"].map(
        lambda d: level_abs(d, "platform"))
    out["level_abs_concourse"] = out["density_eff_concourse"].map(
        lambda d: level_abs(d, "concourse"))
    out["crushpct_platform"] = out["density_peak_platform"].map(
        lambda d: crush_pct(d, "platform"))
    out["crushpct_concourse"] = out["density_eff_concourse"].map(
        lambda d: crush_pct(d, "concourse"))
    return out


# ══════════════════════════ [PATCH 6] 상대 → 배지 ═══════════════════════════

def busier_badge(density: float, usual_density: float,
                 ratio: float = 1.6) -> bool:
    """'평소보다 붐빔' 배지 여부.

    그 역·요일·시간대의 평소 밀도(usual_density) 대비 ratio배 이상이면 True.
    1.6배 기준은 기능 1-3 스펙의 기존 결정값. 절대 등급이 '주의' 이상일 때만
    배지를 띄우는 추가 조건은 서빙 쪽에서 결합한다.
    """
    if density is None or usual_density is None:
        return False
    if isinstance(density, float) and np.isnan(density):
        return False
    if isinstance(usual_density, float) and (np.isnan(usual_density) or usual_density <= 0):
        return False
    return bool(density >= ratio * usual_density)


# ══════════════ 이하 기존 분위수 체계 (하위 호환·배지 근거용 유지) ══════════════

LEVEL_PCT_BANDS = [50, 80, 95]

DEFAULT_BREAKS = {
    "platform": [0.02, 0.04, 0.07],
    "concourse": [0.02, 0.04, 0.07],
}


def level_of(density: float, zone: str = "platform",
             breaks: "dict | None" = None) -> str:
    """(구) 밀도 → 분위수 기반 4단계 라벨. 화면 표기용으로는 level_abs 를 쓸 것."""
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
    """구역별 백분위수→밀도 표(길이 101). '평소 분포에서의 위치' 계산용."""
    out = {}
    for zone, col in [("platform", "density_platform"),
                      ("concourse", "density_concourse")]:
        v = summary[summary["daytype"] == daytype][col].dropna()
        v = v[v >= 0]
        qs = np.linspace(0, 1, 101)
        out[zone] = [round(float(x), 5) for x in np.quantile(v, qs)]
    return out


def percent_of(density: float, table: list) -> "float | None":
    """밀도 → 백분위(0–100). 배지·통계용. 화면의 '혼잡도 %'는 crush_pct 를 쓸 것."""
    if density is None or (isinstance(density, float) and np.isnan(density)):
        return None
    pct = int(np.searchsorted(table, density, side="right"))
    return float(max(0, min(100, pct)))


def level_from_percent(pct: "float | None") -> str:
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
    wk = summary[summary["daytype"] == "평일"]
    out = {}
    for zone, col in [("platform", "density_platform"),
                      ("concourse", "density_concourse")]:
        q = wk[col].quantile(list(quantiles))
        out[zone] = [round(float(q.loc[x]), 4) for x in quantiles]
    return out


def add_level(df: pd.DataFrame, breaks: "dict | None" = None) -> pd.DataFrame:
    """(구) 분위수 등급 컬럼 추가 — 하위 호환용."""
    out = df.copy()
    for zone in ("platform", "concourse"):
        out[f"level_{zone}"] = out[f"density_{zone}"].map(
            lambda d: level_of(d, zone, breaks))
    return out
