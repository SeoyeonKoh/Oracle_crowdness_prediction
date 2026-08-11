#!/usr/bin/env python3
"""KRIC 철도역 편의정보(hc.kric.go.kr) 크롤러.

승강장정보 / 편의시설정보 / 이동경로(동선)정보를 이미지 없이 정형 데이터로 수집한다.
원본 JSON은 data/kric_hc_raw/ 에 캐시하고, 평탄화 결과는 output/*.csv 와
data/kric_hc.sqlite 로 저장한다.

usage:
    python src/crawl_kric_hc.py              # 전체 수집 (캐시 있으면 재사용)
    python src/crawl_kric_hc.py --areas 01   # 특정 지역만
    python src/crawl_kric_hc.py --build-only # 네트워크 없이 캐시로 CSV/DB만 재생성
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sqlite3
import ssl
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "kric_hc_raw"
OUT_DIR = ROOT / "output"
DB_PATH = ROOT / "data" / "kric_hc.sqlite"

BASE = "https://hc.kric.go.kr/hc/visual/handicapped/"
HEADERS = {
    "Referer": "https://hc.kric.go.kr/hc/index.jsp",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/122.0 Safari/537.36",
    "X-Requested-With": "XMLHttpRequest",
    "Accept": "application/json, text/javascript, */*; q=0.01",
}

AREAS = {
    "01": "수도권",
    "02": "부산",
    "03": "대구",
    "04": "광주",
    "05": "대전",
}

# ---- 코드 → 라벨 매핑 (사이트 렌더링 스크립트 기준) -------------------------
GRND_DV = {"1": "지상", "2": "지하"}
SF_DST = {"1": "0~10", "2": "10초과~15이하", "3": "15초과"}
FACILITY = {
    "EV": "일반승강기",
    "WCLF": "휠체어리프트",
    "ELEC": "전동휠체어충전설비",
    "TOLT": "화장실",
    "INFO": "고객센터",
    "LARM": "수유실",
    "ES": "에스컬레이터",
}
TRFC_WEAK = {"1": "일반", "2": "장애인"}
ML_FML = {"1": "남", "2": "여", "3": "공용"}
MV_PATH_DV = {"1": "출입구-승강장", "2": "승강장-출입구", "3": "환승"}

_ssl_ctx = ssl.create_default_context()
_ssl_ctx.check_hostname = False
_ssl_ctx.verify_mode = ssl.CERT_NONE

_print_lock = threading.Lock()


def log(msg: str) -> None:
    with _print_lock:
        print(msg, flush=True)


def fetch(endpoint: str, params: dict, retries: int = 4) -> dict:
    url = BASE + endpoint + "?" + urllib.parse.urlencode(params)
    last = None
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers=HEADERS)
            with urllib.request.urlopen(req, context=_ssl_ctx, timeout=40) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - 네트워크/파싱 모두 재시도 대상
            last = exc
            time.sleep(1.2 * (attempt + 1))
    raise RuntimeError(f"fetch failed: {endpoint} {params}: {last}")


def cached(path: Path, producer) -> dict:
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            path.unlink()
    data = producer()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    return data


# ---- 1단계: 지역 → 노선 → 역 ------------------------------------------------
def collect_stations(area_codes: list[str], line_codes: list[str] | None = None) -> list[dict]:
    stations: list[dict] = []
    seen: set[tuple] = set()
    line_filter = set(line_codes) if line_codes else None

    for are_cd in area_codes:
        area_nm = AREAS.get(are_cd, are_cd)
        area_data = cached(
            RAW_DIR / "index" / f"area_{are_cd}.json",
            lambda a=are_cd: fetch("selectAreCdClickInfo.do", {"paramAreCd": a}),
        )
        lines = area_data.get("resultLnList") or []
        if line_filter is not None:
            lines = [l for l in lines if l["lnCd"] in line_filter]
        log(f"[{area_nm}] 노선 {len(lines)}개: {', '.join(l['lnNm'] for l in lines)}")

        for line in lines:
            ln_cd, ln_nm = line["lnCd"], line["lnNm"]
            st_data = cached(
                RAW_DIR / "index" / f"line_{are_cd}_{urllib.parse.quote(ln_cd, safe='')}.json",
                lambda a=are_cd, l=ln_cd: fetch(
                    "selectLegendClickInfo.do", {"paramAreCd": a, "paramLnCd": l}
                ),
            )
            for order, st in enumerate(st_data.get("resultStinList") or [], start=1):
                key = (st["railOprIsttCd"], st["lnCd"], st["prprStinCd"])
                if key in seen:
                    continue
                seen.add(key)
                stations.append(
                    {
                        "areCd": are_cd,
                        "areNm": area_nm,
                        "lnCd": ln_cd,
                        "lnNm": ln_nm,
                        "railOprIsttCd": st["railOprIsttCd"],
                        "prprStinCd": st["prprStinCd"],
                        "stinNm": st["stinNm"],
                        "lineOrder": order,
                    }
                )
        log(f"[{area_nm}] 누적 역 {len(stations)}개")
    return stations


# ---- 2단계: 역별 3개 탭 + 경로 상세 ------------------------------------------
def station_key(st: dict) -> str:
    return f"{st['areCd']}_{st['railOprIsttCd']}_{st['lnCd']}_{st['prprStinCd']}"


def crawl_station(st: dict) -> None:
    key = station_key(st)
    p = {
        "paramAreCd": st["areCd"],
        "paramRailOprIsttCd": st["railOprIsttCd"],
        "paramLnCd": st["lnCd"],
        "paramPrprStinCd": st["prprStinCd"],
    }
    cached(RAW_DIR / "plf" / f"{key}.json", lambda: fetch("selectStinPlfInfo.do", p))
    cached(RAW_DIR / "cnv" / f"{key}.json", lambda: fetch("selectStinCnvInfo.do", p))
    mp = cached(RAW_DIR / "path" / f"{key}.json", lambda: fetch("selectMovePath.do", p))

    paths = (mp.get("resultMovePathExit") or []) + (mp.get("resultMovePathChtn") or [])
    for entry in paths:
        dp = dict(p)
        dp["paramRailOprIsttCd"] = entry["railOprIsttCd"]
        dp["paramLnCd"] = entry["lnCd"]
        dp["paramPrprStinCd"] = entry["prprStinCd"]
        dp["paramMvPathDvCd"] = entry["mvPathDvCd"]
        dp["paramMgNo"] = entry["mgNo"]
        name = f"{key}_{entry['mvPathDvCd']}_{entry['mgNo']}.json"
        cached(
            RAW_DIR / "path_detail" / name,
            lambda d=dp: fetch("selectMovePathDetail.do", d),
        )


def crawl_all(stations: list[dict], workers: int) -> None:
    done = [0]

    def task(st: dict) -> None:
        try:
            crawl_station(st)
        except Exception as exc:  # noqa: BLE001
            log(f"  !! 실패 {station_key(st)} {st['stinNm']}: {exc}")
        finally:
            done[0] += 1
            if done[0] % 25 == 0 or done[0] == len(stations):
                log(f"  진행 {done[0]}/{len(stations)}")

    with ThreadPoolExecutor(max_workers=workers) as pool:
        list(pool.map(task, stations))


# ---- 3단계: 평탄화 ------------------------------------------------------------
def load(path: Path) -> dict | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def build_tables(stations: list[dict]) -> dict[str, list[dict]]:
    t: dict[str, list[dict]] = {
        "stations": [],
        "platforms": [],
        "platform_gaps": [],
        "platform_cars": [],
        "station_floors": [],
        "helpers": [],
        "facilities": [],
        "move_paths": [],
        "move_path_steps": [],
    }

    for st in stations:
        key = station_key(st)
        base = {
            "are_cd": st["areCd"],
            "are_nm": st["areNm"],
            "rail_opr_istt_cd": st["railOprIsttCd"],
            "ln_cd": st["lnCd"],
            "ln_nm": st["lnNm"],
            "prpr_stin_cd": st["prprStinCd"],
            "stin_nm": st["stinNm"],
        }

        # --- 승강장 ---
        plf = load(RAW_DIR / "plf" / f"{key}.json") or {}
        nm_list = plf.get("resultStinNmList") or []
        head = nm_list[0] if nm_list else {}
        t["stations"].append(
            {
                **base,
                "line_order": st["lineOrder"],
                "stin_cons_ordr": head.get("stinConsOrdr"),
                "prev_rail_opr_istt_cd": head.get("prevRailOprIsttCd"),
                "prev_ln_cd": head.get("prevLnCd"),
                "prev_prpr_stin_cd": head.get("prevPrprStinCd"),
                "prev_stin_nm": head.get("prevStinNm"),
                "next_rail_opr_istt_cd": head.get("nextRailOprIsttCd"),
                "next_ln_cd": head.get("nextLnCd"),
                "next_prpr_stin_cd": head.get("nextPrprStinCd"),
                "next_stin_nm": head.get("nextStinNm"),
                "has_platform_info": bool(plf.get("resultStinPlfInfoList")),
                "has_facility_info": None,  # 아래에서 채움
                "has_move_path_info": None,
            }
        )
        station_row = t["stations"][-1]

        for row in plf.get("resultStinPlfInfoList") or []:
            t["platforms"].append(
                {
                    **base,
                    "plf_no": row.get("plfNo"),
                    "plf_tp_nm": row.get("plfTpNm"),
                    "run_dir_tmn_stin_nm": row.get("runDirTmnStinNm"),
                    "next_stin_nm": row.get("nextStinNm"),
                    "screen_door": row.get("scrCharExt"),
                    "safety_footboard": row.get("sfFotExt"),
                    "platform_crossable": row.get("plfCplFlg"),
                    "braille_block": row.get("brllBlc"),
                    "braille_sign": row.get("brllShow"),
                }
            )

        for row in plf.get("resultStinPlfCarInfoList") or []:
            t["platform_cars"].append(
                {
                    **base,
                    "plf_no": row.get("plfNo"),
                    "car_ordr": row.get("carOrdr"),
                    "door_cnt": row.get("cnt"),
                }
            )

        for row in plf.get("resultStinPlfDstList") or []:
            sf = row.get("sfDst")
            t["platform_gaps"].append(
                {
                    **base,
                    "plf_no": row.get("plfNo"),
                    "car_ordr": row.get("carOrdr"),
                    "car_etrc_no": row.get("carEtrcNo"),
                    "sf_dst_cd": sf,
                    "sf_dst_range_cm": SF_DST.get(str(sf)) if sf is not None else None,
                    "near_elevator": row.get("ev"),
                    "near_escalator": row.get("es"),
                    "near_stair": row.get("sa"),
                }
            )

        # --- 편의시설 ---
        cnv = load(RAW_DIR / "cnv" / f"{key}.json") or {}
        station_row["has_facility_info"] = bool(cnv.get("resultStinCnvInfoList"))

        for row in cnv.get("resultStinFlorInfoList") or []:
            g = str(row.get("grndDvCd"))
            t["station_floors"].append(
                {
                    **base,
                    "grnd_dv_cd": g,
                    "grnd_dv_nm": GRND_DV.get(g),
                    "stin_flor": row.get("stinFlor"),
                    "floor_label": f"{GRND_DV.get(g, '')} {row.get('stinFlor')}층".strip(),
                    "seq": row.get("rn"),
                }
            )

        for row in cnv.get("resultHandicappedHelper") or []:
            t["helpers"].append({**base, "tel_no": row.get("telNo")})

        for row in cnv.get("resultStinCnvInfoList") or []:
            g = str(row.get("grndDvCd"))
            gubun = row.get("gubun")
            weak = row.get("trfcWeakDvCd")
            sex = row.get("mlFmlDvCd")
            name = FACILITY.get(gubun, gubun)
            if gubun == "TOLT":
                sex_nm = ML_FML.get(str(sex))
                name = f"{TRFC_WEAK.get(str(weak), '')}화장실"
                if sex_nm:
                    name += f"({sex_nm})"
            t["facilities"].append(
                {
                    **base,
                    "facility_cd": gubun,
                    "facility_nm": name,
                    "grnd_dv_cd": g,
                    "grnd_dv_nm": GRND_DV.get(g),
                    "stin_flor": row.get("stinFlor"),
                    "floor_label": f"{GRND_DV.get(g, '')} {row.get('stinFlor')}층".strip(),
                    "detail_location": row.get("dtlLoc"),
                    "trfc_weak_dv_cd": weak,
                    "trfc_weak_dv_nm": TRFC_WEAK.get(str(weak)) if weak else None,
                    "ml_fml_dv_cd": sex,
                    "ml_fml_dv_nm": ML_FML.get(str(sex)) if sex else None,
                }
            )

        # --- 이동동선 ---
        mp = load(RAW_DIR / "path" / f"{key}.json") or {}
        paths = (mp.get("resultMovePathExit") or []) + (mp.get("resultMovePathChtn") or [])
        station_row["has_move_path_info"] = bool(paths)

        for row in paths:
            dv = str(row.get("mvPathDvCd"))
            mg = row.get("mgNo")
            t["move_paths"].append(
                {
                    **base,
                    "mv_path_dv_cd": dv,
                    "mv_path_dv_nm": MV_PATH_DV.get(dv, dv),
                    "mg_no": mg,
                    "start_point": row.get("stMovePath"),
                    "end_point": row.get("edMovePath"),
                    "path_label": f"{row.get('stMovePath')} → {row.get('edMovePath')}",
                }
            )
            detail = load(RAW_DIR / "path_detail" / f"{key}_{dv}_{mg}.json") or {}
            for seq, step in enumerate(detail.get("resultMovePathDetail") or [], start=1):
                t["move_path_steps"].append(
                    {
                        **base,
                        "mv_path_dv_cd": dv,
                        "mv_path_dv_nm": MV_PATH_DV.get(dv, dv),
                        "mg_no": mg,
                        "step_no": seq,
                        "step_text": step.get("mvContDtl"),
                    }
                )

    return t


def write_csv(tables: dict[str, list[dict]]) -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for name, rows in tables.items():
        path = OUT_DIR / f"{name}.csv"
        if not rows:
            path.write_text("", encoding="utf-8-sig")
            continue
        cols: list[str] = []
        for row in rows:
            for c in row:
                if c not in cols:
                    cols.append(c)
        with path.open("w", newline="", encoding="utf-8-sig") as fh:
            w = csv.DictWriter(fh, fieldnames=cols)
            w.writeheader()
            w.writerows(rows)
        log(f"  {path.relative_to(ROOT)}  {len(rows):,}행")


def write_sqlite(tables: dict[str, list[dict]]) -> None:
    if DB_PATH.exists():
        DB_PATH.unlink()
    con = sqlite3.connect(DB_PATH)
    for name, rows in tables.items():
        if not rows:
            continue
        cols: list[str] = []
        for row in rows:
            for c in row:
                if c not in cols:
                    cols.append(c)
        col_sql = ", ".join('"%s"' % c for c in cols)
        con.execute('CREATE TABLE "%s" (%s)' % (name, col_sql))
        con.executemany(
            f'INSERT INTO "{name}" VALUES ({", ".join("?" * len(cols))})',
            [[row.get(c) for c in cols] for row in rows],
        )
    for name in ("stations", "platforms", "facilities", "move_paths", "move_path_steps", "platform_gaps"):
        try:
            con.execute(
                f'CREATE INDEX "idx_{name}_stin" ON "{name}"(rail_opr_istt_cd, ln_cd, prpr_stin_cd)'
            )
        except sqlite3.OperationalError:
            pass
    con.commit()
    con.close()
    log(f"  {DB_PATH.relative_to(ROOT)}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--areas", nargs="*", default=["01"], help="지역코드 (기본 01 수도권)")
    ap.add_argument(
        "--lines",
        nargs="*",
        default=[str(i) for i in range(1, 10)],
        help="노선코드 (기본 1~9호선). 'all' 지정 시 전 노선",
    )
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--build-only", action="store_true", help="캐시만으로 CSV/DB 생성")
    args = ap.parse_args()

    RAW_DIR.mkdir(parents=True, exist_ok=True)
    index_path = RAW_DIR / "stations_index.json"

    if args.build_only and index_path.exists():
        stations = json.loads(index_path.read_text(encoding="utf-8"))
    else:
        log("== 1) 지역/노선/역 목록 수집 ==")
        line_codes = None if "all" in args.lines else args.lines
        stations = collect_stations(args.areas, line_codes)
        index_path.write_text(json.dumps(stations, ensure_ascii=False), encoding="utf-8")
    log(f"대상 역 {len(stations):,}개")

    if not args.build_only:
        log("== 2) 역별 승강장/편의시설/이동동선 수집 ==")
        crawl_all(stations, args.workers)

    log("== 3) 평탄화 및 저장 ==")
    tables = build_tables(stations)
    write_csv(tables)
    write_sqlite(tables)

    log("== 요약 ==")
    for name, rows in tables.items():
        log(f"  {name:<18} {len(rows):>8,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
