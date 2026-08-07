#!/bin/bash
# 유저 프롬프트 로깅 훅 (macOS / Linux / Git Bash) — python3 필요
# Claude Code(UserPromptSubmit) · Codex CLI(UserPromptSubmit) · Gemini CLI(BeforeAgent) 공용.
# 훅 JSON 을 stdin 으로 받아 유저 프롬프트를 proc/archive/prompts/YYYY-MM-DD.md 에 기록한다.

INPUT=$(cat)

# 프롬프트·세션·cwd 를 한 번에 추출 (에이전트별 필드 차이 흡수)
read_field() {
  echo "$INPUT" | python3 -c "
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    print(''); sys.exit(0)
key = '$1'
if key == 'prompt':
    v = d.get('prompt')
    if not v:
        # 일부 Gemini 버전: llm_request.messages
        msgs = (d.get('llm_request') or {}).get('messages') or []
        users = [m for m in msgs if m.get('role') == 'user']
        if users:
            c = users[-1].get('content')
            if isinstance(c, str):
                v = c
            elif isinstance(c, list):
                v = ''.join(p.get('text','') for p in c if isinstance(p, dict))
    print(v or '')
elif key == 'cwd':
    print(d.get('cwd') or d.get('project_dir') or '')
else:
    print(d.get(key) or '')
" 2>/dev/null
}

PROMPT=$(read_field prompt)
SESSION=$(read_field session_id)
ROOT=$(read_field cwd)

if [ -z "$PROMPT" ]; then exit 0; fi
if [ -z "$ROOT" ]; then ROOT="${CLAUDE_PROJECT_DIR:-${CODEX_PROJECT_DIR:-${GEMINI_PROJECT_DIR:-$(pwd)}}}"; fi
if [ -z "$SESSION" ]; then SESSION="unknown"; fi

LOG_DIR="$ROOT/proc/archive/prompts"
mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/$(date +%Y-%m-%d).md"

{
  echo ""
  echo "## $(date +%H:%M:%S) | session: ${SESSION:0:8}"
  echo "$PROMPT"
} >> "$LOG_FILE"

exit 0
