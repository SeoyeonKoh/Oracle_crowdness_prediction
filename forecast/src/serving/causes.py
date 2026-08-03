"""1-4 혼잡 원인 — 공사 / 사고 / 지연 / 날씨.

실데이터(서울교통공사 알림정보·기상)는 아직 미확보. 인터페이스와 로더를 먼저 만들고,
데모용 샘플을 제공한다. 데이터 확보 시 `load_causes`만 실연동으로 교체하면 된다.

연동 예정 소스:
- 지연·사고·공사: 서울교통공사 지하철 알림정보(REST, 1분) / 역사내공사현황
- 날씨: 기상청 동네예보(FCST)
"""
from __future__ import annotations

import csv

from src import config

CAUSE_TYPES = ["공사", "사고", "지연", "날씨"]

# 데모용 샘플(실데이터 아님). input/causes.csv 가 있으면 그걸 우선 사용.
SAMPLE_CAUSES = [
    {"line": 2, "station": "시청", "type": "공사", "desc": "승강장 리모델링 공사"},
    {"line": 2, "station": "왕십리", "type": "지연", "desc": "열차 지연 5분"},
    {"line": 2, "station": "강남", "type": "날씨", "desc": "강우로 지상 진입 혼잡"},
]


def load_causes() -> list[dict]:
    """현재 유효한 혼잡 원인 목록. input/causes.csv 있으면 로드, 없으면 샘플."""
    fp = config.INPUT / "causes.csv"
    if fp.exists():
        with open(fp, encoding="utf-8-sig") as f:
            rows = list(csv.DictReader(f))
        out = []
        for r in rows:
            out.append({
                "line": int(r.get("line", 0) or 0),
                "station": str(r.get("station", "")).strip(),
                "type": str(r.get("type", "")).strip(),
                "desc": str(r.get("desc", "")).strip(),
            })
        return out
    return list(SAMPLE_CAUSES)


def causes_for(station: str, line: "int | None" = None,
               all_causes: "list[dict] | None" = None) -> list[dict]:
    """특정 역의 원인만 필터. 없으면 빈 리스트('특이사항 없음')."""
    src = all_causes if all_causes is not None else load_causes()
    return [c for c in src
            if c["station"] == station and (line is None or c["line"] == line)]
