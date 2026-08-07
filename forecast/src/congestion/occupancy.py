"""체류인원 계산 — Little's Law (L = λ · W).

λ = 시간당 도착률(승차/하차/환승 인원), W = 평균 체류시간(시간 단위).

- 비유료구역(대합실) = 승차객 × 게이트대기 + 하차객 × 출구이동
- 유료구역(승강장)   = 승차객 × 열차대기 + 하차객 × 게이트이동
                     + 환승객 × (환승이동 + 열차대기)                    [PATCH 2]

[PATCH 1] 열차대기 = config.train_wait_min_at(line, station, hour)
          — (line,station,hour) 실측 → (line,hour) 실측 → 연속 보간 3단 폴백.
[PATCH 2] 환승항 활성화:
          · 환승객 수 = OA-12033 일평균 환승인원을 그 역의 시간대별
            (승차+하차) 활동 비례로 배분 (add_transfer_estimate)
          · 환승 이동시간 = OA-13290 역별 실측 (station_transfer_walk_min),
            없으면 config.TRANSFER_PASSAGE_MIN 폴백
          · 환승객도 도착 승강장에서 열차를 기다리므로 대기항(배차/2)을 받는다.
[PATCH 4] 순간 첨두(peak_platform) 신설 — 열차 도착 직전 누적 최대
          = (승차객 + 환승객) × 배차간격. 등급 판정은 시간평균이 아니라 이 값으로.
          하차객은 도착 직전엔 이미 빠져나간 상태라 넣으면 이중계상이 된다.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from src import config

_MIN_PER_HOUR = 60.0


# ── 배차 조회 벡터화 (unique (line, station, hour) 조합만 계산해 map) ────────
def _headway_key_series(hour: pd.Series,
                        line: "pd.Series | None",
                        station: "pd.Series | None",
                        fn) -> pd.Series:
    """행별 배차 관련 값(분). fn(line, station, hour) 을 unique 조합에만 호출."""
    if line is None:
        table = {h: fn(None, None, int(h)) for h in hour.dropna().unique()}
        return hour.map(table).astype(float)
    st = station if station is not None else pd.Series([None] * len(hour), index=hour.index)
    key = pd.Series(list(zip(line, st, hour)), index=hour.index)
    table = {}
    for k in key.unique():
        ln, s, hr = k
        if pd.isna(hr):
            continue
        table[k] = fn(ln, s, hr)
    return key.map(table).astype(float)


def _wait_series(hour, line=None, station=None) -> pd.Series:
    """행별 열차 대기시간(분) = 배차/2."""
    return _headway_key_series(hour, line, station, config.train_wait_min_at)


def _headway_series(hour, line=None, station=None) -> pd.Series:
    """행별 배차간격(분)."""
    return _headway_key_series(hour, line, station, config.headway_min_at)


# ── [PATCH 2a] 환승 이동시간: OA-13290 → (도착노선, 역)별 평균 ────────────────
def station_transfer_walk_min(transfer_times: dict) -> dict:
    """loaders.load_transfer_times() 결과 {(역, 출발호선, 도착호선): 분} 를
    '이 노선 승강장으로 들어오는' 관점의 (line, station)별 평균 이동시간으로 축약.

    (노선쌍별 정밀 분해는 환승인원이 역 단위라 불가능 → 도착노선 기준 평균 근사)
    """
    agg: dict = {}
    for (st, _fl, tl), m in transfer_times.items():
        if m is None:
            continue
        agg.setdefault((int(tl), st), []).append(float(m))
    return {k: sum(v) / len(v) for k, v in agg.items()}


# ── [PATCH 2b] 환승객 수 추정: OA-12033 일평균 → 시간대 배분 ─────────────────
def add_transfer_estimate(df: pd.DataFrame, transfer_volume: dict) -> pd.DataFrame:
    """OA-12033 {(역, 평일/토요일/일요일): 일평균 환승인원} 을
    각 (날짜, 역)의 시간대·노선별 (승차+하차) 활동 비례로 배분해 transfer 컬럼 생성.

    같은 역의 여러 노선에도 활동량 비례로 자동 분배된다(합계 = 역 일평균 보존).
    호선 균등분할(구 build.add_transfer)은 폐기 — 2호선과 지선의 규모 차이를
    무시해 환승 부하를 잘못 배분했다.
    데이터가 없는 역은 transfer=0 (기존 동작과 동일).
    """
    out = df.copy()
    d = pd.to_datetime(out["date"])
    dt3 = d.dt.weekday.map(config.daytype3_of)

    daily = pd.Series(
        [float(transfer_volume.get((s, t), 0.0))
         for s, t in zip(out["station"], dt3)],
        index=out.index,
    )
    activity = out["board"].fillna(0.0) + out["alight"].fillna(0.0)
    day_total = activity.groupby([out["date"], out["station"]]).transform("sum")
    share = np.where(day_total > 0, activity / day_total, 0.0)
    out["transfer"] = daily * share
    return out


# ── 구역별 체류인원 ─────────────────────────────────────────────────────────
def concourse_occupancy(board: pd.Series, alight: pd.Series) -> pd.Series:
    """비유료구역(대합실) 평균 체류인원(명)."""
    return (board * (config.GATE_WAIT_MIN / _MIN_PER_HOUR)
            + alight * (config.EXIT_MOVE_MIN / _MIN_PER_HOUR))


def platform_occupancy(
    board: pd.Series,
    alight: pd.Series,
    hour: pd.Series,
    transfer: "pd.Series | None" = None,
    line: "pd.Series | None" = None,
    walk_min: "pd.Series | float | None" = None,
    station: "pd.Series | None" = None,
) -> pd.Series:
    """유료구역(승강장) 평균 체류인원(명).

    [PATCH 1] 대기시간이 역·노선별 실측 우선.
    [PATCH 2] 환승객 = (환승 이동시간 + 열차 대기시간) 두 조각 모두 반영.
    """
    wait = _wait_series(hour, line, station)
    occ = (board * (wait / _MIN_PER_HOUR)
           + alight * (config.PLATFORM_GATE_MOVE_MIN / _MIN_PER_HOUR))
    if transfer is not None:
        if walk_min is None:
            walk_min = config.TRANSFER_PASSAGE_MIN
        occ = occ + transfer * ((walk_min + wait) / _MIN_PER_HOUR)
    return occ


# ── [PATCH 4] 순간 첨두: 열차 도착 직전 누적 최대 ───────────────────────────
def platform_peak_occupancy(
    board: pd.Series,
    hour: pd.Series,
    transfer: "pd.Series | None" = None,
    line: "pd.Series | None" = None,
    station: "pd.Series | None" = None,
) -> pd.Series:
    """열차 도착 직전 승강장 누적 인원(명) ≈ (승차객 + 환승객) × 배차간격.

    시간평균(L = λ×배차/2)의 정확히 2배가 승차 파형의 꼭대기다.
    하차객은 도착 '직전'에는 이미 빠져나간 상태이므로 제외(이중계상 방지).
    등급 판정(levels.add_level_abs)은 이 값 기반의 밀도로 한다.
    """
    hw = _headway_series(hour, line, station)
    lam = board.fillna(0.0)
    if transfer is not None:
        lam = lam + transfer.fillna(0.0)
    return lam * (hw / _MIN_PER_HOUR)


# ── 파이프라인 진입점 ───────────────────────────────────────────────────────
def add_occupancy(df: pd.DataFrame,
                  walk_by_station: "dict | None" = None) -> pd.DataFrame:
    """board/alight/hour(/line/station/transfer) 컬럼이 있는 wide DF에
    occ_concourse, occ_platform, peak_platform 컬럼 추가.

    walk_by_station: station_transfer_walk_min() 결과 {(line, station): 분}.
                     주면 역별 환승 이동시간, 없으면 폴백 상수 사용.
    기존 호출부와 하위 호환: transfer 컬럼이 없으면 환승항 없이 동작.
    """
    out = df.copy()
    b = out["board"].fillna(0.0)
    a = out["alight"].fillna(0.0)
    t = out["transfer"].fillna(0.0) if "transfer" in out.columns else None
    line = out["line"] if "line" in out.columns else None
    station = out["station"] if "station" in out.columns else None

    walk = None
    if t is not None:
        if walk_by_station and line is not None and station is not None:
            key = pd.Series(list(zip(out["line"], out["station"])), index=out.index)
            walk = key.map(walk_by_station).fillna(config.TRANSFER_PASSAGE_MIN).astype(float)
        else:
            walk = config.TRANSFER_PASSAGE_MIN

    out["occ_concourse"] = concourse_occupancy(b, a)
    out["occ_platform"] = platform_occupancy(b, a, out["hour"], t, line, walk, station)
    out["peak_platform"] = platform_peak_occupancy(b, out["hour"], t, line, station)
    return out


# ── 시간 내(intra-hour) 10분 분해 — 총량보존 ────────────────────────────────
# 1시간값을 6×10분으로 쪼갠다. "형태(shape)"는 다른 고빈도 신호(열차혼잡 30분,
# 실시간 도착)에서 빌려온다. 핵심 불변식: 6개 10분값의 평균 == 원래 1시간값
# (= 총량보존). 화면(app.js)도 동일 규칙을 쓴다.
_SLOTS_PER_HOUR = 6


def normalize_shape(weights):
    """가중치 6개를 평균 1로 정규화. 음수/합≤0/None 포함 시 None(형태 없음)."""
    if weights is None:
        return None
    w = list(weights)
    if len(w) != _SLOTS_PER_HOUR or any(x is None or x < 0 for x in w):
        return None
    total = sum(w)
    if total <= 0:
        return None
    mean = total / _SLOTS_PER_HOUR
    return [x / mean for x in w]


def disaggregate_to_10min(hourly_value, shape6=None):
    """1시간값 → 6×10분값. shape6(평균1 가중치)가 없으면 평탄 분배.

    총량보존: sum(result)/6 == hourly_value (부동소수 오차 내).
    """
    sh = normalize_shape(shape6)
    if sh is None:
        return [hourly_value] * _SLOTS_PER_HOUR
    return [hourly_value * w for w in sh]
