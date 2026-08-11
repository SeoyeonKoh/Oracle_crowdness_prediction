# KRIC 철도역 편의정보 — 정형 데이터

출처: 국가철도공단 철도역 편의정보 `https://hc.kric.go.kr/hc/index.jsp`
수집 스크립트: [src/crawl_kric_hc.py](../../src/crawl_kric_hc.py)
원본 JSON 캐시: `data/kric_hc_raw/` · SQLite: `data/kric_hc.sqlite`

**수집 범위: 수도권 1~9호선, 458개 역 (2026-08-11 기준)**

| 테이블 | 행수 |
|---|---:|
| stations | 458 |
| platforms | 907 |
| platform_gaps | 34,417 |
| platform_cars | 8,605 |
| station_floors | 1,096 |
| helpers | 419 |
| facilities | 6,411 |
| move_paths | 2,279 |
| move_path_steps | 14,229 |

승강장 정보 454/458역, 편의시설 457/458역, 이동동선 458/458역 확보 (미확보분은 원본이 미제공).

모든 CSV는 UTF-8 (BOM) 인코딩. 아래 6개 컬럼이 전 테이블 공통 키다.

| 컬럼 | 의미 |
|---|---|
| `are_cd` / `are_nm` | 지역코드 / 지역명 (01 수도권, 02 부산, 03 대구, 04 광주, 05 대전) |
| `rail_opr_istt_cd` | 철도운영기관 코드 (S1 서울교통공사, KR 한국철도공사, BS 부산교통공사 등) |
| `ln_cd` / `ln_nm` | 노선코드 / 노선명 |
| `prpr_stin_cd` | 역 고유코드 |
| `stin_nm` | 역명 |

기본키는 `(rail_opr_istt_cd, ln_cd, prpr_stin_cd)` — 환승역은 노선별로 별도 레코드다.

---

## 1. `stations.csv` — 역 기본정보

| 컬럼 | 의미 |
|---|---|
| `line_order` | 노선 내 목록 순번 |
| `stin_cons_ordr` | 역 구성 순서 |
| `prev_*` / `next_*` | 이전역 / 다음역의 기관·노선·역코드·역명 |
| `has_platform_info` / `has_facility_info` / `has_move_path_info` | 각 탭의 데이터 제공 여부 |

인접역 컬럼으로 노선 그래프를 그대로 복원할 수 있다.

## 2. `platforms.csv` — 승강장

| 컬럼 | 의미 |
|---|---|
| `plf_no` | 승강장 번호 |
| `plf_tp_nm` | 승강장 형식 (섬식 / 상대식 등) |
| `run_dir_tmn_stin_nm` | 운행방향 종착역 |
| `next_stin_nm` | 진행방향 다음역 표기 |
| `screen_door` | 스크린도어 (`●` 있음 / `×` 없음) |
| `safety_footboard` | 안전발판 |
| `platform_crossable` | 승강장 횡단 가능 여부 |
| `braille_block` | 점자블록 |
| `braille_sign` | 점자 안내판 |

## 3. `platform_gaps.csv` — 승강장 이격거리 (핵심 미시 데이터)

승강장 × 호차 × 출입문 단위. 이 사이트에서만 얻을 수 있는 도어 단위 데이터다.

| 컬럼 | 의미 |
|---|---|
| `plf_no`, `car_ordr`, `car_etrc_no` | 승강장 번호, 호차, 출입문 번호 |
| `sf_dst_cd` | 이격거리 구간 코드 (1/2/3) |
| `sf_dst_range_cm` | `0~10` / `10초과~15이하` / `15초과` |
| `near_elevator` / `near_escalator` / `near_stair` | 해당 출입문 위치의 EV·ES·계단 인접 (`Y`) |

`near_stair`, `near_elevator`가 `Y`인 출입문 = 승하차 집중 지점. 혼잡도 분석에서
차량별 편중(car-level imbalance) 추정에 바로 쓸 수 있다.

## 4. `platform_cars.csv` — 차량 편성

`plf_no`, `car_ordr`, `door_cnt`(호차별 출입문 수).

## 5. `station_floors.csv` — 역 층 구성

| 컬럼 | 의미 |
|---|---|
| `grnd_dv_cd` / `grnd_dv_nm` | 1=지상, 2=지하 |
| `stin_flor` | 층수 |
| `floor_label` | `지하 2층` 형태의 표기 |
| `seq` | 표시 순서 |

## 6. `facilities.csv` — 편의시설

| 컬럼 | 의미 |
|---|---|
| `facility_cd` / `facility_nm` | EV=일반승강기, WCLF=휠체어리프트, ELEC=전동휠체어충전설비, TOLT=화장실, INFO=고객센터, LARM=수유실 |
| `grnd_dv_cd`, `stin_flor`, `floor_label` | 설치 층 |
| `detail_location` | 상세 위치 문자열 (예: `[3호기]1번출구측`) |
| `trfc_weak_dv_cd` / `_nm` | 화장실 구분: 1=일반, 2=장애인 |
| `ml_fml_dv_cd` / `_nm` | 1=남, 2=여, 3=공용 |

## 7. `helpers.csv` — 교통약자 도우미 연락처

`tel_no`.

## 8. `move_paths.csv` — 이동동선 목록

| 컬럼 | 의미 |
|---|---|
| `mv_path_dv_cd` / `_nm` | 1=출입구-승강장, 3=환승 |
| `mg_no` | 경로 일련번호 |
| `start_point` / `end_point` | 출발 지점 / 도착 지점 |
| `path_label` | `3번 출입구 옆 엘리베이터 → 대림 방면` |

환승 경로(`mv_path_dv_cd=3`)는 노선쌍 단위 환승 동선을 그대로 담고 있다.

## 9. `move_path_steps.csv` — 이동동선 단계별 상세

`mg_no` + `step_no` 순서로 이어지는 `step_text`.
예: `1) (1F) 3번 출입구 옆 엘리베이터 탑승` → `2) (B1) 대합실로 이동` → …
층 이동 횟수, EV/ES/계단 사용 여부를 텍스트에서 파싱하면 환승 저항(transfer
resistance) 지표를 만들 수 있다.

---

---

# 파생 데이터 — 층별 배치도 + 동선 안내

생성 스크립트: [src/build_station_layout.py](../../src/build_station_layout.py)

원본에는 **층 간 연결 관계가 없다.** `move_path_steps`의 단계 텍스트에 박힌 층 표기와
행위 동사를 파싱해 역산했다. 층 표기는 두 관례를 모두 지원한다.

- 괄호형 (서울교통공사 등): `3) (B1) 대합실로 이동`
- 인라인형 (코레일 구간): `2) 지상2층 엘리베이터 하차`

행위 동사 → `탑승/이용`=BOARD, `하차`=ALIGHT, `승차`=RIDE, `통과/태그`=GATE, 나머지=MOVE.
BOARD 직후 층 표기가 바뀌면 그 구간을 **연결(edge)** 로 만든다.

## 10. `station_layout.json` — UI용 통합 구조 (458개 역)

역 1건의 형태:

```json
{
  "station_id": "S1_2_0497", "stin_nm": "잠실", "ln_nm": "2호선",
  "helper_tel": "02-6110-2161",
  "floors": [
    { "floor": "B1", "level": -1, "label": "지하 1층",
      "nodes": [ {"kind": "대합실", "label": "대합실", "detail": null},
                 {"kind": "엘리베이터", "label": "일반승강기", "detail": "[1호기]잠실나루방면5-2"} ],
      "platforms": [ {"plf_no": 1, "toward": "잠실새내", "screen_door": "●",
                      "facility_positions": [{"car_label": "5-1칸", "facility_nm": "엘리베이터"}]} ] }
  ],
  "connections": [ {"from_floor": "1F", "to_floor": "B1", "direction": "down",
                    "floor_span": 1, "conveyance_nm": "엘리베이터",
                    "label": "1번 출입구 옆 엘리베이터",
                    "source": "move_path", "corroborated": 1} ],
  "routes": { "entrance_to_platform": [...], "transfer": [...] }
}
```

`floors`는 위층부터 아래층 순으로 정렬돼 있어 그대로 세로 배치하면 된다.

`kind` 값: `출입구` `대합실` `개찰구` `승강장` `환승승강장` `엘리베이터` `휠체어리프트`
`전동휠체어충전설비` `화장실` `고객센터` `수유실`.

## 11. `floor_nodes.csv` — 역 × 층 × 시설 (9,470행)

`floor`, `level`, `floor_label`, `kind`, `label`, `detail`.
`level`은 지상 양수 / 지하 음수 (0층 없음).

## 12. `floor_edges.csv` — 층 간 연결 (3,425행)

| 컬럼 | 의미 |
|---|---|
| `from_floor` / `to_floor` | 출발 층 / 도착 층 |
| `direction` | `up` / `down` / `same`(같은 층 통로) |
| `floor_span` | 실제 이동 층수. 0층이 없으므로 `1F↔B1`은 1이다 |
| `conveyance` / `_nm` | EV, ES, WCLF, STAIR, RAMP, PASSAGE |
| `label` | 원본이 부르는 이름 (`잠실나루 방면 엘리베이터`) |
| `source` | `move_path`(동선 텍스트에서 역산) / `facility_span`(같은 호기가 여러 층에 등재) |
| `floor_notation` | 근거가 된 층 표기 관례 `paren` / `inline` |
| `corroborated` | 두 근거가 일치하면 1, 동선 텍스트만 있으면 0, 같은 층 통로는 공란 |

**`corroborated`를 반드시 보라.** 층간 이동 연결 1,712건 중 1,230건(71.8%)이
승강기 층등재로 교차검증된다. 나머지는 근거가 동선 텍스트 하나뿐이다.

## 13. `platform_facility_positions.csv` — 승강장 위 시설 위치 (3,159행)

`plf_no`, `car_ordr`, `car_etrc_no`, `car_label`(`8-2칸`), `facility_nm`
(엘리베이터/에스컬레이터/계단). 예시 화면의 `8-2칸` 표기가 이 데이터다.

## 14. `route_guides.csv` — 경로별 안내문 (2,279건)

`path_label`, `floor_sequence`(`B2 → B1 → B3`), `n_steps`, `n_elevator`,
`n_escalator`, `guide_text`(한 줄), `guide_lines`(번호 매긴 단계, `|` 구분).

## 15. `transfer_guides.csv` — 환승 전용 (675건)

`from_line`, `from_direction`, `to_line`, `to_direction` 로 분해돼 있어
"A호선 X방면 → B호선 Y방면" 질의에 바로 답할 수 있다.

```
왕십리 2호선 상왕십리 방면 → 5호선 행당 방면   [B2 → B4 → B5] EV 2회
  1. [B2] 2호선 상왕십리 방면 승강장 하차
  2. [B2] 환승대합실로 이동
  3. 5호선 방향 엘리베이터(으)로 2개 층 내려가기 (B2 → B4, 엘리베이터)
  4. [B4] 5호선 대합실로 이동
  5. 5호선 행당 방면 엘리베이터(으)로 1개 층 내려가기 (B4 → B5, 엘리베이터)
  6. [B5] 5호선 행당 방면 승강장으로 이동
  7. [B5] 승차 (휠체어칸)
```

## 16. `station_ui_bundle.json` — 화면 구성용 단일 번들 ★

생성 스크립트: [src/build_ui_bundle.py](../../src/build_ui_bundle.py)

**층별 시설 + 시설 위치 + 역산 동선을 한 파일에 담고, 스키마·코드범례·한계까지
파일 안에 넣었다.** 다른 문서 없이 이 파일 하나로 화면을 구성할 수 있다.

```
{
  "meta": {
    "title", "purpose",
    "source":      { 출처 URL, 수집범위, 수집일 },
    "schema":      { 모든 필드의 의미 },
    "legend":      { 시설 종류 목록, 이격거리 구간, '8-2칸' 표기법 },
    "derivation":  { links 를 어떻게 역산했는지 },
    "howToUse":    { 화면 구성 시 지침 },
    "limitations": { 좌우 없음 / 실시간 없음 / 미확정 구간 },
    "coverage":    { 커버리지 수치 }
  },
  "stations": [ 458개 역 ]
}
```

역 1건의 구조:

```json
{
  "id": "S1_2_0497", "name": "잠실", "line": "2호선", "operator": "S1",
  "helperTel": "02-6110-2161", "prev": "잠실새내", "next": "잠실나루",
  "floors": [
    { "code": "B2", "level": -2, "label": "지하 2층",
      "facilities": [{"type": "엘리베이터", "name": "일반승강기", "loc": "[1호기]잠실나루방면5-2"}],
      "platforms": [{ "no": 2, "type": "상대식", "toward": "잠실나루",
                      "screenDoor": true, "crossable": false, "brailleBlock": false,
                      "spots": [{"car": "6-3칸", "type": "엘리베이터"}],
                      "gap": {"0~10": 38, "10~15": 2} }] }
  ],
  "links": [{"from":"B1","to":"B2","dir":"down","span":1,"via":"엘리베이터",
             "label":"잠실나루 방면 엘리베이터","src":"move_path","verified":true}],
  "routes": {
    "toPlatform": [{"label":"…","floors":["1F","B1","B2"],"ev":2,"es":0,"steps":["…"]}],
    "transfer":   [{"from":{"line":"2호선","dir":"잠실나루"},
                    "to":{"line":"8호선","dir":"몽촌토성"},
                    "floors":["B2","B1","B3"],"ev":2,"steps":["…"]}]
  }
}
```

`floors`는 위층 → 아래층 순으로 정렬돼 있어 그대로 세로로 쌓으면 단면도가 된다.
`links`가 층간 연결선, `spots`의 `car`(`8-2칸`)가 승강장 위 아이콘 위치다.
`verified=false`인 연결은 근거가 동선 텍스트뿐이니 점선 등으로 구분하는 게 좋다.

### 크기 주의

전체 번들은 **2.8MB(458역)** 라 한 번에 컨텍스트에 올리기 어렵다.
스키마 파악용으로 **`station_ui_bundle.sample.json` (46KB, 잠실·왕십리·연천 3개 역)**
을 같이 만들어 뒀다. 구조는 완전히 동일하다. 스키마는 발췌본으로 익히고
전체 데이터는 코드로 읽어 쓰는 것을 권한다.

## 좌/우 방향에 대하여

**원본에 좌우 방향 정보는 사실상 없다.** 14,229개 단계 중 `좌측/우측/왼쪽/오른쪽`
표현은 37건뿐이다. 있으면 `side_hint`로 안내문에 괄호로 붙이지만, 대부분의 역은
층 이동(올라가기/내려가기)과 랜드마크(`6번 출입구 방향`, `표 내는 곳`)로만 안내된다.
좌우를 채우려면 역 구내도 이미지 판독이나 별도 실측이 필요하다.

## 커버리지와 한계

| 항목 | 결과 |
|---|---|
| 층 정보 | 458 / 458역 |
| 층 간 연결 | 457 / 458역 (능길역만 없음) |
| 승강장의 소속 층 확정 | 418 / 458역 |
| 환승 안내 | 146역 675건 |

승강장 층이 확정되지 않은 40개 역은 동선 텍스트가 승강장 단계에 층을 안 적은
경우다. 시설·승강장 정보 자체는 다 들어 있고 층 배치만 비어 있다.

원본이 자체 모순인 경우도 있다. 예: 연천역은 4단계에서 `지상3층 엘리베이터 탑승`,
5단계에서 `지상1층 승강장`이라 적혀 층 이동이 어긋난다. 추측으로 보정하지 않고
`corroborated=0`으로 표시했다.

---

## 재수집 / 범위 확장

기본값이 수도권 1~9호선이다. 원본 JSON이 `data/kric_hc_raw/`에 캐시되어 있으면
네트워크 호출을 건너뛴다.

```bash
python3 src/crawl_kric_hc.py
```

CSV/SQLite만 다시 만들려면:

```bash
python3 src/crawl_kric_hc.py --build-only
```

수도권 전 노선(경의중앙·수인분당·공항·GTX-A 등 포함):

```bash
python3 src/crawl_kric_hc.py --lines all
```

전국 5개 지역 전체:

```bash
python3 src/crawl_kric_hc.py --areas 01 02 03 04 05 --lines all
```

## 수집하지 않은 것

역 구내도·이동경로도 **이미지**(`/hc/ext/images/visual/handicapped/cnv/…png`,
`…/mvPath/…png`)는 요청대로 제외했다. 필요하면 `move_paths.csv`의
`rail_opr_istt_cd_ln_cd_prpr_stin_cd_mg_no_mv_path_dv_cd.png` 규칙으로 조립 가능하다.
