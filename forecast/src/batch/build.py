"""Apex 혼잡도 추정 — Phase 1 파이프라인.

승하차(OA-12921) → 체류인원(Little's Law) → 밀도/LOS → 산출물 저장.
실행:  python -m src.pipeline
"""
from __future__ import annotations

import sqlite3
import sys

import numpy as np
import pandas as pd

from src import config
from src.loading import loaders as io_load
from src.loading import stations as station_master
from src.congestion import occupancy, los
from src import evaluation as validate

KEYS = ["date", "line", "station_no", "station", "station_raw", "hour"]


def _md_table(df: pd.DataFrame) -> str:
    """tabulate 의존 없이 DataFrame → 마크다운 표."""
    cols = list(df.columns)
    head = "| " + " | ".join(map(str, cols)) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"
    rows = ["| " + " | ".join(str(v) for v in rec) + " |"
            for rec in df.itertuples(index=False, name=None)]
    return "\n".join([head, sep, *rows])


def build_wide(long: pd.DataFrame) -> pd.DataFrame:
    """승/하차 long → (키, board, alight) wide."""
    board = (long[long["io"] == "승차"].groupby(KEYS)["cnt"].sum().rename("board"))
    alight = (long[long["io"] == "하차"].groupby(KEYS)["cnt"].sum().rename("alight"))
    wide = pd.concat([board, alight], axis=1).reset_index()
    wide[["board", "alight"]] = wide[["board", "alight"]].fillna(0.0)
    wd = wide["date"].dt.weekday
    wide["daytype"] = np.where(wd < 5, "평일", "주말")
    wide["dow3"] = np.select([wd < 5, wd == 5], ["평일", "토요일"], default="일요일")
    return wide


def add_transfer(detail: pd.DataFrame) -> pd.DataFrame:
    """OA-12033 환승인원 → transfer 컬럼. occupancy.add_transfer_estimate 로 일원화.

    [PATCH 2] 구현은 occupancy 쪽 한 벌만 유지한다. 구 버전의 '호선 균등분할'은
    폐기했다 — 2호선과 지선의 규모 차이를 무시해 환승 부하를 잘못 배분했다.
    새 방식은 (승차+하차) 활동 비례로 시간대·노선에 동시 배분한다(역 일평균 보존).
    """
    tv = io_load.load_transfer_volume()
    if not tv:
        detail["transfer"] = 0.0
        return detail
    return occupancy.add_transfer_estimate(detail, tv)


def summarize(detail: pd.DataFrame) -> pd.DataFrame:
    """역×요일유형×시간대 평균으로 요약하고 LOS 재산정(서비스 소비용)."""
    grp = (detail.groupby(["line", "station", "daytype", "hour"], as_index=False)
           .agg(board=("board", "mean"), alight=("alight", "mean"),
                occ_concourse=("occ_concourse", "mean"),
                occ_platform=("occ_platform", "mean"),
                concourse_area=("concourse_area", "first"),
                platform_area=("platform_area", "first")))
    grp = los.add_los(grp)
    return grp


def save_sqlite(summary: pd.DataFrame, area: pd.DataFrame, unmatched: pd.DataFrame) -> None:
    config.DATA.mkdir(exist_ok=True)
    con = sqlite3.connect(config.DATA / "apex.sqlite")
    summary.to_sql("los_summary", con, if_exists="replace", index=False)
    area.to_sql("station_area", con, if_exists="replace", index=False)
    unmatched.to_sql("unmatched_stations", con, if_exists="replace", index=False)
    con.close()


def write_validation_report(vol: pd.DataFrame, peak: pd.DataFrame,
                            unmatched: pd.DataFrame, n_detail: int) -> None:
    lines = ["# 계산 타당성 교차검증 리포트\n"]
    lines.append(f"- 상세 레코드 수: **{n_detail:,}** (역×날짜×시간)\n")

    lines.append("\n## 1. 볼륨 sanity (우리 승차 합계 ÷ CARD 승차 합계)\n")
    if vol.empty:
        lines.append("- CARD 매칭 없음\n")
    else:
        by_line = vol.groupby("line")["ratio"].mean().round(3)
        lines.append("호선별 평균 비율 (1.0 근처면 정합):\n")
        for ln, r in by_line.items():
            lines.append(f"- {ln}호선: {r}\n")
        lines.append(f"\n전체 평균 비율: **{vol['ratio'].mean():.3f}**\n")

    lines.append("\n## 2. 피크 정렬 (승강장 체류 피크시간 vs 열차혼잡 피크시간)\n")
    if peak.empty:
        lines.append("- 비교 가능한 역 없음\n")
    else:
        good = (peak["peak_gap_h"] <= 1).mean()
        lines.append(f"- 피크시간 1시간 이내 일치 비율: **{good:.0%}**\n")
        lines.append(f"- 시간대 상관계수 중앙값: **{peak['corr'].median():.3f}**\n\n")
        lines.append(_md_table(peak))
        lines.append("\n")

    lines.append("\n## 3. 면적 미매칭 역 (LOS 계산 제외)\n")
    if unmatched.empty:
        lines.append("- 없음\n")
    else:
        lines.append(f"- {len(unmatched)}건\n\n")
        lines.append(_md_table(unmatched))
        lines.append("\n")

    config.OUTPUT.mkdir(exist_ok=True)
    (config.OUTPUT / "calc_validation.md").write_text("".join(lines), encoding="utf-8")


def main() -> None:
    config.OUTPUT.mkdir(exist_ok=True)
    print("[1/6] 승하차 로드 …")
    long = io_load.load_boarding()
    print(f"      long rows: {len(long):,}  기간: {long['date'].min().date()} ~ {long['date'].max().date()}")

    print("[2/6] 승/하차 wide 변환 …")
    wide = build_wide(long)
    print(f"      wide rows: {len(wide):,}")

    print("[3/6] 역사면적 조인 + 체류인원 + LOS …")
    area = io_load.load_station_area()
    detail = station_master.attach_area(wide, area)
    detail = add_transfer(detail)
    # [PATCH 2] 환승 이동시간은 OA-13290 역별 실측 우선(없으면 폴백 상수)
    walk_by_station = occupancy.station_transfer_walk_min(io_load.load_transfer_times())
    detail = occupancy.add_occupancy(detail, walk_by_station)
    detail = los.add_los(detail)
    unmatched = station_master.unmatched_report(detail)
    print(f"      면적 미매칭: {len(unmatched)}건")

    print("[4/6] 상세 산출물 저장 …")
    # [PATCH 4·5] peak_platform(첨두)과 면적을 함께 저장 — 하류(summarize_byday)에서
    # 유효면적 기준 첨두 밀도·절대 등급을 재계산할 수 있어야 한다.
    detail_cols = ["date", "line", "station", "daytype", "hour",
                   "board", "alight", "transfer",
                   "occ_concourse", "occ_platform", "peak_platform",
                   "concourse_area", "platform_area",
                   "density_concourse", "density_platform",
                   "los_concourse", "los_platform"]
    out = detail[detail_cols].copy()
    for c in ["board", "alight", "transfer",
              "occ_concourse", "occ_platform", "peak_platform",
              "density_concourse", "density_platform"]:
        out[c] = out[c].round(3)
    out.to_csv(config.OUTPUT / "occupancy_hourly.csv.gz", index=False,
               compression="gzip")

    print("[5/6] 요약 + SQLite 저장 …")
    summary = summarize(detail)
    summary.round(3).to_csv(config.OUTPUT / "los_summary.csv", index=False)
    save_sqlite(summary.round(3), area, unmatched)

    print("[6/6] 교차검증 …")
    try:
        card = io_load.load_card_monthly_totals()
        vol = validate.volume_sanity(long, card)
    except Exception as e:  # CARD 로드 실패해도 파이프라인은 완료
        print(f"      (CARD 로드 경고: {e})")
        vol = pd.DataFrame()
    try:
        cong = io_load.load_train_congestion()
        peak = validate.peak_alignment(detail, cong)
    except Exception as e:  # 혼잡도 로드 실패해도 파이프라인은 완료
        print(f"      (열차혼잡 로드 경고: {e})")
        peak = pd.DataFrame()
    write_validation_report(vol, peak, unmatched, len(detail))

    print("\n완료. 산출물:")
    print(f"  - {config.OUTPUT/'occupancy_hourly.csv.gz'}")
    print(f"  - {config.OUTPUT/'los_summary.csv'}")
    print(f"  - {config.OUTPUT/'calc_validation.md'}")
    print(f"  - {config.DATA/'apex.sqlite'}")

    # 콘솔 스팟체크: 대표 역 평일 피크
    print("\n[스팟체크] 평일 승강장 LOS 분포:")
    wk = summary[summary["daytype"] == "평일"]
    print(wk["los_platform"].value_counts().sort_index().to_string())


if __name__ == "__main__":
    sys.exit(main())
