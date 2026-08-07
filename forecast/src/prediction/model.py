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
    """date → dow, month, is_weekend, is_holiday, year 파생.

    is_holiday: seasonal-naive의 키는 (역, 요일, 시간)이라 공휴일을 평일로 취급해
    과대예측한다. 별도 플래그로 보정한다(관측: 공휴일 ≈ 평일의 0.74배).
    """
    out = df.copy()
    d = pd.to_datetime(out["date"])
    out["dow"] = d.dt.weekday
    out["month"] = d.dt.month
    out["is_weekend"] = (d.dt.weekday >= 5).astype(int)
    out["year"] = d.dt.year
    try:
        import holidays as _hol
        kr = _hol.SouthKorea(years=sorted(d.dt.year.unique().tolist()))
        out["is_holiday"] = d.dt.date.map(lambda x: x in kr).astype(int)
    except Exception:
        out["is_holiday"] = 0
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


def seasonal_correction(train: pd.DataFrame, target: str,
                        keys=("month", "hour")) -> pd.Series:
    """학습셋에서 (월, 시간)별 보정계수 = 실제 합 ÷ seasonal-naive 예측 합.

    seasonal-naive는 역×요일×시간 평균이라 '월 계절성'과 '시간대별 계통 편의'를
    담지 못한다. 그 잔차를 비율 하나로 흡수한다. (HGB가 하던 일과 사실상 동일)
    """
    base = seasonal_naive(train, train, target)
    t = pd.DataFrame({"a": train[target].to_numpy(), "b": base})
    for k in keys:
        t[k] = train[k].to_numpy()
    g = t.groupby(list(keys))[["a", "b"]].sum()
    return (g["a"] / g["b"]).replace([np.inf, -np.inf], 1.0).fillna(1.0)


def holiday_factor(train: pd.DataFrame, target: str) -> float:
    """공휴일 보정계수 = 공휴일 실제 합 ÷ 공휴일 naive 예측 합.

    seasonal-naive 키에 공휴일이 없어 평일로 예측되므로 그만큼 낮춰준다.
    """
    if "is_holiday" not in train.columns or train["is_holiday"].sum() == 0:
        return 1.0
    base = seasonal_naive(train, train, target)
    m = train["is_holiday"].to_numpy() == 1
    a, b = train[target].to_numpy()[m].sum(), base[m].sum()
    return float(a / b) if b > 0 else 1.0


def seasonal_naive_corrected(train: pd.DataFrame, test: pd.DataFrame,
                             target: str, keys=("month", "hour")):
    """운영 예측기: seasonal-naive × (월,시간) 보정 × 공휴일 보정.

    HGB와 동등한 정확도를 룩업 두 개로 낸다(검증: prediction_metrics.md).
    학습 즉시, 산출물 수 KB, 해석 가능.
    반환: (예측 배열, 보정계수 Series, 공휴일 계수)
    """
    base = seasonal_naive(train, test, target)
    f = seasonal_correction(train, target, keys)
    idx = pd.MultiIndex.from_arrays([test[k] for k in keys])
    factor = pd.Series(idx.map(f), index=test.index).astype(float).fillna(1.0)
    pred = base * factor.to_numpy()

    hf = holiday_factor(train, target)
    if "is_holiday" in test.columns:
        pred = np.where(test["is_holiday"].to_numpy() == 1, pred * hf, pred)
    return pred, f, hf


def grade_agreement(y_true: np.ndarray, y_pred: np.ndarray,
                    area: np.ndarray, zone: str = "platform") -> float:
    """예측·실제를 각각 절대 4단계로 변환했을 때의 일치율.

    MAE보다 서비스 품질에 가깝다 — 사용자는 숫자가 아니라 등급을 본다.
    """
    from src import config
    from src.congestion import levels as L

    denom = area * config.EFFECTIVE_AREA_RATIO[zone]
    ok = np.isfinite(denom) & (denom > 0)
    if not ok.any():
        return float("nan")
    b = L.abs_breaks(zone)

    def g(v):
        return np.searchsorted(b, v, side="left")

    return float((g(y_true[ok] / denom[ok]) == g(y_pred[ok] / denom[ok])).mean())


def corr_by_station(test: pd.DataFrame, target: str, pred_col: str) -> float:
    """역별 상관의 중앙값.

    ⚠️ 전체를 합쳐(pooled) 계산한 상관은 '강남은 크고 뚝섬은 작다'는 역 규모
    차이만으로 0.9대가 나와 성능을 과대평가한다. 역 안에서의 시간 패턴을
    실제로 맞추는지 보려면 역별로 계산해 중앙값을 봐야 한다.
    """
    vals = []
    for _, g in test.groupby(["line", "station"]):
        a, b = g[target].to_numpy(), g[pred_col].to_numpy()
        if len(a) > 2 and np.std(a) > 0 and np.std(b) > 0:
            vals.append(float(np.corrcoef(a, b)[0, 1]))
    return float(np.median(vals)) if vals else float("nan")


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

    # 운영 예측기(naive + 월·시 + 공휴일 보정) — HGB와 동등 성능을 룩업으로 낸다.
    pred_corr, corr_table, hol_f = seasonal_naive_corrected(train, test, target)
    test[f"corr_{target}"] = pred_corr

    mm = _metrics(test[target].to_numpy(), pred_model)
    mb = _metrics(test[target].to_numpy(), pred_base)
    mc = _metrics(test[target].to_numpy(), pred_corr)

    # 등급 4단계 일치율 — 승강장 계열 타깃만(면적이 필요).
    zone = "platform" if "platform" in target else "concourse"
    acol = f"{zone}_area"
    if acol in test.columns:
        area = test[acol].to_numpy(dtype=float)
        yt = test[target].to_numpy()
        for pred, m in ((pred_model, mm), (pred_base, mb), (pred_corr, mc)):
            m["grade_acc"] = grade_agreement(yt, pred, area, zone)
    else:
        for m in (mm, mb, mc):
            m["grade_acc"] = float("nan")
    # 역 규모 효과를 뺀 '진짜' 형태 일치도 + 베이스라인 대비 개선율(skill)
    mm["corr_station"] = corr_by_station(test, target, f"pred_{target}")
    mb["corr_station"] = corr_by_station(test, target, f"base_{target}")
    mc["corr_station"] = corr_by_station(test, target, f"corr_{target}")
    for m in (mm, mc):
        m["skill_%"] = (1 - m["MAE"] / mb["MAE"]) * 100 if mb["MAE"] > 0 else np.nan
    mb["skill_%"] = 0.0

    return {
        "model": model,
        "metrics_model": mm,
        "metrics_baseline": mb,
        "metrics_corrected": mc,
        "corr_table": corr_table,
        "holiday_factor": hol_f,
        "test": test,
        "n_train": len(train), "n_test": len(test),
    }
