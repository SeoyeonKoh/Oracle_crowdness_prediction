"""요일(월~일) + 공휴일별 재집계 & 빨간날 패턴 학습.

Phase 1 상세 산출물(occupancy_hourly.csv.gz)을 날짜→요일/공휴일로 분류해
(line, station, daycat, hour) 평균 밀도로 재집계한다.
daycat = 공휴일 | 월 | 화 | 수 | 목 | 금 | 토 | 일  (공휴일이 요일보다 우선)

실행:  python -m src.summarize_byday
산출:  output/los_summary_byday.csv  (+ 콘솔에 공휴일 vs 평일/일요일 비교)
"""
from __future__ import annotations

import holidays
import numpy as np
import pandas as pd

from src import config
from src.congestion import levels as congestion_level

WEEKDAY = ["월", "화", "수", "목", "금", "토", "일"]
DAYCATS = ["월", "화", "수", "목", "금", "토", "일", "공휴일"]


def day_category(dates: pd.Series) -> pd.Series:
    d = pd.to_datetime(dates)
    yrs = sorted(d.dt.year.unique().tolist())
    kr = holidays.SouthKorea(years=yrs)
    is_hol = d.dt.date.map(lambda x: x in kr)
    wd = d.dt.weekday.map(lambda i: WEEKDAY[i])
    return np.where(is_hol, "공휴일", wd)


def main() -> None:
    print("[1/3] 상세 산출물 로드 …")
    df = pd.read_csv(config.OUTPUT / "occupancy_hourly.csv.gz", parse_dates=["date"])
    df["daycat"] = day_category(df["date"])

    print("[2/3] 요일·공휴일 재집계 …")
    agg = (df.groupby(["line", "station", "daycat", "hour"], as_index=False)
           .agg(board=("board", "mean"),
                alight=("alight", "mean"),
                transfer=("transfer", "mean"),
                occ_platform=("occ_platform", "mean"),
                occ_concourse=("occ_concourse", "mean"),
                peak_platform=("peak_platform", "mean"),
                platform_area=("platform_area", "first"),
                concourse_area=("concourse_area", "first"),
                density_platform=("density_platform", "mean"),
                density_concourse=("density_concourse", "mean")))

    # ── [PATCH 4·5] 첨두 밀도 → 절대 등급 ─────────────────────────
    # 첨두(peak_platform)는 build 단계에서 이미 (승차+환승) × 배차간격 으로 계산됐다.
    # 구 abspct(= occ + board×배차/2, 하차 포함)는 폐기 — 열차 도착 직전엔 직전
    # 하차객이 이미 빠져나간 상태라 하차를 넣으면 이중계상이 된다.
    # 여기서는 유효면적 기준 밀도로 환산하고 만원(CRUSH) 대비 %와 등급을 붙인다.
    agg = congestion_level.add_peak_density(agg)
    agg = congestion_level.add_level_abs(agg)
    _n_measured = sum(
        (int(r.line), str(r.station), int(r.hour)) in config._load_measured_headway()
        for r in agg.itertuples(index=False))
    if _n_measured:
        print(f"      · 배차 실측 적용 셀: {_n_measured:,} (나머지는 노선·보간 폴백)")

    agg.round(4).to_csv(config.OUTPUT / "los_summary_byday.csv", index=False)
    print(f"      저장: output/los_summary_byday.csv  ({len(agg):,} 행)")

    print("[3/3] 빨간날 패턴 학습 …\n")
    # 전 역 시간대 평균 프로파일(승강장 밀도)로 요일간 비교
    prof = (df.groupby(["daycat", "hour"])["density_platform"].mean().unstack("daycat"))
    weekday_mean = prof[["월", "화", "수", "목", "금"]].mean(axis=1)

    print("일 평균 승강장 밀도(명/㎡):")
    means = df.groupby("daycat")["density_platform"].mean().reindex(DAYCATS).round(4)
    for k, v in means.items():
        print(f"  {k}: {v}")

    def corr(a, b):
        m = a.notna() & b.notna()
        return round(float(np.corrcoef(a[m], b[m])[0, 1]), 3)
    print("\n공휴일 시간대 프로파일 상관:")
    print(f"  vs 평일(월~금): {corr(prof['공휴일'], weekday_mean)}")
    print(f"  vs 일요일:      {corr(prof['공휴일'], prof['일'])}")
    print(f"  vs 토요일:      {corr(prof['공휴일'], prof['토'])}")

    hol_peak = int(prof["공휴일"].idxmax())
    wk_peak = int(weekday_mean.idxmax())
    hol_ratio = round(float(means["공휴일"] / weekday_mean.mean()), 2)
    print(f"\n피크 시각 — 공휴일 {hol_peak}시 vs 평일 {wk_peak}시")
    print(f"공휴일 혼잡도는 평일의 약 {hol_ratio}배")
    verdict = ("공휴일은 일요일과 매우 유사" if corr(prof['공휴일'], prof['일']) >= 0.9
               else "공휴일은 독자 패턴")
    print(f"→ 결론: {verdict} (빨간날은 별도 카테고리로 예보 제공)")


if __name__ == "__main__":
    main()
