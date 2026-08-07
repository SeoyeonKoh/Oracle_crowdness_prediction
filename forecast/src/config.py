"""Apex 혼잡도 추정 — 전역 설정.

경로, 방법론 파라미터(시간상수), LOS 임계표를 한곳에 모은다.

⚠️ 시간상수는 '데이터셋'이 아니라 Little's Law의 '방법론 파라미터'다.
   실측이 확보되는 대로 이 값들을 교체한다.

[PATCH 1] 배차간격: 이진 계단(피크 3분/그외 6분) 폐지 → **3단 폴백**
          ① data/realtime_headway.csv  (line, station, hour) 실측  ← 최우선
             (실시간 도착 API 로그에서 src/loading/realtime.py 가 생성)
          ② data/headway_measured.csv  (line, hour) 실측
             (열차위치 로그 기반 노선 단위 집계 — 향후 생성)
          ③ 앵커 시각 사이 선형 보간하는 연속 프로파일 (가정값)
[PATCH 2] TRANSFER_PASSAGE_MIN(2.5분)은 OA-13290 역별 실측이 없는 역의 폴백으로 강등.
[PATCH 3] EFFECTIVE_AREA_RATIO 신설 — 밀도 분모를 전체 면적이 아닌 유효면적으로.
"""
from __future__ import annotations

from pathlib import Path

# ── 경로 ────────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parent.parent
INPUT = ROOT / "input"
OUTPUT = ROOT / "output"
DATA = ROOT / "data"

# OA-12921 승하차: 연도별 '전체 기간' 파일만 사용(부분·중복 파일 제외해 중복 방지)
BOARDING_DIR = INPUT / "OA-12921 서울교통굥사 역별 일별 시간대별 승하차 인원"
BOARDING_FILES = [
    BOARDING_DIR / "서울교통공사_역별 시간대별 승하차인원(23.1~23.12).csv",
    BOARDING_DIR / "서울교통공사_역별 시간대별 승하차인원(24.1~24.12).csv",
    BOARDING_DIR / "서울교통공사_역별 일별 시간대별 승하차인원_20251231.csv",
]

STATION_AREA_FILE = INPUT / "서울교통공사_역사면적정보_20251231.csv"

TRAIN_CONGESTION_DIR = INPUT / "OA-12928 서울교통공사_지하철혼잡도정보"
CARD_DIR = INPUT / "서울시 지하철호선별 역별 승하차 인원 정보"

# ── 방법론 파라미터: 체류시간(분) ─────────────────────────────────────────
GATE_WAIT_MIN = 1.0            # 승차객: 진입→게이트 통과까지 대합실 대기 (비유료)
EXIT_MOVE_MIN = 1.5            # 하차객: 게이트→출구 이동 (비유료)
PLATFORM_GATE_MOVE_MIN = 1.5   # 하차객: 승강장→게이트 이동 (유료)

# [PATCH 2] 환승통로 통과시간 — 이제 '폴백'으로만 사용.
# 기본은 OA-13290(환승역거리)의 (역, 출발호선, 도착호선)별 실측 환승소요시간을
# occupancy.station_transfer_walk_min() 으로 만들어 주입한다.
TRANSFER_PASSAGE_MIN = 2.5

# ── [PATCH 1] 배차간격: 실측 우선 + 연속 프로파일 폴백 ─────────────────────
# ① 역 단위 실측(최우선): line, station, hour, headway_sec, n_samples
REALTIME_DIR = DATA / "subway_realtime"          # scripts/sync_realtime.sh 로 서버→로컬
REALTIME_HEADWAY_CSV = DATA / "realtime_headway.csv"
# ② 노선 단위 실측: line, hour, headway_min
HEADWAY_MEASURED_FILE = DATA / "headway_measured.csv"

# ③ 폴백 연속 프로파일: (시각, 배차간격 분) 앵커를 선형 보간.
# 이진 계단(8시 3분 → 9시 6분)이 만들던 인위적 2배 점프를 제거하고
# 어깨 시간대(9시, 17시)가 자연스럽게 이어지게 한다. 값 자체는 여전히
# 가정이므로 실측이 생기는 즉시 그쪽이 우선한다.
_HEADWAY_ANCHORS = [
    (5, 10.0), (6, 6.0), (7, 3.5), (8, 3.0), (9, 4.0), (11, 5.5),
    (16, 5.0), (17, 4.0), (18, 3.0), (19, 3.5), (21, 5.5), (24, 9.0),
]

# (구버전 호환용 — 새 코드에서는 사용하지 않음)
PEAK_HOURS = {7, 8, 18, 19}
HEADWAY_PEAK_MIN = 3.0
HEADWAY_OFFPEAK_MIN = 6.0


def _interp_headway(hour: float) -> float:
    """앵커 사이 선형 보간. 범위 밖은 양끝 값으로 클램프."""
    pts = _HEADWAY_ANCHORS
    if hour <= pts[0][0]:
        return pts[0][1]
    if hour >= pts[-1][0]:
        return pts[-1][1]
    for (h0, v0), (h1, v1) in zip(pts, pts[1:]):
        if h0 <= hour <= h1:
            t = (hour - h0) / (h1 - h0)
            return v0 + (v1 - v0) * t
    return pts[-1][1]


_MEASURED_BY_STATION: "dict | None" = None
_MEASURED_BY_LINE: "dict | None" = None


def _measured_by_station() -> dict:
    """① data/realtime_headway.csv → {(line, station, hour): 배차(분)}."""
    global _MEASURED_BY_STATION
    if _MEASURED_BY_STATION is None:
        _MEASURED_BY_STATION = {}
        try:
            import pandas as pd
            if REALTIME_HEADWAY_CSV.exists():
                df = pd.read_csv(REALTIME_HEADWAY_CSV)
                for r in df.itertuples(index=False):
                    _MEASURED_BY_STATION[(int(r.line), str(r.station), int(r.hour))] = \
                        float(r.headway_sec) / 60.0
        except Exception:
            pass   # 실측 로드 실패는 치명적이지 않다 — 다음 단계로 폴백.
    return _MEASURED_BY_STATION


def _measured_by_line() -> dict:
    """② data/headway_measured.csv → {(line, hour): 배차(분)}."""
    global _MEASURED_BY_LINE
    if _MEASURED_BY_LINE is None:
        _MEASURED_BY_LINE = {}
        try:
            import pandas as pd
            if HEADWAY_MEASURED_FILE.exists():
                df = pd.read_csv(HEADWAY_MEASURED_FILE)
                for r in df.itertuples(index=False):
                    _MEASURED_BY_LINE[(int(r.line), int(r.hour))] = float(r.headway_min)
        except Exception:
            pass
    return _MEASURED_BY_LINE


# 하위 호환 별칭(기존 호출부에서 실측 커버리지 집계에 사용).
def _load_measured_headway() -> dict:
    return _measured_by_station()


def headway_min_at(line, station, hour) -> float:
    """배차간격(분) — 3단 폴백: (line,station,hour) → (line,hour) → 연속 보간."""
    h = int(hour)
    if line is not None:
        if station is not None:
            v = _measured_by_station().get((int(line), str(station), h))
            if v is not None and v > 0:
                return v
        v = _measured_by_line().get((int(line), h))
        if v is not None and v > 0:
            return v
    return _interp_headway(h)


def train_wait_min_at(line, station, hour) -> float:
    """열차 대기시간(분) = 배차간격/2 (균일 도착 가정의 평균 대기). 3단 폴백."""
    return headway_min_at(line, station, hour) / 2.0


def headway_min(hour: int, line: "int | None" = None) -> float:
    """해당 시(hour)·노선(line)의 배차간격(분). headway_min_at 에 위임(역 정보 없음)."""
    return headway_min_at(line, None, hour)


def train_wait_min(hour: int, line: "int | None" = None) -> float:
    """열차 대기시간(분) = 배차간격/2. headway_min 에 위임."""
    return headway_min(hour, line) / 2.0


# ── 순간 첨두(peak) & 정원 밀도 ─────────────────────────────────────────────
# 순간 첨두 = 열차 도착 직전 승강장 누적 최대 ≈ (승차율 + 환승대기율) × 배차간격.
# CRUSH = 구역 '면적평균' 만원 밀도(명/㎡). 튜닝 가능한 가정값.
CRUSH_DENSITY = {"platform": 1.5, "concourse": 1.0}

# [PATCH 3] 유효면적 비율 — 밀도 분모 보정.
# 역사면적 CSV의 전체 면적 중 실제로 사람이 대기·이동에 쓰는 비율(가정값).
# 승강장은 승차 위치 주변에 몰리고 끝단·설비 공간은 비므로 0.5,
# 대합실은 동선이 넓게 퍼지므로 0.7 로 시작. ⚠️ 답사 관측으로 보정할 1순위 상수.
EFFECTIVE_AREA_RATIO = {"platform": 0.5, "concourse": 0.7}


# ── LOS 임계표 (1인당 점유면적 ㎡/명) ──────────────────────────────────────
# 근거: Fruin 보행 서비스수준(1971) walkway 기준.
# 국토부 지침은 승강장·계단 목표=D, 환승통로=E 수준을 허용.
LOS_THRESHOLDS = [
    ("A", 3.24),   # 자유 통행
    ("B", 2.32),
    ("C", 1.39),
    ("D", 0.93),   # 승강장·계단 허용 하한
    ("E", 0.46),   # 환승통로 허용 하한
    ("F", 0.0),    # 정체
]


# ── 요일 구분 ──────────────────────────────────────────────────────────────
def daytype_of(weekday: int) -> str:
    """0=월 … 6=일. 평일/주말 라벨."""
    return "평일" if weekday < 5 else "주말"


def daytype3_of(weekday: int) -> str:
    """OA-12033(환승인원) 키용 3분류: 평일/토요일/일요일."""
    if weekday < 5:
        return "평일"
    return "토요일" if weekday == 5 else "일요일"
