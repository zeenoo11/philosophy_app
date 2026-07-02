"""graphRAG 데이터 계약 — Graph-Project C_RAG(rag/core/schema.py) 이식.

흐름: LiteRetriever → RetrievalBundle → build_diagnosis → Diagnosis → LLM 진단문.
원본과의 차이: GNN 체크포인트가 없는 경량 이식이라 asserts_philosophers(GNN 디코더)·
predicted_community(GNN head)는 기본값으로 비어 있다 — 스키마는 원본과 동일하게 유지해
포맷터(diagnose.format_diagnosis)가 조건부로 생략한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RetrievedNode:
    """회수된 그래프 노드 + 그래프 JSON 조인(source_quote — 인용·근거용)."""

    id: str
    type: str
    label: str
    article: str | None = None
    score: float | None = None
    source_quote: str | None = None


@dataclass
class RetrievalBundle:
    """한 질의(또는 한 sub-claim)에 대한 회수 결과."""

    query: str
    neighbors: list[RetrievedNode] = field(default_factory=list)  # 텍스트 cosine
    asserts_philosophers: list[RetrievedNode] = field(default_factory=list)  # (GNN — 미사용)
    opposes_claims: list[RetrievedNode] = field(default_factory=list)  # 그래프 opposes 엣지
    predicted_community: int = -1  # (GNN head — 미사용)
    community_concepts: list[RetrievedNode] = field(default_factory=list)
    expanded_nodes: list[RetrievedNode] = field(default_factory=list)  # BFS hop 확장

    def all_nodes(self) -> list[RetrievedNode]:
        return [
            *self.neighbors,
            *self.asserts_philosophers,
            *self.opposes_claims,
            *self.community_concepts,
            *self.expanded_nodes,
        ]


@dataclass
class PhilosopherMatch:
    """사용자 생각과 유사한 철학자 + 근거. canonical 단위로 집계(같은 인물 통합)."""

    id: str  # canonical_id (예: P::davidson)
    label: str
    score: float  # 유사 claim 저자 가중합(주 신호)
    n_support: int = 0  # 뒷받침한 유사 claim 수(그래프 asserts)
    gnn_score: float | None = None  # (원본 호환 — 이 이식에서는 항상 None)
    articles: list[str] = field(default_factory=list)
    support_claims: list[str] = field(default_factory=list)  # 근거가 된 유사 claim 라벨
    contributions: dict = field(default_factory=dict)  # claim_id → 기여 score


@dataclass
class Diagnosis:
    """가치관 진단 결과 — 사용자 입력을 철학 지형에 위치시킨다."""

    query: str
    sub_claims: list[str]
    top_philosophers: list[PhilosopherMatch] = field(default_factory=list)
    predicted_community: int = -1
    school_concepts: list[RetrievedNode] = field(default_factory=list)
    similar_claims: list[RetrievedNode] = field(default_factory=list)
    contrasting_claims: list[RetrievedNode] = field(default_factory=list)


@dataclass
class RagAnswer:
    """최종 답변 + 역매핑된 인용 + 진단(감사용)."""

    query: str
    answer: str
    citations: list[RetrievedNode] = field(default_factory=list)
    diagnosis: Diagnosis | None = None
    meta: dict | None = None  # LLM 모델·토큰·비용 (engine.narrator.llm_meta 동형)
