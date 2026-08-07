"""Phase 2 실행 — 체류인원 예측 학습·평가·산출.

실행:  python -m src.predict
입력:  output/occupancy_hourly.csv.gz (Phase 1 산출)
산출:  output/prediction_metrics.md, output/prediction_sample.csv, data/model_*.joblib
"""
from __future__ import annotations

import joblib
import pandas as pd

from src import config
from src.prediction import model

SAMPLE_STATIONS = [(2, "강남"), (2, "왕십리"), (2, "삼성"), (1, "서울역"), (2, "신도림")]


def _md_table(df: pd.DataFrame) -> str:
    cols = list(df.columns)
    head = "| " + " | ".join(map(str, cols)) + " |"
    sep = "| " + " | ".join(["---"] * len(cols)) + " |"
    rows = ["| " + " | ".join(str(v) for v in rec) + " |"
            for rec in df.itertuples(index=False, name=None)]
    return "\n".join([head, sep, *rows])


def main() -> None:
    print("[1/4] Phase 1 상세 산출물 로드 …")
    detail = pd.read_csv(config.OUTPUT / "occupancy_hourly.csv.gz",
                         parse_dates=["date"])
    print(f"      rows: {len(detail):,}")

    results = {}
    # peak_platform 추가 — 등급 판정이 시간평균이 아니라 첨두로 바뀌었으므로
    # 실제 서비스가 예측해야 하는 값은 이쪽이다.
    for target in ["occ_platform", "occ_concourse", "peak_platform"]:
        print(f"[2/4] 학습·평가: {target} …")
        results[target] = model.train_eval(detail, target)
        mm = results[target]["metrics_model"]
        mb = results[target]["metrics_baseline"]
        print(f"      model MAE {mm['MAE']:.2f} vs baseline {mb['MAE']:.2f} "
              f"(train {results[target]['n_train']:,} / test {results[target]['n_test']:,})")

    print("[3/4] 지표 리포트 저장 …")
    rows = []
    for target, r in results.items():
        for name, mset in [("naive+월·시보정 ⭐운영", r["metrics_corrected"]),
                           ("HGB 모델", r["metrics_model"]),
                           ("seasonal-naive", r["metrics_baseline"])]:
            rows.append({
                "target": target, "방식": name,
                "MAE": round(mset["MAE"], 2), "RMSE": round(mset["RMSE"], 2),
                "sMAPE_%": round(mset["sMAPE_%"], 1),
                "corr(pooled)": round(mset["corr"], 3),
                "corr(역별 중앙값)": round(mset["corr_station"], 3),
                "등급 일치율": round(mset["grade_acc"], 4),
                "skill_%": round(mset["skill_%"], 1),
            })
    metrics_df = pd.DataFrame(rows)

    lines = ["# Phase 2 체류인원 예측 — 검증 리포트\n\n"]
    lines.append("학습 2023–2024 / 검증 2025 홀드아웃. 단위: 평균 체류인원(명).\n\n")
    lines.append(_md_table(metrics_df))
    lines.append("\n\n## 해석\n")
    for target, r in results.items():
        sm = r["metrics_model"]["skill_%"]
        sc = r["metrics_corrected"]["skill_%"]
        lines.append(f"- **{target}**: seasonal-naive 대비 MAE 개선 — "
                     f"HGB {sm:+.1f}% / naive+보정 {sc:+.1f}%\n")

    lines.append("\n### 공휴일 보정계수 (naive 키에 공휴일이 없어 평일로 과대예측되는 것을 보정)\n\n")
    for target, r in results.items():
        lines.append(f"- {target}: **×{r['holiday_factor']:.3f}**\n")

    lines.append("- ⚠️ **등급 일치율(99.6~100%)은 포화 지표다.** 전체 셀의 대부분이 '여유'라 예측이 조금 틀려도 같은 칸에 남는다. 등급이 갈리는 상위 구간에서만 따로 봐야 의미가 있다 — 현재는 '등급을 뒤집을 만큼 크게 틀리지는 않는다'는 하한 보증으로만 읽을 것.\n")
    lines.append("- 공휴일 계수(×0.82)는 요약 리포트의 '평일의 0.74배'와 정의가 다르다. 0.74는 일 평균 밀도 비율, 0.82는 naive 예측 대비 비율이다(naive가 이미 요일 평균을 반영하므로 격차가 작다).\n")

    lines.append("\n## 결론: HGB 대신 naive+보정을 운영으로 채택\n\n")
    lines.append("- HGB의 이득(+2.0~3.2%)을 **(월,시간) 보정계수 룩업 하나가 그대로 재현**한다.\n")
    lines.append("- 원인은 구조적이다: HGB 입력에 seasonal-naive 예측값(`snaive`)을 "
                 "피처로 넣어, 모델이 할 수 있는 일이 그 위의 미세 보정으로 제한된다.\n")
    lines.append("- 같은 정확도라면 단순한 쪽이 낫다 — 학습 즉시, 산출물 수 KB, "
                 "해석 가능, 예측 시 scikit-learn 불필요.\n")
    lines.append("- ⚠️ `corr(pooled)`는 역 규모 차이 때문에 0.98까지 부풀려진다. "
                 "역별 상관 중앙값이 실제 시간패턴 일치도이며, 여기서도 "
                 "naive와 모델의 차이는 0.003 수준이다.\n")
    lines.append("- 참고: 화면 서빙 경로(`export_forecast` → `los_summary_byday.csv`)는 "
                 "과거 평균을 직접 쓰므로 이 모델을 통과하지 않는다. 단순화의 위험이 낮다.\n")
    lines.append("\n> 캘린더 피처만 사용(승하차 실측 없이 미래 예측). 실시간 요인"
                 "(날씨·POI·행사) 확보 시 추가 개선 여지.\n")
    (config.OUTPUT / "prediction_metrics.md").write_text("".join(lines), encoding="utf-8")

    print("[4/4] 샘플 예측 + 모델 저장 …")
    test = results["occ_platform"]["test"]
    wk = test[test["is_weekend"] == 0]
    samp = wk[wk.set_index(["line", "station"]).index.isin(SAMPLE_STATIONS)]
    prof = (samp.groupby(["line", "station", "hour"], as_index=False)
            .agg(actual=("occ_platform", "mean"),
                 pred=("pred_occ_platform", "mean"),
                 baseline=("base_occ_platform", "mean")))
    prof.round(1).to_csv(config.OUTPUT / "prediction_sample.csv", index=False)

    config.DATA.mkdir(exist_ok=True)
    for target, r in results.items():
        # 운영 산출물: (월,시간) 보정계수 룩업 — 수 KB, 해석 가능.
        r["corr_table"].rename("factor").reset_index().to_csv(
            config.DATA / f"correction_{target}.csv", index=False)
        # HGB는 비교·연구용으로만 보관.
        joblib.dump(r["model"], config.DATA / f"model_{target}.joblib")

    print("\n완료. 산출물:")
    print(f"  - {config.OUTPUT/'prediction_metrics.md'}")
    print(f"  - {config.OUTPUT/'prediction_sample.csv'}")
    print(f"  - {config.DATA/'model_occ_platform.joblib'} (+ concourse)")
    print("\n[샘플] 강남 평일 시간대별 (actual / pred / baseline):")
    g = prof[(prof.line == 2) & (prof.station == "강남")].sort_values("hour")
    print(g[["hour", "actual", "pred", "baseline"]].round(1).to_string(index=False))


if __name__ == "__main__":
    main()
