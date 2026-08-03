# scripts/ — 서버 설정·자동화

## `setup_server.sh` — 수집 서버 초기 설정 (우분투 24.04)
서버에 SSH 접속 후 **한 번만** 실행. 여러 번 실행해도 안전(이미 된 항목은 건너뜀).

**하는 일**
1. 시간대를 `Asia/Seoul` 로 설정 (안 하면 러시아워 cron이 9시간 어긋남) + `cron` 재시작
2. python3·git 설치
3. 깃허브에서 코드 받기 (`~/collector`) — 스크립트 상단 `GITHUB_REPO` 에 저장소 URL 입력
4. `config/APIkey.py` 서식 생성 (키는 직접 입력)
5. cron 등록 (러시아워 10분 / 그 외 30분 간격)

**사용법**
```bash
# 맥북(프로젝트 루트)에서 서버로 전송
scp -i ~/.ssh/collector.key scripts/setup_server.sh ubuntu@서버IP:~/
# 서버에서 실행
bash ~/setup_server.sh
```

⚠️ **함정**: 시간대를 바꿨으면 `sudo systemctl restart cron` 필수 (cron 데몬은 시작 시점 시간대를 계속 씀). 스크립트가 자동 처리하지만 수동 변경 시 주의.
