#!/usr/bin/env bash
# 수집본 → realtime.json 가공 → OCI Object Storage 업로드.
# cron 이 10분마다 부른다. 수집(:00,:10,…) 직후를 피해 2분 늦게 도는 것을 권장.
#
# PAR URL 은 파일에서 읽는다(cron 은 셸 환경변수를 물려받지 않으므로).
#   /home/ubuntu/collector/config/par_write_url.txt   ← 쓰기 PAR, 한 줄
#   권한은 600 으로 둘 것: chmod 600 config/par_write_url.txt
#
# 업로드 없이 가공만 확인하려면:  SKIP_UPLOAD=1 bash scripts/publish_realtime.sh
set -euo pipefail

ROOT=/home/ubuntu/collector
OUT="$ROOT/data/realtime.json"
PAR_FILE="$ROOT/config/par_write_url.txt"

cd "$ROOT"
python3 scripts/build_realtime_json.py --out "$OUT"

if [ "${SKIP_UPLOAD:-}" = "1" ]; then
  echo "[publish] SKIP_UPLOAD=1 — 업로드 생략"
  exit 0
fi

if [ ! -s "$PAR_FILE" ]; then
  echo "[publish] PAR URL 없음 ($PAR_FILE) — 가공만 하고 업로드는 건너뜁니다." >&2
  exit 0
fi

PAR_URL="$(tr -d ' \t\r\n' < "$PAR_FILE")"
[[ "$PAR_URL" == */ ]] || PAR_URL="$PAR_URL/"

# 항상 같은 이름으로 덮어쓴다 → 앱은 고정 URL 하나만 알면 된다.
code=$(curl -sS -X PUT --fail-with-body \
        -H "Content-Type: application/json" \
        -H "Cache-Control: max-age=60" \
        --upload-file "$OUT" \
        -w '%{http_code}' -o /dev/null \
        "${PAR_URL}realtime.json")

echo "[publish] 업로드 HTTP $code · $(date '+%H:%M:%S')"
