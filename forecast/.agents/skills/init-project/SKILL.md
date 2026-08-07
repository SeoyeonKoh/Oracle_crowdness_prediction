---
name: init-project
description: 프로젝트 초기화 스킬. "프로젝트 초기화", "셋업", "프로젝트 시작", "만들어줘/구축" 등 새 프로젝트를 시작하려는 의도를 감지하면 사용한다. 유저 의도를 보고 카테고리(웹앱기초/웹앱고급/모바일앱/데스크톱앱/캐쥬얼 3D 게임/캐쥬얼 2D 게임)를 고르거나 일반 Node 프로젝트로 폴더구조·기술스택을 잡아준다.
argument-hint: "[만들 프로젝트 설명]"
---

# 프로젝트 초기화 스킬

유저의 의도를 파악해 무엇을 만들지 정한 뒤, 아래 카테고리에서 골라 **폴더구조 + 기술스택**을 잡아준다. 카테고리에 안 맞으면 일반 Node 프로젝트로 안내한다.

## 규칙
- 임의로 정하지 말 것. 카테고리가 모호하면 유저에게 확인한다.
- 유저가 단순히 "웹앱"이라고만 하면 **웹앱기초**를 기본값으로 선택한다. Hono·Zod·Bun 또는 고급 구성을 명시한 경우 **웹앱고급**을 선택한다.
- 루트는 이미 비어있지 않다(`proc/`·`input/`·`output/` 등). 스캐폴더는 **하위 폴더(`app/`·`svr/`·`src/`)를 타깃**으로 생성해 충돌을 피한다. SQLite와 개발용 영구 데이터가 필요하면 루트의 `data/`를 사용한다.
- 사용자에게는 프로젝트 초기화에 필요한 선택, 설치 URL, 준비할 입력 파일, 실행 방법만 한글로 간결하게 안내한다.
- 사용자가 행동하는 데 필요하지 않은 내부 구현 설명, 명칭 교정, 도구 비교, 호환성 해설은 먼저 말하지 않는다. 실제 작업이 막힐 때만 필요한 이유와 대안을 설명한다.

## 카테고리 (하나 선택)

| 카테고리 | 기술스택 | 폴더 |
|---|---|---|
| 웹앱기초 (기본값) | React + Vite + Express + SQLite | `app/` + `svr/` |
| 웹앱고급 | Bun + React + Vite + Hono + Zod + SQLite | `app/` + `svr/` |
| 모바일앱 | React Native + Expo | `app/` (+ `svr/`) |
| 데스크톱앱 | Electron | `app/` (+ `svr/`) |
| 캐쥬얼 3D 게임 | three.js + WebSocket | `app/` + `svr/` |
| 캐쥬얼 2D 게임 | Phaser + WebSocket | `app/` + `svr/` |

## 폴더
- `app/` — 프론트엔드 / 앱 (모바일 등)
- `svr/` — 백엔드 (필요 시)
- `src/` — 기타
- `data/` — SQLite DB 파일과 프로젝트 개발용 영구 데이터
- 필요에 따라 추가

## 위 카테고리에 안 맞으면 → 일반 Node 프로젝트
`package.json` 기반 Node 프로젝트로 안내하고 `src/`를 쓴다.
(자료처리 / 자동화 / 채팅봇 / 자동화봇(Slack 등) / 크롬 익스텐션 등)

## 기능별 안내 (의도에 있으면 추가)

| 기능 | 안내 |
|---|---|
| DB | SQLite로 잡고 필요한 패키지를 안내하며, DB 파일은 `data/`에 저장 |
| AI | 서비스/제품을 만드는 경우 LangChain + LangGraph 사용, LLM은 OpenAI API key (단, 아래 「AI 요청 구분」 먼저 확인) |
| 실시간 | WebSocket |
| 3D | three.js |
| 데이터 시각화 | Tabulator 또는 D3 |
| 지도 | OSM, EPSG:3857 사용 |
| 문서 (Office) | **iOfficeAI/OfficeCLI** 사용 (`.docx`·`.xlsx`·`.pptx` 읽기·생성·수정). 아래 「문서 형식별 처리」 참고 |
| 문서 (한글) | **airmang/python-hwpx** 사용 (`.hwpx` 읽기·생성·수정·검증). 아래 「문서 형식별 처리」 참고 |
| Python | Python 설치 여부를 먼저 확인하고, 환경·패키지는 **uv**로 관리. 아래 「Python 환경」 참고 |
| 디자인 | **pen.dev standalone**으로 디자인하고 `input/`에 `.pen` 파일을 넣어 AI 작업. 아래 「디자인 작업」 참고 |
| 토큰 절약 | 셸 출력 토큰을 줄이고 싶으면 **rtk-ai/rtk** 사용. 아래 「토큰 절약」 참고 |
| 브라우저 자동화 | **Playwright CLI** 사용 (크롤링·스크래핑·E2E 등). 아래 「브라우저 자동화 / 웹 테스트」 참고 |

## AI 요청 구분
- AI로 **자료를 만들거나 검증**하려는 경우, 또는 유저가 **혼자 파일을 처리**하려는 경우에는 API key 기반 AI 서비스를 만들지 말 것.
- 대신 **직접 해결**해 준 뒤 **스킬화**(재사용 가능한 스킬로 만들기)를 안내한다.
- 유저가 AI 서비스부터 만들려 하면, "AI 서비스를 만들기보다 AI로 문제를 해결하고 스킬화하는 게 낫다"고 **한 번 제안한다**.

## 브라우저 자동화 / 웹 테스트
- **브라우저 자동화가 필요하면 Playwright CLI를 사용한다** (크롤링·스크래핑·폼 입력·E2E 등). 다른 자동화 도구를 임의로 고르지 않는다.
- **웹앱을 개발할 때도 Playwright를 개발 테스트에 활용한다** — 화면 렌더링·동작 확인, 핵심 플로우 E2E 검증, 회귀 테스트 작성에 쓴다.
- 설치/실행 안내: `npm i -D playwright` 후 `npx playwright install`, 테스트는 `npx playwright test`로 돌린다.

## 문서 형식별 처리
- 문서가 들어오면 먼저 파일 확장자를 확인하고 형식에 맞는 도구를 선택한다.
- Microsoft Office 문서(`.docx`·`.xlsx`·`.pptx`)를 읽거나 생성·수정할 때는 **iOfficeAI/OfficeCLI**를 우선 사용한다.
- 특히 Word 문서(`.docx`) 작업은 OfficeCLI의 `officecli-docx` 워크플로를 따른다.
- 작업 후에는 `officecli validate`와 `officecli view`를 사용해 구조와 렌더링 결과를 검증한다.
- 한글 HWPX 문서(`.hwpx`)를 읽거나 생성·수정할 때는 **airmang/python-hwpx**를 우선 사용하고 저장 결과를 검증한다.
- 구형 바이너리 한글 문서(`.hwp`)는 python-hwpx의 지원 대상이 아니므로 가능하면 `.hwpx`로 변환한 뒤 처리한다.
- 공식 GitHub:
  - OfficeCLI: https://github.com/iOfficeAI/OfficeCLI
  - python-hwpx: https://github.com/airmang/python-hwpx

## Python 환경
- Python이 필요한 작업이면 먼저 `python --version` 또는 `python3 --version`으로 설치 여부와 버전을 확인한다.
- Python 패키지와 가상환경은 `pip`를 직접 사용하지 말고 **uv**로 관리한다.
- uv가 없으면 공식 설치 문서(https://docs.astral.sh/uv/getting-started/installation/)를 안내한다.
- Python이 없으면 uv 설치 후 `uv python install`로 필요한 Python 버전을 설치하도록 안내한다.
- 새 프로젝트는 `uv init`, 패키지는 `uv add <package>`, 기존 `requirements.txt`는 `uv pip install -r requirements.txt`를 사용한다.

## 개발용 데이터 저장
- SQLite 데이터베이스 파일(`.db`·`.sqlite`·`.sqlite3`)은 루트의 `data/` 폴더에 저장한다.
- 프로젝트 실행 중 생성되고 다음 실행에도 유지되어야 하는 개발용 영구 데이터도 `data/`에 저장한다.
- DB 스키마·마이그레이션·시드 소스 코드는 `svr/` 또는 `src/`에 두고, 실제 생성 데이터만 `data/`에 둔다.
- `input/`은 유저가 제공한 원본 자료, `output/`은 최종 산출물 용도이므로 애플리케이션의 영구 데이터 저장소로 사용하지 않는다.

## 디자인 작업
- 유저가 UI·UX나 화면 디자인을 원하면 **pen.dev standalone 데스크톱 앱**을 먼저 설치하도록 안내한다.
- 공식 다운로드: https://www.pen.dev/downloads
- standalone 앱에서 디자인한 `.pen` 파일을 `input/` 폴더에 넣고 pen.dev를 실행한 상태에서 AI 에이전트를 시작하도록 안내한다.
- AI는 `input/`의 `.pen` 파일을 디자인 원본(source of truth)으로 사용하며, 유저의 명시적 지시 없이 입력 파일을 임의로 덮어쓰지 않는다.

## 토큰 절약
- 셸 명령 출력으로 소비되는 AI 입력 토큰을 줄이고 싶으면 **rtk-ai/rtk** 사용을 안내한다.
- 공식 GitHub: https://github.com/rtk-ai/rtk
- 설치 후 사용하는 에이전트에 맞춰 초기화한다. 예: Claude Code `rtk init -g`, Codex `rtk init -g --codex`, Gemini CLI `rtk init -g --gemini`.

## 서버 / 포트 규칙
- 프론트 **9000** 포트, 백엔드 **9001** 포트.
- 서버는 **0.0.0.0** 으로 바인딩(어디서든 접근 가능).
- **CORS 허용**.
