# 실시간 지하철 도착정보 수집기 — 서버 실행 안내

혼잡 경보 기능에서 **배차 간격 표본**을 모으는 수집기입니다.
도시데이터 수집기와 **인증키가 다르고 한도도 별개**라 서로 영향이 없습니다.

---

## 1. 무엇을 받아오나

한 번 실행에 **4번 호출**합니다.

| 대상 | 서비스 |
|---|---|
| 2호선 열차 위치 | `realtimePosition` |
| 4호선 열차 위치 | `realtimePosition` |
| 왕십리 도착정보 | `realtimeStationArrival` |
| 동대문역사문화공원 도착정보 | `realtimeStationArrival` |

응답은 **가공 없이 원본 JSON 그대로** 저장합니다.
저장 위치: `data/realtime/20260803_081500_arrival_왕십리.json` (파일명에 수집 시각 포함, 덮어쓰지 않음)

---

## 2. 인증키

⚠️ **도시데이터에 쓰는 일반 인증키가 아닙니다.**
열린데이터광장은 인증키가 두 종류이고, 이건 **"실시간 지하철 인증키"** 쪽입니다.

- 주소: `swopenapi.seoul.go.kr` (일반 API는 `openapi.seoul.go.kr`)
- 한도: **하루 1,000회 · 일반 키와 별도**

**키는 GitHub에 올리지 않았습니다.** 서버에서 아래 파일을 직접 만들어 주세요.

```bash
cd ~/collector
cat > APIkey.py << 'EOF'
SUBWAY_KEY = "여기에_실시간지하철_인증키"
EOF
```

키 문자열은 별도로 전달드리겠습니다.

---

## 3. cron 등록

도시데이터 수집기와 같은 주기로 맞췄습니다.

```
*/10 7-9,17-19 * * * cd ~/collector && /usr/bin/python3 fetch_realtime.py >> realtime.log 2>&1
*/30 0-6,10-16,20-23 * * * cd ~/collector && /usr/bin/python3 fetch_realtime.py >> realtime.log 2>&1
```

**하루 호출량 약 288회** (72주기 × 4호출) — 한도 1,000회의 30% 수준입니다.

---

## 4. 정상 동작 확인

```bash
tail -20 realtime.log                  # 최근 로그
ls -lh data/realtime/ | tail           # 파일이 쌓이고 있는가
ls data/realtime/ | wc -l              # 하루 정상 = 72주기 × 4개 = 288개 근처
```

로그는 이렇게 찍힙니다.

```
[2026-08-03 08:15:00] [realtime] 수집 시작 (4건)
  [성공] position_2호선 → 20260803_081500_position_2호선.json · realtimePositionList 40건
  ...
[2026-08-03 08:15:02] [realtime] 완료: 성공 4 / 실패 0 · 저장 /home/ubuntu/collector/data/realtime
```

**실패가 계속 4/4로 나오면** 인증키가 일반 키로 들어갔을 가능성이 큽니다.

---

## 5. 참고

- 새벽 시간대(운행 종료 후)는 응답이 비어 있는 게 정상입니다
- 파일명에 한글이 들어갑니다 (`arrival_왕십리`). Ubuntu에서는 문제없습니다
- **`data/` 폴더는 지우지 말아 주세요.** 표본이 쌓일수록 판정이 정확해집니다
- 파일이 많아져도 용량은 작습니다 (하루 수 MB 수준)
