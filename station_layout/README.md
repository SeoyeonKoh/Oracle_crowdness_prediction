# station_layout — 역사 층별 시설·이동동선 데이터

이동약자 경로 안내에 필요한 **역 내부 구조**를 정형 데이터로 담는다.
어느 층에 무엇이 있는지, 층과 층이 무엇으로 연결되는지, 출입구에서 승강장까지·
환승할 때 어떤 동선을 타야 하는지.

출처: 국가철도공단 철도역 편의정보 `https://hc.kric.go.kr/hc/index.jsp`
범위: **수도권 1~9호선 458개 역** (수집일 2026-08-11)
이미지는 받지 않았다. 전부 정형 데이터다.

```
station_layout/
├── src/
│   ├── crawl_kric_hc.py         KRIC 크롤러 → 원본 9종
│   ├── build_station_layout.py  층 그래프 역산 + 동선 안내문 생성
│   └── build_ui_bundle.py       화면 구성용 단일 번들 생성
├── output/
│   ├── station_ui_bundle.json          ★ 화면 구성용 단일 파일 (458역, 2.8MB)
│   ├── station_ui_bundle.sample.json   스키마 파악용 발췌 (3역, 46KB)
│   ├── DATA_DICTIONARY.md              전체 컬럼 정의
│   └── *.csv                           원본 9종 + 파생 5종
└── README.md
```

## 바로 쓰려면

`output/station_ui_bundle.json` 하나만 보면 된다. 파일 안에 스키마·코드범례·
한계·커버리지가 `meta`로 들어 있어 별도 문서 없이 화면을 구성할 수 있다.

```python
import json
b = json.load(open("output/station_ui_bundle.json"))
b["meta"]["schema"]      # 필드 의미
b["meta"]["limitations"] # 한계
st = {s["id"]: s for s in b["stations"]}
```

역 1건의 구조:

```json
{
  "id": "S1_2_0497", "name": "잠실", "line": "2호선",
  "helperTel": "02-6110-2161", "prev": "잠실새내", "next": "잠실나루",
  "floors": [                                    // 위층 → 아래층 순 정렬
    { "code": "B2", "level": -2, "label": "지하 2층",
      "facilities": [{"type":"엘리베이터","name":"일반승강기","loc":"[1호기]잠실나루방면5-2"}],
      "platforms": [{ "no": 2, "type": "상대식", "toward": "잠실나루",
                      "screenDoor": true, "crossable": false,
                      "spots": [{"car":"6-3칸","type":"엘리베이터"}],
                      "gap": {"0~10": 38, "10~15": 2} }] }
  ],
  "links": [{"from":"B1","to":"B2","dir":"down","span":1,"via":"엘리베이터",
             "label":"잠실나루 방면 엘리베이터","src":"move_path","verified":true}],
  "routes": {
    "toPlatform": [{"label":"…","floors":["1F","B1","B2"],"ev":2,"steps":["…"]}],
    "transfer":   [{"from":{"line":"2호선","dir":"잠실나루"},
                    "to":{"line":"8호선","dir":"몽촌토성"},
                    "floors":["B2","B1","B3"],"ev":2,"steps":["…"]}]
  }
}
```

생성되는 환승 안내문:

```
왕십리 2호선 상왕십리 방면 → 5호선 행당 방면   [B2 → B4 → B5] 엘리베이터 2회
  1. [B2] 2호선 상왕십리 방면 승강장 하차
  2. [B2] 환승대합실로 이동
  3. 5호선 방향 엘리베이터(으)로 2개 층 내려가기 (B2 → B4, 엘리베이터)
  4. [B4] 5호선 대합실로 이동
  5. 5호선 행당 방면 엘리베이터(으)로 1개 층 내려가기 (B4 → B5, 엘리베이터)
  6. [B5] 5호선 행당 방면 승강장으로 이동
  7. [B5] 승차 (휠체어칸)
```

## `links`는 파생 데이터다

**원본에는 층과 층의 연결 관계가 없다.** 이동경로 단계 텍스트에서 역산했다.

1. 층 표기 파싱 — 괄호형 `(B1) 대합실로 이동`, 인라인형 `지상2층 엘리베이터 하차` 둘 다 처리
2. 행위 동사 분류 — 탑승·이용=BOARD, 하차=ALIGHT, 승차=RIDE, 통과·태그=GATE, 그 외=MOVE
3. BOARD 직후 층이 바뀌면 그 구간을 연결로 확정
4. 교차검증 — 같은 승강기 호기가 여러 층에 등재돼 있으면 그 층들도 연결로 본다.
   두 근거가 일치하면 `verified=true`

층간 연결 3,425건 중 85.5%가 검증됐다. 동선 텍스트로만 역산한 것(`src=move_path`)
기준으로는 71.8%다. **`verified=false`는 근거가 하나뿐이니 화면에서 약하게 표기할 것.**

## 이 레포의 다른 데이터와 붙는 지점

- `data/elevator_status.csv` — 승강기 **실시간 사용가능 여부**(`USE_YN`, `INSTL_PSTN`).
  이 모듈은 정적 시설 대장이라 고장 상태가 없다. 역명 + 설치위치로 조인하면
  예시 화면의 "운행중지 · 대체 EV 이용" 배지를 만들 수 있다.
- `data/elevator_location.csv`, `escalator.csv`, `accessible_restroom.csv` —
  좌표 기반. 이 모듈의 `loc` 문자열(`[3호기]1번출구측`)과 상호 보완된다.
- `forecast/` — `platform_gaps`의 `near_stair`/`near_elevator`가 `Y`인 출입문이
  승하차 집중 지점이라 차량별 편중 추정에 쓸 수 있다.
  `routes.transfer`의 단계 수·층 이동 횟수는 환승 저항 지표가 된다.

## 한계

- **좌/우 방향은 원본에 사실상 없다.** 14,229개 단계 중 좌측/우측/왼쪽/오른쪽
  표현이 37건뿐이다. 안내는 층 이동(올라가기/내려가기)과 랜드마크
  (`6번 출입구 방향`, `표 내는 곳`) 위주다. 화면에서 좌우 배치는 임의로 정하되
  방향을 단정하는 문구는 쓰지 말 것.
- **실시간 고장 상태 없음.** 전부 시설 대장 기준 정적 정보다.
- 승강장이 어느 층인지 확정된 역은 418/458. 나머지는 동선 텍스트가 승강장 단계에
  층을 안 적었다. 시설·승강장 정보 자체는 있고 층 배치만 비어 있다.
- 원본이 자체 모순인 역이 있다. 연천역은 `지상3층 엘리베이터 탑승` 다음 단계가
  `지상1층 승강장`이라 층 이동이 어긋난다. 추측 보정 없이 `verified=false`로 남겼다.
- 원본 미제공: 승강장정보 4역(탕정·진접·오남·별내별가람), 편의시설정보 1역(1호선 창동).

## 재생성

```bash
cd station_layout
python3 src/crawl_kric_hc.py           # KRIC 크롤 (~5분) → data/kric_hc.sqlite + output/*.csv
python3 src/build_station_layout.py    # 층 그래프 역산 → output/station_layout.json + 파생 CSV
python3 src/build_ui_bundle.py         # 단일 번들 → output/station_ui_bundle.json
```

`data/kric_hc.sqlite`(11MB)와 중간 산출물 `output/station_layout.json`(6MB)은 커밋하지
않았다. CSV와 완전히 중복이라서다. 2·3단계만 다시 돌리려면 1단계를 먼저 실행해
sqlite를 만들어야 한다. 원본 JSON이 `data/kric_hc_raw/`에 캐시되면 재크롤은 생략된다.

크롤러 기본값이 수도권 1~9호선이다. 범위를 넓히려면:

```bash
python3 src/crawl_kric_hc.py --lines all                      # 수도권 전 노선
python3 src/crawl_kric_hc.py --areas 01 02 03 04 05 --lines all  # 전국(부산·대구·광주·대전)
```

스크립트는 `ROOT = 파일위치의 상위 2단계` 기준으로 `data/`·`output/` 경로를 잡는다.
다른 위치에서 돌리려면 각 스크립트 상단의 `ROOT` 정의를 확인할 것.
