# 지하철 접근성 예보 — 데이터 수집

과거 패턴이 있어야 예보를 만들 수 있는데, 서울시 실시간 도시데이터는
최근 12시간과 향후 12시간 예측만 준다. **소급 조회가 불가능함.**
그래서 직접 스냅샷을 찍어 쌓는다.

최대한 일찍 시작하여 최대한 많은 데이터를 얻는 것이 목표!!

---

## 폴더 구조

```
collector/
├── collectors/              데이터를 가져오는 코드
│   └── collect_citydata.py  실시간 도시데이터 수집기
├── config/                  인증키와 설정
│   ├── APIkey_example.py    인증키 서식 (깃허브에 올라감)
│   └── APIkey.py            실제 인증키 (깃허브에 안 올라감)
├── scripts/                 서버 설정·자동화 스크립트
│   └── setup_server.sh
├── logs/                    실행 로그 (깃허브에 안 올라감)
├── .gitignore
├── requirements.txt
├── README.md
└── data/
    └── citydata/
        ├── 2026-07-26.jsonl      날짜별 수집 결과
        └── call_counter.json     오늘 호출 수
```

수집기는 자기 위치(collectors/) 기준으로 프로젝트 루트를 계산하므로
어느 폴더에서 실행해도 저장 경로가 어긋나지 않는다.

수집기가 늘어나면 같은 규칙으로 붙인다.

| 데이터 | 스크립트 | 저장 위치 | 필요 키 |
|---|---|---|---|
| 실시간 도시데이터 | `collectors/collect_citydata.py` | `data/citydata/` | `SEOUL_OPENDATA_GENERAL_KEY` |
| (예정) 지하철 도착정보 | `collectors/collect_subway_arrival.py` | `data/subway_arrival/` | `SEOUL_OPENDATA_SUBWAY_KEY` |
| (예정) 서울교통공사 혼잡도 | `collectors/collect_subway_congestion.py` | `data/subway_congestion/` | `DATA_GO_KR_KEY` |

### 이름 규칙

- 인증키: `{발급처}_{키 종류}_KEY`
  데이터셋 이름이 아니라 발급처 기준이다. 열린데이터광장은 데이터셋마다
  키를 주지 않고, 일반 인증키 하나로 여러 API를 호출한다.
- 수집 코드: `collectors/collect_{데이터}.py`
- 설정 파일: `config/`
- 서버 자동화: `scripts/`
- 저장 폴더: `data/{데이터}/`
- 로그: `logs/{데이터}.log`
- 각 레코드에 `source` 필드를 넣어 어느 수집기가 만들었는지 남긴다.
  나중에 여러 소스를 합칠 때 필요하다.

### 깃허브 공개 기준

기준은 하나: **인터넷에 공개돼도 괜찮은가?**

- 올라감: 코드, `scripts/`, `config/APIkey_example.py`(빈 서식), 문서
- 안 올라감(.gitignore 자동 차단): `config/APIkey.py`, `data/`, `logs/`, `wallet/`
- SSH 키(`collector.key`)는 애초에 저장소 폴더에 두지 않는다
- push 전 `git status` 로 APIkey.py 가 목록에 없는지 확인하는 습관

---

## 현재 설정

| 항목 | 값 |
|---|---|
| 상태 | **가동 중** — OCI 도쿄 서버(collector-server)에서 cron 자동 수집 |
| 대상 장소 | 경기도민 유입 관문 환승역 12곳 |
| 수집 간격 | 러시아워(07~09, 17~19시) 10분 / 그 외 30분 |
| 하루 호출 | 864회 |
| 안전 한도 | 950회 (스크립트가 스스로 세다가 멈춤) |

대상 12곳: 서울역, 사당역, 고속터미널역, 신도림역, 잠실역, 왕십리역,
청량리 제기동 일대, 강남역, 종로·청계 관광특구, 총신대입구(이수)역,
김포공항, 연신내역

**확정이 아니다.** 승강기 가동현황이 2주쯤 쌓이면 접근성 취약 역으로
교체를 검토한다. 그때까지 쌓인 데이터도 버려지지 않는다.

일일 한도가 공개되지 않아 1,000회를 가정한 보수적 설정이다.
활용사례(갤러리) 등록으로 제한이 풀리면 대상을 늘리고 간격을 줄인다.

---

## 처음 설치

```bash
pip3 install -r requirements.txt
```

(맥은 `pip` 가 아니라 `pip3`. 서버(우분투 24)에서는
`pip3 install -r requirements.txt --break-system-packages`)

인증키 파일을 만든다.

```bash
cp config/APIkey_example.py config/APIkey.py
```

`config/APIkey.py` 를 열어 발급받은 키를 채운다.

```python
SEOUL_OPENDATA_GENERAL_KEY = "발급받은키"
```

`config/APIkey.py` 는 `.gitignore` 에 있어 깃허브에 올라가지 않는다.
**키를 코드에 직접 적지 말 것.**

## 한 번 실행해 보기

```bash
python3 collectors/collect_citydata.py
```

(pyenv 환경에서는 `python` 이 아니라 `python3`)

성공하면 이렇게 나온다.

```
[2026-07-26 15:20:03] [citydata] 수집 서울역 → 보통 (58000~60000명, 기준시각 2026-07-26 15:05)
[2026-07-26 15:20:12] [citydata] 완료: 성공 12 / 실패 0 / 9.4초 소요 · 오늘 누적 12/950회
```

`data/citydata/2026-07-26.jsonl` 이 생기고, 한 줄이 한 장소의 기록이다.

## 자동 반복 걸기 (서버)

**권장: 설치 스크립트 사용.** 폴더 구조 생성, 시간대 설정, cron 등록·재시작을
한 번에 처리하고, 여러 번 실행해도 안전하다.

```bash
# [맥북] 전송 (프로젝트 루트에서)
scp -i ~/.ssh/collector.key scripts/setup_server.sh ubuntu@서버IP:~/
# [서버] 실행
bash ~/setup_server.sh
```

직접 걸 때는 `crontab -e` 에 두 줄. 러시아워는 촘촘하게, 나머지는 성기게.

```
*/10 7-9,17-19 * * * cd /home/ubuntu/collector && /usr/bin/python3 collectors/collect_citydata.py >> logs/citydata.log 2>&1
*/30 0-6,10-16,20-23 * * * cd /home/ubuntu/collector && /usr/bin/python3 collectors/collect_citydata.py >> logs/citydata.log 2>&1
```

- python3 경로가 다를 수 있다. `which python3` 로 확인
- cron은 서버 재부팅 후 자동으로 다시 시작된다
- **⚠️ 시간대를 바꿨다면 cron 재시작 필수.** cron 데몬은 시작 시점의
  시간대를 계속 쓴다. 안 하면 러시아워 예약이 9시간 어긋난 시각에 돈다.
  ```bash
  sudo timedatectl set-timezone Asia/Seoul
  sudo systemctl restart cron
  ```

등록 확인:

```bash
crontab -l
```

## 잘 돌고 있는지 확인

```bash
ls -l data/citydata/                    # 날짜별 파일이 커지고 있어야 한다
tail -30 logs/citydata.log              # 최근 수집 기록
wc -l data/citydata/*.jsonl             # 날짜별 누적 건수
cat data/citydata/call_counter.json     # 오늘 호출 수
```

하루 정상 동작 시 줄 수는 `장소 수 × 72` 근처가 된다. (12곳이면 864줄)

`logs/citydata.log` 는 cron이 처음 실행될 때 생긴다.
파일이 없으면 오류가 아니라 "cron이 아직 안 돌았다"는 신호다.

## 멈추기 / 다시 시작하기

```bash
crontab -e     # 해당 줄 맨 앞에 # 를 붙이면 중단, 지우면 재개
```

---

## 저장되는 내용

| 필드 | 설명 |
|---|---|
| `source` | 어느 수집기가 만든 레코드인지 (`seoul_citydata`) |
| `collected_at` | **우리가 호출한 시각** |
| `ppltn_base_time` | **서울시가 값을 잰 시각** — 약 15분 전이다 |
| `requested_poi_cd` | 우리가 요청한 POI 코드 |
| `area_cd` / `area_nm` | 응답에 담겨 온 장소 코드·이름 |
| `congest_lvl` | 혼잡도 등급 (여유 / 보통 / 약간 붐빔 / 붐빔) |
| `congest_msg` | 혼잡도 설명 문구 |
| `ppltn_min` / `ppltn_max` | **추정 인구 범위** |
| `ppltn_forecast` | 서울시의 향후 12시간 예측 |
| `raw_response` | **응답 원본 전체** |

### 왜 이렇게 저장하나

**시각을 두 개 남기는 이유** — 실시간 인구는 집계 후 15분 뒤에 제공된다.
요일·시간대 패턴을 만들 때는 `ppltn_base_time` 을 써야 한다.
`collected_at` 으로 집계하면 전체가 15분씩 밀린다.

**인구수를 함께 남기는 이유** — 혼잡도 등급은 그 장소의 최근 28일 평균 대비
비율이다. 장소끼리 비교할 수 없고 기준선도 계속 움직인다.
등급만 저장하면 나중에 기준을 바꿔 다시 계산할 수 없다.

**예측값을 함께 남기는 이유** — 우리가 쌓은 실제값과 대조하면
"서울시 예측이 얼마나 맞았는지"를 검증할 수 있다. 발표의 근거가 된다.

**원본을 통째로 남기는 이유** — 응답에는 지하철 도착·승하차, 버스, 주차장,
따릉이, 날씨, 문화행사가 모두 들어 있다. 특히 지하철 항목에는
**서울교통공사 교통약자 이용시설(승강기) 가동현황**이 포함된다.
지금 이 순간에도 엘리베이터 고장 이력이 쌓이고 있고, 이건 소급 조회가 불가능하다.

---

## 실패했을 때의 동작

- 한 장소가 실패해도 다음 장소로 넘어간다
- 재시도는 1회까지만 (폭주 방지)
- 실패는 로그에만 남기고 스크립트는 정상 종료한다
- 다음 주기에 cron이 다시 실행한다

**몇 번 빠지는 것은 허용한다. 스케줄러가 죽는 것이 진짜 사고다.**

---

## 알려진 함정 (실전에서 겪은 것)

- **시간대 변경 후 cron 재시작 필수** — 위 자동 반복 절 참고
- **scp/ssh 는 맥북 창에서, 나머지는 서버 창에서** — 프롬프트로 구분:
  `%` 로 끝나면 맥북, `ubuntu@...$` 면 서버
- **공백이 든 경로는 따옴표로 감싼다** — 또는 Finder에서 터미널로 드래그
- **pyenv 환경에서는 `python3` / `pip3`** — `python` 은 command not found
- **대중교통 승하차는 01~05시 미제공** — 그 시간대 항목이 비어도 정상

---

## 팀과 논의할 것

- [ ] 예보의 출력 — 혼잡도 등급인가, 인구수인가, 승하차 인원인가
- [ ] 대상역을 관문 기준으로 갈지 접근성 취약 기준으로 갈지
- [ ] 활용사례(갤러리) 등록 — 실제 구동 URL 확보 시점
- [ ] 서울교통공사 혼잡도정보를 기준선으로 쓸지
- [ ] 파일 → Oracle DB 이관 시점
- [ ] 서버 디스크 여유 (원본을 통째로 쌓으므로 용량이 는다)
