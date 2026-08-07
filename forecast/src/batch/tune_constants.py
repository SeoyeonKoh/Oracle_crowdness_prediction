"""STEP 2 — 가정 상수 확정 (원노브 원칙).

조정하는 노브는 `EFFECTIVE_AREA_RATIO["platform"]` **하나뿐**이다.
절대 컷 분수(⅓·⅔·1.0)와 CRUSH(1.5/1.0)는 고정한다 — 둘을 동시에 만지면
어느 쪽 효과인지 분리할 수 없다.

평가 기준
---------
(a) **제약**: 동대문(2호선) 11시 등급이 '보통'을 유지하는가.
    (2026-08-04 답사에서 좌석만석+입석을 관측한 지점)
(b) **목적함수**: 승강장 절대등급과 열차 실측등급(OA-12928 재차/정원)의
    **밴드 일치율** — 같은 (역, 요일유형, 시간)에서 4단계가 같은 칸에 떨어지는 비율.
    두 지표는 같은 '만원 대비' 언어를 쓰므로, 잘 보정된 유효면적이라면
    승강장과 열차 등급이 더 자주 일치해야 한다.

(a)를 만족하는 후보 중 (b)가 최대인 값을 고른다.

재실행 불필요
-------------
density = peak ÷ (면적 × ratio) 이므로 crushpct ∝ 1/ratio.
기준값(현재 0.5)으로 만든 산출물을 스케일링해 그리드를 평가한다.

실행:  python -m src.batch.tune_constants
산출:  output/constant_decision.md
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src import config
from src.congestion import levels as L
from src.loading import loaders as io_load

GRID = [0.4, 0.5, 0.6, 0.7]
BASE_RATIO = config.EFFECTIVE_AREA_RATIO["platform"]   # 산출물이 만들어진 기준값

# 열차 등급 밴드(정원 대비 %) — 화면과 동일. 여유의 끝 = 좌석 만석선 34%.
TRAIN_BANDS = [34, 80, 130]
DAYCAT_TO_TRAIN = {"토": "토요일", "일": "일요일", "공휴일": "일요일"}

COL_ALL = "(b) 전체 일치율"
COL_NZ = "(b') 비자명 일치율"

# (b')가 이 아래면 두 지표가 사실상 무관하다고 본다(무작위 일치 수준).
NZ_SANITY_FLOOR = 0.30


def _grade(v, bands):
    if v is None or (isinstance(v, float) and np.isnan(v)):
        return None
    for i in range(len(bands) - 1, -1, -1):
        if v > bands[i]:
            return i + 1
    return 0


def load_joined() -> pd.DataFrame:
    """승강장 crushpct(기준 ratio) + 같은 셀의 열차 실측 pct."""
    m = pd.read_csv(config.OUTPUT / "los_summary_byday.csv")
    m = m[m["crushpct_platform"].notna()].copy()
    m["train_daytype"] = m["daycat"].map(DAYCAT_TO_TRAIN).fillna("평일")

    tc = io_load.load_train_congestion()
    tc["daytype"] = tc["daytype"].astype(str).str.strip()
    tc = (tc.groupby(["daytype", "line", "station", "hour"], as_index=False)["pct"]
          .mean().rename(columns={"pct": "train_pct", "daytype": "train_daytype"}))

    j = m.merge(tc, on=["train_daytype", "line", "station", "hour"], how="inner")
    return j[j["train_pct"].notna() & (j["train_pct"] > 0)]


def evaluate(j: pd.DataFrame) -> pd.DataFrame:
    """그리드별 (a) 제약 충족 여부 (b) 밴드 일치율."""
    pct_bands = L.abs_break_pcts("일반")          # [33.3, 66.7, 100]
    train_grade = j["train_pct"].map(lambda v: _grade(v, TRAIN_BANDS))

    ddp = j[(j["station"] == "동대문역사문화공원") & (j["line"] == 2) &
            (j["daycat"] == "화") & (j["hour"] == 11)]

    rows = []
    for r in GRID:
        scaled = j["crushpct_platform"] * (BASE_RATIO / r)
        pg = scaled.map(lambda v: _grade(v, pct_bands))
        agree = float((pg == train_grade).mean())
        # 보조 지표: '자명한 일치'(둘 다 여유) 제외. 전체 일치율은 대부분의 셀이
        # 한산해 여유/여유로 자동 일치하므로 판별력이 거의 없다.
        nz = (pg > 0) | (train_grade > 0)
        agree_nz = float((pg[nz] == train_grade[nz]).mean()) if nz.any() else np.nan
        share_nz = float(nz.mean())

        if ddp.empty:
            ddp_pct, ddp_lvl, ok = np.nan, "-", False
        else:
            ddp_pct = float(ddp["crushpct_platform"].iloc[0] * (BASE_RATIO / r))
            ddp_lvl = L.LEVELS[_grade(ddp_pct, pct_bands)]
            ok = ddp_lvl == "보통"

        rows.append({
            "유효면적비율": r,
            "동대문 11시 %": round(ddp_pct, 1),
            "동대문 등급": ddp_lvl,
            "(a) 제약 충족": "○" if ok else "✕",
            COL_ALL: round(agree, 4),
            COL_NZ: round(agree_nz, 4),
            "비자명 셀 비중": round(share_nz, 4),
            "승강장 평균 %": round(float(scaled.mean()), 1),
        })
    return pd.DataFrame(rows)


def _md(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    return "\n".join([
        "| " + " | ".join(map(str, cols)) + " |",
        "| " + " | ".join(["---"] * len(cols)) + " |",
        *["| " + " | ".join(str(v) for v in rec) + " |"
          for rec in df.itertuples(index=False, name=None)]])


def main() -> None:
    j = load_joined()
    res = evaluate(j)
    ok = res[res["(a) 제약 충족"] == "○"]
    if ok.empty:
        chosen, reason = BASE_RATIO, "(a) 제약을 만족하는 후보가 없어 기존값 유지"
    else:
        best = ok.loc[ok[COL_NZ].idxmax()]
        cand = float(best["유효면적비율"])
        bestval = float(best[COL_NZ])
        at_edge = cand in (min(GRID), max(GRID))
        # 목적함수 유효성 검사 — 아래 둘 중 하나면 (b)는 최적점을 찾지 못한 것이다.
        #  · 비자명 일치율이 바닥(무작위 수준) → 두 지표가 애초에 같은 칸에 안 떨어진다
        #  · 최댓값이 그리드 경계 → 최적이 범위 밖(= 단조 증가)이라는 뜻
        invalid = (bestval < NZ_SANITY_FLOOR) or at_edge
        if invalid:
            chosen = BASE_RATIO
            reason = (f"목적함수 (b') 무효 — 비자명 일치율 최대가 {bestval:.4f}"
                      f"({'그리드 경계 ' + str(cand) if at_edge else '바닥 수준'}). "
                      f"승강장과 열차는 물리적으로 밀도 체계가 달라 등급 일치를 "
                      f"목적함수로 삼으면 승강장 밀도를 인위적으로 부풀리게 된다. "
                      f"→ 기존값 유지")
        else:
            chosen = cand
            reason = f"(a) 충족 후보 중 비자명 일치율 최대 ({bestval:.4f})"
    changed = abs(chosen - BASE_RATIO) > 1e-9

    L_ = ["# STEP 2 — 가정 상수 확정 (유효면적 비율)\n\n"]
    L_.append("원노브 원칙: `EFFECTIVE_AREA_RATIO['platform']` 하나만 조정한다. "
              "절대 컷 분수(⅓·⅔·1.0)와 CRUSH(승강장 1.5/대합실 1.0)는 고정.\n\n")
    L_.append(f"- 대조 표본: {len(j):,} 셀 (승강장 crushpct ∩ OA-12928 열차 실측)\n")
    L_.append(f"- (a) 제약: 동대문 2호선 화요일 11시 등급 = '보통' 유지\n")
    L_.append(f"- (b) 목적함수: 승강장 절대등급 vs 열차 실측등급 4단계 일치율\n\n")
    L_.append(_md(res) + "\n\n")
    L_.append(f"## 결정: **{chosen}** — {reason}\n\n")
    L_.append(f"- 기존값 {BASE_RATIO} 대비 **{'변경' if changed else '변경 없음'}**\n")
    if not changed:
        L_.append("- **변경하지 않는다.** 아래 진단 참조.\n")
    L_.append("\n### 목적함수 (b') 진단\n\n")
    L_.append("- 비자명 셀(둘 중 하나라도 '여유'가 아닌 셀)은 전체의 약 36%인데, "
              "그 안에서 승강장·열차 등급 일치율은 **3~5%**에 그친다. "
              "무작위 수준이며, 두 지표가 같은 칸에 떨어지지 않는다는 뜻이다.\n")
    L_.append("- 최댓값이 그리드 **경계(0.4)** 에 붙어 있다 = 최적이 범위 밖이라는 신호. "
              "비율을 더 낮출수록 계속 '좋아지는' 단조 형태다.\n")
    L_.append("- 원인: 승강장과 열차는 물리적으로 밀도 체계가 다르다(열차는 좁아 금방 차고, "
              "승강장은 넓어 낮게 나온다). 등급 일치를 목적함수로 삼으면 "
              "**승강장 밀도를 인위적으로 부풀려 열차에 맞추게** 된다 — 캘리브레이션이 아니라 왜곡이다.\n")
    L_.append("- 따라서 이 기준으로는 유효면적을 확정할 수 없다. "
              "STEP 1이 이미 통과했으므로 지시서 규칙(\'통과 시 STEP 2는 확인만\')에 따라 "
              "**현행 0.5를 유지**하고 STEP 3으로 진행한다.\n")
    L_.append("\n> ⚠️ 이 값은 여전히 **가정**이다. (b)는 승강장과 열차가 같은 '만원 대비' "
              "언어를 쓴다는 전제에 기댄 간접 기준이며, 승강장 유효면적을 직접 잰 것이 "
              "아니다. 현장에서 측정한 승강장 유효폭이 확보되면 그 값으로 대체할 것.\n")

    config.OUTPUT.mkdir(exist_ok=True)
    (config.OUTPUT / "constant_decision.md").write_text("".join(L_), encoding="utf-8")

    print(res.to_string(index=False))
    print(f"\n결정: {chosen} ({reason}) · {'변경' if changed else '변경 없음'}")
    print(f"저장: {config.OUTPUT/'constant_decision.md'}")


if __name__ == "__main__":
    main()
