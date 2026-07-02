"""철학 탐구 서비스 — 7축 가치관 분석·사상 매칭·사용자 연결.

legacy/src (Streamlit + LangChain + OpenAI) 를 사주 플랫폼과 같은 스택
(Chainlit + engine.narrator OpenRouter + sqlite store) 으로 포팅한 패키지.

- analysis  : LLM 대화 유도 + 축별 점수화 (7축: agency/logic/focus/outlook/time/meta/social)
- matching  : 철학 사상 매칭(결정론, philo.csv) + 사용자 간 유사도(연결)
- store     : 철학 프로필 영속 — 사주와 같은 sqlite(SAJU_DB_PATH) 공유
"""
