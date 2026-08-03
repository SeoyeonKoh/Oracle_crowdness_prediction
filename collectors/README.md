# collectors/ — 데이터 수집기

소급 조회가 불가능한 실시간 데이터를 주기적으로 스냅샷 찍어 쌓는다.
모든 수집기는 같은 규칙을 따른다: 원본 그대로 저장 · 실패해도 안 죽음 · 호출 수 자가 집계 · `source` 필드 기록.
경로는 파일 위치(collectors/) 기준으로 계산해 어디서 실행해도 동작한다.

## 파일

### `collect_citydata.py` — 서울 실시간 도시데이터
- **API**: `openapi.seoul.go.kr` citydata · **키**: `SEOUL_OPENDATA_GENERAL_KEY`
- **저장**: `data/citydata/YYYY-MM-DD.jsonl` (+ `call_counter.json`)
- 주요 장소(관문 환승역)의 실시간 인구·혼잡등급·예측인구를 수집. 응답 원본에 지하철 도착·승강기 가동현황·버스·날씨 등이 모두 포함.
- 인구수(`ppltn_min/max`)와 집계시각(`ppltn_base_time`)을 함께 저장 — 등급은 28일 평균 대비 상대값이라 인구수가 있어야 재계산 가능.
- **실행**: `python3 collectors/collect_citydata.py`

### `collect_subway_realtime.py` — 실시간 지하철 (열차위치·도착정보)
- **API**: `swopenapi.seoul.go.kr` · **키**: `SEOUL_OPENDATA_SUBWAY_KEY` *(일반 키와 별개, 하루 1,000회 독립)*
- **저장**: `data/subway_realtime/YYYY-MM-DD.jsonl` (+ `call_counter.json`)
- 한 번 실행에 **4호출**: 2·4호선 열차위치(`realtimePosition`), 왕십리·동대문역사문화공원 도착정보(`realtimeStationArrival`).
- 용도: 혼잡 경보의 **배차 간격 표본**·도착 ETA. 응답 원본 그대로 저장.
- **실행**: `python3 collectors/collect_subway_realtime.py`
- ⚠️ 이 키는 도시데이터 일반 키가 아니다. 주소가 `swopenapi`(일반은 `openapi`)이고 별도 신청분.

## 저장 레코드 공통 필드
`source`(수집기 ID) · `collected_at`(호출 시각) · `raw_response`(원본 전체) + 수집기별 부가 필드.

## 자동 반복 (cron)
러시아워(07–09·17–19시)는 촘촘히, 그 외는 성기게. 예:
```
*/10 7-9,17-19 * * * cd /home/ubuntu/collector && python3 collectors/collect_subway_realtime.py >> logs/subway_realtime.log 2>&1
*/30 0-6,10-16,20-23 * * * cd /home/ubuntu/collector && python3 collectors/collect_subway_realtime.py >> logs/subway_realtime.log 2>&1
```
서버 설정·cron 등록은 `scripts/setup_server.sh` 참고. 시간대 변경 시 `sudo systemctl restart cron` 필수.

## 새 수집기 추가 규칙
`collectors/collect_{데이터}.py` · 저장 `data/{데이터}/` · 로그 `logs/{데이터}.log` · 키는 `config/APIkey.py` (이름 `{발급처}_{종류}_KEY`) · 레코드에 `source` 필드.
