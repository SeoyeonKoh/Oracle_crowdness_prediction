"""LOS(서비스수준) — 체류인원·면적 → 밀도 → A~F 등급.

밀도(명/㎡) = 체류인원 / 면적
1인당 점유면적(㎡/명) = 면적 / 체류인원
등급은 점유면적을 config.LOS_THRESHOLDS(Fruin) 기준으로 판정(클수록 A).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src import config


def grade_from_space(space_per_person: float) -> str:
    """1인당 점유면적(㎡/명) → 등급 문자. 체류 0(무한 여유) → 'A'."""
    if space_per_person is None or np.isnan(space_per_person):
        return ""
    if np.isinf(space_per_person):
        return "A"
    for grade, min_space in config.LOS_THRESHOLDS:
        if space_per_person >= min_space:
            return grade
    return "F"


def add_los(df: pd.DataFrame) -> pd.DataFrame:
    """occ_concourse/occ_platform + concourse_area/platform_area 로 밀도·등급 산출."""
    out = df.copy()
    for zone, occ_col, area_col in [
        ("concourse", "occ_concourse", "concourse_area"),
        ("platform", "occ_platform", "platform_area"),
    ]:
        occ = out[occ_col]
        area = out[area_col]
        with np.errstate(divide="ignore", invalid="ignore"):
            density = np.where(area > 0, occ / area, np.nan)
            space = np.where(occ > 0, area / occ, np.inf)
        out[f"density_{zone}"] = density          # 명/㎡
        out[f"space_{zone}"] = space              # ㎡/명
        out[f"los_{zone}"] = pd.Series(space, index=out.index).map(grade_from_space)
    return out
