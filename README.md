# 哲命 — 나를 읽는 두 개의 렌즈

> 동양의 명리는 **태어난 순간**을 읽고, 서양의 철학은 **살아온 생각**을 읽는다.
> 두 서비스가 나뉘어 있는 하나의 플랫폼 — 🔮 **사주 운세** × 🧭 **철학 탐구**.

**핵심 명제: 계산은 정답이 있고, 해석은 정답이 없다.**
사주의 팔자·대운·괘도, 철학의 7축 좌표·매칭도 **결정론 계산**과 **LLM 해석**을
물리적으로 분리하고, 모든 풀이에 근거(trace/푸터)를 남긴다.

```
/          랜딩 페이지 (FastAPI)
/app       哲命 셸 안에서 도는 채팅 (iframe)
/chat      채팅 (Chainlit Chat Profiles)
  ├─ 🔮 사주 운세   결정론 사주 엔진 + 유파별 해석 + LLM 리포트 + 궁합 매칭
  └─ 🧭 철학 탐구   PhiloGraph graphRAG 가치관 진단 — SEP 지식그래프 3,600노드
/me        개인 보고서 — 저장된 모든 탐색(사주·철학·통합)을 다시 보기 (채팅 계정)
```

**탐색은 저장된다.** 로그인 상태의 모든 사주 리포트·철학 진단은 자동으로 히스토리에
쌓이고(`reports_store.py` — 같은 sqlite), 채팅의 **🔗 사주×철학 통합 리포트** 버튼은
두 렌즈(팔자·강약·용신 × top 철학자·가치관)를 한 장의 보고서로 묶는다.
`/me` 는 그 전부를 다시 보는 개인 페이지다(HTTP Basic — 채팅과 같은 계정).

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
main.py            FastAPI — 랜딩(/) + /app + /me(개인 보고서) + mount_chainlit(/chat)
app.py             Chainlit 라우터 — Chat Profiles 분기 + 공용 인증 + 🔗 통합 리포트 콜백
saju_service.py    사주 프로필 핸들러 (메뉴형 대화·스트리밍 리포트·인연 매칭)
philo_service.py   철학 프로필 핸들러 (graphRAG 진단·닮은 영혼)
fusion.py          사주×철학 통합 리포트 — 두 렌즈의 값을 묶은 프롬프트 + 근거 푸터
reports_store.py   탐색 히스토리 (saju/philo/fusion_reports — /me 의 데이터 소스)
me_page.py         /me 서버 렌더 HTML (哲命 팔레트, marked+DOMPurify)
web/index.html     랜딩 페이지 (정적 단일 파일)

engine/            사주 결정론 엔진 + LLM 서술 (상세: docs/SPEC.md)
  pillars·daeun·relations·sinsal·luck·tojeong·lifelong·compatibility ...
  narrator.py      LLM 백엔드 (OpenRouter 스트리밍 / claude -p) — 플랫폼 공용
  store.py         sqlite — users/profiles/candidates
presets/           사주 해석 유파 프리셋 (YAML)

philosophy/        철학 탐구 서비스 — PhiloGraph graphRAG (Graph-Project C_RAG 이식)
  graph.py         unified_graph.json 로더 + asserts/opposes/인접 인덱스 + BFS 확장
  embed.py         fastembed(all-MiniLM-L6-v2 ONNX) — 노드 임베딩 사전계산 + 쿼리 임베딩
  retriever.py     텍스트 cosine 회수 + 유사 주장의 실제 저자(asserts) 랭킹
  decompose.py     LLM 명제 분해 + 영어 정규화 (규칙 폴백)
  diagnose.py      Diagnosis 조립·포맷 (원본 그대로)
  pipeline.py      PhiloRAG — 단계 기록과 함께 진단, LLM 진단문
  store.py         philo_diagnoses 테이블 (사주와 같은 DB 공유)
  data/            unified_graph.json (SEP 3,600노드·8,397엣지) · embeddings.npz

legacy/            v1 철학 앱 (Streamlit·LangChain·OpenAI) — 이력 보존, import 금지
```

### 철학 탐구 — graphRAG 가치관 진단

[Graph-Project(PhiloGraph)](https://github.com/zeenoo11/Graph-Project) C_RAG 파이프라인의
경량 이식. 흐름:

```
가치관 한 문장 → decompose (LLM: 핵심 명제 2~4개 + 영어 정규화)
             → retrieve  (명제별 임베딩 cosine 회수 + BFS 이웃 확장)
             → rank      (유사 주장의 실제 저자를 asserts 엣지로 — canonical 통합)
             → diagnose  (유사 주장·가까운 철학자·대비 입장 + SEP 원문 인용)
             → LLM 진단문 (OpenRouter 스트리밍, 근거 안에서만 서술)
```

원본과의 차이: GNN 체크포인트(RGCN+TransE)는 레포에 없어 **텍스트+그래프 주 신호만**
이식했다 — GNN 보조 신호(asserts 디코더·community head)는 제외, opposes 는 그래프
엣지에서 직접 조회. 임베딩은 같은 MiniLM 모델의 ONNX 포트(fastembed, torch 불필요).
노드 임베딩 재계산: `uv run python scripts/build_philo_embeddings.py`

로그인 사용자끼리는 **닮은 영혼**(top 철학자 분포 코사인) 랭킹을 제공 —
사주의 궁합 매칭과 대칭 구조.

### LLM 백엔드 (engine/narrator.py — 두 서비스 공용)

| 백엔드 | 설정 | 기본 모델 | 비고 |
|---|---|---|---|
| **OpenRouter** (권장) | `OPENROUTER_API_KEY` | `deepseek/deepseek-v4-flash` | 빠름·저렴, 사주 리포트는 토큰 스트리밍 |
| Claude | `ANTHROPIC_API_KEY` + `SAJU_LLM_BACKEND=claude` | `sonnet` | 품질 최상 |

## 테스트

```bash
uv run pytest -q                       # 전체
uv run pytest -m philosophy -q         # 철학 graphRAG (그래프·분해·회수·저장 — LLM 미호출)
uv run pytest -m deterministic -q      # 사주 L1 (골든·속성·엣지·교차출처)
uv run pytest -m interpretation -q     # 사주 L2~L4 (유파 충실도·그라운딩)
```

## 로드맵 — 철학 '연결'의 다음 단계

- **GNN 회수 복원**: Graph-Project B_GNN 체크포인트(RGCN+TransE, AUC 0.957)를 학습·반입하면
  retriever 의 보조 신호(asserts 디코더·community head)를 원본대로 켤 수 있다.
- **그래프 경로 설명**: 사용자 ↔ 철학자 사이의 경로("당신과 Velleman 사이에는 '사랑은
  취약함'이라는 주장이 있다")를 진단문에 명시.
- **통합 리포트 심화**: 현재 fusion 은 최근 진단 1건 기준 — 여러 진단의 철학자 분포
  누적, 대운(10년) 흐름과 철학적 변화의 교차 서사로 확장.

## 크레딧

- 사주 엔진: [saju-engine](docs/SPEC.md) — 다중 유파 해석, 천문 교차검증 (278 테스트)
- 철학 지식그래프·graphRAG: [Graph-Project(PhiloGraph)](https://github.com/zeenoo11/Graph-Project)
  — SEP 기반 3,600노드 그래프(A_KG)와 C_RAG 진단 파이프라인의 원본
- 철학 v1: `legacy/` — Streamlit 프로토타입 (이력 보존)

> ⚠️ 본 서비스는 재미와 자기 성찰을 위한 것입니다. 중요한 결정은 당신의 몫.
