
# SPARK + IPO

SPARK(Spec, Plan, Archive, Research, Knowhow) 명령 처리 규칙 체계와 IPO(Input, Proc, Output) 데이터 처리 흐름을 결합한 AI Agentic 만능 명령 및 데이터 처리 시스템이다.

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

Agent Skills 오픈 표준(agentskills.io) 기반. 위치: `.claude/skills/<name>/SKILL.md`

| 스킬 | 설명 |
|------|------|
| `/init-project` | 유저 의도에 맞춰 카테고리(웹앱기초(기본값)/웹앱고급/모바일앱/데스크톱앱/3D·2D 게임) 또는 일반 Node 프로젝트로 폴더구조·기술스택 초기화 |
| `/create-spec` | 명세(Spec)를 `proc/spec/`에 항목별 문서로 작성 |
| `/update-plan` | `proc/plan/`에 작업 계획 생성/업데이트 |
| `/update-spec` | 명세·업무규칙 변경 시 `proc/spec/` 문서 업데이트 (FSD/rules/architecture/nfr/user-flow/api/work-rules/decisions + ADR) |
| `/update-research` | 사전 조사·연구 문서를 `proc/research/`에 작성 |
