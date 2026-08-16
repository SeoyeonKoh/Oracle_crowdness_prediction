"""기능 1 (혼잡도 예보) 서비스 계층 — 기능 2·3과 공유하는 공통 API.

- 전체 호선 통합: 출발/도착역을 이름으로 지정, 환승 포함 최단시간 경로 계산
- 요일: 월~일 + 공휴일(daycat)
- 공통 출력 스키마: {line, station, hour, platform/concourse:{density,percent,level,baseline,badge}, causes}

'평소' 기준선 = los_summary_byday.csv(2023–25 요일/공휴일별 평균).
혼잡도 % = 밀도의 백분위수(평일 분포 기준). 4단계 경계 = 50/80/95%.
"""
from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

import pandas as pd

from src import config
from src.congestion import levels as congestion_level
from src.loading import loaders as io_load
from src.serving import causes

MIN_PER_STATION = 2.0     # 역간 표준 소요(가정)
TRANSFER_MIN = 4.0        # 환승 소요(가정)
BADGE_RATIO = 1.6
SERVICE_HOURS = list(range(5, 25))
ZONES = ("platform", "concourse")
WEEKDAYS = ["월", "화", "수", "목", "금"]


def _clean(v):
    if v is None or (isinstance(v, float) and math.isnan(v)):
        return None
    return round(float(v), 4)


@dataclass
class ForecastData:
    order: dict = field(default_factory=dict)          # line -> [station,...] 운행 순서(표시용)
    edges: dict = field(default_factory=dict)          # line -> [[a,b,min],...] 실제 인접(순환·지선 반영)
    adj: dict = field(default_factory=dict)            # (line,station) -> [(이웃역, 분),...]
    curve: dict = field(default_factory=dict)          # (line,station,daycat,hour) -> {zone:density}
    daily_mean: dict = field(default_factory=dict)     # (line,station,daycat,zone) -> mean density
    breaks: dict = field(default_factory=dict)
    pct_table: dict = field(default_factory=dict)      # zone -> [density@percentile 0..100]
    name_lines: dict = field(default_factory=dict)     # station -> [line,...]
    all_stations: list = field(default_factory=list)   # 정렬된 전체 역명
    seg_time: dict = field(default_factory=dict)       # (line,station) -> 전역→현역 분 (실측)
    xfer_time: dict = field(default_factory=dict)      # (station,from_line,to_line) -> 환승 분 (실측)


def load_summary() -> pd.DataFrame:
    """los_summary_byday.csv + 별칭 통일. 그래프 노드와 키를 맞추는 단일 진입점.

    별칭 통일 후 같은 역이 두 이름으로 실려 있던 행(4호선 당고개/불암산)이 한 키로
    겹치므로 셀 단위로 평균 낸다. 겹치지 않는 역은 값이 그대로다.
    """
    df = pd.read_csv(config.OUTPUT / "los_summary_byday.csv")
    df["station"] = df["station"].map(io_load.normalize_station)
    keys = ["line", "station", "daycat", "hour"]
    if df.duplicated(subset=keys).any():
        num = [c for c in df.columns if c not in keys and pd.api.types.is_numeric_dtype(df[c])]
        df = df.groupby(keys, as_index=False)[num].mean()
    return df


def load_data() -> ForecastData:
    summary = load_summary()
    # % 기준 분포는 평일(월~금)로 고정 → 요일 간 비교 가능
    wk = summary[summary["daycat"].isin(WEEKDAYS)].rename(columns={"daycat": "daytype"})
    wk["daytype"] = "평일"
    breaks = congestion_level.compute_breaks(wk)
    pct_table = congestion_level.build_pct_table(wk)

    order = io_load.load_line_order()
    edges = io_load.load_line_edges(order)
    adj: dict = {}
    for line, es in edges.items():
        for a, b, t in es:
            w = t if t else MIN_PER_STATION
            adj.setdefault((line, a), []).append((b, w))
            adj.setdefault((line, b), []).append((a, w))

    curve, daily = {}, {}
    for r in summary.itertuples(index=False):
        curve[(int(r.line), r.station, r.daycat, int(r.hour))] = {
            "platform": float(r.density_platform), "concourse": float(r.density_concourse)}
    dm = (summary.groupby(["line", "station", "daycat"])
          [["density_platform", "density_concourse"]].mean())
    for (line, station, daycat), row in dm.iterrows():
        daily[(int(line), station, daycat, "platform")] = float(row.density_platform)
        daily[(int(line), station, daycat, "concourse")] = float(row.density_concourse)

    name_lines: dict = {}
    for line, stns in order.items():
        for s in stns:
            name_lines.setdefault(s, []).append(line)
    all_stations = sorted(name_lines.keys())

    return ForecastData(order=order, edges=edges, adj=adj,
                        curve=curve, daily_mean=daily, breaks=breaks,
                        pct_table=pct_table, name_lines=name_lines, all_stations=all_stations,
                        seg_time=io_load.load_travel_times(),
                        xfer_time=io_load.load_transfer_times())


# ── 환승 그래프 & 경로 ─────────────────────────────────────────────
def _seg(data, line, station):
    """전 역→해당 역 소요(분). 실측 없으면 기본값."""
    t = data.seg_time.get((line, station))
    return t if t else MIN_PER_STATION


def _xfer(data, station, a, b):
    """환승 소요(분). 실측(양방향) 없으면 기본값."""
    t = data.xfer_time.get((station, a, b)) or data.xfer_time.get((station, b, a))
    return t if t else TRANSFER_MIN


def _neighbors(data: ForecastData, node):
    """(line,station) 인접 노드: 같은 호선 인접역(실측 소요) + 같은 역 타 호선(실측 환승).

    인접은 `data.adj`(명시적 간선)에서 온다. 배열 index±1로 구하면 2호선 순환 폐합이
    빠지고 지선이 분기점 대신 배열상 앞 역에 붙는다.
    """
    line, st = node
    out = [((line, nb), w, "move") for nb, w in data.adj.get((line, st), [])]
    for other in data.name_lines.get(st, []):
        if other != line:
            out.append(((other, st), _xfer(data, st, line, other), "transfer"))
    return out


def route(data: ForecastData, frm: str, to: str) -> list[dict]:
    """전체 호선 통합 최단시간 경로(환승 포함).

    반환: [{line, station, cum_min, transfer(bool)}], 실패 시 [].
    """
    if frm not in data.name_lines or to not in data.name_lines:
        return []
    starts = [(line, frm) for line in data.name_lines[frm]]
    dist = {s: 0.0 for s in starts}
    prev = {s: None for s in starts}
    pq = [(0.0, s) for s in starts]
    heapq.heapify(pq)
    goal = None
    while pq:
        d, node = heapq.heappop(pq)
        if d > dist.get(node, math.inf):
            continue
        if node[1] == to:
            goal = node
            break
        for nb, w, _ in _neighbors(data, node):
            nd = d + w
            if nd < dist.get(nb, math.inf):
                dist[nb] = nd
                prev[nb] = node
                heapq.heappush(pq, (nd, nb))
    if goal is None:
        return []
    # 경로 복원
    chain = []
    n = goal
    while n is not None:
        chain.append(n)
        n = prev[n]
    chain.reverse()
    legs = []
    for idx, (line, st) in enumerate(chain):
        transfer = idx > 0 and chain[idx - 1][1] == st and chain[idx - 1][0] != line
        legs.append({"line": line, "station": st,
                     "cum_min": round(dist[(line, st)], 1), "transfer": transfer})
    return legs


# ── 예보 ───────────────────────────────────────────────────────────
def _clamp_hour(h: int) -> int:
    return max(SERVICE_HOURS[0], min(SERVICE_HOURS[-1], h))


def forecast_at(data: ForecastData, line: int, station: str,
                daycat: str, hour: int, all_causes=None) -> dict:
    hour = _clamp_hour(hour)
    cell = data.curve.get((line, station, daycat, hour), {})
    out = {"line": line, "station": station, "hour": hour}
    for zone in ZONES:
        density = _clean(cell.get(zone))
        base = _clean(data.daily_mean.get((line, station, daycat, zone)))
        pct = (congestion_level.percent_of(density, data.pct_table[zone])
               if density is not None else None)
        level = congestion_level.level_from_percent(pct)
        badge = bool(density is not None and base and base > 0
                     and density >= base * BADGE_RATIO and level in ("주의", "혼잡"))
        out[zone] = {"density": density, "percent": pct,
                     "level": level, "baseline": base, "badge": badge}
    out["causes"] = causes.causes_for(station, line, all_causes)
    return out


def journey(data: ForecastData, frm: str, to: str,
            depart_hour: int, daycat: str) -> dict:
    """1-1 도착 시점 예보 — 환승 경로 각 역을 도착 시각 혼잡으로 조회."""
    legs_route = route(data, frm, to)
    all_causes = causes.load_causes()
    legs = []
    for leg in legs_route:
        arrive_hour = _clamp_hour(depart_hour + int(round(leg["cum_min"] / 60)))
        f = forecast_at(data, leg["line"], leg["station"], daycat, arrive_hour, all_causes)
        f["cum_min"] = leg["cum_min"]
        f["transfer"] = leg["transfer"]
        legs.append(f)
    return {"from": frm, "to": to, "depart_hour": depart_hour, "daycat": daycat, "legs": legs}


def recommend_departure(data: ForecastData, frm: str, to: str,
                        desired_hour: int, daycat: str, window: int = 1) -> dict:
    def score(h):
        j = journey(data, frm, to, _clamp_hour(h), daycat)
        vals = [leg["platform"]["density"] for leg in j["legs"]
                if leg["platform"]["density"] is not None]
        return max(vals) if vals else float("inf")
    options = [{"depart_hour": _clamp_hour(h), "score": round(score(h), 4)}
               for h in range(desired_hour - window, desired_hour + window + 1)]
    return {"desired_hour": desired_hour,
            "best": min(options, key=lambda o: o["score"]), "options": options}
