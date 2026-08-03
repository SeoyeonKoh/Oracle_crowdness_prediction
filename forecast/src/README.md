# forecast/src/ — 모듈 구성

기능별 하위 패키지. 실행은 `forecast/` 에서 `python -m src.<경로>` (예: `python -m src.batch.build`).
파이프라인 순서: **loading → congestion → (prediction) → serving/export → web**.

## `config.py`
경로(input/output/data), 시간 상수(배차·게이트대기·이동시간), LOS·정원밀도(CRUSH), 피크시간대, 공휴일 매핑. 값은 여기서만 바꾼다.

## `loading/` — 데이터 로드
- `loaders.py` — 인코딩(cp949/utf-8-sig)·스키마 흡수 로더: 승하차(OA-12921)·열차혼잡(OA-12928)·역간거리(OA-12034)·환승소요(OA-13290)·환승인원(OA-12033)·CARD·역사면적.
- `stations.py` — 역명 정규화, 역·면적 조인, 환승역 감지.

## `congestion/` — 혼잡 계산·등급
- `occupancy.py` — Little's Law 체류인원(비유료 대합실 / 유료 승강장 + 환승항).
- `los.py` — 밀도 → LOS 등급.
- `levels.py` — 4단계·백분위(상대) / 정원대비 경계 계산.

## `prediction/` — 예측
- `model.py` — seasonal-naive + HistGradientBoosting 하이브리드.
- `run.py` — 학습(2023–24)·검증(2025) 실행 → `data/model_*.joblib`, 지표 리포트.

## `serving/` — 예보 서비스 (공통 API)
- `service.py` — 도착 시점 예보·환승 경로(Dijkstra)·출발시간 추천. 화면·타 기능이 공유할 계층.
- `causes.py` — 혼잡 원인(공사/사고/지연/날씨) 인터페이스 (현재 데모 샘플, 실데이터 연동 예정).

## `batch/` — 실행 엔트리포인트
- `build.py` — 승하차 → 체류인원 → LOS (`output/occupancy_hourly.csv.gz`). `python -m src.batch.build`
- `summarize_byday.py` — 요일/공휴일별 요약 + 정원대비%(`los_summary_byday.csv`).
- `export_forecast.py` — 화면용 `output/forecast.json` 생성.

## `evaluation.py`
교차검증 — 승강장 체류 피크 vs 열차혼잡 피크 정렬, 승하차 볼륨 vs CARD 정합.

## `web/` — 정적 웹 화면
`index.html`·`app.js`·`style.css`(예보) + `dashboard.html`(대시보드). `forecast.json` 을 읽어 동작.
`python -m http.server 8765` 후 `/src/web/index.html`. 상세는 `web/README.md`.
