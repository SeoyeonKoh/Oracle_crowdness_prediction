# config/ — 인증키·설정

인증키는 **발급처 기준**으로 이름 붙인다(`{발급처}_{종류}_KEY`). 열린데이터광장은 일반 인증키 하나로 여러 API를 호출하므로 데이터셋마다 키를 두지 않는다.

## 파일

### `APIkey_example.py` — 키 서식 (깃허브에 올라감, 값 비어 있음)
어떤 키가 필요한지 팀원에게 알려주는 빈 템플릿. 이 파일을 복사해 실제 키 파일을 만든다:
```bash
cp config/APIkey_example.py config/APIkey.py
```

### `APIkey.py` — 실제 키 (⚠️ 깃허브에 안 올라감, `.gitignore` 차단)
발급받은 키를 채워 넣는다. **코드에 키를 직접 적지 말 것.**

## 등록된 키
| 변수 | 발급처 | 쓰는 곳 | 상태 |
|------|--------|---------|------|
| `SEOUL_OPENDATA_GENERAL_KEY` | data.seoul.go.kr 일반 | `collect_citydata.py` | 사용 중 |
| `SEOUL_OPENDATA_SUBWAY_KEY` | data.seoul.go.kr 실시간지하철 | `collect_subway_realtime.py` | 사용 중 |
| `DATA_GO_KR_KEY` | data.go.kr | 서울교통공사 혼잡도 등 | 예정 |
| `SKT_PUZZLE_APP_KEY` | SKT 지오비전 | 열차/칸 혼잡(유료 검토) | 검토 |

각 수집기는 `config/APIkey.py` 에서 해당 변수를 import 하고, 없으면 동일 이름의 환경변수를 fallback 으로 읽는다.
