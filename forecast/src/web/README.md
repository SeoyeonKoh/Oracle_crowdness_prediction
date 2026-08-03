# 예보 화면 (web)

정적 웹 데모. `output/forecast.json`(= `python -m src.batch.export_forecast` 산출)을 읽어 동작한다.
`file://` 로 열면 fetch가 막히므로 **정적 서버**로 실행한다.

## 실행
```bash
python -m src.batch.export_forecast     # forecast.json 생성(데이터 있을 때)
python -m http.server 8765              # 저장소 루트에서
# http://localhost:8765/src/web/index.html      (예보)
# http://localhost:8765/src/web/dashboard.html  (대시보드)
```
`output/forecast.json` 이 포함돼 있어 데이터 없이도 데모는 바로 실행된다.

## 화면 구성
- **입력**: 요일(월~일·공휴일) · 출발시각(5분) · 출발/도착역 검색(전체 호선)
- **모드**: 일반 / 휠체어(6단계·보수적)
- **구역**: 승강장 · 대합실 · 열차 내
- **기준**: 상대(백분위) / 정원 대비(순간 첨두)
- **경로**: 환승 포함 최단시간/최소환승 대안 선택 · 호선색 타임라인
- **표시**: 도착 시점 4단계·%, "평소보다 붐빔" 배지, 혼잡 원인(데모), 출발시간 추천(승차 혼잡 기준)

## 구조
- `index.html` · `app.js` · `style.css` · `dashboard.html`
- 로직 단일 출처는 `src/serving/service.py`(파이썬) — 화면은 export된 JSON을 읽음.
  실서비스는 service를 API로 감싸 동일 스키마로 연결.
