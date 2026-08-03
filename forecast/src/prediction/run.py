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
    for target in ["occ_platform", "occ_concourse"]:
        print(f"[2/4] 학습·평가: {target} …")
        results[target] = model.train_eval(detail, target)
        mm = results[target]["metrics_model"]
        mb = results[target]["metrics_baseline"]
        print(f"      model MAE {mm['MAE']:.2f} vs baseline {mb['MAE']:.2f} "
              f"(train {results[target]['n_train']:,} / test {results[target]['n_test']:,})")

    print("[3/4] 지표 리포트 저장 …")
    rows = []
    for target, r in results.items():
        for name, mset in [("HGB 모델", r["metrics_model"]),
                           ("seasonal-naive", r["metrics_baseline"])]:
            rows.append({
                "target": target, "방식": name,
                "MAE": round(mset["MAE"], 2), "RMSE": round(mset["RMSE"], 2),
                "sMAPE_%": round(mset["sMAPE_%"], 1), "corr": round(mset["corr"], 3),
            })
    metrics_df = pd.DataFrame(rows)

    lines = ["# Phase 2 체류인원 예측 — 검증 리포트\n\n"]
    lines.append("학습 2023–2024 / 검증 2025 홀드아웃. 단위: 평균 체류인원(명).\n\n")
    lines.append(_md_table(metrics_df))
    lines.append("\n\n## 해석\n")
    for target, r in results.items():
        imp = (1 - r["metrics_model"]["MAE"] / r["metrics_baseline"]["MAE"]) * 100
        lines.append(f"- **{target}**: HGB가 seasonal-naive 대비 MAE "
                     f"{imp:+.1f}% ({'개선' if imp > 0 else '악화'}).\n")
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
