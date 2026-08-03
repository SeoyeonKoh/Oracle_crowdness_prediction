"""Apex 혼잡도 추정 — 전역 설정.

경로, 방법론 파라미터(시간상수), LOS 임계표를 한곳에 모은다.

⚠️ 시간상수(게이트대기·이동시간·배차간격)는 '데이터셋'이 아니라 Little's Law의
   '방법론 파라미터'다. 원천 데이터로 확정할 수 없어 문헌·상식 기반 기본 가정값을
   두고, 팀이 튜닝할 수 있게 여기 노출한다. 누락 데이터(환승인원·실시간 등)와는
   성격이 다르다. 배차간격·환승통로 등 실측이 확보되면 이 값들을 교체한다.
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
# Little's Law  L = λ · W  에서 W(평균 체류시간)에 해당. 단위: 분.
# 근거: 도시철도 보행·대기 관행 기반 가정값(실측 확보 시 교체).
GATE_WAIT_MIN = 1.0        # 승차객: 진입→게이트 통과까지 대합실 대기 (비유료)
EXIT_MOVE_MIN = 1.5        # 하차객: 게이트→출구 이동 (비유료)
PLATFORM_GATE_MOVE_MIN = 1.5   # 하차객: 승강장→게이트 이동 (유료)
TRANSFER_PASSAGE_MIN = 2.5     # 환승객: 환승통로 통과 (유료) — Phase1 미사용(데이터 없음)

# 열차대기시간 = 배차간격/2. 배차간격 실측 미보유 → 시간대별 기본 가정.
PEAK_HOURS = {7, 8, 18, 19}
HEADWAY_PEAK_MIN = 3.0     # 피크 배차간격
HEADWAY_OFFPEAK_MIN = 6.0  # 비피크 배차간격


def train_wait_min(hour: int) -> float:
    """해당 시(hour)의 열차 대기시간(분) = 배차간격/2 (평균 대기)."""
    headway = HEADWAY_PEAK_MIN if hour in PEAK_HOURS else HEADWAY_OFFPEAK_MIN
    return headway / 2.0


def headway_min(hour: int) -> float:
    """해당 시(hour)의 배차간격(분). 순간 첨두 = 승차율 × 배차간격."""
    return HEADWAY_PEAK_MIN if hour in PEAK_HOURS else HEADWAY_OFFPEAK_MIN


# ── 순간 첨두(peak) & 정원 밀도 ─────────────────────────────────────────────
# 열차 도착 직전 승강장 누적(파형 최댓값)을 '정원 밀도(만원=100%)'로 나눠 정원대비%.
# CRUSH = 구역 '면적평균' 만원 밀도(명/㎡). 국지 밀도(문앞 3~4명/㎡)가 아니라
# 승강장 전체 평균이 이 값이면 만원으로 본다(가정, 튜닝 가능).
CRUSH_DENSITY = {"platform": 1.5, "concourse": 1.0}


# ── LOS 임계표 (1인당 점유면적 ㎡/명) ──────────────────────────────────────
# 근거: Fruin 보행 서비스수준(1971) walkway 기준. 값이 클수록(여유) A, 작을수록 F.
# 국토부 지침은 승강장·계단 목표=D, 환승통로=E 수준을 허용.
# (grade, 해당 등급의 최소 점유면적 ㎡/명) — 내림차순.
LOS_THRESHOLDS = [
    ("A", 3.24),   # 자유 통행
    ("B", 2.32),
    ("C", 1.39),
    ("D", 0.93),   # 승강장·계단 허용 하한
    ("E", 0.46),   # 환승통로 허용 하한
    ("F", 0.0),    # 정체
]

# 요일 구분: 평일 vs 주말
def daytype_of(weekday: int) -> str:
    """0=월 … 6=일. 평일/주말 라벨."""
    return "평일" if weekday < 5 else "주말"
