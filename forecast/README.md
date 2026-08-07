# Oracle Crowdness Prediction — Apex 지하철 혼잡도 예보

이동약자(휠체어 이용자)를 위한 서울 지하철 **혼잡도 예보** 시스템. 팀 프로젝트 Apex의 **기능 1(혼잡도 예보)** 구현체.
승하차·열차혼잡·역사면적 등 공개데이터로 **역사 내(승강장/대합실) + 열차 내** 혼잡을 계산·예측하고, 도착 시점 기준으로 경로를 안내한다.

## 핵심 기능
- **1-1 도착 시점 예보**: 경로 각 역을 "지금"이 아니라 "내가 도착할 시각"의 혼잡으로 표시 (역간거리·환승 소요 실측 ETA)
- **1-2 4단계 혼잡**: 여유 / 보통 / 주의 / 혼잡 (+ 휠체어 모드는 6단계로 더 세분·보수적)
- **1-3 "평소보다 붐빔" 배지** / **1-4 혼잡 원인**(공사·사고·지연·날씨, 현재 데모) / **1-5 출발 시간 추천**
- **구역별**: 승강장(유료) · 대합실(비유료) · 열차 내(재차/정원 %)
- **혼잡 기준 2종**: 상대(백분위) · 정원 대비(순간 첨두 모형)
- **전체 호선 통합 검색 + 환승 경로**(여러 경로 대안 선택), **호선색 타임라인**
- **일반 / 휠체어 모드**(ADA 점유면적 근거로 더 보수적)
- 요일(월~일) + **공휴일** 별도 카테고리 (공휴일 ≈ 일요일, 평일과 확연히 다름)

## 방법론 (요약)
- **체류인원** = Little's Law `L = λ·W` (시간당 인원 × 평균 체류시간) → ÷ 면적 = **밀도**
- **상대 %** = 밀도의 백분위(평일 분포). 4단계 경계 = 50/80/95%
- **정원 대비 %** = 순간 첨두밀도(열차 직전 누적) ÷ 정원밀도 × 100
- **열차 혼잡 %** = OA-12928 재차/정원 (실측)
- 예측 = 과거 평균(seasonal-naive) + Gradient Boosting 보정, 2023–24 학습 / 2025 검증 (승강장 MAE 6.41, r 0.97)
- 자세한 내용: [`proc/research/혼잡도-추정-방법론.md`](proc/research/혼잡도-추정-방법론.md)

## 폴더 구조 (SPARK + IPO)
```
├── input/     # 원천 데이터 (Git 제외 — 아래 '데이터 준비' 참고)
├── src/       # 소스 코드 (기능별 폴더)
│   ├── config.py            # 설정(경로·상수·정원밀도)
│   ├── loading/             # 데이터 로드 — loaders.py(원천 CSV/XLSX), stations.py(역마스터·면적)
│   ├── congestion/          # 혼잡 계산 — occupancy.py(체류인원), los.py(LOS), levels.py(4단계·%)
│   ├── prediction/          # 예측 — model.py(HGB), run.py(학습·검증)
│   ├── serving/             # 예보 서비스 — service.py(도착시점·환승·추천), causes.py(원인)
│   ├── batch/               # 실행 엔트리 — build.py, summarize_byday.py, export_forecast.py
│   ├── evaluation.py        # 교차검증(피크·볼륨)
│   └── web/                 # 화면 — index.html·app.js·style.css·dashboard.html
├── output/    # 산출물 (forecast.json 등만 포함, 대용량 제외)
├── data/      # SQLite·모델 (Git 제외)
└── proc/      # 설계·계획·리서치 문서 (SPARK)
```

## 실행
```bash
pip install -r requirements.txt

# 1) 데이터 준비(아래) 후 파이프라인
python -m src.batch.build            # 승하차 → 체류인원 → LOS (output/occupancy_hourly.csv.gz)
python -m src.batch.summarize_byday  # 요일/공휴일별 요약 + 정원대비% (los_summary_byday.csv)
python -m src.prediction.run         # 체류인원 예측 모델 (data/model_*.joblib)
python -m src.batch.export_forecast  # 화면용 output/forecast.json

# 2) 화면 실행 (저장소 루트에서)
python -m http.server 8765
# http://localhost:8765/src/web/index.html      (예보 화면)
# http://localhost:8765/src/web/dashboard.html  (대시보드)
```
> `output/forecast.json`이 저장소에 포함되어 있어, 데이터 없이도 화면 데모는 바로 실행된다.

## 데이터 준비 (`input/`)
원천 데이터는 용량이 커 Git에 포함하지 않는다. [서울 열린데이터광장](https://data.seoul.go.kr)에서 아래를 받아 `input/OA-##### 이름/` 형식 폴더로 넣는다.

| 폴더 | 데이터셋 | 용도 |
|------|----------|------|
| OA-12921 | 역별 일별 시간대별 승하차 | 체류·예측 입력 |
| OA-12928 | 지하철 혼잡도(열차, 30분) | 열차 내 혼잡 |
| OA-12034 | 역간거리·소요시간 | ETA |
| OA-13290 | 환승역거리·소요시간 | 환승 ETA |
| OA-12033 | 환승역 환승인원 | 유료구역 환승항 |
| OA-12914(CARD) | 호선별 역별 승하차 | 검증(볼륨) |
| — | 역사면적정보 | 밀도(LOS) 분모 |

> 파일 다운로드: `datasetView` 페이지의 `downloadFile('N')` 번호로
> `https://datafile.seoul.go.kr/bigfile/iot/inf/nio_download.do?infId=OA-XXXX&seq=N&infSeq=1&useCache=false`

## 데이터 신뢰도 (정직 고지)
- 🟢 **실제**: 열차 혼잡 %(OA-12928), 승하차·환승·역간거리·면적
- 🟡 **근사**: 승강장/대합실 체류(Little's Law + 가정 상수), 정원밀도(1.5/1.0 가정), 첨두 배율, 환승 시간분배
- 🔴 **데모/가정**: 혼잡 원인(공사·지연·날씨) 샘플, "평소보다 붐빔" 1.6배 임계

## 한계 & 다음 단계
- 승하차 공개데이터가 1시간 단위 → 분 단위는 실시간 도착 API(키 필요)
- 실시간 원인(알림정보·기상), 9호선, 노선별 지연은 미통합
- 정원밀도·환승 분배는 실측 확보 시 교체 권장
