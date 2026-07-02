# 哲命 — 나를 읽는 두 개의 렌즈

> 동양의 명리는 **태어난 순간**을 읽고, 서양의 철학은 **살아온 생각**을 읽는다.
> 두 서비스가 나뉘어 있는 하나의 플랫폼 — 🔮 **사주 운세** × 🧭 **철학 탐구**.

**핵심 명제: 계산은 정답이 있고, 해석은 정답이 없다.**
사주의 팔자·대운·괘도, 철학의 7축 좌표·매칭도 **결정론 계산**과 **LLM 해석**을
물리적으로 분리하고, 모든 풀이에 근거(trace/푸터)를 남긴다.

```
/          랜딩 페이지 (FastAPI)
/chat      채팅 (Chainlit Chat Profiles)
  ├─ 🔮 사주 운세   결정론 사주 엔진 + 유파별 해석 + LLM 리포트 + 궁합 매칭
  └─ 🧭 철학 탐구   7축 가치관 분석 + 12사상 매칭 + 사용자 유사도 연결
```

## 빠른 시작

```bash
uv sync                                        # Python 3.11 (sxtwl 휠 제약)
echo "OPENROUTER_API_KEY=sk-or-..." > .env     # LLM 인증 (권장: OpenRouter)

uv run uvicorn main:app --host 0.0.0.0 --port 8123   # 랜딩 + 채팅
# 또는 채팅만:  uv run chainlit run app.py --port 8123
```

- **LLM 키 없이도** 결정론 기능(사주 차트·주제 힌트·궁합·철학 사상 매칭)은 동작한다.
  LLM 이 필요한 것은 사주 상세 리포트와 철학 대화 유도·점수화.
- 로그인을 켜려면 `.env` 에 `CHAINLIT_AUTH_SECRET`(생성: `uv run chainlit create-secret`).
  한 계정으로 **사주 프로필과 철학 좌표가 함께** 저장된다(sqlite 한 파일).

### Docker

```bash
docker compose up --build      # .env 자동 주입 → http://localhost:8123
```

## 아키텍처

```
main.py            FastAPI — 랜딩(/) + mount_chainlit(/chat)
app.py             Chainlit 라우터 — Chat Profiles 분기 + 공용 인증
saju_service.py    사주 프로필 핸들러 (메뉴형 대화·스트리밍 리포트·인연 매칭)
philo_service.py   철학 프로필 핸들러 (질문 대화·7축 분석·닮은 영혼)
web/index.html     랜딩 페이지 (정적 단일 파일)

engine/            사주 결정론 엔진 + LLM 서술 (상세: docs/SPEC.md)
  pillars·daeun·relations·sinsal·luck·tojeong·lifelong·compatibility ...
  narrator.py      LLM 백엔드 (OpenRouter 스트리밍 / claude -p) — 플랫폼 공용
  store.py         sqlite — users/profiles/candidates
presets/           사주 해석 유파 프리셋 (YAML)

philosophy/        철학 탐구 서비스
  analysis.py      LLM 대화 유도 + 축별 점수화 (engine.narrator 재사용)
  matching.py      사상 매칭 + 사용자 유사도 (결정론, 순수 파이썬)
  store.py         philo_profiles 테이블 (사주와 같은 DB 공유)
  data/            philo.csv(12사상) · question_list.json(21문) · system_prompt.md

legacy/            v1 철학 앱 (Streamlit·LangChain·OpenAI) — 이력 보존, import 금지
```

### 철학 탐구 — 7축

| 축 | 0 ← | → 10 |
|---|---|---|
| Agency (주체성) | 운명·수용 | 자유의지·능동 |
| Logic (판단 근거) | 감성·직관 | 이성·논리 |
| Focus (지향점) | 나·개인 | 모두·이타 |
| Outlook (세계관) | 비관·냉소 | 낙관·진보 |
| Time (시간 지향) | 과거·전통 | 미래·진보 |
| Meta (형이상학) | 유물·물질 | 영성·초월 |
| Social (사회 동조) | 반항·비순응 | 순응·질서 |

답변마다 현재 축을 0~10 으로 점수화(누적 평균)하고, 12개 사상(philo.csv)과
유클리드 거리 → 선형 일치율로 매칭한다. 로그인 사용자끼리는 같은 좌표계에서
**철학 유사도 랭킹**(나와 닮은 영혼)을 제공 — 사주의 궁합 매칭과 대칭 구조.

### LLM 백엔드 (engine/narrator.py — 두 서비스 공용)

| 백엔드 | 설정 | 기본 모델 | 비고 |
|---|---|---|---|
| **OpenRouter** (권장) | `OPENROUTER_API_KEY` | `deepseek/deepseek-v4-flash` | 빠름·저렴, 사주 리포트는 토큰 스트리밍 |
| Claude | `ANTHROPIC_API_KEY` + `SAJU_LLM_BACKEND=claude` | `sonnet` | 품질 최상 |

## 테스트

```bash
uv run pytest -q                       # 전체
uv run pytest -m philosophy -q         # 철학 서비스 (매칭·저장 — 결정론)
uv run pytest -m deterministic -q      # 사주 L1 (골든·속성·엣지·교차출처)
uv run pytest -m interpretation -q     # 사주 L2~L4 (유파 충실도·그라운딩)
```

## 로드맵 — 철학 '연결'의 다음 단계

현재 사용자 연결은 7축 좌표 유사도다. [Graph-Project(PhiloGraph)](https://github.com/zeenoo11/Graph-Project)
의 SEP 지식그래프 · graphRAG 가치관 진단과 이어 붙이면:
사용자 좌표 → 철학자/개념 노드 매핑 → 그래프 경로 기반 설명("당신과 스토아 사이에는
에픽테토스의 '통제 이원론'이 있다") → 사용자 간 개념 수준의 연결로 확장할 수 있다.

## 크레딧

- 사주 엔진: [saju-engine](docs/SPEC.md) — 다중 유파 해석, 천문 교차검증 (278 테스트)
- 철학 v1: `legacy/` — Streamlit 프로토타입 (7축 체계·질문·사상 DB 의 원형)

> ⚠️ 본 서비스는 재미와 자기 성찰을 위한 것입니다. 중요한 결정은 당신의 몫.
