# Hooks — 프롬프트 로깅 (Claude · Codex · Gemini 공통)

유저가 프롬프트를 입력하는 시점에 그 내용을 `proc/archive/prompts/YYYY-MM-DD.md` 에 자동 기록한다. 세 에이전트가 **동일한 스크립트**를 호출하며, 스크립트는 stdin 으로 들어오는 훅 JSON 에서 `prompt` 와 `cwd` 를 읽어 로그 경로를 스스로 결정한다.

## 스크립트

| 파일 | 플랫폼 | 비고 |
|------|--------|------|
| `log_user_input.ps1` | Windows (PowerShell)      | 추가 의존성 없음. stdin 을 UTF-8 로 디코딩(한글 보존) |
| `log_user_input.sh`  | macOS / Linux / Git Bash | `python3` 필요 |
| `log_user_input.cjs` | Windows / macOS / Linux  | Gemini CLI/Antigravity의 Node.js 사용 |

Claude와 Codex는 플랫폼별 셸 스크립트를 사용하고, Gemini CLI/Antigravity는 `.gemini/hooks/log_user_input.cjs`를 사용한다.

> 각 에이전트는 **저장소 루트에서 실행**해야 `-File` 상대경로와 로그 경로가 올바르게 해석된다.

## 에이전트별 설정

### Claude Code — `.claude/settings.json`
```json
{
  "hooks": {
    "UserPromptSubmit": [
      { "hooks": [ { "type": "command", "command": "bash \"${CLAUDE_PROJECT_DIR}/.claude/hooks/log_user_input.sh\"" } ] }
    ]
  }
}
```

### Codex CLI — `.codex/config.toml`
```toml
[features]
hooks = true

[[hooks.UserPromptSubmit]]

[[hooks.UserPromptSubmit.hooks]]
type = "command"
command         = "bash .codex/hooks/log_user_input.sh"
command_windows = "powershell -NoProfile -ExecutionPolicy Bypass -File .codex/hooks/log_user_input.ps1"
timeout = 30
```
> Codex 는 `command`(macOS/Linux)와 `command_windows`(Windows)를 자동 분기한다. POSIX 명령은 `bash`로 스크립트를 호출하므로 파일 실행 권한에 의존하지 않는다.

### Gemini CLI — `.gemini/settings.json`
```json
{
  "context": { "fileName": ["AGENTS.md", "GEMINI.md"] },
  "hooks": {
    "BeforeAgent": [
      { "hooks": [ { "name": "log-user-prompt", "type": "command", "command": "node .gemini/hooks/log_user_input.cjs", "timeout": 10000 } ] }
    ]
  }
}
```
> `context.fileName` 은 Gemini 가 `AGENTS.md` 를 읽도록 하는 설정이다 (기본값은 `GEMINI.md`).

## 플랫폼 동작

- Claude Code는 기본 제공되는 `bash` 명령으로 같은 `.sh` 훅을 macOS·Linux·Windows에서 실행한다.
- Codex CLI는 macOS·Linux에서 `bash` + `.sh`, Windows에서 PowerShell + `.ps1`을 자동 선택한다.
- Gemini CLI/Antigravity 2.0·CLI는 자체 실행 환경의 Node.js로 같은 훅을 Windows·macOS·Linux에서 실행한다.

## 동작 확인

- 프롬프트를 한 번 입력한 뒤 `proc/archive/prompts/<오늘날짜>.md` 에 `## HH:MM:SS | session: ...` 항목과 프롬프트가 추가됐는지 확인한다.
- 기록되지 않으면: (1) 에이전트를 저장소 루트에서 실행했는지, (2) Windows의 PowerShell 실행 정책(스크립트는 `-ExecutionPolicy Bypass` 로 우회), (3) 설정 파일을 에이전트가 다시 읽도록 재시작했는지 확인한다.
