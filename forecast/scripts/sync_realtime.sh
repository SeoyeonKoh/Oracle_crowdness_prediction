#!/usr/bin/env bash
# 서버의 실시간 수집본(subway_realtime/*.jsonl)을 로컬 data/ 로 동기화(읽기 전용 복사).
# 서버는 cron으로 계속 스냅샷을 쌓고, 로컬은 이걸 내려받아 배차간격을 추출한다.
#
# 사용:  bash scripts/sync_realtime.sh
# 환경변수로 접속정보 덮어쓰기 가능:
#   COLLECTOR_KEY  (기본 ~/.ssh/collector.key)
#   COLLECTOR_HOST (기본 ubuntu@158.179.178.222)
set -euo pipefail

KEY="${COLLECTOR_KEY:-$HOME/.ssh/collector.key}"
HOST="${COLLECTOR_HOST:-ubuntu@158.179.178.222}"
DEST="$(cd "$(dirname "$0")/.." && pwd)/data/subway_realtime"

mkdir -p "$DEST"
echo "[sync] $HOST:~/collector/data/subway_realtime/  →  $DEST"
scp -i "$KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new \
    "$HOST:~/collector/data/subway_realtime/*.jsonl" "$DEST/"
echo "[sync] 완료. 다음: python -m src.loading.realtime"
