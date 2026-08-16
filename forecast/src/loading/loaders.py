"""데이터 로더 — 인코딩·스키마 차이를 흡수해 표준 형태로 반환.

OA-12921(승하차)은 파일마다 컬럼명이 두 가지다:
  변형 A: 수송일자 / 승하차구분 / '06-07시간대' …
  변형 B: 날짜     / 구분       / '06시-07시'   …
두 변형을 표준 컬럼으로 통일하고, 시간대 라벨을 '시작 시(hour)' 정수로 바꾼다.
"""
from __future__ import annotations

import re
from pathlib import Path

import pandas as pd

from src import config


def _read_csv_flex(fp, encodings=("utf-8-sig", "cp949", "utf-8"), **kw) -> pd.DataFrame:
    """여러 인코딩을 순서대로 시도해 CSV 로드(파일별 인코딩 혼재 대응)."""
    last = None
    for enc in encodings:
        try:
            return pd.read_csv(fp, encoding=enc, **kw)
        except UnicodeDecodeError as e:
            last = e
    raise last


# ── 역명 정규화 ────────────────────────────────────────────────────────────
# 같은 역이 자료마다 다른 이름으로 실려 노드가 갈라지는 경우를 하나로 모은다.
# 괄호 제거만으로는 해결되지 않는다(4호선 '총신대입구(이수)' → '총신대입구' vs
# 7호선 '이수'). 갈라진 채로 두면 그 역의 환승 간선이 통째로 사라진다.
STATION_ALIASES = {
    "총신대입구": "이수",     # 4호선 표기 → 7호선과 동일 역
    "당고개": "불암산",       # 2024 개명
    "신내역": "신내",         # OA-12034 표기 흔들림
}


def normalize_station(name: str) -> str:
    """'왕십리(성동구청)' → '왕십리'. 괄호 부기·공백 제거 후 별칭 통일."""
    s = str(name)
    s = re.sub(r"\(.*?\)", "", s)   # 괄호 및 내부 텍스트 제거
    s = re.sub(r"\s+", "", s)       # 공백 제거
    s = s.strip()
    return STATION_ALIASES.get(s, s)


def line_number(line: str) -> "int | None":
    """'2호선' → 2. 숫자 추출 실패 시 None."""
    m = re.search(r"(\d+)", str(line))
    return int(m.group(1)) if m else None


# ── 시간대 라벨 → 시작 시(hour) 정수 ────────────────────────────────────────
def _timelabel_to_hour(label: str) -> "int | None":
    """'06-07시간대'/'06시-07시' → 6, '06시이전' → 5, '24시이후' → 24."""
    if "이전" in label:
        return 5          # 06시 이전 버킷
    if "이후" in label:
        return 24         # 24시 이후(익일 새벽) 버킷
    m = re.search(r"(\d{1,2})", label)
    return int(m.group(1)) if m else None


# 표준 컬럼명 매핑(변형 B → 변형 A)
_COL_ALIASES = {"날짜": "수송일자", "구분": "승하차구분"}


def load_boarding(files: "list[Path] | None" = None) -> pd.DataFrame:
    """OA-12921 승하차 → long 표준 DF.

    반환 컬럼: date(datetime), line(int), station_no, station_raw,
              station(정규화), io('승차'/'하차'), hour(int), cnt(float)
    (수송일자, 호선, 역번호, 승하차구분) 기준 중복 제거.
    """
    files = files or config.BOARDING_FILES
    frames = []
    for fp in files:
        raw = pd.read_csv(fp, encoding="cp949")
        raw = raw.rename(columns={k: v for k, v in _COL_ALIASES.items() if k in raw.columns})
        # 시간대 컬럼 식별(‘시’ 포함, id 컬럼 제외)
        id_cols = ["수송일자", "호선", "역번호", "역명", "승하차구분"]
        time_cols = [c for c in raw.columns if "시" in c and c not in id_cols]
        raw = raw.dropna(subset=["수송일자", "호선", "역명", "승하차구분"])
        long = raw.melt(
            id_vars=id_cols, value_vars=time_cols,
            var_name="timelabel", value_name="cnt",
        )
        frames.append(long)

    df = pd.concat(frames, ignore_index=True)
    # 중복 제거(부분·전체 파일 겹침 방지)
    df = df.drop_duplicates(subset=["수송일자", "호선", "역번호", "승하차구분", "timelabel"])

    df["date"] = pd.to_datetime(df["수송일자"], errors="coerce")
    df["line"] = df["호선"].map(line_number)
    df["hour"] = df["timelabel"].map(_timelabel_to_hour)
    df["station_raw"] = df["역명"]
    df["station"] = df["역명"].map(normalize_station)
    df["io"] = df["승하차구분"].astype(str).str.strip()
    df["cnt"] = pd.to_numeric(df["cnt"], errors="coerce").fillna(0.0)
    df = df.rename(columns={"역번호": "station_no"})

    df = df.dropna(subset=["date", "line", "hour"])
    df["line"] = df["line"].astype(int)
    df["hour"] = df["hour"].astype(int)
    keep = ["date", "line", "station_no", "station_raw", "station", "io", "hour", "cnt"]
    return df[keep].reset_index(drop=True)


def load_station_area(fp: "Path | None" = None) -> pd.DataFrame:
    """역사면적 → line, station, concourse_area(대합실), platform_area(승강장)."""
    fp = fp or config.STATION_AREA_FILE
    a = pd.read_csv(fp, encoding="cp949")
    a = a.rename(columns={
        "호선": "line", "역명": "station_raw",
        "대합실면적": "concourse_area", "승강장면적": "platform_area",
    })
    a["line"] = pd.to_numeric(a["line"], errors="coerce")
    a["station"] = a["station_raw"].map(normalize_station)
    for c in ["concourse_area", "platform_area"]:
        a[c] = pd.to_numeric(a[c], errors="coerce")
    a = a.dropna(subset=["line", "station"])
    a["line"] = a["line"].astype(int)
    # (line, station) 중복 시 면적 평균
    a = (a.groupby(["line", "station"], as_index=False)
           [["concourse_area", "platform_area"]].mean())
    return a


def _mmss_to_min(s) -> "float | None":
    """'MM:SS' → 분(float). 파싱 실패 시 None."""
    try:
        parts = str(s).strip().split(":")
        if len(parts) == 2:
            return int(parts[0]) + int(parts[1]) / 60.0
    except Exception:
        pass
    return None


def load_travel_times() -> dict:
    """OA-12034 역간거리 → {(line, station): 전 역→현 역 소요(분)}. 첫 역은 0."""
    fp = next((config.INPUT).glob("OA-12034*/*.csv"), None)
    if fp is None:
        return {}
    df = pd.read_csv(fp, encoding="cp949")
    out = {}
    for r in df.itertuples(index=False):
        line = line_number(r.호선)
        if line is None:
            continue
        out[(int(line), normalize_station(r.역명))] = _mmss_to_min(getattr(r, "소요시간"))
    return out


def load_transfer_times() -> dict:
    """OA-13290 환승역거리 → {(station, from_line, to_line): 환승 소요(분)} (1~8호선만)."""
    fp = next((config.INPUT).glob("OA-13290*/*.csv"), None)
    if fp is None:
        return {}
    df = pd.read_csv(fp, encoding="cp949")
    out = {}
    for r in df.itertuples(index=False):
        fl = line_number(r.호선)
        tl = line_number(r.환승노선)
        if fl is None or tl is None:
            continue
        t = _mmss_to_min(getattr(r, "환승소요시간"))
        if t is not None:
            out[(normalize_station(r.환승역명), int(fl), int(tl))] = t
    return out


def load_transfer_volume() -> dict:
    """OA-12033 환승인원 → {(station, 요일유형): 일평균 환승인원}. 요일유형=평일/토요일/일요일."""
    fp = next(config.INPUT.glob("OA-12033*/*.xlsx"), None) or next(config.INPUT.glob("OA-12033*/*.csv"), None)
    if fp is None:
        return {}
    df = pd.read_excel(fp) if str(fp).lower().endswith("xlsx") else _read_csv_flex(fp)
    out = {}
    for _, row in df.iterrows():
        st = normalize_station(row.get("출발역명", ""))
        for col in ("평일", "토요일", "일요일"):
            if col in df.columns and pd.notna(row[col]):
                out[(st, col)] = float(row[col])
    return out


def load_station_master(fp: "Path | None" = None) -> pd.DataFrame:
    """역 마스터(호선·역번호·역명) — 경로 순서용.

    승하차 원자료는 환승역을 **한 호선에만** 기재하는 해가 있어, 한 파일만 읽으면
    반대편 호선 노드가 통째로 사라진다(예: 2025년 파일에 3호선 충무로·6호선 연신내
    없음 → 3↔4·3↔6 환승 간선 소실). 전 연도 union으로 복원한다.
    """
    fps = [fp] if fp is not None else config.BOARDING_FILES
    frames = []
    for f in fps:
        raw = pd.read_csv(f, encoding="cp949", usecols=["호선", "역번호", "역명"])
        frames.append(raw.dropna(subset=["호선", "역번호", "역명"]).drop_duplicates())
    raw = pd.concat(frames, ignore_index=True).drop_duplicates()
    raw["line"] = raw["호선"].map(line_number)
    raw["station_no"] = pd.to_numeric(raw["역번호"], errors="coerce")
    raw["station"] = raw["역명"].map(normalize_station)
    raw = raw.dropna(subset=["line", "station_no"])
    raw["line"] = raw["line"].astype(int)
    raw["station_no"] = raw["station_no"].astype(int)
    return (raw[["line", "station_no", "station"]]
            .drop_duplicates(subset=["line", "station"])
            .sort_values(["line", "station_no"])
            .reset_index(drop=True))


def load_line_order(master: "pd.DataFrame | None" = None) -> dict:
    """호선 → 역 배열(운행 순서). 경로 그래프의 인접 관계가 여기서 나온다.

    두 자료를 합친다.
    - OA-12034(역간거리) 행 순서 = 실제 운행 순서. 2호선 지선(성수·신정)이
      올바르게 이어지고 까치산이 포함된다. 승하차 역번호는 지선을 평면 번호로
      매겨 신정네거리 다음에 용두가 오는 등 순서가 어긋난다.
    - 승하차 마스터 = 커버리지. 7호선 인천 연장·뚝섬유원지처럼 OA-12034에
      없는 역을 채운다.

    OA-12034에 없는 역은 역번호상 **직전 역 뒤에** 끼워 넣어 중간역도 제자리를
    찾게 한다(끝에 붙이면 뚝섬유원지가 종점 뒤로 간다).
    """
    master = load_station_master() if master is None else master
    fp = next(config.INPUT.glob("OA-12034*/*.csv"), None)
    base: dict = {}
    if fp is not None:
        df = pd.read_csv(fp, encoding="cp949")
        for r in df.itertuples(index=False):
            line = line_number(r.호선)
            if line is None:
                continue
            seq = base.setdefault(int(line), [])
            st = normalize_station(r.역명)
            if st not in seq:
                seq.append(st)

    out: dict = {}
    for line, g in master.groupby("line"):
        by_no = list(g.sort_values("station_no")["station"])
        seq = list(base.get(int(line), []))
        if not seq:                       # OA-12034에 없는 호선 → 역번호 순서 그대로
            out[int(line)] = by_no
            continue
        for i, st in enumerate(by_no):
            if st in seq:
                continue
            # 역번호상 앞쪽에서 seq에 이미 있는 가장 가까운 역 뒤에 삽입
            anchor = next((p for p in reversed(by_no[:i]) if p in seq), None)
            seq.insert(seq.index(anchor) + 1 if anchor else 0, st)
        out[int(line)] = seq
    return out


# 배열 순서만으로는 표현할 수 없는 노선 구조(순환선·지선)를 보정한다.
# add = 배열상 떨어져 있으나 실제로 이어진 구간, drop = 배열상 이웃이나 실제로는 끊긴 구간.
# add는 (앞 역, 뒤 역) 순서로 적는다 — 간선 소요시간은 '뒤 역'의 역간 소요를 쓴다.
LINE_EDGE_FIXES = {
    2: {  # 순환선 + 성수지선(용답~신설동) + 신정지선(도림천~까치산)
        "add": [("충정로", "시청"),      # 순환 폐합
                ("성수", "용답"),        # 성수지선 분기점
                ("신도림", "도림천")],   # 신정지선 분기점
        "drop": [("충정로", "용답"),     # 본선 끝 ↔ 성수지선 머리 (배열이 만든 가짜 간선)
                 ("신설동", "도림천")],  # 성수지선 끝 ↔ 신정지선 머리
    },
    5: {  # 마천지선(둔촌동~마천)은 하남 방면이 아니라 강동에서 갈라진다
        "add": [("강동", "둔촌동")],
        "drop": [("하남검단산", "둔촌동")],
    },
    6: {  # 응암순환: 응암→역촌→…→구산→응암 을 돈 뒤 응암에서 새절로 나간다
        "add": [("구산", "응암"), ("응암", "새절")],
        "drop": [("구산", "새절")],
    },
}


def load_line_edges(order: "dict | None" = None, seg: "dict | None" = None) -> dict:
    """호선 → [[역A, 역B, 소요분], ...] 실제 인접 간선.

    `load_line_order()`의 배열은 역 목록·표시 순서로는 맞지만 인접 관계로 쓰면
    2·5·6호선에서 틀린다. 순환선의 폐합 구간이 빠지고, 지선이 본선 분기점이 아니라
    배열상 앞 역에 붙기 때문이다. 여기서 그 차이를 명시적으로 메운다.
    """
    order = load_line_order() if order is None else order
    seg = load_travel_times() if seg is None else seg
    out: dict = {}
    for line, seq in order.items():
        line = int(line)
        pairs = {(seq[i], seq[i + 1]): seq[i + 1] for i in range(len(seq) - 1)}
        fix = LINE_EDGE_FIXES.get(line, {})
        for a, b in fix.get("drop", []):
            pairs.pop((a, b), None)
            pairs.pop((b, a), None)
        for a, b in fix.get("add", []):
            pairs[(a, b)] = b
        edges = []
        for (a, b), succ in pairs.items():
            t = seg.get((line, succ))
            edges.append([a, b, round(t, 2) if t else None])
        out[line] = sorted(edges, key=lambda e: (seq.index(e[0]), seq.index(e[1])))
    return out


def load_train_congestion(dir_: "Path | None" = None) -> pd.DataFrame:
    """OA-12928 열차 혼잡도(교차검증용) → long.

    반환: daytype(요일구분), line, station, updown(상하구분), hour(int), pct(float)
    csv(cp949)만 로드(안정성). xlsx는 openpyxl 설치 시 확장 가능.
    """
    dir_ = dir_ or config.TRAIN_CONGESTION_DIR
    frames = []
    for fp in sorted(dir_.glob("*.csv")):
        raw = pd.read_csv(fp, encoding="cp949")
        id_cols = ["요일구분", "호선", "역번호", "출발역", "상하구분"]
        time_cols = [c for c in raw.columns if "시" in c and c not in id_cols]
        long = raw.melt(id_vars=id_cols, value_vars=time_cols,
                        var_name="timelabel", value_name="pct")
        frames.append(long)
    df = pd.concat(frames, ignore_index=True)
    df["line"] = df["호선"].map(line_number)
    df["station"] = df["출발역"].map(normalize_station)
    df["updown"] = df["상하구분"]
    df["daytype"] = df["요일구분"]
    # '5시30분','6시00분' → hour(정수) + slotmin(30분 격자 분 단위)
    hm = df["timelabel"].str.extract(r"(\d{1,2})시(\d{1,2})분")
    df["hour"] = pd.to_numeric(hm[0], errors="coerce")
    minute = pd.to_numeric(hm[1], errors="coerce").fillna(0)
    df["slotmin"] = df["hour"] * 60 + minute
    df["pct"] = pd.to_numeric(df["pct"], errors="coerce")
    df = df.dropna(subset=["line", "hour"])
    df["line"] = df["line"].astype(int)
    df["hour"] = df["hour"].astype(int)
    df["slotmin"] = df["slotmin"].astype(int)
    return df[["daytype", "line", "station", "updown", "hour", "slotmin", "pct"]]


def load_card_monthly_totals(dir_: "Path | None" = None) -> pd.DataFrame:
    """CARD_SUBWAY(=OA-12914) → 월별 승하차 합계(볼륨 sanity용).

    반환: month(YYYYMM), line(int|NaN), boardings, alightings
    """
    dir_ = dir_ or config.CARD_DIR
    frames = []
    for fp in sorted(dir_.glob("CARD_SUBWAY_MONTH_*.csv")):
        # 일부 파일은 행 끝에 빈 필드가 있어 컬럼이 밀림 → index_col=False로 방지
        c = _read_csv_flex(fp, index_col=False)
        c.columns = [x.strip().strip('"') for x in c.columns]
        c["month"] = fp.stem.split("_")[-1]
        frames.append(c[["month", "노선명", "승차총승객수", "하차총승객수"]])
    df = pd.concat(frames, ignore_index=True)
    df["line"] = df["노선명"].map(line_number)
    df["boardings"] = pd.to_numeric(df["승차총승객수"], errors="coerce")
    df["alightings"] = pd.to_numeric(df["하차총승객수"], errors="coerce")
    return (df.groupby(["month", "line"], as_index=False)
              [["boardings", "alightings"]].sum())
