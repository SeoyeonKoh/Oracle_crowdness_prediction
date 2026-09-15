# collectors/ — 실시간 데이터 수집기

소급 조회가 어려운 실시간 데이터를 주기적으로 저장하는 수집기입니다. 실제 API 키는 `config/APIkey.py` 또는 동일 이름의 환경변수에서 읽습니다.

## 파일

| 파일 | 역할 |
|---|---|
| `collect_citydata.py` | 서울 실시간 도시데이터를 관문/환승역 중심으로 수집 |
| `collect_subway_realtime.py` | 실시간 지하철 위치·도착 정보를 수집 |
| `facility_collector.py` | 지하철 편의시설 위치/상태 데이터를 수집 |

## 실행 예시

```bash
pip3 install -r requirements.txt
cp config/APIkey_example.py config/APIkey.py
python3 collectors/collect_citydata.py
python3 collectors/collect_subway_realtime.py
```

## 저장/공개 기준

- 원본 실시간 로그(`*.jsonl`)와 실행 로그(`*.log`, `logs/`)는 `.gitignore`로 제외합니다.
- 공개 가능한 정적 CSV와 빈 키 템플릿만 GitHub에 올립니다.
- push 전에는 `git status`로 `config/APIkey.py`와 실시간 로그가 포함되지 않았는지 확인하세요.
