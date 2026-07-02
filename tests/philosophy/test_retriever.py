"""LiteRetriever + Diagnosis — 임베딩 npz 기반 회수·랭킹 (LLM 미호출).

fastembed 쿼리 임베딩 1회가 필요해 첫 실행은 모델 로드로 수 초 걸린다.
"""
import pytest

from philosophy.diagnose import build_diagnosis, format_diagnosis
from philosophy.retriever import LiteRetriever

pytestmark = pytest.mark.philosophy


@pytest.fixture(scope="module")
def retriever():
    return LiteRetriever(top_k=8)


@pytest.fixture(scope="module")
def love_bundles(retriever):
    return retriever.retrieve_many([
        "love enriches the world",
        "love creates lack in each other",
    ])


def test_retrieve_returns_scored_neighbors(retriever, love_bundles):
    b = love_bundles[0]
    assert len(b.neighbors) == 8
    scores = [n.score for n in b.neighbors]
    assert scores == sorted(scores, reverse=True)
    assert all(n.type in ("claim", "concept") for n in b.neighbors)
    assert any(n.source_quote for n in b.neighbors), "source_quote 조인 필수"
    assert b.expanded_nodes, "BFS 이웃 확장 동작"


def test_love_query_finds_love_philosophers(retriever, love_bundles):
    """원본 C_RAG 예시 재현 — 사랑 문장은 SEP love 문서 저자들로 랭킹돼야 한다."""
    ranked = retriever.rank_philosophers(love_bundles, top_k=8)
    assert ranked, "저자 랭킹 비면 안 됨"
    labels = " / ".join(p.label for p in ranked)
    assert any(name in labels for name in ("Singer", "Nagel", "Velleman", "Frankfurt")), labels
    top = ranked[0]
    assert top.score > 0 and top.n_support >= 1
    assert top.gnn_score is None, "경량 이식 — GNN 보조 신호 없음"
    assert top.contributions, "rank breakdown(기여 claim) 제공"


def test_rank_is_canonical_unique(retriever, love_bundles):
    ranked = retriever.rank_philosophers(love_bundles, top_k=10)
    ids = [p.id for p in ranked]
    assert len(ids) == len(set(ids)), "canonical 단위로 중복 없이 집계"


def test_diagnosis_build_and_format(retriever, love_bundles):
    ranked = retriever.rank_philosophers(love_bundles, top_k=5)
    d = build_diagnosis("사랑은 풍요와 결핍을 준다",
                        ["love enriches", "love creates lack"], love_bundles, ranked)
    assert d.similar_claims and len(d.similar_claims) <= 10
    assert d.predicted_community == -1, "GNN 없음 — 학파 예측은 비활성"
    md = format_diagnosis(d)
    assert "## 유사한 주장" in md and "## 가장 가까운 철학자" in md
    assert "추정 학파" not in md, "community<0 이면 학파 섹션 생략"


def test_opposes_from_graph(retriever):
    """justice 계열 질의 — 그래프 opposes 엣지에서 대비 입장이 붙는다(있을 때)."""
    b = retriever.retrieve("Justice is the advantage of the stronger")
    # opposes 는 데이터 의존 — 형식만 보장(있다면 claim/concept 이고 점수 부여)
    for o in b.opposes_claims:
        assert o.score is not None
