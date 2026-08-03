# -*- coding: utf-8 -*-
"""
실시간 지하철 데이터 받아오기

서울 열린데이터광장 실시간 지하철 API 4개를 호출해서
응답을 '가공 없이 그대로' 파일로 저장합니다.

실행 방법:  python3 fetch_realtime.py

처음 실행하면 인증키를 물어봅니다. 한 번 입력하면 APIkey.py 에 저장돼서
다음부터는 안 물어봅니다. (그 파일은 .gitignore 에 자동 추가됩니다)

한 번 실행할 때 4번 호출합니다. 하루 한도 1000번이니 넉넉합니다.
"""

import json
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime

폴더 = os.path.dirname(os.path.abspath(__file__))
저장위치 = os.path.join(폴더, "data", "realtime")


# ---------------------------------------------------------------
# 인증키 준비
# ---------------------------------------------------------------

def 인증키_가져오기():
    키파일 = os.path.join(폴더, "APIkey.py")

    if os.path.exists(키파일):
        내용 = {}
        with open(키파일, encoding="utf-8") as f:
            exec(f.read(), 내용)
        키 = 내용.get("SUBWAY_KEY")
        if 키:
            print("APIkey.py 에서 인증키를 읽었습니다.")
            return 키

    # cron 처럼 키보드가 없는 환경에서는 입력을 기다리지 않고 종료합니다
    if not sys.stdin.isatty():
        print("[오류] APIkey.py 에 SUBWAY_KEY 가 없습니다.")
        print("       서버에서는 APIkey.py 를 미리 만들어 두어야 합니다:")
        print('       SUBWAY_KEY = "발급받은_실시간지하철_인증키"')
        sys.exit(1)

    print("\n실시간 지하철 인증키가 필요합니다.")
    print("(열린데이터광장 마이페이지 > 인증키 신청 에서 받은 것)")
    키 = input("인증키를 붙여넣고 엔터: ").strip()

    if not 키:
        print("인증키가 비어 있습니다. 종료합니다.")
        sys.exit(1)

    with open(키파일, "w", encoding="utf-8") as f:
        f.write('# 이 파일은 절대 GitHub 에 올리면 안 됩니다\n')
        f.write(f'SUBWAY_KEY = "{키}"\n')
    print("APIkey.py 에 저장했습니다.")

    깃무시 = os.path.join(폴더, ".gitignore")
    기존 = ""
    if os.path.exists(깃무시):
        with open(깃무시, encoding="utf-8") as f:
            기존 = f.read()
    if "APIkey.py" not in 기존:
        with open(깃무시, "a", encoding="utf-8") as f:
            f.write("\nAPIkey.py\ndata/\n")
        print(".gitignore 에 APIkey.py 를 추가했습니다.")

    return 키


# ---------------------------------------------------------------
# 호출할 목록
# ---------------------------------------------------------------

호출목록 = [
    ("position_2호선",  "realtimePosition",       "0/100", "2호선"),
    ("position_4호선",  "realtimePosition",       "0/100", "4호선"),
    ("arrival_왕십리",  "realtimeStationArrival", "0/20",  "왕십리"),
    ("arrival_동대문",  "realtimeStationArrival", "0/20",  "동대문역사문화공원"),
]


def 한번_호출(키, 이름, 서비스, 범위, 대상, 시각표시):
    주소 = (f"http://swopenapi.seoul.go.kr/api/subway/{urllib.parse.quote(키)}/json/"
            f"{서비스}/{범위}/{urllib.parse.quote(대상)}")
    try:
        with urllib.request.urlopen(주소, timeout=15) as 응답:
            원문 = 응답.read().decode("utf-8")
    except Exception as e:
        print(f"  [실패] {이름} — {e}")  # noqa
        return False

    파일이름 = f"{시각표시}_{이름}.json"
    저장경로 = os.path.join(저장위치, 파일이름)
    with open(저장경로, "w", encoding="utf-8") as f:
        f.write(원문)

    # 뭐가 들어왔는지 간단히 알려주기
    설명 = ""
    try:
        자료 = json.loads(원문)
        조각 = []
        for 키이름, 값 in 자료.items():
            if isinstance(값, list):
                조각.append(f"{키이름} {len(값)}건")
            elif isinstance(값, dict) and "message" in 값:
                조각.append(str(값.get("message"))[:40])
        설명 = " · " + ", ".join(조각) if 조각 else ""
    except Exception:
        설명 = " · (JSON 형식이 아님 — 파일을 직접 열어보세요)"

    print(f"  [성공] {이름} → {파일이름}{설명}")
    return True


def main():
    키 = 인증키_가져오기()
    os.makedirs(저장위치, exist_ok=True)

    시각 = datetime.now()
    시각표시 = 시각.strftime("%Y%m%d_%H%M%S")
    표 = 시각.strftime('%Y-%m-%d %H:%M:%S')
    print(f"[{표}] [realtime] 수집 시작 (4건)")

    성공 = 0
    for 이름, 서비스, 범위, 대상 in 호출목록:
        if 한번_호출(키, 이름, 서비스, 범위, 대상, 시각표시):
            성공 += 1

    print(f"[{표}] [realtime] 완료: 성공 {성공} / 실패 {len(호출목록) - 성공}"
          f" · 저장 {저장위치}")

    if 성공 == 0:
        print("\n전부 실패했습니다. 확인해 보세요:")
        print("  - 인증키가 '실시간 지하철' 인증키가 맞는지 (일반 인증키 아님)")
        print("  - 인터넷 연결이 되는지")
        print("  - APIkey.py 를 지우고 다시 실행하면 키를 새로 입력할 수 있습니다")


if __name__ == "__main__":
    main()
