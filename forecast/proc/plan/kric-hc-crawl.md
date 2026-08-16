# KRIC 철도역 편의정보(hc.kric.go.kr) 크롤링

## 목표
승강장정보 / 편의시설정보 / 이동경로(동선)정보를 이미지 없이 **정형 데이터(CSV + SQLite)** 로 수집.

## 소스
`https://hc.kric.go.kr/hc/visual/handicapped/*.do` (GET, JSON 응답)

| 엔드포인트 | 파라미터 | 반환 |
|---|---|---|
| `selectAreCdClickInfo.do` | paramAreCd | resultLnList(노선), resultStinList |
| `selectLegendClickInfo.do` | paramAreCd, paramLnCd | resultStinList(역 목록) |
| `selectStinPlfInfo.do` | +paramRailOprIsttCd, paramPrprStinCd | 승강장/이격거리/차량편성/전후역 |
| `selectStinCnvInfo.do` | 〃 | 층정보, 도우미전화, 편의시설 |
| `selectMovePath.do` | 〃 | 경로구분/출입구경로/환승경로 |
| `selectMovePathDetail.do` | +paramMvPathDvCd, paramMgNo | 경로 단계별 상세 |

지역코드: 01 수도권 / 02 부산 / 03 대구 / 04 광주 / 05 대전

**수집 범위: 수도권(01) 1~9호선.** (`--areas`, `--lines`로 확장 가능)

## 절차
1. 지역 → 노선 → 역 목록 수집 (`stations`)
2. 역별 3개 탭 호출 + 경로별 상세 호출
3. 원본 JSON을 `data/kric_hc_raw/`에 캐시 (재실행 시 스킵)
4. 평탄화 → `output/kric_hc/*.csv` + `data/kric_hc.sqlite`

## 산출 테이블
- `stations` 역 기본 + 전/후역
- `platforms` 승강장(형식, 스크린도어, 횡단, 점자블록, 안전발판)
- `platform_gaps` 승강장×호차×출입문 이격거리 + 계단/EV/ES 근접
- `platform_cars` 승강장×호차 출입문 수
- `facilities` 편의시설(EV/휠체어리프트/충전설비/화장실/고객센터/수유실) 위치
- `station_floors` 역 층 구성
- `helpers` 교통약자 도우미 연락처
- `move_paths` 이동경로 목록(출입구-승강장 / 환승)
- `move_path_steps` 경로 단계별 상세 문구

## 코드 매핑
- `grndDvCd` 1=지상, 2=지하
- `sfDst` 1=0~10, 2=10초과~15이하, 3=15초과 (cm)
- `sa`=계단, `ev`=엘리베이터, `es`=에스컬레이터 인접 (Y)
- `gubun` EV=일반승강기, WCLF=휠체어리프트, ELEC=전동휠체어충전설비, TOLT=화장실, INFO=고객센터, LARM=수유실
- `trfcWeakDvCd` 1=일반, 2=장애인 / `mlFmlDvCd` 1=남, 2=여, 3=공용
- `mvPathDvCd` 1=출입구-승강장, 3=환승
- `●`=있음, `×`=없음

## 상태
- [x] API 리버싱 및 검증
- [x] 크롤러 작성 (`src/crawl_kric_hc.py`)
- [x] 수도권 1~9호선 수집
- [x] CSV/SQLite 산출

---

## 2단계 — 층별 배치도 + 동선 안내 파생 (src/build_station_layout.py)

원본에 없는 **층 간 연결 관계**를 `move_path_steps` 텍스트에서 역산.

- 층 표기 2종 지원: 괄호형 `(B1)` / 인라인형 `지상2층`
- 행위 동사: 탑승·이용=BOARD, 하차=ALIGHT, 승차=RIDE, 통과·태그=GATE, 그 외=MOVE
- BOARD 직후 층 변화 → edge(from→to, 이동수단, 라벨)
- 교차검증: 같은 승강기 호기가 여러 층에 등재되면 그 층쌍은 연결됨 (`facility_span`)
- `floor_span`은 0층 없음을 반영 (1F↔B1 = 1개 층)

산출: `station_layout.json`, `floor_nodes.csv`, `floor_edges.csv`,
`platform_facility_positions.csv`, `route_guides.csv`, `transfer_guides.csv`

### 알려진 한계
- 좌/우 방향은 원본에 37건뿐 — 사실상 제공 안 됨
- 승강장 소속 층 확정 418/458역
- 층간 연결 1,712건 중 1,230건(71.8%)만 시설 데이터로 교차검증됨
- 연천역 등 원본 자체 모순 존재 → `corroborated=0`으로 표시, 보정하지 않음

- [x] 층 그래프 역산 및 교차검증
- [x] 자연어 안내문 생성

---

## 3단계 — 화면 구성용 단일 번들 (src/build_ui_bundle.py)

층별 시설 + 시설 위치 + 역산 동선을 한 파일로 통합. 파일 자체에 스키마·범례·
한계·커버리지를 넣어 자기설명적으로 만들었다 (다른 문서 없이 화면 구성 가능).

- `output/kric_hc/station_ui_bundle.json` — 458역, 2.8MB
- `output/kric_hc/station_ui_bundle.sample.json` — 3역 발췌, 46KB (스키마 파악용)

구조: `{meta:{title,purpose,source,schema,legend,derivation,howToUse,limitations,coverage},
stations:[{id,name,line,operator,helperTel,prev,next,floors[],links[],routes{}}]}`

- [x] 단일 번들 생성
- [x] 스키마/범례/한계 내장
