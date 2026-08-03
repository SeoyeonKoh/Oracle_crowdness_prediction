"""체류인원 계산 — Little's Law (L = λ · W).

λ = 시간당 도착률(= 시간대별 승차/하차/환승 인원),  W = 평균 체류시간(시간 단위).
counts 는 '시간당 인원'이므로 W 를 시간으로 환산하면 곱이 곧 평균 체류인원(명)이 된다.

- 비유료구역(대합실) = 승차객 × 게이트대기 + 하차객 × 출구이동
- 유료구역(승강장)   = 승차객 × 열차대기 + 하차객 × 게이트이동 + 환승객 × 통로통과
  (환승항은 환승 데이터 부재로 Phase 1 기본 0. transfer 인자로 확장 가능.)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src import config

_MIN_PER_HOUR = 60.0


def concourse_occupancy(board: pd.Series, alight: pd.Series) -> pd.Series:
    """비유료구역(대합실) 평균 체류인원(명)."""
    return (board * (config.GATE_WAIT_MIN / _MIN_PER_HOUR)
            + alight * (config.EXIT_MOVE_MIN / _MIN_PER_HOUR))


def platform_occupancy(
    board: pd.Series,
    alight: pd.Series,
    hour: pd.Series,
    transfer: "pd.Series | None" = None,
) -> pd.Series:
    """유료구역(승강장) 평균 체류인원(명). hour별 열차대기시간 반영."""
    wait_min = hour.map(config.train_wait_min).astype(float)
    occ = (board * (wait_min / _MIN_PER_HOUR)
           + alight * (config.PLATFORM_GATE_MOVE_MIN / _MIN_PER_HOUR))
    if transfer is not None:
        occ = occ + transfer * (config.TRANSFER_PASSAGE_MIN / _MIN_PER_HOUR)
    return occ


def add_occupancy(df: pd.DataFrame) -> pd.DataFrame:
    """board/alight/hour 컬럼이 있는 wide DF에 두 구역 체류인원 컬럼 추가."""
    out = df.copy()
    b = out["board"].fillna(0.0)
    a = out["alight"].fillna(0.0)
    t = out["transfer"].fillna(0.0) if "transfer" in out.columns else None
    out["occ_concourse"] = concourse_occupancy(b, a)
    out["occ_platform"] = platform_occupancy(b, a, out["hour"], t)
    return out
