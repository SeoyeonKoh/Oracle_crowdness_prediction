#!/usr/bin/env python3
"""KRIC 원본 데이터 → 역별 층별 배치도 + 이동동선 안내 텍스트 생성.

crawl_kric_hc.py 가 만든 data/kric_hc.sqlite 를 읽어
  1) 역 × 층 × 시설 노드 배치 (floor_nodes)
  2) 층 간 연결 관계 (floor_edges) — 어떤 수단으로 어느 층에서 어느 층까지
  3) 승강장 위 EV/ES/계단 위치 (n-m칸)
  4) 경로별 자연어 안내문 (올라가기/내려가기 포함)
을 산출한다.

층 연결 관계는 원본에 없다. move_path_steps 의 단계 텍스트에 박혀 있는
층 표기 `(B2)` 와 행위 동사(탑승/이동/통과/하차/승차)를 파싱해 역산한다.

usage:
    python3 src/build_station_layout.py
"""
from __future__ import annotations

import csv
import json
import re
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB_PATH = ROOT / "data" / "kric_hc.sqlite"
OUT_DIR = ROOT / "output" / "kric_hc"

# ---- 층 표기 정규화 ---------------------------------------------------------
FLOOR_RE = re.compile(r"^(?:B(\d+)|F?(\d+)F?)$")


def norm_floor(token: str) -> tuple[str, int, str] | None:
    """'(B2)' 안의 토큰 → (코드, 레벨, 라벨). 층 표기가 아니면 None."""
    t = token.strip().upper().replace(" ", "")
    m = FLOOR_RE.match(t)
    if not m:
        return None
    if m.group(1):
        lv = -int(m.group(1))
        return f"B{-lv}", lv, f"지하 {-lv}층"
    lv = int(m.group(2))
    if lv == 0 or lv > 20:
        return None
    return f"{lv}F", lv, f"지상 {lv}층"


def floor_label(level: int) -> str:
    return f"지하 {-level}층" if level < 0 else f"지상 {level}층"


def floor_code(level: int) -> str:
    return f"B{-level}" if level < 0 else f"{level}F"


def ordinal(level: int) -> int:
    """물리적 층 순서. 0층이 없으므로 지하는 +1 해서 연속 정수로 만든다.

    1F=1, B1=0, B2=-1 … → 1F↔B1 은 1개 층 차이가 된다.
    """
    return level if level > 0 else level + 1


def floor_span(a: int, b: int) -> int:
    return abs(ordinal(a) - ordinal(b))


# ---- 이동수단 / 행위 사전 ----------------------------------------------------
CONVEYANCES = [
    ("EV", "엘리베이터", ("엘리베이터", "엘리베에터", "EV", "승강기")),
    ("WCLF", "휠체어리프트", ("휠체어리프트", "리프트")),
    ("ES", "에스컬레이터", ("에스컬레이터", "에스컬레이타")),
    ("STAIR", "계단", ("계단",)),
    ("RAMP", "경사로", ("경사로",)),
    ("MOVINGWALK", "무빙워크", ("무빙워크",)),
    ("PASSAGE", "환승통로", ("환승통로", "이동통로", "연결통로")),
]

FACILITY_KIND = {
    "EV": "엘리베이터",
    "WCLF": "휠체어리프트",
    "ELEC": "전동휠체어충전설비",
    "TOLT": "화장실",
    "INFO": "고객센터",
    "LARM": "수유실",
}

# 원본에 좌/우 표현은 드물지만 있으면 살린다 (앞=`엘리베이터 앞` 관용구라 제외)
SIDE_WORDS = ("좌측", "우측", "왼쪽", "오른쪽", "좌회전", "우회전", "유턴", "직진")


def detect_conveyance(text: str) -> tuple[str, str] | tuple[None, None]:
    for code, name, keys in CONVEYANCES:
        if any(k in text for k in keys):
            return code, name
    return None, None


def detect_action(text: str) -> str:
    if "하차" in text:
        return "ALIGHT"
    if "승차" in text:
        return "RIDE"
    if "탑승" in text or "이용" in text:
        return "BOARD"
    if "통과" in text or "태그" in text:
        return "GATE"
    return "MOVE"


STEP_PREFIX = re.compile(r"^\s*\d+\s*\)\s*")
LEAD_PAREN = re.compile(r"^\s*\(([^)]{1,8})\)\s*")
# 코레일 구간은 괄호 표기 대신 '지상2층' / '지하1층' 을 문장 안에 쓴다
INLINE_FLOOR = re.compile(r"지(상|하)\s*(\d+)\s*층")


def parse_step(raw: str) -> dict:
    """'3) (B1) 대합실로 이동' → {floor, text, action, conveyance}

    층 표기는 두 가지 관례를 모두 지원한다.
      - 괄호형: '(B1) 대합실로 이동'
      - 인라인형: '지상2층 엘리베이터 하차'
    """
    t = STEP_PREFIX.sub("", raw or "").strip()
    floor = None
    notation = None
    m = LEAD_PAREN.match(t)
    if m:
        f = norm_floor(m.group(1))
        if f:
            floor = f
            notation = "paren"
            t = t[m.end() :].strip()
    if floor is None:
        im = INLINE_FLOOR.search(t)
        if im:
            lv = int(im.group(2)) * (1 if im.group(1) == "상" else -1)
            floor = (floor_code(lv), lv, floor_label(lv))
            notation = "inline"
    cv, cv_nm = detect_conveyance(t)
    return {
        "floor": floor,
        "floor_notation": notation,
        "text": t,
        "raw": raw,
        "action": detect_action(t),
        "conveyance": cv,
        "conveyance_nm": cv_nm,
        "side_hint": next((w for w in SIDE_WORDS if w in t), None),
    }


# ---- 경로 파싱: 층 전이 그래프 + 안내문 ---------------------------------------
PLATFORM_RE = re.compile(
    r"(?:(\S*?호선|\S*?선)\s*)?(.+?)\s*방면\s*(?:지[상하]\s*\d+\s*층\s*)?승강장"
)
EXIT_RE = re.compile(r"(\d+(?:-\d+)?)\s*번\s*(?:출입구|출구)")


def walk_path(steps: list[dict]) -> dict:
    """단계 목록을 훑어 층 전이(edges)와 층별 등장 노드를 뽑는다."""
    cur = None          # 현재 층 (code, level, label)
    pending = None      # 탑승했으나 아직 도착층을 모르는 이동수단
    edges: list[dict] = []
    concourse: set[int] = set()
    gates: set[int] = set()
    platforms: list[tuple[int, str, str]] = []  # (level, line, direction)
    floors_seq: list[str] = []

    for s in steps:
        if s["floor"]:
            arrived = s["floor"]
            if pending and cur and arrived[1] != cur[1]:
                edges.append(
                    {
                        "from_level": cur[1],
                        "to_level": arrived[1],
                        "conveyance": pending["conveyance"],
                        "conveyance_nm": pending["conveyance_nm"],
                        "label": pending["label"],
                        "notation": s["floor_notation"],
                    }
                )
                pending = None
            cur = arrived
            if not floors_seq or floors_seq[-1] != cur[0]:
                floors_seq.append(cur[0])

        if cur:
            # '대합실 방향 엘리베이터 탑승'은 대합실이 그 층에 있다는 뜻이 아니다
            if "대합실" in s["text"] and not re.search(r"대합실\s*(방향|방면|쪽)", s["text"]):
                concourse.add(cur[1])
            if "표" in s["text"] and s["action"] == "GATE":
                gates.add(cur[1])
            pm = PLATFORM_RE.search(s["text"])
            if pm:
                platforms.append((cur[1], (pm.group(1) or "").strip(), pm.group(2).strip()))

        if s["action"] == "BOARD" and s["conveyance"] in ("EV", "ES", "WCLF", "STAIR", "RAMP"):
            pending = {
                "conveyance": s["conveyance"],
                "conveyance_nm": s["conveyance_nm"],
                "label": re.sub(r"\s*(탑승|이용)\s*$", "", s["text"]).strip(),
            }
        elif s["conveyance"] == "PASSAGE" and cur:
            edges.append(
                {
                    "from_level": cur[1],
                    "to_level": cur[1],
                    "conveyance": "PASSAGE",
                    "conveyance_nm": "환승통로",
                    "label": s["text"],
                }
            )

    return {
        "edges": edges,
        "concourse_levels": concourse,
        "gate_levels": gates,
        "platform_hits": platforms,
        "floors_seq": floors_seq,
    }


def make_guide(steps: list[dict]) -> tuple[list[str], str]:
    """단계 목록 → 사람이 읽는 안내 문장 + 한 줄 요약."""
    cur = None
    pending = None
    lines: list[str] = []
    n = 0

    def add(text: str) -> None:
        nonlocal n
        n += 1
        lines.append(f"{n}. {text}")

    for s in steps:
        arrived = s["floor"]
        if arrived and pending and cur and arrived[1] != cur[1]:
            way = "올라가기" if arrived[1] > cur[1] else "내려가기"
            add(
                f"{pending['label']}(으)로 {floor_span(cur[1], arrived[1])}개 층 {way} "
                f"({cur[0]} → {arrived[0]}, {pending['conveyance_nm']})"
            )
            pending = None
        if arrived:
            cur = arrived

        here = f"[{cur[0]}] " if cur else ""
        act = s["action"]
        txt = s["text"]

        if act == "BOARD" and s["conveyance"] in ("EV", "ES", "WCLF", "STAIR", "RAMP"):
            pending = {
                "conveyance": s["conveyance"],
                "conveyance_nm": s["conveyance_nm"],
                "label": re.sub(r"\s*(탑승|이용)\s*$", "", txt).strip(),
            }
            continue
        if act == "ALIGHT":
            add(f"{here}{txt}")
        elif act == "RIDE":
            add(f"{here}{txt}")
        elif act == "GATE":
            add(f"{here}{txt}")
        else:
            side = f" ({s['side_hint']})" if s["side_hint"] else ""
            add(f"{here}{txt}{side}")

    if pending:
        add(f"{pending['label']} 이용 ({pending['conveyance_nm']})")
    return lines, " → ".join(re.sub(r"^\d+\.\s*", "", x) for x in lines)


# ---- 메인 ---------------------------------------------------------------------
def main() -> int:
    if not DB_PATH.exists():
        print(f"먼저 크롤러를 실행하세요: {DB_PATH} 없음", file=sys.stderr)
        return 1

    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    q = lambda sql: [dict(r) for r in con.execute(sql)]  # noqa: E731

    stations = q("select * from stations")
    by_key = lambda r: (r["rail_opr_istt_cd"], r["ln_cd"], r["prpr_stin_cd"])  # noqa: E731

    facilities = defaultdict(list)
    for r in q("select * from facilities"):
        facilities[by_key(r)].append(r)

    floors_raw = defaultdict(list)
    for r in q("select * from station_floors"):
        floors_raw[by_key(r)].append(r)

    platforms = defaultdict(list)
    for r in q("select * from platforms"):
        platforms[by_key(r)].append(r)

    gaps = defaultdict(list)
    for r in q(
        "select * from platform_gaps where near_elevator='Y' or near_escalator='Y' or near_stair='Y'"
    ):
        gaps[by_key(r)].append(r)

    helpers = {}
    for r in q("select * from helpers"):
        helpers.setdefault(by_key(r), r["tel_no"])

    paths = defaultdict(list)
    for r in q("select * from move_paths"):
        paths[by_key(r)].append(r)

    steps_idx = defaultdict(list)
    for r in q("select * from move_path_steps order by step_no"):
        steps_idx[(by_key(r), str(r["mv_path_dv_cd"]), r["mg_no"])].append(r["step_text"])

    out_nodes: list[dict] = []
    out_edges: list[dict] = []
    out_positions: list[dict] = []
    out_guides: list[dict] = []
    out_transfers: list[dict] = []
    layouts: list[dict] = []

    for st in stations:
        key = by_key(st)
        sid = f"{st['rail_opr_istt_cd']}_{st['ln_cd']}_{st['prpr_stin_cd']}"
        base = {
            "station_id": sid,
            "ln_nm": st["ln_nm"],
            "stin_nm": st["stin_nm"],
        }

        # --- 경로 파싱 (층 그래프의 근거) ---
        agg_edges: dict[tuple, dict] = {}
        concourse: set[int] = set()
        gates: set[int] = set()
        plat_floor: dict[tuple[str, str], int] = {}
        routes = {"entrance_to_platform": [], "transfer": []}

        for p in sorted(paths[key], key=lambda r: (r["mv_path_dv_cd"], r["mg_no"])):
            dv, mg = str(p["mv_path_dv_cd"]), p["mg_no"]
            raw_steps = steps_idx.get((key, dv, mg), [])
            if not raw_steps:
                continue
            steps = [parse_step(s) for s in raw_steps]
            walked = walk_path(steps)
            lines, one_line = make_guide(steps)

            for e in walked["edges"]:
                k = (e["from_level"], e["to_level"], e["conveyance"], e["label"])
                agg_edges.setdefault(k, e)
            concourse |= walked["concourse_levels"]
            gates |= walked["gate_levels"]
            for lv, line, direction in walked["platform_hits"]:
                plat_floor.setdefault((line or st["ln_nm"], direction), lv)

            n_ev = sum(1 for e in walked["edges"] if e["conveyance"] == "EV")
            n_es = sum(1 for e in walked["edges"] if e["conveyance"] == "ES")
            route = {
                "mv_path_dv_cd": dv,
                "mv_path_dv_nm": p["mv_path_dv_nm"],
                "mg_no": mg,
                "label": p["path_label"],
                "start_point": p["start_point"],
                "end_point": p["end_point"],
                "floor_sequence": walked["floors_seq"],
                "n_steps": len(lines),
                "n_elevator": n_ev,
                "n_escalator": n_es,
                "guide_lines": lines,
                "guide_text": one_line,
            }
            (routes["transfer"] if dv == "3" else routes["entrance_to_platform"]).append(route)

            out_guides.append(
                {
                    **base,
                    "mv_path_dv_cd": dv,
                    "mv_path_dv_nm": p["mv_path_dv_nm"],
                    "mg_no": mg,
                    "path_label": p["path_label"],
                    "floor_sequence": " → ".join(walked["floors_seq"]),
                    "n_steps": len(lines),
                    "n_elevator": n_ev,
                    "n_escalator": n_es,
                    "guide_text": one_line,
                    "guide_lines": " | ".join(lines),
                }
            )

            if dv == "3":
                sm = re.match(r"(\S*[호]?선)?\s*(.+?)\s*방면$", p["start_point"] or "")
                em = re.match(r"(\S*[호]?선)?\s*(.+?)\s*방면$", p["end_point"] or "")
                out_transfers.append(
                    {
                        **base,
                        "from_line": (sm.group(1) if sm else None) or st["ln_nm"],
                        "from_direction": sm.group(2) if sm else p["start_point"],
                        "to_line": em.group(1) if em else None,
                        "to_direction": em.group(2) if em else p["end_point"],
                        "floor_sequence": " → ".join(walked["floors_seq"]),
                        "n_steps": len(lines),
                        "n_elevator": n_ev,
                        "n_escalator": n_es,
                        "guide_text": one_line,
                    }
                )

        # --- 같은 승강기/리프트가 여러 층에 등재되어 있으면 그 층들은 서로 연결된다 ---
        span: dict[tuple[str, str], set[int]] = defaultdict(set)
        for f in facilities[key]:
            if f["facility_cd"] not in ("EV", "WCLF"):
                continue
            loc = (f["detail_location"] or "").strip()
            if not loc:
                continue
            lv = f["stin_flor"] if f["grnd_dv_cd"] == "1" else -int(f["stin_flor"])
            span[(f["facility_cd"], loc)].add(lv)
        for (cd, loc), lvs in span.items():
            if len(lvs) < 2:
                continue
            ordered = sorted(lvs, reverse=True)
            for a, b in zip(ordered, ordered[1:]):
                agg_edges.setdefault(
                    (a, b, cd, loc),
                    {
                        "from_level": a,
                        "to_level": b,
                        "conveyance": cd,
                        "conveyance_nm": FACILITY_KIND[cd],
                        "label": loc,
                        "source": "facility_span",
                    },
                )

        # 시설 등재(호기별 층)로 교차검증되는 층쌍
        verified_pairs = {
            frozenset((a, b))
            for (a, b, cd, loc), e in agg_edges.items()
            if e.get("source") == "facility_span"
        }

        for k, e in agg_edges.items():
            src = e.get("source", "move_path")
            pair = frozenset((e["from_level"], e["to_level"]))
            out_edges.append(
                {
                    **base,
                    "source": src,
                    "floor_notation": e.get("notation"),
                    # 같은 층 통로는 승강기 층등재로 검증할 대상이 아니므로 None
                    "corroborated": (
                        None
                        if e["from_level"] == e["to_level"]
                        else (1 if src == "facility_span" or pair in verified_pairs else 0)
                    ),
                    "from_floor": floor_code(e["from_level"]),
                    "to_floor": floor_code(e["to_level"]),
                    "floor_span": floor_span(e["from_level"], e["to_level"]),
                    "direction": (
                        "up"
                        if e["to_level"] > e["from_level"]
                        else ("down" if e["to_level"] < e["from_level"] else "same")
                    ),
                    "conveyance": e["conveyance"],
                    "conveyance_nm": e["conveyance_nm"],
                    "label": e["label"],
                }
            )

        # --- 승강장 층 매칭 ---
        plf_rows = []
        for pl in platforms[key]:
            tokens = [t.strip() for t in re.split(r"[·,/]", pl["next_stin_nm"] or "") if t.strip()]
            lv = None
            for (line, direction), level in plat_floor.items():
                if direction in tokens or any(direction in t or t in direction for t in tokens):
                    if line in (st["ln_nm"], "", None) or line == st["ln_nm"]:
                        lv = level
                        break
            if lv is None:
                own = [v for (line, _), v in plat_floor.items() if line in (st["ln_nm"], "")]
                lv = own[0] if own else None
            plf_rows.append({**pl, "_level": lv})

        # --- 승강장 위 EV/ES/계단 위치 ---
        pos_by_plf = defaultdict(list)
        for g in gaps[key]:
            for col, nm in (
                ("near_elevator", "엘리베이터"),
                ("near_escalator", "에스컬레이터"),
                ("near_stair", "계단"),
            ):
                if g[col] == "Y":
                    item = {
                        "plf_no": g["plf_no"],
                        "car_ordr": g["car_ordr"],
                        "car_etrc_no": g["car_etrc_no"],
                        "car_label": f"{g['car_ordr']}-{g['car_etrc_no']}칸",
                        "facility_nm": nm,
                    }
                    pos_by_plf[g["plf_no"]].append(item)
                    out_positions.append({**base, **item})

        # --- 층 구성 ---
        levels: dict[int, dict] = {}

        def touch(level: int) -> dict:
            if level not in levels:
                levels[level] = {
                    "floor": floor_code(level),
                    "level": level,
                    "label": floor_label(level),
                    "nodes": [],
                    "platforms": [],
                }
            return levels[level]

        for fr in floors_raw[key]:
            lv = fr["stin_flor"] if fr["grnd_dv_cd"] == "1" else -int(fr["stin_flor"])
            touch(lv)

        for lv in concourse:
            touch(lv)["nodes"].append({"kind": "대합실", "label": "대합실", "detail": None})
        for lv in gates:
            touch(lv)["nodes"].append({"kind": "개찰구", "label": "표 내는 곳", "detail": None})

        for f in facilities[key]:
            lv = f["stin_flor"] if f["grnd_dv_cd"] == "1" else -int(f["stin_flor"])
            touch(lv)["nodes"].append(
                {
                    "kind": FACILITY_KIND.get(f["facility_cd"], f["facility_cd"]),
                    "label": f["facility_nm"],
                    "detail": f["detail_location"],
                }
            )

        exits: dict[str, bool] = {}
        for p in paths[key]:
            if str(p["mv_path_dv_cd"]) != "1":
                continue
            for m in EXIT_RE.finditer(p["start_point"] or ""):
                exits[m.group(1)] = True  # 접근가능 동선이 연결된 출입구
        for f in facilities[key]:
            for m in EXIT_RE.finditer(f["detail_location"] or ""):
                exits.setdefault(m.group(1), False)
        entry_level = 1
        for route in routes["entrance_to_platform"]:
            if route["floor_sequence"]:
                f = norm_floor(route["floor_sequence"][0])
                if f:
                    entry_level = f[1]
                break
        for num, accessible in sorted(exits.items(), key=lambda x: (len(x[0]), x[0])):
            touch(entry_level)["nodes"].append(
                {
                    "kind": "출입구",
                    "label": f"{num}번 출입구",
                    "detail": "교통약자 동선 연결" if accessible else None,
                }
            )

        for pl in plf_rows:
            lv = pl["_level"]
            if lv is None:
                continue
            node = {
                "plf_no": pl["plf_no"],
                "plf_tp_nm": pl["plf_tp_nm"],
                "toward": pl["next_stin_nm"],
                "screen_door": pl["screen_door"],
                "safety_footboard": pl["safety_footboard"],
                "platform_crossable": pl["platform_crossable"],
                "braille_block": pl["braille_block"],
                "braille_sign": pl["braille_sign"],
                "facility_positions": pos_by_plf.get(pl["plf_no"], []),
            }
            touch(lv)["platforms"].append(node)
            touch(lv)["nodes"].append(
                {
                    "kind": "승강장",
                    "label": f"{st['ln_nm']} 승강장 ({pl['next_stin_nm']} 방면)",
                    "detail": pl["plf_tp_nm"],
                }
            )

        # 타 노선 승강장(환승 대상)도 층에 얹는다
        for (line, direction), lv in plat_floor.items():
            if line and line != st["ln_nm"]:
                touch(lv)["nodes"].append(
                    {"kind": "환승승강장", "label": f"{line} 승강장 ({direction} 방면)", "detail": line}
                )

        floors = sorted(levels.values(), key=lambda x: -x["level"])
        for fl in floors:
            seen = set()
            uniq = []
            for nd in fl["nodes"]:
                k = (nd["kind"], nd["label"], nd["detail"])
                if k not in seen:
                    seen.add(k)
                    uniq.append(nd)
            fl["nodes"] = uniq
            for nd in uniq:
                out_nodes.append(
                    {
                        **base,
                        "floor": fl["floor"],
                        "level": fl["level"],
                        "floor_label": fl["label"],
                        "kind": nd["kind"],
                        "label": nd["label"],
                        "detail": nd["detail"],
                    }
                )

        layouts.append(
            {
                **base,
                "are_nm": st["are_nm"],
                "rail_opr_istt_cd": st["rail_opr_istt_cd"],
                "ln_cd": st["ln_cd"],
                "prpr_stin_cd": st["prpr_stin_cd"],
                "helper_tel": helpers.get(key),
                "prev_stin_nm": st["prev_stin_nm"],
                "next_stin_nm": st["next_stin_nm"],
                "floors": floors,
                "connections": [e for e in out_edges if e["station_id"] == sid],
                "routes": routes,
            }
        )

    # ---- 저장 ----
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    (OUT_DIR / "station_layout.json").write_text(
        json.dumps(layouts, ensure_ascii=False, indent=1), encoding="utf-8"
    )
    print(f"  output/kric_hc/station_layout.json  {len(layouts)}개 역")

    for name, rows in (
        ("floor_nodes", out_nodes),
        ("floor_edges", out_edges),
        ("platform_facility_positions", out_positions),
        ("route_guides", out_guides),
        ("transfer_guides", out_transfers),
    ):
        path = OUT_DIR / f"{name}.csv"
        if not rows:
            path.write_text("", encoding="utf-8-sig")
            continue
        cols: list[str] = []
        for r in rows:
            for c in r:
                if c not in cols:
                    cols.append(c)
        with path.open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
        print(f"  output/kric_hc/{name}.csv  {len(rows):,}행")

    con2 = sqlite3.connect(DB_PATH)
    for name, rows in (
        ("floor_nodes", out_nodes),
        ("floor_edges", out_edges),
        ("platform_facility_positions", out_positions),
        ("route_guides", out_guides),
        ("transfer_guides", out_transfers),
    ):
        con2.execute(f'DROP TABLE IF EXISTS "{name}"')
        if not rows:
            continue
        cols = []
        for r in rows:
            for c in r:
                if c not in cols:
                    cols.append(c)
        con2.execute('CREATE TABLE "%s" (%s)' % (name, ", ".join('"%s"' % c for c in cols)))
        con2.executemany(
            'INSERT INTO "%s" VALUES (%s)' % (name, ", ".join("?" * len(cols))),
            [[r.get(c) for c in cols] for r in rows],
        )
    con2.commit()
    con2.close()
    print(f"  data/kric_hc.sqlite  (파생 테이블 5종 갱신)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
