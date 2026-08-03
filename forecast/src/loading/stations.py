"""역 마스터 — 승하차 데이터에 역사면적을 조인하고 환승역을 표시.

조인 키: (line, station). station은 io_load.normalize_station 으로 정규화된 값.
매칭 실패 역은 로그로 남기고 면적 NaN 으로 통과(LOS 계산 시 제외).
"""
from __future__ import annotations

import pandas as pd


def attach_area(boarding: pd.DataFrame, area: pd.DataFrame) -> pd.DataFrame:
    """승하차 long DF에 concourse_area / platform_area 조인."""
    merged = boarding.merge(area, on=["line", "station"], how="left")
    return merged


def transfer_stations(area_or_boarding: pd.DataFrame) -> set[str]:
    """여러 호선에 같은 역명이 있으면 환승역으로 간주. (station 이름 집합 반환)"""
    g = area_or_boarding.groupby("station")["line"].nunique()
    return set(g[g > 1].index)


def unmatched_report(merged: pd.DataFrame) -> pd.DataFrame:
    """면적 미매칭 (line, station) 목록."""
    miss = merged[merged["platform_area"].isna()]
    return (miss[["line", "station", "station_raw"]]
            .drop_duplicates()
            .sort_values(["line", "station"])
            .reset_index(drop=True))
