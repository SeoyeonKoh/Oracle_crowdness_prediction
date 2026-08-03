# Phase 2 체류인원 예측 — 검증 리포트

학습 2023–2024 / 검증 2025 홀드아웃. 단위: 평균 체류인원(명).

| target | 방식 | MAE | RMSE | sMAPE_% | corr |
| --- | --- | --- | --- | --- | --- |
| occ_platform | HGB 모델 | 6.41 | 15.64 | 13.1 | 0.967 |
| occ_platform | seasonal-naive | 6.67 | 16.04 | 13.4 | 0.966 |
| occ_concourse | HGB 모델 | 4.04 | 10.51 | 13.0 | 0.966 |
| occ_concourse | seasonal-naive | 4.18 | 10.67 | 13.3 | 0.965 |

## 해석
- **occ_platform**: HGB가 seasonal-naive 대비 MAE +3.9% (개선).
- **occ_concourse**: HGB가 seasonal-naive 대비 MAE +3.2% (개선).

> 캘린더 피처만 사용(승하차 실측 없이 미래 예측). 실시간 요인(날씨·POI·행사) 확보 시 추가 개선 여지.
