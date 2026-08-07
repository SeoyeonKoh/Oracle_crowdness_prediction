
# SPARK + IPO

SPARK(Spec, Plan, Archive, Research, Knowhow) 명령 처리 규칙 체계와 IPO(Input, Proc, Output) 데이터 처리 흐름을 결합한 AI Agentic 만능 명령 및 데이터 처리 시스템이다.

이 문서(`AGENTS.md`)는 **Codex CLI · Gemini CLI · Antigravity 2.0 · Antigravity CLI**용 프로젝트 지침이다. Claude Code는 별도의 [`CLAUDE.md`](CLAUDE.md)를 읽는다.

### SPARK — 명령 처리 규칙
```
proc/
├── spec/       # S — 설계 명세
├── plan/       # P — 작업 계획 (간결한 작업 메모)
├── archive/    # A — 비활성 문서 (AI 열람 금지)
├── research/   # R — AI 조사·분석 결과
└── knowhow/    # K — 재사용 프롬프트 (AI 열람 금지)
```

### IPO — 데이터 처리 흐름
```
project/
├── input/              # I — 입력 데이터, 참고 데이터
├── proc/               # P — 명령 처리 규칙
├── output/             # O — 출력 데이터
├── data/               # 개발용 영구 데이터 (SQLite 등)
└── src/                # 소스 코드
```

---

## 규칙
- 복잡한 작업 요청 시 `proc/plan/`에 계획 문서를 작성하고, 업데이트하면서 개발한다
- 명세가 변경되면 `proc/spec/`의 관련 문서를 업데이트한다
- 사전 조사가 필요하면 `proc/research/`에 리서치 문서를 작성한다
- `input/`은 명시적 지시 없이 수정하지 않는다
- SQLite와 프로젝트 개발용 영구 데이터는 `data/`에 저장한다
- `proc/archive/`는 명시적 지시 없이 열람하지 않는다
- `proc/knowhow/`는 명시적 지시 없이 열람하지 않는다
- 기술 스택·프로젝트 유형은 유저 지시 또는 `input/`·`proc/spec/`을 따른다. 명시되지 않았으면 임의로 정하지 말고 유저에게 확인한다 (웹·모바일(React Native)·데스크탑(Electron)·데이터처리(Node/Python)·라이브러리 등 무엇이든 될 수 있다)


## Agent Skills

스킬은 **`.agents/skills/<name>/SKILL.md`** 에 정의한다 (agentskills.io 오픈 표준). Codex CLI 와 Gemini CLI 가 이 위치를 자동 인식한다 — 저장소에 포함되며 별도 설치가 필요 없다.

| 플랫폼 | 스킬 위치 | 호출 방식 |
|--------|-----------|-----------|
| Codex CLI | `.agents/skills/<name>/SKILL.md` | `/skills` 또는 `$` 멘션, 설명(description) 일치 시 자동 호출 |
| Gemini CLI | `.agents/skills/<name>/SKILL.md` | `/<name>` 또는 자연어 트리거 |

> Claude Code 의 스킬은 별도 위치 `.claude/skills/<name>/SKILL.md` 에 있다 (Claude 는 `.agents/`를 읽지 않는다). Claude 측은 `CLAUDE.md` 참조.
> Codex 의 `~/.codex/prompts/` 커스텀 프롬프트는 저장소로 공유되지 않으므로 이 템플릿은 사용하지 않는다. 저장소 공유 스킬은 `.agents/skills/` 로 통일한다.

### 제공 스킬

| 스킬 | 설명 |
|------|------|
| `/init-project` | 유저 의도에 맞춰 카테고리(웹앱기초(기본값)/웹앱고급/모바일앱/데스크톱앱/3D·2D 게임) 또는 일반 Node 프로젝트로 폴더구조·기술스택 초기화 |
| `/create-spec` | 명세(Spec)를 `proc/spec/`에 항목별 문서로 작성 |
| `/update-plan` | `proc/plan/`에 작업 계획 생성/업데이트 |
| `/update-spec` | 명세·업무규칙 변경 시 `proc/spec/` 문서 업데이트 (FSD/rules/architecture/nfr/user-flow/api/work-rules/decisions 카테고리 + ADR 처리) |
| `/update-research` | 구현 전 사전 조사·연구 문서를 `proc/research/`에 작성 (방안 비교 + 권장안 + 구현 제안) |

스킬 추가/수정 시 두 위치(공용 `.agents/skills/`, Claude `.claude/skills/`)를 모두 동기화한다.


## Hooks — 프롬프트 로깅

유저 프롬프트는 입력 시점에 `proc/archive/prompts/YYYY-MM-DD.md` 로 자동 기록된다. 각 훅은 stdin JSON 의 `cwd` 로 로그 경로를 해석한다.

| 플랫폼 | 설정 파일 | 이벤트 |
|--------|-----------|--------|
| Codex CLI | `.codex/config.toml` | `UserPromptSubmit` |
| Gemini CLI | `.gemini/settings.json` | `BeforeAgent` |
| Claude Code | `.claude/settings.json` | `UserPromptSubmit` |

Codex는 Bash/PowerShell을 운영체제에 맞게 선택하고, Claude는 Bash, Gemini CLI/Antigravity는 Node.js 훅을 사용한다. Windows·macOS·Linux에서 별도 전환 없이 동작한다.

> Gemini CLI 는 기본적으로 `GEMINI.md` 를 읽으므로, 이 `AGENTS.md` 를 읽도록 `.gemini/settings.json` 의 `context.fileName` 에 `AGENTS.md` 를 지정해 두었다.
