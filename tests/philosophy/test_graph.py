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


# ── 엔티티 링킹 (문자열 매칭 — LLM/임베딩 미호출) ──────────────────────────
def test_link_entities_surname_matching(g):
    # 성(surname) 매칭 — 단일 성이든 'First Last' 어순이든 같은 인물로
    assert g.link_entities(["Nietzsche"]) == ["hope::P_nietzsche"]
    assert g.link_entities(["Friedrich Nietzsche"]) == ["hope::P_nietzsche"]
    kant = g.link_entities(["Immanuel Kant"])
    assert kant and all(nid.split("::", 1)[-1] == "P_kant" for nid in kant), kant
    # 같은 인물의 여러 article-scoped 노드가 앵커로 다 잡힌다(경로 subgraph 별)
    assert len(kant) > 1


def test_link_entities_concept_and_misses(g):
    # 개념 label 완전일치
    util = g.link_entities(["utilitarianism"])
    assert util and any(nid.split("::", 1)[-1] == "C_utilitarianism" for nid in util)
    # 매칭 실패·빈 입력은 조용히 빈 목록(폴백 규약)
    assert g.link_entities(["Zxqvwbbbbnope"]) == []
    assert g.link_entities([]) == []


# ── 경로 탐색 (결정론 · 최단 · value hub 배제) ────────────────────────────
def test_find_paths_deterministic_and_valid(g):
    niet = g.link_entities(["Nietzsche"])
    hope_claims = sorted(nid for nid, n in g.nodes.items()
                         if n.get("type") == "claim" and nid.startswith("hope::"))[:8]
    p1 = g.find_paths(niet, hope_claims, max_paths=5, max_len=4)
    p2 = g.find_paths(niet, hope_claims, max_paths=5, max_len=4)
    assert p1, "경로가 하나 이상 나와야 한다"
    assert [x.nodes for x in p1] == [x.nodes for x in p2], "같은 입력 → 같은 경로(결정론)"
    adj = g.adj_index
    for p in p1:
        assert len(p.nodes) == len(p.rels) + 1
        assert 2 <= len(p.nodes) <= 5, "max_len=4 → 최대 5노드"
        for nid in p.nodes[1:-1]:  # 중간 노드는 value hub 배제
            assert g.node(nid)["type"] != "value"
        for a, b in zip(p.nodes, p.nodes[1:]):  # 연속 노드는 실제 인접
            assert b in {x for x, _ in adj.get(a, [])}


def test_find_paths_prefers_direct_assert(g):
    """앵커가 직접 asserts 하는 claim 이 target 이면 1홉 asserts 경로가 나온다."""
    niet = g.link_entities(["Nietzsche"])[0]
    asserted = [cid for cid, authors in g.asserts_index.items()
                if any(pid == niet for pid, _ in authors)]
    assert asserted, "Nietzsche 가 asserts 하는 claim 이 있어야 한다(hope 문서)"
    paths = g.find_paths([niet], asserted, max_paths=3)
    assert paths and len(paths[0].nodes) == 2
    assert paths[0].rels[0] == ("asserts", True)
