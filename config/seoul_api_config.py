"""
서울 열린데이터광장 (data.seoul.go.kr) Open API 설정.

인증키는 절대 코드/저장소에 직접 적지 말고, 환경변수로 주입한다.
    export SEOUL_OPENAPI_KEY="발급받은_인증키"

또는 저장소 루트에 .env 파일을 만들고 (반드시 .gitignore에 추가):
    SEOUL_OPENAPI_KEY=발급받은_인증키
"""
import os

API_KEY_ENV_VAR = "SEOUL_OPENAPI_KEY"


def get_api_key() -> str:
    key = os.environ.get(API_KEY_ENV_VAR)
    if not key:
        raise RuntimeError(
            f"환경변수 {API_KEY_ENV_VAR}가 설정되어 있지 않습니다. "
            f"실행 전에 `export {API_KEY_ENV_VAR}=발급받은_인증키` 를 먼저 실행하세요."
        )
    return key


# service_id: data.seoul.go.kr API 서비스명 (URL 경로에 그대로 들어감)
# file: data/ 폴더에 누적 저장될 CSV 파일명
# label: 참고용 한글 설명 (서비스명에서 추정한 것 — 실제 응답을 받아보고 다르면 수정)
SERVICES = {
    "SeoulMetroFaciInfo": {"file": "elevator_status.csv", "label": "승강기 가동 현황"},
    "getWksnRstrm":       {"file": "accessible_restroom_status.csv", "label": "교통약자 장애인화장실 현황"},
    "getNtceList":        {"file": "subway_notice_status.csv", "label": "지하철 알림정보 현황"},
    "getFcLckr":          {"file": "locker_status.csv", "label": "물품보관함 현황 (추정)"},
    "getWksnMvnwlk":      {"file": "moving_walk_status.csv", "label": "무빙워크 현황 (추정)"},
    "getWksnHelper":      {"file": "helper_status.csv", "label": "교통약자 도우미 현황 (추정)"},
    "getWksnSafePlfm":    {"file": "safe_platform_status.csv", "label": "안전발판 보유 현황 (추정)"},
    "getFcEsctr":         {"file": "escalator_status.csv", "label": "에스컬레이터 현황 (추정)"},
    "tbTraficElvtr":      {"file": "traffic_elevator_status.csv", "label": "엘리베이터 관련 정보 (추정)"},
    "getFcNrsrm":         {"file": "nursing_room_status.csv", "label": "수유실 현황 (추정)"},
    "getWksnSlng":        {"file": "sign_language_phone_status.csv", "label": "수어영상전화기 현황 (추정)"},
    "TbSubwayLineInfo":   {"file": "subway_line_info.csv", "label": "지하철 노선 정보 (추정)"},
}

BASE_URL = "http://openapi.seoul.go.kr:8088"
