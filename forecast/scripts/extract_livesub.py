"""서버 citydata jsonl → LIVE_SUB_PPLTN / 인구 요약 CSV (stdout).

원본은 건드리지 않고 읽기만 한다. 필요한 필드만 뽑아 로컬로 스트리밍한다.
"""
import csv
import glob
import json
import sys

COLS = [
    "collected_at", "area_nm", "stn_cnt",
    "ppltn_base_time", "ppltn_min", "ppltn_max", "congest_lvl",
    "gton30_min", "gton30_max", "gtoff30_min", "gtoff30_max",
    "gton10_min", "gton10_max", "gtoff10_min", "gtoff10_max",
    "acml_gton_min", "acml_gton_max", "acml_gtoff_min", "acml_gtoff_max",
]


def num(d, k):
    v = (d or {}).get(k)
    try:
        return int(str(v).strip())
    except (TypeError, ValueError):
        return ""


w = csv.writer(sys.stdout)
w.writerow(COLS)

for fp in sorted(glob.glob("data/citydata/*.jsonl")):
    for line in open(fp, encoding="utf-8"):
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue
        cd = (r.get("raw_response") or {}).get("CITYDATA") or {}
        s = cd.get("LIVE_SUB_PPLTN")
        if isinstance(s, list):
            s = s[0] if s else None
        if not s:
            continue
        w.writerow([
            r.get("collected_at", "")[:19],
            r.get("area_nm", ""),
            num(s, "SUB_STN_CNT"),
            r.get("ppltn_base_time", ""),
            r.get("ppltn_min", ""), r.get("ppltn_max", ""), r.get("congest_lvl", ""),
            num(s, "SUB_30WTHN_GTON_PPLTN_MIN"), num(s, "SUB_30WTHN_GTON_PPLTN_MAX"),
            num(s, "SUB_30WTHN_GTOFF_PPLTN_MIN"), num(s, "SUB_30WTHN_GTOFF_PPLTN_MAX"),
            num(s, "SUB_10WTHN_GTON_PPLTN_MIN"), num(s, "SUB_10WTHN_GTON_PPLTN_MAX"),
            num(s, "SUB_10WTHN_GTOFF_PPLTN_MIN"), num(s, "SUB_10WTHN_GTOFF_PPLTN_MAX"),
            num(s, "SUB_ACML_GTON_PPLTN_MIN"), num(s, "SUB_ACML_GTON_PPLTN_MAX"),
            num(s, "SUB_ACML_GTOFF_PPLTN_MIN"), num(s, "SUB_ACML_GTOFF_PPLTN_MAX"),
        ])
