"""
서울 열린데이터광장 Open API 범용 수집기.

- 서비스마다 응답 스키마를 몰라도 동작하도록, XML에서 반복되는 행(row/item) 태그를
  자동으로 찾아 그 안의 필드를 그대로 딕셔너리로 뽑아낸다.
- 이미 저장된 CSV가 있으면 이어서 append 하고, 완전히 동일한 내용의 행은
  다시 추가하지 않는다 (내용이 바뀐 경우에만 새 행 + 새 collected_at 으로 기록).

사용 예:
    python collectors/seoul_open_api_collector.py                # 등록된 전 서비스 수집
    python collectors/seoul_open_api_collector.py --service getFcLckr --end 1000
"""
import argparse
import csv
import hashlib
import sys
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

import requests

sys.path.append(str(Path(__file__).resolve().parent.parent))
from config.seoul_api_config import SERVICES, BASE_URL, get_api_key  # noqa: E402

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)


def build_url(service_id: str, api_key: str, start: int, end: int) -> str:
    return f"{BASE_URL}/{api_key}/xml/{service_id}/{start}/{end}/"


def fetch_xml(url: str) -> str:
    resp = requests.get(url, timeout=30)
    resp.raise_for_status()
    resp.encoding = "utf-8"
    return resp.text


def find_row_tag(root: ET.Element):
    """반복되는 데이터 행을 담은 태그를 자동으로 찾는다.
    - 후보: 부모 아래 같은 태그 이름의 자식이 2개 이상 있고, 그 자식들이 leaf(자식 텍스트 필드)로 구성된 경우.
    """
    counts = {}
    for parent in root.iter():
        tag_children = {}
        for child in parent:
            tag_children.setdefault(child.tag, []).append(child)
        for tag, children in tag_children.items():
            if len(children) >= 2:
                counts[tag] = children
    if not counts:
        # row가 1개뿐인 응답일 수도 있으니 흔한 이름을 우선 탐색
        for candidate in ("row", "item"):
            found = root.findall(f".//{candidate}")
            if found:
                return found
        return []
    # 가장 많이 반복된 태그를 데이터 행으로 판단
    best_tag = max(counts, key=lambda t: len(counts[t]))
    return counts[best_tag]


def parse_generic(xml_text: str):
    """알 수 없는 스키마의 서비스 응답을 파싱. row/item 태그를 자동 탐지해 필드를 그대로 추출."""
    root = ET.fromstring(xml_text)
    rows = find_row_tag(root)
    result = []
    for row in rows:
        rec = {child.tag: (child.text or "").strip() for child in row}
        if rec:
            result.append(rec)
    return result


def row_hash(rec: dict) -> str:
    """collected_at을 제외한 필드 값으로 해시를 만들어 완전 동일한 행 중복을 방지."""
    payload = "|".join(f"{k}={v}" for k, v in sorted(rec.items()) if k != "collected_at")
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def load_existing(csv_path: Path):
    if not csv_path.exists():
        return [], set()
    with open(csv_path, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        rows = list(reader)
    hashes = {row_hash(r) for r in rows}
    return rows, hashes


def write_csv(csv_path: Path, rows: list):
    if not rows:
        return
    fieldnames = []
    for r in rows:
        for k in r.keys():
            if k not in fieldnames:
                fieldnames.append(k)
    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        for r in rows:
            w.writerow(r)


def collect_service(service_id: str, api_key: str, start: int, end: int):
    info = SERVICES[service_id]
    csv_path = DATA_DIR / info["file"]

    url = build_url(service_id, api_key, start, end)
    xml_text = fetch_xml(url)
    new_records = parse_generic(xml_text)

    collected_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    for rec in new_records:
        rec["collected_at"] = collected_at

    existing_rows, existing_hashes = load_existing(csv_path)

    added = 0
    for rec in new_records:
        h = row_hash(rec)
        if h not in existing_hashes:
            existing_rows.append(rec)
            existing_hashes.add(h)
            added += 1

    write_csv(csv_path, existing_rows)
    print(f"[{service_id}] {info['label']}: 신규 {added}건 추가 (수신 {len(new_records)}건, 누적 {len(existing_rows)}건) -> {csv_path.name}")


def main():
    parser = argparse.ArgumentParser(description="서울 열린데이터광장 API 수집기")
    parser.add_argument("--service", help="특정 서비스 ID만 수집 (미지정 시 전체)")
    parser.add_argument("--start", type=int, default=1)
    parser.add_argument("--end", type=int, default=1000)
    parser.add_argument("--sleep", type=float, default=0.5, help="서비스 간 호출 간격(초)")
    args = parser.parse_args()

    api_key = get_api_key()
    targets = [args.service] if args.service else list(SERVICES.keys())

    for service_id in targets:
        if service_id not in SERVICES:
            print(f"[!] 등록되지 않은 서비스: {service_id} (config/seoul_api_config.py에 먼저 추가하세요)")
            continue
        try:
            collect_service(service_id, api_key, args.start, args.end)
        except Exception as e:
            print(f"[!] {service_id} 수집 실패: {e}")
        time.sleep(args.sleep)


if __name__ == "__main__":
    main()
