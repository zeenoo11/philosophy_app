"""철학 탐구 서비스 — PhiloGraph graphRAG 가치관 진단.

Graph-Project(github.com/zeenoo11/Graph-Project) C_RAG 파이프라인의 경량 이식:
자연어 가치관 → 명제 분해(영어 정규화) → SEP 지식그래프(3,600 노드) 회수 →
유사 주장의 **실제 저자** 기준 철학자 랭킹 → 근거 인용과 함께 진단문.

- graph      : unified_graph.json 로더 + asserts/opposes/인접 인덱스 + BFS 확장
- embed      : fastembed(all-MiniLM-L6-v2 ONNX) — 노드 임베딩 사전계산 + 쿼리 임베딩
- retriever  : 텍스트 cosine 회수 + 저자 랭킹 (원본의 주 신호; GNN 보조 신호는 제외)
- decompose  : LLM 명제 분해(engine.narrator) + 규칙 폴백
- diagnose   : Diagnosis 조립·포맷 (원본 그대로)
- pipeline   : PhiloRAG — 단계 기록과 함께 진단, LLM 진단문
- store      : 진단 영속(사주와 같은 sqlite) + 사용자 간 철학자 분포 유사도
"""
