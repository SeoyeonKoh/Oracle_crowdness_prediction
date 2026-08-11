#!/usr/bin/env python3
"""화면 구성용 단일 번들 파일 생성.

층별 시설 / 시설 위치 / 역산한 동선을 한 파일에 담고,
파일 자체에 스키마·코드범례·커버리지·한계를 넣어 자기설명적으로 만든다.
이 파일 하나만 읽으면 화면을 구성할 수 있어야 한다.

출력:
    output/station_ui_bundle.json        전체 458역 (압축 표기)
    output/station_ui_bundle.sample.json 스키마 + 3개 역만 (context 투입용)

usage:
    python3 src/build_ui_bundle.py
"""
from __future__ import annotations

import json
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "kric_hc.sqlite"
LAYOUT = ROOT / "output" / "station_layout.json"
OUT = ROOT / "output" / "station_ui_bundle.json"
OUT_SAMPLE = ROOT / "output" / "station_ui_bundle.sample.json"

GENERATED_ON = "2026-08-11"

MARK = {"●": True, "×": False, "O": True, "X": False}


def flag(v):
    return MARK.get((v or "").strip()) if v is not None else None


META = {
    "title": "수도권 도시철도 역사 층별 시설·동선 데이터",
    "purpose": "역별 층 단면도 화면(층별 시설 배치 + 층간 연결 + 이동/환승 안내) 구성용",
    "source": {
        "name": "국가철도공단 철도역 편의정보",
        "url": "https://hc.kric.go.kr/hc/index.jsp",
        "scope": "수도권 1~9호선 458개 역",
        "collected_on": GENERATED_ON,
        "note": "역 구내도·동선도 이미지는 수집하지 않았다. 모든 값은 정형 데이터다.",
    },
    "schema": {
        "stations[]": {
            "id": "역 고유키. 운영기관_노선_역코드. 환승역은 노선별로 별도 레코드",
            "name": "역명",
            "line": "노선명",
            "operator": "운영기관코드 (S1 서울교통공사, KR 한국철도공사, NU 남양주도시공사 등)",
            "helperTel": "교통약자 도우미 연락처. 없으면 null",
            "prev / next": "인접역명. 노선 그래프 복원용",
            "floors[]": "위층 → 아래층 순으로 정렬됨. 그대로 세로 배치하면 단면도가 된다",
            "links[]": "층과 층의 연결. 화면의 층간 연결선에 대응",
            "routes": "이동 안내문. toPlatform=출입구→승강장, transfer=환승",
        },
        "floors[]": {
            "code": "B2, 1F 등 표시용 코드",
            "level": "정렬용 정수. 지상 양수 / 지하 음수. 0층은 존재하지 않는다",
            "label": "지하 2층 등 한글 라벨",
            "facilities[]": "그 층에 있는 시설 목록",
            "platforms[]": "그 층에 있는 승강장 목록",
        },
        "facilities[]": {
            "type": "시설 종류. 아이콘 매핑 키로 쓸 것. legend.facilityTypes 참조",
            "name": "표시명 (예: 장애인화장실(남))",
            "loc": "원본이 적은 상세 위치 문자열. 없으면 null. 예: [3호기]1번출구측",
        },
        "platforms[]": {
            "no": "승강장 번호",
            "type": "섬식 / 상대식 등",
            "toward": "진행방향 인접역 표기",
            "screenDoor / safetyFootboard / crossable / brailleBlock / brailleSign":
                "true=있음, false=없음, null=원본 미제공",
            "spots[]": "승강장 위 시설 위치. car='8-2칸'(8호차 2번문), type=엘리베이터/에스컬레이터/계단",
            "gap": "출입문 이격거리 구간별 문 개수. 키는 cm 구간",
        },
        "links[]": {
            "from / to": "출발 층코드 / 도착 층코드",
            "dir": "up / down / same(같은 층 통로)",
            "span": "실제 이동 층수. 0층이 없으므로 1F↔B1은 1이다",
            "via": "이동수단명 (엘리베이터/에스컬레이터/휠체어리프트/환승통로 등)",
            "label": "원본이 부르는 이름 (예: 잠실나루 방면 엘리베이터)",
            "src": "근거. move_path=동선 텍스트에서 역산 / facility_span=같은 승강기 호기가 여러 층에 등재",
            "verified": "두 근거가 일치하면 true. false면 동선 텍스트 하나뿐이니 화면에서 약하게 표기할 것. null=같은 층 통로라 검증 대상 아님",
        },
        "routes.toPlatform[] / routes.transfer[]": {
            "label": "경로명 (출발 → 도착)",
            "from / to": "transfer 전용. {line, dir} 로 분해된 출발/도착 노선·방면",
            "floors": "거치는 층 순서",
            "ev / es": "경로 중 엘리베이터 / 에스컬레이터 이용 횟수",
            "steps[]": "번호 매긴 안내 문장. 그대로 화면에 출력 가능",
        },
    },
    "legend": {
        "facilityTypes": [
            "출입구", "대합실", "개찰구", "승강장", "환승승강장",
            "엘리베이터", "휠체어리프트", "전동휠체어충전설비",
            "화장실", "고객센터", "수유실",
        ],
        "gapRanges": {
            "0~10": "승강장-차량 이격거리 10cm 이하",
            "10~15": "10cm 초과 15cm 이하",
            ">15": "15cm 초과. 휠체어 진입 주의 구간",
        },
        "spotCarLabel": "'8-2칸' = 8호차 2번 출입문 위치",
    },
    "derivation": {
        "note": "원본에는 층과 층의 연결 관계가 없다. links는 파생 데이터다.",
        "method": [
            "이동경로 단계 텍스트의 층 표기를 파싱한다. 괄호형 '(B1) 대합실로 이동' 과 인라인형 '지상2층 엘리베이터 하차' 두 관례를 모두 처리한다.",
            "행위 동사를 분류한다. 탑승/이용=BOARD, 하차=ALIGHT, 승차=RIDE, 통과/태그=GATE, 그 외=MOVE.",
            "BOARD 직후 층이 바뀌면 그 구간을 연결(link)로 만든다.",
            "같은 승강기 호기가 여러 층에 등재돼 있으면 그 층들도 연결로 본다(facility_span). 두 근거가 일치하면 verified=true.",
        ],
    },
    "howToUse": [
        "meta 만 읽어도 필드 의미와 코드 범례를 알 수 있게 만들었다. 별도 문서 없이 이 파일만으로 화면을 구성할 것.",
        "floors 는 위층 → 아래층 순으로 이미 정렬돼 있다. 그대로 세로로 쌓으면 역 단면도가 된다.",
        "층 단면도의 연결선은 links 를 쓴다. verified=false 인 연결은 근거가 약하므로 점선 등으로 구분하는 것을 권한다.",
        "승강장 위 아이콘 위치는 platforms[].spots 의 car 값('8-2칸')을 쓴다. 호차 순서대로 배치하면 된다.",
        "이 파일은 458개 역 전체라 한 번에 컨텍스트에 올리기엔 크다. 스키마 파악은 station_ui_bundle.sample.json(3개 역)으로 하고, 전체 데이터는 코드로 읽어 처리할 것.",
    ],
    "limitations": [
        "좌/우 방향 정보는 원본에 사실상 없다. 전체 14,229개 단계 중 좌측/우측/왼쪽/오른쪽 표현이 37건뿐이다. 안내는 층 이동(올라가기/내려가기)과 랜드마크(N번 출입구 방향, 표 내는 곳) 위주다. 화면에서 좌우 배치는 임의로 정하되 방향을 단정하는 문구는 쓰지 말 것.",
        "실시간 고장·운행중지 상태는 이 데이터에 없다. 전부 시설 대장 기준의 정적 정보다.",
        "승강장이 어느 층인지 확정된 역은 418/458이다. 나머지는 동선 텍스트가 승강장 단계에 층을 안 적었다. 시설·승강장 정보 자체는 있고 층 배치만 비어 있다.",
        "층간 연결 중 verified=false 인 건이 있다. 근거가 동선 텍스트 하나뿐이라는 뜻이다.",
        "원본이 자체 모순인 역이 있다. 예: 연천역은 '지상3층 엘리베이터 탑승' 다음 단계가 '지상1층 승강장'이라 층 이동이 어긋난다. 추측 보정을 하지 않고 verified=false로 남겼다.",
        "승강장정보 미제공 4역(탕정, 진접, 오남, 별내별가람), 편의시설정보 미제공 1역(1호선 창동)은 원본이 비어 있다.",
    ],
}


def main() -> int:
    if not LAYOUT.exists() or not DB_PATH.exists():
        print("먼저 crawl_kric_hc.py 와 build_station_layout.py 를 실행하세요", file=sys.stderr)
        return 1

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row

    # 승강장별 이격거리 분포
    gap: dict[tuple, Counter] = defaultdict(Counter)
    for r in con.execute("select * from platform_gaps"):
        key = (r["rail_opr_istt_cd"], r["ln_cd"], r["prpr_stin_cd"], r["plf_no"])
        rng = r["sf_dst_range_cm"]
        if rng == "10초과~15이하":
            rng = "10~15"
        elif rng == "15초과":
            rng = ">15"
        gap[key][rng or "unknown"] += 1

    layouts = json.loads(LAYOUT.read_text(encoding="utf-8"))
    stations = []

    for s in layouts:
        okey = (s["rail_opr_istt_cd"], s["ln_cd"], s["prpr_stin_cd"])
        floors = []
        for f in s["floors"]:
            facilities = [
                {"type": n["kind"], "name": n["label"], "loc": n["detail"]}
                for n in f["nodes"]
                if n["kind"] != "승강장"
            ]
            plats = []
            for p in f["platforms"]:
                g = gap.get((*okey, p["plf_no"]), Counter())
                plats.append(
                    {
                        "no": p["plf_no"],
                        "type": p["plf_tp_nm"],
                        "toward": p["toward"],
                        "screenDoor": flag(p["screen_door"]),
                        "safetyFootboard": flag(p["safety_footboard"]),
                        "crossable": flag(p["platform_crossable"]),
                        "brailleBlock": flag(p["braille_block"]),
                        "brailleSign": flag(p["braille_sign"]),
                        "spots": [
                            {"car": x["car_label"], "type": x["facility_nm"]}
                            for x in p["facility_positions"]
                        ],
                        "gap": {k: v for k, v in sorted(g.items()) if k != "unknown"},
                    }
                )
            floors.append(
                {
                    "code": f["floor"],
                    "level": f["level"],
                    "label": f["label"],
                    "facilities": facilities,
                    "platforms": plats,
                }
            )

        links = [
            {
                "from": e["from_floor"],
                "to": e["to_floor"],
                "dir": e["direction"],
                "span": e["floor_span"],
                "via": e["conveyance_nm"],
                "label": e["label"],
                "src": e["source"],
                "verified": (None if e["corroborated"] is None else bool(e["corroborated"])),
            }
            for e in s["connections"]
        ]

        def route(r, transfer=False):
            out = {
                "label": r["label"],
                "floors": r["floor_sequence"],
                "ev": r["n_elevator"],
                "es": r["n_escalator"],
                "steps": [x.split(". ", 1)[1] if ". " in x else x for x in r["guide_lines"]],
            }
            if transfer:
                import re

                sm = re.match(r"(\S*[호]?선)?\s*(.+?)\s*방면$", r["start_point"] or "")
                em = re.match(r"(\S*[호]?선)?\s*(.+?)\s*방면$", r["end_point"] or "")
                out["from"] = {
                    "line": (sm.group(1) if sm else None) or s["ln_nm"],
                    "dir": sm.group(2) if sm else r["start_point"],
                }
                out["to"] = {
                    "line": em.group(1) if em else None,
                    "dir": em.group(2) if em else r["end_point"],
                }
            return out

        stations.append(
            {
                "id": s["station_id"],
                "name": s["stin_nm"],
                "line": s["ln_nm"],
                "operator": s["rail_opr_istt_cd"],
                "helperTel": s["helper_tel"],
                "prev": s["prev_stin_nm"],
                "next": s["next_stin_nm"],
                "floors": floors,
                "links": links,
                "routes": {
                    "toPlatform": [route(r) for r in s["routes"]["entrance_to_platform"]],
                    "transfer": [route(r, True) for r in s["routes"]["transfer"]],
                },
            }
        )

    coverage = {
        "stations": len(stations),
        "withFloors": sum(1 for x in stations if x["floors"]),
        "withLinks": sum(1 for x in stations if x["links"]),
        "withPlatformFloorResolved": sum(
            1 for x in stations if any(f["platforms"] for f in x["floors"])
        ),
        "withTransferGuide": sum(1 for x in stations if x["routes"]["transfer"]),
        "totalFacilities": sum(len(f["facilities"]) for x in stations for f in x["floors"]),
        "totalLinks": sum(len(x["links"]) for x in stations),
        "totalRoutes": sum(
            len(x["routes"]["toPlatform"]) + len(x["routes"]["transfer"]) for x in stations
        ),
    }
    vl = [l for x in stations for l in x["links"] if l["verified"] is not None]
    mp = [l for l in vl if l["src"] == "move_path"]
    coverage["linksVerifiedRatio"] = round(sum(1 for l in vl if l["verified"]) / len(vl), 3)
    coverage["linksVerifiedRatio_note"] = (
        "전체 층간 연결 기준. facility_span 근거는 정의상 항상 verified 다. "
        "동선 텍스트에서만 역산한 연결(src=move_path)만 보면 "
        f"{round(sum(1 for l in mp if l['verified']) / len(mp), 3)} 이다."
    )

    bundle = {"meta": {**META, "generated_on": GENERATED_ON, "coverage": coverage},
              "stations": stations}

    OUT.write_text(
        json.dumps(bundle, ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
    )
    size = OUT.stat().st_size
    print(f"  {OUT.relative_to(ROOT)}  {len(stations)}역  {size/1024/1024:.1f}MB")

    picks = ["잠실", "왕십리", "연천"]
    sample = [next(x for x in stations if x["name"] == p) for p in picks]
    sample_bundle = {
        "meta": {
            **bundle["meta"],
            "note_on_this_file": (
                "이 파일은 스키마 확인용 발췌본이다. 역 3개만 들어 있다. "
                "전체 458역은 station_ui_bundle.json 에 같은 구조로 들어 있다."
            ),
        },
        "stations": sample,
    }
    OUT_SAMPLE.write_text(
        json.dumps(sample_bundle, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(
        f"  {OUT_SAMPLE.relative_to(ROOT)}  3역(발췌)  "
        f"{OUT_SAMPLE.stat().st_size/1024:.0f}KB"
    )
    print("\n커버리지:", json.dumps(coverage, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
