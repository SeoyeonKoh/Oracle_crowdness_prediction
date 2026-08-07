"""화면용 forecast.json export.

service 계층의 예보 결과를 (line→station→daytype→hour) 로 미리 계산해 JSON으로 저장.
화면(정적 HTML/JS)은 이 파일만 읽어 1-1~1-5를 구현한다. 로직 단일 출처 = service.

실행:  python -m src.export_forecast  →  output/forecast.json
"""
from __future__ import annotations

import json

import pandas as pd

from src import config
from src.serving import service, causes
from src.congestion import levels as congestion_level
from src.loading import loaders as io_load

# 밀도가 너무 작은 대합실 대신 승강장(platform)을 화면 기본 지표로 사용.


def build() -> dict:
    data = service.load_data()
    all_causes = causes.load_causes()

    lines = {str(ln): stns for ln, stns in sorted(data.order.items())}
    # 정원대비%(첨두 기반) 맵: (line,station,daycat,hour) -> (platform, concourse)
    abs_df = pd.read_csv(config.OUTPUT / "los_summary_byday.csv")
    _cl = lambda v: None if pd.isna(v) else round(float(v), 1)
    # [PATCH 4·5] 소스 컬럼이 abspct_* → crushpct_*(첨두÷유효면적, 만원 대비 %)로
    # 바뀌었다. JSON 스키마(pa/ca)는 그대로 두어 화면 변경 없이 동작한다.
    absmap = {(int(r.line), r.station, r.daycat, int(r.hour)):
              (_cl(r.crushpct_platform), _cl(r.crushpct_concourse))
              for r in abs_df.itertuples(index=False)}
    # per-cell: density(p,c)+badge(pb,cb)+정원대비%(pa,ca). 상대%는 화면이 pct_table로 계산.
    curve: dict = {}
    for (line, station, daycat, hour), cell in data.curve.items():
        f = service.forecast_at(data, line, station, daycat, hour, all_causes)
        p, c = f["platform"], f["concourse"]
        pa, ca = absmap.get((line, station, daycat, hour), (None, None))
        # [STEP 4] 절대 등급·만원대비%·배지를 명시 필드로 내보낸다.
        # badge_busier = 평소 대비 1.6배 이상 **그리고** 절대 등급이 주의 이상일 때만.
        #   (한산한 역이 조금 붐볐다고 경고를 띄우지 않기 위한 결합 조건)
        lv_p = congestion_level.level_abs_from_pct(pa)
        lv_c = congestion_level.level_abs_from_pct(ca, zone="concourse")
        (curve.setdefault(str(line), {})
              .setdefault(station, {})
              .setdefault(daycat, {})[str(hour)]) = {
            "p": p["density"], "pb": p["badge"], "pa": pa,
            "c": c["density"], "cb": c["badge"], "ca": ca,
            "level": lv_p,                 # 승강장 절대 4단계
            "level_c": lv_c,               # 대합실 절대 4단계
            # crush_pct(만원 대비 %)는 pa/ca 와 **완전히 같은 값**이라 중복 export하지
            # 않는다(파일이 4MB→9.5MB로 불어난다). pa/ca 가 곧 crush_pct 다.
            "badge_busier": bool(p["badge"]) and lv_p in ("주의", "혼잡"),
            "badge_busier_c": bool(c["badge"]) and lv_c in ("주의", "혼잡"),
        }

    return {
        "meta": {
            "source": "los_summary_byday.csv (2023–2025 요일/공휴일별 평균)",
            "min_per_station": service.MIN_PER_STATION,
            "transfer_min": service.TRANSFER_MIN,
            "note": "평소 기준선 = 과거 평균. 공휴일은 별도 카테고리(≈일요일).",
        },
        "days": ["월", "화", "수", "목", "금", "토", "일", "공휴일"],
        "levels": ["여유", "보통", "주의", "혼잡"],
        # [PATCH 5] 절대 등급 경계를 '데이터로' 내보낸다 — 화면에 하드코딩하지 않는다.
        # crushpct(pa/ca) = 밀도÷CRUSH×100 이므로 경계도 만원 대비 %로 표현된다.
        # 유효면적·컷을 튜닝해도 이 숫자만 바뀌고 스키마는 그대로다.
        "absBands": {p: congestion_level.abs_break_pcts(p) for p in ("일반", "휠체어")},
        "absMeta": {
            "crush": config.CRUSH_DENSITY,
            "effArea": config.EFFECTIVE_AREA_RATIO,
            "note": "pa/ca = 첨두밀도 ÷ 만원밀도 × 100. 경계는 만원 대비 %.",
        },
        "pctBands": congestion_level.LEVEL_PCT_BANDS,   # [50,80,95] — 배지 근거용
        "pctTable": data.pct_table,                     # zone -> 밀도@백분위 0..100
        "lines": lines,                                 # line -> [station,...] 역번호순
        "allStations": data.all_stations,               # 전체 역명(검색용)
        "segMin": _seg_min(data),                        # line -> station -> 전역→현역 분(실측)
        "xferMin": _xfer_min(data),                      # station -> {"a-b": 환승 분(실측)}
        "trainPct": _train_pct(),                         # line -> station -> 요일유형 -> hour -> 열차혼잡%(재차/정원)
        "curve": curve,
        "causes": all_causes,
    }


def _train_pct() -> dict:
    """OA-12928 열차 혼잡도(재차/정원 %) → line→station→요일유형→slotmin(30분,분단위)→%."""
    tc = io_load.load_train_congestion()
    tc["daytype"] = tc["daytype"].astype(str).str.strip()
    g = tc.groupby(["daytype", "line", "station", "slotmin"])["pct"].mean().reset_index()
    g = g.dropna(subset=["pct"])   # 빈 슬롯(NaN) 제외 → JSON 유효
    out: dict = {}
    for r in g.itertuples(index=False):
        (out.setdefault(str(int(r.line)), {})
            .setdefault(r.station, {})
            .setdefault(r.daytype, {})[str(int(r.slotmin))]) = round(float(r.pct), 1)
    return out


def _seg_min(data) -> dict:
    out: dict = {}
    for (line, station), m in data.seg_time.items():
        if m is not None:
            out.setdefault(str(line), {})[station] = round(m, 2)
    return out


def _xfer_min(data) -> dict:
    out: dict = {}
    for (station, a, b), m in data.xfer_time.items():
        out.setdefault(station, {})[f"{a}-{b}"] = round(m, 2)
    return out


def main() -> None:
    config.OUTPUT.mkdir(exist_ok=True)
    payload = build()
    fp = config.OUTPUT / "forecast.json"
    fp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    n_cells = sum(len(h) for l in payload["curve"].values()
                  for s in l.values() for h in s.values())
    size_kb = fp.stat().st_size / 1024
    print(f"forecast.json 저장: {fp}")
    print(f"  호선 {len(payload['lines'])} · 셀 {n_cells:,} · {size_kb:.0f} KB")


if __name__ == "__main__":
    main()
