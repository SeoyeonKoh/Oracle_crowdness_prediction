"""STEP 1 — 독립 실측 검증: 계산 프로파일 vs 서울 실시간 도시데이터.

우리 파이프라인은 OA-12921(과거 승하차)로 시간대별 체류·첨두를 계산한다.
직접 수집한 실시간 도시데이터의 **게이트 통과 실측**(Tmoney)과 대조해
① 시간 프로파일의 모양 ② 규모를 독립 검증한다.

────────────────────────────────────────────────────────────────────────
실제 스키마 (인계 지시서의 가정과 다른 점 — 확인 결과)
────────────────────────────────────────────────────────────────────────
· 지시서 가정: `SUB_STTS`에 역 단위 실시간 승·하차가 있다.
  **실제**: `SUB_STTS`는 열차 *도착정보*다(SUB_STN_NM/LINE/DETAIL의 도착 예정).
  승하차 인원은 오직 `LIVE_SUB_PPLTN`에만 있고, **POI 단위 집계**다(역 단위 아님).
  → 역별 직접 매칭 불가. POI가 덮는 역을 모두 합산해 POI 단위로 비교한다.

· `SUB_STTS`는 그 POI가 덮는 (역, 호선)을 알려준다 → 매핑 근거로 사용.
  SUB_STN_CNT(역·호선 레코드 수)와 우리가 매핑한 개수가 **정확히 일치하는
  POI만** 사용한다. 코레일·9호선 등 미보유 구간이 섞이면 분모가 달라진다.

· 시각 정렬: `LIVE_SUB_PPLTN`에는 별도 기준시각이 없다(SUB_STN_TIME은 날짜뿐).
  → 승하차는 collected_at − (Tmoney 지연 5분 + 30분창 중심 15분) = −20분.
    인구는 API가 주는 `ppltn_base_time`(관측 시각) 그대로 사용.

· 누적/구간 판정: 샘플 확인 결과 `SUB_ACML_*`는 단조 증가(누적),
  `SUB_30WTHN_*`는 구간치다. → 구간치를 그대로 시간당으로 환산(차분 불필요).

· Tmoney 01~05시 미제공(값 None) → 해당 시간대 비교 제외.
────────────────────────────────────────────────────────────────────────

실행:  python -m src.batch.validate_live
산출:  output/validate_live.md
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src import config
from src.batch.summarize_byday import day_category

LIVE_CSV = config.DATA / "live_sub_ppltn.csv"

# POI → 우리 데이터의 (호선, 역명). SUB_STTS로 확인한 실제 커버리지이며
# SUB_STN_CNT와 개수가 일치하는 POI만 등록한다.
POI_STATIONS = {
    "뚝섬역": [(2, "뚝섬")],                                            # CNT 1
    "건대입구역": [(2, "건대입구"), (7, "건대입구")],                      # CNT 2
    "성수카페거리": [(2, "뚝섬"), (2, "성수")],                           # CNT 2
    "DDP(동대문디자인플라자)": [(2, "동대문역사문화공원"),
                          (4, "동대문역사문화공원"),
                          (5, "동대문역사문화공원")],                     # CNT 3
    "동대문 관광특구": [(1, "동대문"), (4, "동대문"),
                   (2, "동대문역사문화공원"), (4, "동대문역사문화공원"),
                   (5, "동대문역사문화공원"), (2, "신당"), (6, "신당")],   # CNT 7
    "사당역": [(2, "사당"), (4, "사당")],                                # CNT 2
    "총신대입구(이수)역": [(4, "총신대입구"), (7, "이수")],                 # CNT 2
}

# 제외한 POI와 사유 — 리포트에 그대로 싣는다.
EXCLUDED = {
    "왕십리역": "SUB_STN_CNT=5 이나 서울교통공사 구간은 왕십리(2·5)·한양대(2)·마장(5) "
             "4개뿐. 나머지는 경의중앙·수인분당(코레일)으로 우리 데이터에 없어 "
             "실측 분모가 더 크다.",
    "명동 관광특구": "SUB_STN_CNT=7 과 SUB_STTS의 역·호선 9건이 불일치해 커버 범위가 "
                "확정되지 않는다.",
    "상왕십리·충무로": "실시간 도시데이터 POI에 포함되지 않아 실측 자체가 없다(답사 경로 역).",
    "그 외 POI": "9호선·코레일 구간이 섞여 우리 데이터(1~8호선)와 분모가 다르다.",
}

TMONEY_LAG_MIN = 5      # Tmoney 집계 지연
WINDOW_MIN = 30         # SUB_30WTHN_* 창 길이
EXCLUDE_HOURS = set(range(1, 5))   # Tmoney 미제공 시간대

PASS_CORR_MEDIAN = 0.75
PASS_PEAK_RATIO = 0.70


def load_live() -> pd.DataFrame:
    d = pd.read_csv(LIVE_CSV, parse_dates=["collected_at"])
    d = d[d["area_nm"].isin(POI_STATIONS)].copy()

    mid = d["collected_at"] - pd.Timedelta(minutes=TMONEY_LAG_MIN + WINDOW_MIN / 2)
    d["obs_hour"] = mid.dt.hour
    d["obs_daycat"] = day_category(mid)
    scale = 60.0 / WINDOW_MIN                      # 30분 구간치 → 시간당
    d["obs_board"] = (d["gton30_min"] + d["gton30_max"]) / 2 * scale
    d["obs_alight"] = (d["gtoff30_min"] + d["gtoff30_max"]) / 2 * scale
    d["obs_activity"] = d["obs_board"] + d["obs_alight"]

    pt = pd.to_datetime(d["ppltn_base_time"], errors="coerce")
    d["ppltn_hour"] = pt.dt.hour
    d["ppltn_daycat"] = day_category(pt)
    d["obs_ppltn"] = (d["ppltn_min"] + d["ppltn_max"]) / 2

    d = d[~d["obs_hour"].isin(EXCLUDE_HOURS)]      # Tmoney 미제공 구간 제외
    d = d[d["obs_activity"] > 0]
    return d


def observed(live: pd.DataFrame) -> pd.DataFrame:
    return (live.groupby(["area_nm", "obs_daycat", "obs_hour"], as_index=False)
            .agg(obs_board=("obs_board", "mean"), obs_alight=("obs_alight", "mean"),
                 obs_activity=("obs_activity", "mean"), n=("obs_board", "size"))
            .rename(columns={"obs_daycat": "daycat", "obs_hour": "hour"}))


def observed_ppltn(live: pd.DataFrame) -> pd.DataFrame:
    return (live.groupby(["area_nm", "ppltn_daycat", "ppltn_hour"], as_index=False)
            .agg(obs_ppltn=("obs_ppltn", "mean"))
            .rename(columns={"ppltn_daycat": "daycat", "ppltn_hour": "hour"}))


def modeled() -> pd.DataFrame:
    m = pd.read_csv(config.OUTPUT / "los_summary_byday.csv")
    rows = []
    for area, pairs in POI_STATIONS.items():
        sel = pd.concat([m[(m["line"] == ln) & (m["station"] == st)] for ln, st in pairs])
        g = (sel.groupby(["daycat", "hour"], as_index=False)
             .agg(mdl_board=("board", "sum"), mdl_alight=("alight", "sum"),
                  mdl_peak=("peak_platform", "sum"),
                  mdl_occ=("occ_platform", "sum")))
        g["mdl_activity"] = g["mdl_board"] + g["mdl_alight"]
        g["area_nm"] = area
        rows.append(g)
    return pd.concat(rows, ignore_index=True)


def _z(s: pd.Series) -> np.ndarray:
    v = s.to_numpy(dtype=float)
    sd = np.std(v)
    return (v - np.mean(v)) / sd if sd > 0 else v * 0.0


def _zcorr(a: pd.Series, b: pd.Series) -> float:
    """z-정규화 후 Pearson — 규모 차이를 빼고 '모양'만 본다."""
    m = a.notna() & b.notna()
    if m.sum() < 3:
        return float("nan")
    za, zb = _z(a[m]), _z(b[m])
    if np.std(za) == 0 or np.std(zb) == 0:
        return float("nan")
    return float(np.corrcoef(za, zb)[0, 1])


def profile_check(obs, mdl, ppl) -> pd.DataFrame:
    j = obs.merge(mdl, on=["area_nm", "daycat", "hour"]).merge(
        ppl, on=["area_nm", "daycat", "hour"], how="left")
    wk = j[~j["daycat"].isin(["토", "일", "공휴일"])]
    rows = []
    for area, g in wk.groupby("area_nm"):
        gg = g.groupby("hour", as_index=False).agg(
            obs_activity=("obs_activity", "mean"), mdl_activity=("mdl_activity", "mean"),
            obs_board=("obs_board", "mean"), mdl_peak=("mdl_peak", "mean"),
            obs_ppltn=("obs_ppltn", "mean"))
        pk_o = int(gg.loc[gg["obs_activity"].idxmax(), "hour"])
        pk_m = int(gg.loc[gg["mdl_activity"].idxmax(), "hour"])
        pk_pk = int(gg.loc[gg["mdl_peak"].idxmax(), "hour"])
        rows.append({
            "POI": area, "시간대": len(gg),
            "활동 상관(z)": round(_zcorr(gg["mdl_activity"], gg["obs_activity"]), 3),
            "첨두 상관(z)": round(_zcorr(gg["mdl_peak"], gg["obs_board"]), 3),
            "인구 상관(참고)": round(_zcorr(gg["mdl_peak"], gg["obs_ppltn"]), 3),
            "규모비(우리/실측)": round(gg["mdl_activity"].sum() / gg["obs_activity"].sum(), 3),
            "피크(실측)": pk_o, "피크(계산)": pk_m, "피크(첨두)": pk_pk,
            "피크차(h)": abs(pk_o - pk_m),
        })
    return pd.DataFrame(rows).sort_values("POI").reset_index(drop=True)


def grade_check() -> pd.DataFrame:
    """답사 라벨 대조 — 2026-08-04(화) 11~12시대 경로 역의 시스템 등급."""
    m = pd.read_csv(config.OUTPUT / "los_summary_byday.csv")
    targets = [
        ("동대문역사문화공원", 2, 11, "좌석만석+입석 → 체감 보통~주의"),
        ("왕십리", 2, 11, "(체감 메모 없음 — 사람 판정 필요)"),
        ("왕십리", 5, 11, "(체감 메모 없음)"),
        ("충무로", 4, 12, "(체감 메모 없음)"),
    ]
    rows = []
    for st, ln, hr, note in targets:
        r = m[(m["station"] == st) & (m["line"] == ln) &
              (m["daycat"] == "화") & (m["hour"] == hr)]
        if r.empty:
            continue
        r = r.iloc[0]
        rows.append({"역": f"{ln}호선 {st}", "시각": f"{hr}시",
                     "crushpct_platform": r["crushpct_platform"],
                     "등급": r["level_abs_platform"], "답사 메모": note})
    return pd.DataFrame(rows)


def _md(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    return "\n".join([
        "| " + " | ".join(map(str, cols)) + " |",
        "| " + " | ".join(["---"] * len(cols)) + " |",
        *["| " + " | ".join(str(v) for v in rec) + " |"
          for rec in df.itertuples(index=False, name=None)]])


def main() -> None:
    if not LIVE_CSV.exists():
        print(f"실측 CSV 없음: {LIVE_CSV} — bash scripts/sync_live_sub.sh 먼저 실행")
        return

    live = load_live()
    prof = profile_check(observed(live), modeled(), observed_ppltn(live))
    grades = grade_check()

    corr_med = float(prof["활동 상관(z)"].median())
    peak_ratio = float((prof["피크차(h)"] <= 1).mean())
    passed = corr_med >= PASS_CORR_MEDIAN and peak_ratio >= PASS_PEAK_RATIO

    L = ["# STEP 1 — 독립 실측 검증 (실시간 도시데이터)\n\n"]
    L.append(f"- 실측: {live['collected_at'].min():%Y-%m-%d} ~ "
             f"{live['collected_at'].max():%Y-%m-%d}, {len(live):,} 레코드\n")
    L.append(f"- 시각 정렬: 승하차 = collected_at − {TMONEY_LAG_MIN + WINDOW_MIN // 2}분 "
             f"(Tmoney 지연 {TMONEY_LAG_MIN} + 30분창 중심 15) / 인구 = ppltn_base_time\n")
    L.append(f"- 01~05시 제외(Tmoney 미제공), 평일만 집계\n\n")

    L.append("## 판정\n\n")
    L.append(f"**{'통과 ✅' if passed else '미달 ❌'}** — "
             f"활동 상관 중앙값 **{corr_med:.3f}** (기준 ≥{PASS_CORR_MEDIAN}), "
             f"피크차 ≤1h 비율 **{peak_ratio:.0%}** (기준 ≥{PASS_PEAK_RATIO:.0%})\n\n")

    L.append("## 1. 프로파일 검증 (평일, z-정규화)\n\n")
    L.append(_md(prof) + "\n\n")
    L.append("> 활동 = 승차+하차. 첨두 상관은 peak_platform vs 실측 승차.\n"
             "> 인구 상관은 **참고용** — AREA_PPLTN은 역 밖 거리 인구를 포함한다.\n\n")

    L.append("## 2. 등급 검증 (답사 라벨 대조)\n\n")
    L.append(_md(grades) + "\n\n")

    L.append("## 3. 실제 스키마 — 지시서 가정과 다른 점\n\n")
    L.append("- ❗ `SUB_STTS`에는 **승하차 인원이 없다**. 열차 *도착정보*(SUB_STN_NM/"
             "LINE/DETAIL)다. 승하차 원값은 `LIVE_SUB_PPLTN`에만 있고 **POI 단위 집계**이며 "
             "역 단위가 아니다 → 역별 직접 매칭 불가, POI 단위로 합산 비교했다.\n")
    L.append("- `SUB_STTS`는 POI가 덮는 (역, 호선)을 주므로 **매핑 근거**로 사용했다. "
             "SUB_STN_CNT와 매핑 개수가 정확히 일치하는 POI만 채택.\n")
    L.append("- `LIVE_SUB_PPLTN`에는 별도 기준시각이 없다(SUB_STN_TIME은 날짜뿐) → "
             "지시서의 'SUB_STTS 기준시각 우선' 규칙을 적용할 수 없어 "
             "collected_at 기준 오프셋 보정으로 대체했다.\n")
    L.append("- 누적/구간: `SUB_ACML_*`는 단조 증가(누적), `SUB_30WTHN_*`는 구간치임을 "
             "샘플로 확인(뚝섬 00:00→00:30 ACML 25,400→25,500 / 30분값 200·150). "
             "**구간치를 사용해 차분 불필요.**\n\n")

    L.append("## 4. 제외한 POI와 사유\n\n")
    for k, v in EXCLUDED.items():
        L.append(f"- **{k}**: {v}\n")

    config.OUTPUT.mkdir(exist_ok=True)
    (config.OUTPUT / "validate_live.md").write_text("".join(L), encoding="utf-8")

    print(prof.to_string(index=False))
    print(f"\n활동 상관 중앙값 {corr_med:.3f} · 피크차≤1h {peak_ratio:.0%} → "
          f"{'통과' if passed else '미달'}")
    print(f"\n{grades.to_string(index=False)}")
    print(f"\n저장: {config.OUTPUT/'validate_live.md'}")
    return passed


if __name__ == "__main__":
    main()
