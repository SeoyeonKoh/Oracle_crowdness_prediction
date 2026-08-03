# forecast — 지하철 혼잡도 예보 (기능 1)

수집기(`../collectors/`)가 쌓는 데이터와 공개데이터로 **역사 내(승강장/대합실) + 열차 내** 혼잡을
계산·예측하고, 도착 시점 기준으로 경로를 안내하는 모듈. 팀 프로젝트 Apex의 **기능 1(혼잡도 예보)**.

> 상위 저장소는 데이터 수집(collector) 프로젝트다. 이 폴더는 그 위에 얹는 **분석·예측·화면** 계층으로,
> 상위의 `collectors/ config/ data/` 는 건드리지 않고 `forecast/` 안에서 독립적으로 동작한다.

## 핵심 기능
- **도착 시점 예보**: 각 역을 "도착할 시각"의 혼잡으로 표시 (역간거리·환승 소요 실측 ETA)
- **4단계 혼잡**(여유/보통/주의/혼잡) + **휠체어 모드**(6단계·보수적)
- 구역별 **승강장 / 대합실 / 열차 내**, 기준 **상대(백분위) / 정원 대비(순간 첨두)**
- 전체 호선 통합 검색 + **환승 경로**(여러 대안 선택), **호선색 타임라인**
- 요일(월~일) + **공휴일** 별도, "평소보다 붐빔" 배지, 혼잡 원인(데모), 출발시간 추천

## 실행 (이 폴더 기준)
```bash
pip install -r requirements.txt --break-system-packages

# 데이터(input/) 준비 후
python -m src.batch.build            # 승하차 → 체류인원 → LOS
python -m src.batch.summarize_byday  # 요일/공휴일별 + 정원대비%
python -m src.prediction.run         # 예측 모델
python -m src.batch.export_forecast  # 화면용 output/forecast.json

# 화면 (forecast/ 에서)
python -m http.server 8765
# http://localhost:8765/src/web/index.html      (예보)
# http://localhost:8765/src/web/dashboard.html  (대시보드)
```
`output/forecast.json` 이 포함돼 있어 데이터 없이도 화면 데모는 바로 실행된다.

## 데이터 준비 (`forecast/input/`)
서울 열린데이터광장에서 받아 `input/OA-##### 이름/` 형식으로 넣는다: OA-12921(승하차)·OA-12928(열차혼잡)·
OA-12034(역간거리)·OA-13290(환승소요)·OA-12033(환승인원)·역사면적정보. 상세: `proc/research/혼잡도-추정-방법론.md`.

## 방법론 요약
체류인원 = Little's Law(L=λ·W) → ÷면적 = 밀도. 상대%=백분위, 정원대비%=순간첨두밀도÷정원밀도.
열차%=OA-12928 실측(재차/정원). 예측=seasonal-naive + Gradient Boosting(2023–24 학습/2025 검증, MAE 6.41).

## 신뢰도 (정직 고지)
- 🟢 실제: 열차 혼잡%(OA-12928), 승하차·환승·역간거리·면적
- 🟡 근사: 승강장/대합실 체류(Little's Law+가정), 정원밀도(1.5/1.0 가정), 첨두 배율, 환승 시간분배
- 🔴 데모: 혼잡 원인(공사·지연·날씨), "평소보다 붐빔" 1.6배 임계
