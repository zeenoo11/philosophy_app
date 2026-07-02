"""LiteRetriever — 텍스트 cosine 회수 + 그래프 신호(저자·opposes·BFS 확장).

Graph-Project C_RAG GraphRetriever 의 경량 이식:
- 회수(neighbors): GNN serve 대신 사전계산 임베딩 cosine (같은 MiniLM 모델)
- opposes: GNN 디코더 대신 그래프 opposes 엣지에서 직접 조회
- rank_philosophers: 원본 그대로 — 유사 claim 의 **실제 저자**(asserts)를
  cosine 가중으로 누적, canonical 단위 집계 (주 신호. GNN 보조 신호는 없음)
"""
from __future__ import annotations

from philosophy import embed
from philosophy.graph import PhiloGraph, get_graph
from philosophy.schema import PhilosopherMatch, RetrievalBundle, RetrievedNode


class LiteRetriever:
    def __init__(self, graph: PhiloGraph | None = None, *, top_k: int = 10,
                 expand_depth: int = 1, expand_max: int = 50):
        self.graph = graph or get_graph()
        self.top_k = top_k
        self.expand_depth = expand_depth
        self.expand_max = expand_max
        self._ids: list[str] | None = None
        self._vectors = None

    def _ensure_embeddings(self):
        if self._ids is None:
            self._ids, self._vectors = embed.load_node_embeddings()
        return self._ids, self._vectors

    # -- 회수 ---------------------------------------------------------------
    def retrieve(self, text: str) -> RetrievalBundle:
        ids, vectors = self._ensure_embeddings()
        qv = embed.encode([text])[0]
        top = embed.top_k_similar(qv, ids, vectors, k=self.top_k)

        g = self.graph
        neighbors = []
        for nid, score in top:
            n = g.node(nid) or {}
            neighbors.append(RetrievedNode(
                id=nid, type=n.get("type", "unknown"), label=n.get("label", nid),
                article=n.get("article"), score=round(score, 3)))

        # 반대 입장: 유사 노드의 opposes 상대 (그래프 엣지 — GNN 불필요)
        opposes, seen = [], {nid for nid, _ in top}
        for nid, score in top:
            for oid in g.opposes_index.get(nid, []):
                if oid in seen:
                    continue
                seen.add(oid)
                o = g.node(oid) or {}
                opposes.append(RetrievedNode(
                    id=oid, type=o.get("type", "unknown"), label=o.get("label", oid),
                    article=o.get("article"), score=round(score * 0.9, 3)))

        bundle = RetrievalBundle(query=text, neighbors=neighbors,
                                 opposes_claims=opposes[:5])
        g.expand_neighbors(bundle, depth=self.expand_depth, max_nodes=self.expand_max)
        g.attach_source_quotes(bundle)
        return bundle

    def retrieve_many(self, claims: list[str]) -> list[RetrievalBundle]:
        return [self.retrieve(c) for c in claims if c and c.strip()]

    # -- 철학자 랭킹 (원본 이식) ----------------------------------------------
    def rank_philosophers(self, bundles: list[RetrievalBundle],
                          top_k: int = 10) -> list[PhilosopherMatch]:
        g = self.graph
        asserts_idx = g.asserts_index
        agg: dict[str, dict] = {}

        def slot(cid: str, label: str) -> dict:
            e = agg.get(cid)
            if e is None:
                e = {"label": label, "score": 0.0, "n": 0,
                     "arts": set(), "claims": [], "contrib": {}}
                agg[cid] = e
            return e

        for b in bundles:
            candidates = list(b.neighbors) + list(b.expanded_nodes)
            for nb in candidates:
                authors = asserts_idx.get(nb.id)
                if not authors:
                    continue
                w = max(nb.score or 0.0, 0.0)
                for pid, plabel in authors:
                    e = slot(g.canonical(pid), plabel)
                    e["score"] += w
                    e["n"] += 1
                    e["contrib"][nb.id] = round(e["contrib"].get(nb.id, 0.0) + w, 3)
                    if nb.article:
                        e["arts"].add(nb.article)
                    if nb.label and nb.label not in e["claims"]:
                        e["claims"].append(nb.label)

        ranked = sorted(agg.items(),
                        key=lambda kv: (kv[1]["score"], kv[1]["n"]), reverse=True)
        return [
            PhilosopherMatch(
                id=cid, label=e["label"], score=round(e["score"], 3),
                n_support=e["n"], gnn_score=None,
                articles=sorted(e["arts"]), support_claims=e["claims"][:3],
                contributions=e["contrib"],
            )
            for cid, e in ranked[:top_k]
        ]
