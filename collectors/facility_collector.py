# -*- coding: utf-8 -*-
"""서울 열린데이터광장 시설 API 12종 일일 수집기 (GitHub Actions용)

- 인증키는 환경변수 SEOUL_OPENAPI_KEY 로 주입 (코드에 절대 넣지 않음)
- 서비스마다 최대 1000행씩, 전체 건수만큼 자동 페이지네이션
- data/<이름>.csv 에 누적 저장:
    * 내용이 완전히 같은 행은 다시 추가하지 않음
    * 값이 바뀐 행(예: 승강기 상태 변화)만 collected_at 과 함께 새 행으로 기록
"""
import csv
import os
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import datetime, timezone, timedelta

BASE = "http://openapi.seoul.go.kr:8088"
PAGE = 1000            # 한 번에 받는 최대 행 수
MAX_TOTAL = 20000      # 안전장치: 서비스당 이 이상은 받지 않음
KST = timezone(timedelta(hours=9))

# (서비스 ID, 저장 파일 이름, 한글 라벨)
SERVICES = [
    ("getWksnRstrm",       "accessible_restroom",  "교통약자 장애인화장실"),
    ("getFcLckr",          "locker",               "물품보관함"),
    ("getWksnMvnwlk",      "moving_walk",          "무빙워크"),
    ("getWksnHelper",      "helper",               "교통약자 도우미"),
    ("getWksnSafePlfm",    "safe_platform",        "안전발판"),
    ("getFcEsctr",         "escalator",            "에스컬레이터"),
    ("getNtceList",        "notice",               "지하철 알림정보"),
    ("tbTraficElvtr",      "elevator_location",    "엘리베이터 위치정보"),
    ("getFcNrsrm",         "nursing_room",         "수유실"),
    ("getWksnSlng",        "sign_language_phone",  "수어영상전화기"),
    ("SeoulMetroFaciInfo", "elevator_status",      "승강기 가동현황"),
    ("TbSubwayLineInfo",   "subway_line_info",     "지하철 노선정보"),
]

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")


def fetch_xml(key: str, service: str, start: int, end: int) -> str:
    url = f"{BASE}/{key}/xml/{service}/{start}/{end}/"
    with urllib.request.urlopen(url, timeout=60) as resp:
        return resp.read().decode("utf-8", errors="replace")


def parse_xml(text: str):
    """(결과코드, 전체건수, 행 리스트) 반환. 반복 태그는 자동 감지."""
    root = ET.fromstring(text)
    code = root.findtext(".//CODE") or ""
    total_text = root.findtext(".//list_total_count")
    total = int(total_text) if total_text and total_text.strip().isdigit() else None

    # 자식 요소를 가진 반복 태그를 자동 감지 (보통 'row')
    counter = Counter(
        el.tag for el in root.iter()
        if len(el) > 0 and el.tag not in (root.tag, "RESULT")
    )
    rows = []
    if counter:
        row_tag = counter.most_common(1)[0][0]
        for el in root.iter(row_tag):
            rows.append({c.tag: (c.text or "").strip() for c in el})
    return code, total, rows


def collect_service(key: str, service: str, label: str):
    """페이지네이션 포함 전체 수집. 행 dict 리스트 반환."""
    all_rows = []
    start = 1
    while start <= MAX_TOTAL:
        end = start + PAGE - 1
        text = fetch_xml(key, service, start, end)
        code, total, rows = parse_xml(text)

        if code == "INFO-200":          # 해당하는 데이터 없음
            break
        if code and code != "INFO-000":
            print(f"  [경고] {label}({service}) 응답 코드 {code} — 이번 회차 건너뜀")
            break

        all_rows.extend(rows)
        if total is None or len(all_rows) >= total or not rows:
            break
        start = end + 1
        time.sleep(0.3)
    return all_rows


def row_signature(d: dict):
    """collected_at 을 제외한 내용 기준 중복 판정 키."""
    return tuple(sorted((k, v) for k, v in d.items() if k != "collected_at"))


def load_existing(path: str):
    """기존 CSV의 (헤더, 시그니처 집합, 전체 행) 로드."""
    if not os.path.exists(path):
        return [], set(), []
    with open(path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        header = reader.fieldnames or []
        rows = list(reader)
    sigs = {row_signature(r) for r in rows}
    return header, sigs, rows


def save(path: str, header, old_rows, new_rows, now_str: str):
    """헤더가 확장되면 전체 재작성, 아니면 이어붙이기."""
    new_keys = []
    for r in new_rows:
        for k in r:
            if k not in header and k not in new_keys:
                new_keys.append(k)

    for r in new_rows:
        r["collected_at"] = now_str

    if not header:
        header = ["collected_at"] + [k for k in new_keys if k != "collected_at"]
        new_keys = []

    if new_keys:  # 새 컬럼 등장 → 파일 전체 재작성
        header = header + new_keys
        with open(path, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
            w.writeheader()
            for r in old_rows + new_rows:
                w.writerow(r)
    else:
        file_exists = os.path.exists(path)
        with open(path, "a", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=header, extrasaction="ignore")
            if not file_exists:
                w.writeheader()
            for r in new_rows:
                w.writerow(r)


def main():
    key = os.environ.get("SEOUL_OPENAPI_KEY", "").strip()
    if not key:
        print("오류: 환경변수 SEOUL_OPENAPI_KEY 가 없습니다.")
        sys.exit(1)

    os.makedirs(DATA_DIR, exist_ok=True)
    now_str = datetime.now(KST).strftime("%Y-%m-%d %H:%M")
    print(f"수집 시작 ({now_str} KST)")

    for service, fname, label in SERVICES:
        path = os.path.join(DATA_DIR, f"{fname}.csv")
        try:
            fetched = collect_service(key, service, label)
        except Exception as e:  # 한 서비스 실패해도 나머지는 계속
            print(f"  [실패] {label}({service}): {e}")
            continue

        header, sigs, old_rows = load_existing(path)
        fresh = [r for r in fetched if row_signature(r) not in sigs]
        if fresh:
            save(path, header, old_rows, fresh, now_str)
        print(f"  {label}: 받음 {len(fetched)}건 / 새로 저장 {len(fresh)}건")

    print("수집 완료")


if __name__ == "__main__":
    main()
