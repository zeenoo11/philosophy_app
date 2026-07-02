"""PhiloGraph — 그래프 로딩·인덱스·BFS 확장 (결정론, LLM/임베딩 미호출)."""
import pytest

from philosophy.graph import build_text, get_graph
from philosophy.schema import RetrievalBundle, RetrievedNode

pytestmark = pytest.mark.philosophy


@pytest.fixture(scope="module")
def g():
    return get_graph()


def test_graph_loads_expected_shape(g):
    s = g.stats()
    assert s["nodes"] == 3600 and s["edges"] == 8397
    assert s["types"]["philosopher"] == 1379
    assert s["types"]["claim"] == 1032
    assert s["types"]["concept"] == 977


def test_asserts_index_maps_claims_to_philosophers(g):
    idx = g.asserts_index
    assert len(idx) > 500
    some_claim = next(iter(idx))
    authors = idx[some_claim]
    assert all(g.node(pid)["type"] == "philosopher" for pid, _ in authors)


def test_opposes_index_bidirectional(g):
    idx = g.opposes_index
    assert idx, "opposes 엣지가 있어야 한다(원본 495건)"
    a = next(iter(idx))
    b = idx[a][0]
    assert a in idx[b], "opposes 는 양방향 인덱스"


def test_canonical_resolves_davidson(g):
    # action::P_davidson 의 canonical 은 P::davidson (그래프 실데이터)
    assert g.canonical("action::P_davidson") == "P::davidson"
    # canonical 없는 노드는 자기 자신
    no_canon = next(nid for nid, n in g.nodes.items()
                    if not n.get("canonical_id") or n.get("canonical_id") == "None")
    assert g.canonical(no_canon) == no_canon


def test_embed_targets_are_claims_and_concepts(g):
    targets = g.embed_targets()
    assert len(targets) == 1032 + 977
    assert targets == sorted(targets, key=lambda t: t[0]), "결정적 순서(id 정렬)"
    ids = {t[0] for t in targets}
    assert all(g.node(i)["type"] in ("claim", "concept") for i in list(ids)[:50])


def test_build_text_rules(g):
    claim = {"type": "claim", "label": "L", "source_quote": "Q"}
    assert build_text(claim) == "L. Context: Q"
    phil = {"type": "philosopher", "label": "P", "aliases": ["a", "b"]}
    assert build_text(phil) == "P; aliases: a, b"
    assert build_text({"type": "sentence", "label": "L", "source_quote": "Q"}) == "Q"


def test_expand_neighbors_deterministic_and_capped(g):
    seed_id = next(iter(g.asserts_index))  # 저자가 있는 claim — 이웃 보장
    bundle = RetrievalBundle(query="t", neighbors=[
        RetrievedNode(id=seed_id, type="claim", label="seed", score=0.9)])
    g.expand_neighbors(bundle, depth=1, max_nodes=10)
    first = [n.id for n in bundle.expanded_nodes]
    assert 0 < len(first) <= 10
    assert seed_id not in first, "시드 자신은 확장에서 제외"
    # 같은 입력 → 같은 결과(결정론)
    bundle2 = RetrievalBundle(query="t", neighbors=[
        RetrievedNode(id=seed_id, type="claim", label="seed", score=0.9)])
    g.expand_neighbors(bundle2, depth=1, max_nodes=10)
    assert [n.id for n in bundle2.expanded_nodes] == first
