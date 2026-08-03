"""Phase 2 — 체류인원 예측 (과거 → 미래).

목표: 미래 날짜의 캘린더 정보(요일·시간·월·역)만으로 구역별 체류인원을 예측.
- 모델: HistGradientBoostingRegressor (요일·시간·월·호선은 네이티브 범주형)
  · 역(273개)은 범주 상한(255)을 넘어 **타깃 인코딩**(학습셋 역별 평균)으로 수치화.
- 베이스라인: seasonal-naive (역×요일×시간 학습 평균).
- 검증: 2023–24 학습 / 2025 홀드아웃.

체류인원은 승하차의 선형 변환이므로, 사실상 캘린더 → 전형적 혼잡 패턴을 학습한다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingRegressor

# 역(273개)은 범주 상한(255) 초과 → 타깃 인코딩 수치 피처로 대체:
#   sbase   = 역별 평균 (규모)
#   snaive  = 역×요일×시간 평균 (= seasonal-naive 예측을 피처로 주입)
# HGB는 snaive를 그대로 통과시키며 그 위에 월 계절성·상호작용 보정을 학습(하이브리드).
CAT_FEATURES = ["hour", "dow", "month", "line"]
NUM_FEATURES = ["is_weekend", "sbase", "snaive"]
FEATURES = CAT_FEATURES + NUM_FEATURES


def add_calendar(df: pd.DataFrame) -> pd.DataFrame:
    """date → dow, month, is_weekend, year 파생."""
    out = df.copy()
    d = pd.to_datetime(out["date"])
    out["dow"] = d.dt.weekday
    out["month"] = d.dt.month
    out["is_weekend"] = (d.dt.weekday >= 5).astype(int)
    out["year"] = d.dt.year
    return out


def _prep_X(df: pd.DataFrame) -> pd.DataFrame:
    X = df[FEATURES].copy()
    for c in CAT_FEATURES:
        X[c] = X[c].astype("category")
    return X


def seasonal_naive(train: pd.DataFrame, test: pd.DataFrame, target: str) -> np.ndarray:
    """역×요일×시간 학습 평균으로 예측(강력한 베이스라인)."""
    key = ["line", "station", "dow", "hour"]
    tbl = train.groupby(key)[target].mean()
    pred = test.set_index(key).index.map(tbl)
    fallback = train[target].mean()
    return pd.Series(pred, index=test.index).fillna(fallback).to_numpy()


def _metrics(y_true: np.ndarray, y_pred: np.ndarray) -> dict:
    err = y_pred - y_true
    mae = float(np.mean(np.abs(err)))
    rmse = float(np.sqrt(np.mean(err ** 2)))
    # sMAPE (0 근처 안정), 유의미 값(>1명)만
    m = y_true > 1
    smape = float(np.mean(2 * np.abs(err[m]) / (np.abs(y_true[m]) + np.abs(y_pred[m]))) * 100) if m.any() else np.nan
    corr = float(np.corrcoef(y_true, y_pred)[0, 1]) if len(y_true) > 2 else np.nan
    return {"MAE": mae, "RMSE": rmse, "sMAPE_%": smape, "corr": corr}


def train_eval(detail: pd.DataFrame, target: str) -> dict:
    """target(occ_platform/occ_concourse) 학습·평가.

    반환: {'model', 'metrics_model', 'metrics_baseline', 'test'(예측 부착)}
    """
    df = add_calendar(detail)
    train = df[df["year"].isin([2023, 2024])].copy()
    test = df[df["year"] == 2025].copy()

    # 타깃 인코딩(누수 방지: train만으로 산출)
    global_mean = train[target].mean()
    sbase = train.groupby(["line", "station"])[target].mean()
    snaive = train.groupby(["line", "station", "dow", "hour"])[target].mean()
    for part in (train, test):
        part["sbase"] = (part.set_index(["line", "station"]).index.map(sbase)
                         .to_series(index=part.index).fillna(global_mean).astype(float))
        part["snaive"] = (part.set_index(["line", "station", "dow", "hour"]).index.map(snaive)
                          .to_series(index=part.index).fillna(part["sbase"]).astype(float))

    model = HistGradientBoostingRegressor(
        max_iter=300, learning_rate=0.08, max_depth=8,
        categorical_features=CAT_FEATURES, early_stopping=True,
        validation_fraction=0.1, random_state=0,
    )
    model.fit(_prep_X(train), train[target])

    pred_model = model.predict(_prep_X(test))
    pred_base = seasonal_naive(train, test, target)

    test = test.copy()
    test[f"pred_{target}"] = pred_model
    test[f"base_{target}"] = pred_base

    return {
        "model": model,
        "metrics_model": _metrics(test[target].to_numpy(), pred_model),
        "metrics_baseline": _metrics(test[target].to_numpy(), pred_base),
        "test": test,
        "n_train": len(train), "n_test": len(test),
    }
