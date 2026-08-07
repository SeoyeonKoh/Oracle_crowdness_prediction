# Seoul Open API 수집기

## 준비
```bash
pip install requests
export SEOUL_OPENAPI_KEY="발급받은_인증키"
```

## 실행
```bash
# 전체 서비스 한 번에 수집 (data/ 폴더에 누적 append)
python collectors/seoul_open_api_collector.py

# 특정 서비스만, 더 많은 행 수로
python collectors/seoul_open_api_collector.py --service getFcLckr --end 1000
```

## 동작 방식
- `config/seoul_api_config.py`의 `SERVICES`에 등록된 서비스마다 API를 호출해서 `data/<파일명>.csv`에 이어붙인다.
- 이전 실행과 **완전히 동일한 내용의 행**은 다시 추가하지 않는다. 값이 바뀐 경우(예: 승강기 상태 변경)는 새 행으로 `collected_at` 타임스탬프와 함께 기록된다.
- `SeoulMetroFaciInfo`(승강기), `getWksnRstrm`(장애인화장실), `getNtceList`(알림정보) 3개는 실제 응답으로 확인한 필드로 저장된다.
- 나머지 9개(`getFcLckr`, `getWksnMvnwlk` 등)는 **실제 응답을 아직 못 봐서** 서비스명에서 추정한 한글 라벨만 달아뒀고, XML 구조는 row/item 반복 태그를 자동 감지해서 그대로 뽑아온다. 한 번 실행해서 `data/` 폴더에 CSV가 생기면 실제 컬럼명을 눈으로 확인하고 `config/seoul_api_config.py`의 `label`을 정확히 고쳐주면 된다.

## 매일 자동 수집하고 싶다면
GitHub Actions로 스케줄 실행이 가능하다 (예: 매일 새벽에 `--end 1000`으로 실행 후 결과를 커밋). 필요하면 워크플로 파일도 만들어줄 수 있음 — 이 경우 `SEOUL_OPENAPI_KEY`는 저장소 Settings → Secrets에 등록해서 쓴다 (코드에 절대 노출 금지).
