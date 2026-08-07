#!/usr/bin/env bash
# 서버 citydata에서 LIVE_SUB_PPLTN(실시간 승하차)·인구만 추출해 로컬 CSV로 가져온다.
# 원본 jsonl(하루 수십 MB)은 내려받지 않고 서버에서 필요한 필드만 뽑아 스트리밍한다.
# 사용:  bash scripts/sync_live_sub.sh   →  data/live_sub_ppltn.csv
set -euo pipefail
KEY="${COLLECTOR_KEY:-$HOME/.ssh/collector.key}"
HOST="${COLLECTOR_HOST:-ubuntu@158.179.178.222}"
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
ssh -i "$KEY" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$HOST" \
    "cd ~/collector && python3 -" < "$ROOT/scripts/extract_livesub.py" \
    > "$ROOT/data/live_sub_ppltn.csv"
echo "[sync] data/live_sub_ppltn.csv  ($(wc -l < "$ROOT/data/live_sub_ppltn.csv") 행)"
