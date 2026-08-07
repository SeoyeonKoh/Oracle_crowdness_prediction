"""기상청 초단기실황 클라이언트 — 혼잡 보정용 실시간 외생변수.  [Phase 3 · 뼈대]

강수·기온을 10분 예측의 실시간 외생변수로 쓰기 위한 최소 클라이언트다.
아직 모델에 결선(結線)하지 않았다 — API 키 확보 + 데이터 축적 후 연결한다.

필요 키: config/APIkey.py 의  KMA_API_KEY = "발급받은_기상청_서비스키"
        (공공데이터포털 '기상청_단기예보 조회서비스' 15084084 에서 무료 발급)

사용:
    from src.loading.weather import ultra_now
    obs = ultra_now(lat=37.561, lon=127.038)   # 왕십리 근처
    print(obs)   # {'T1H': 27.3, 'RN1': 0.0, 'REH': 62.0, ...}  또는 None(키 없음)

좌표 변환(위경도→격자)은 기상청 공식 LCC(Lambert Conformal Conic) 파라미터를 쓴다.
"""
from __future__ import annotations

import math
import os
import sys
from datetime import datetime, timedelta, timezone

try:
    import requests
except ImportError:                       # requests 미설치 환경 방어
    requests = None

KST = timezone(timedelta(hours=9))
KMA_ULTRA_NCST_URL = (
    "http://apis.data.go.kr/1360000/VilageFcstInfoService_2.0/getUltraSrtNcst")

# ── API 키: config/APIkey.py 의 KMA_API_KEY (없으면 환경변수) ──────────────
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(_ROOT, "config"))
try:
    from APIkey import KMA_API_KEY        # type: ignore
except Exception:
    KMA_API_KEY = os.environ.get("KMA_API_KEY", "")


def latlon_to_grid(lat: float, lon: float) -> "tuple[int, int]":
    """위경도 → 기상청 격자(nx, ny). 기상청 공식 LCC 파라미터."""
    RE, GRID = 6371.00877, 5.0
    SLAT1, SLAT2, OLON, OLAT, XO, YO = 30.0, 60.0, 126.0, 38.0, 43, 136
    DEGRAD = math.pi / 180.0
    re = RE / GRID
    slat1, slat2 = SLAT1 * DEGRAD, SLAT2 * DEGRAD
    olon, olat = OLON * DEGRAD, OLAT * DEGRAD
    sn = math.tan(math.pi * 0.25 + slat2 * 0.5) / math.tan(math.pi * 0.25 + slat1 * 0.5)
    sn = math.log(math.cos(slat1) / math.cos(slat2)) / math.log(sn)
    sf = math.tan(math.pi * 0.25 + slat1 * 0.5)
    sf = (sf ** sn) * math.cos(slat1) / sn
    ro = math.tan(math.pi * 0.25 + olat * 0.5)
    ro = re * sf / (ro ** sn)
    ra = math.tan(math.pi * 0.25 + lat * DEGRAD * 0.5)
    ra = re * sf / (ra ** sn)
    theta = lon * DEGRAD - olon
    if theta > math.pi:
        theta -= 2.0 * math.pi
    if theta < -math.pi:
        theta += 2.0 * math.pi
    theta *= sn
    nx = int(ra * math.sin(theta) + XO + 0.5)
    ny = int(ro - ra * math.cos(theta) + YO + 0.5)
    return nx, ny


def _base_datetime(now: "datetime | None" = None) -> "tuple[str, str]":
    """초단기실황 base_date/base_time. 매시각 발표, 정시+40분 후 제공 → 여유 40분."""
    now = now or datetime.now(KST)
    t = now - timedelta(minutes=40)
    return t.strftime("%Y%m%d"), t.strftime("%H00")


def ultra_now(lat: float, lon: float, now: "datetime | None" = None) -> "dict | None":
    """해당 좌표의 초단기실황(기온 T1H·1시간강수 RN1·습도 REH·풍속 WSD 등).

    키가 없거나 requests 미설치면 None(치명적이지 않음 — 호출부가 skip).
    """
    if not KMA_API_KEY or requests is None:
        return None
    nx, ny = latlon_to_grid(lat, lon)
    base_date, base_time = _base_datetime(now)
    params = {
        "serviceKey": KMA_API_KEY, "dataType": "JSON", "numOfRows": 100, "pageNo": 1,
        "base_date": base_date, "base_time": base_time, "nx": nx, "ny": ny,
    }
    try:
        res = requests.get(KMA_ULTRA_NCST_URL, params=params, timeout=15)
        res.raise_for_status()
        items = res.json()["response"]["body"]["items"]["item"]
    except Exception:
        return None
    out: dict = {}
    for it in items:
        try:
            out[it["category"]] = float(it["obsrValue"])
        except (KeyError, ValueError):
            continue
    return out or None


if __name__ == "__main__":
    if not KMA_API_KEY:
        print("KMA_API_KEY 없음. config/APIkey.py 에 KMA_API_KEY = \"발급키\" 를 넣으세요.")
        print("발급: 공공데이터포털 15084084 '기상청_단기예보 조회서비스'(무료).")
        sys.exit(0)
    print("왕십리 근처 초단기실황:", ultra_now(37.561, 127.038))
