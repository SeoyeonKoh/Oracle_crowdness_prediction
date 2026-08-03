# Oracle Crowdness Prediction — 지하철 접근성·혼잡도 예보

이동약자(휠체어 이용자)를 위한 서울 지하철 **혼잡도 예보** 프로젝트(Apex). 두 축으로 구성된다.

1. **데이터 수집** (`collectors/`) — 소급 조회가 불가능한 실시간 데이터를 스냅샷으로 쌓는다.
2. **혼잡도 예보** (`forecast/`) — 공개데이터로 역사 내·열차 내 혼잡을 계산·예측하고, 도착 시점 기준으로 경로를 안내한다.

> 데이터 흐름: **수집(실시간 축적) → forecast(계산·예측) → 화면(예보·대시보드)**

## 폴더 구조
```
.
├── collectors/     실시간 데이터 수집기        → collectors/README.md
│   ├── collect_citydata.py          서울 실시간 도시데이터
│   └── collect_subway_realtime.py   실시간 지하철(위치·도착)
├── config/         인증키·설정               → config/README.md
├── scripts/        서버 설정·자동화(cron)     → scripts/README.md
├── data/           수집 원본(.jsonl, Git 제외)
├── logs/           실행 로그(Git 제외)
├── forecast/       혼잡도 예보 모듈           → forecast/README.md
│   ├── src/        계산·예측·서비스·화면       → forecast/src/README.md
│   └── output/     forecast.json 등 산출물
├── requirements.txt   (수집기용: requests)
└── README.md
```
각 폴더의 상세는 해당 `README.md` 참고. 파일별 설명은 폴더 README에 있다.

## 빠른 시작
**수집기**
```bash
pip3 install -r requirements.txt --break-system-packages
cp config/APIkey_example.py config/APIkey.py   # 키 채우기
python3 collectors/collect_citydata.py
python3 collectors/collect_subway_realtime.py
```
**예보 모듈** — `forecast/README.md` 참고 (`forecast/` 에서 `python -m src.batch.build` … `export_forecast`, 화면은 `src/web/`).

## 깃허브 공개 기준
기준 하나: **인터넷에 공개돼도 괜찮은가?**
- 올라감: 코드, `scripts/`, `config/APIkey_example.py`(빈 서식), 문서, `forecast/output/forecast.json`
- 안 올라감(.gitignore): `config/APIkey.py`, `data/`, `logs/`, `wallet/`, `forecast/input/`, 대용량 산출물
- push 전 `git status` 로 `APIkey.py` 가 목록에 없는지 확인

---

## 버전 기록 (Changelog)

### v0.2 — 2026-08-03
- **`forecast/` 혼잡도 예보 모듈 추가** — 승하차·열차혼잡·역사면적으로 체류인원(Little's Law)→밀도→4단계·정원대비 예보, HGB 예측(MAE 6.41), 환승 경로·휠체어 모드·정적 웹 화면(`src/web/`)·대시보드
- **실시간 지하철 수집기 통합** — 팀원 `fetch_realtime.py` 를 기존 규칙(`config/APIkey.py`·`data/{name}/`·jsonl·source 필드)에 맞춰 `collectors/collect_subway_realtime.py` 로 정리
- **폴더별 README 정비** (collectors·config·scripts·forecast)

### v0.1 — 2026-07-26
- **실시간 도시데이터 수집기(`collect_citydata.py`) 서버 가동** — OCI 도쿄 서버에서 cron 자동 수집(관문 환승역 12곳, 러시 10분/그 외 30분, 하루 864회, 안전한도 950)

---

## 팀과 논의할 것
- [ ] 예보 출력 기준 — 혼잡 등급 / 인구수 / 승하차
- [ ] 대상역 — 관문 기준 vs 접근성 취약 기준
- [ ] 서울교통공사 혼잡도(DATA_GO_KR_KEY)를 기준선으로 쓸지
- [ ] **파일 → Oracle DB 이관** (아래 'Oracle 연결' 절)
- [ ] 활용사례(갤러리) 등록 → 호출 한도 상향
