# 유저 프롬프트 로깅 훅 (Windows / PowerShell)
# Claude Code(UserPromptSubmit) · Codex CLI(UserPromptSubmit) · Gemini CLI(BeforeAgent) 공용.
# 훅 JSON 을 stdin 으로 받아 유저 프롬프트를 proc/archive/prompts/YYYY-MM-DD.md 에 기록한다.
# 세 에이전트의 필드 차이를 흡수하므로 어느 CLI에서 호출해도 동일하게 동작한다.

$ErrorActionPreference = 'SilentlyContinue'

# stdin 으로 들어오는 JSON 읽기 (UTF-8 명시 디코딩 — 콘솔 코드페이지 무관하게 한글 보존)
$reader = New-Object System.IO.StreamReader([Console]::OpenStandardInput(), [System.Text.Encoding]::UTF8)
$raw = $reader.ReadToEnd()
if ([string]::IsNullOrWhiteSpace($raw)) { exit 0 }

try { $data = $raw | ConvertFrom-Json } catch { exit 0 }

# --- 프롬프트 추출 (에이전트별 필드 차이 흡수) ---
$prompt = [string]$data.prompt
if ([string]::IsNullOrEmpty($prompt)) {
    # 일부 Gemini 버전: llm_request.messages 안에 들어온다
    try {
        $msgs = $data.llm_request.messages
        if ($msgs) {
            $last = ($msgs | Where-Object { $_.role -eq 'user' } | Select-Object -Last 1)
            if ($last) {
                if ($last.content -is [string]) { $prompt = [string]$last.content }
                else { $prompt = (($last.content | ForEach-Object { $_.text }) -join '') }
            }
        }
    } catch {}
}
if ([string]::IsNullOrWhiteSpace($prompt)) { exit 0 }

# --- 프로젝트 루트 결정 (stdin cwd → env → 현재 위치 순) ---
$root = [string]$data.cwd
if ([string]::IsNullOrEmpty($root)) { $root = [string]$data.project_dir }
if ([string]::IsNullOrEmpty($root)) {
    foreach ($v in 'CLAUDE_PROJECT_DIR','CODEX_PROJECT_DIR','GEMINI_PROJECT_DIR') {
        $e = [Environment]::GetEnvironmentVariable($v)
        if (-not [string]::IsNullOrEmpty($e)) { $root = $e; break }
    }
}
if ([string]::IsNullOrEmpty($root)) { $root = (Get-Location).Path }

$session = [string]$data.session_id
if ([string]::IsNullOrEmpty($session)) { $session = 'unknown' }

$logDir = Join-Path $root 'proc/archive/prompts'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

$logFile  = Join-Path $logDir ((Get-Date -Format 'yyyy-MM-dd') + '.md')
$time     = Get-Date -Format 'HH:mm:ss'
$sessHead = if ($session.Length -ge 8) { $session.Substring(0, 8) } else { $session }

$entry = "`r`n## $time | session: $sessHead`r`n$prompt"
Add-Content -Path $logFile -Value $entry -Encoding UTF8

# stdout 은 비워 둔다 (Claude UserPromptSubmit 는 stdout 을 컨텍스트에 주입하므로)
exit 0
