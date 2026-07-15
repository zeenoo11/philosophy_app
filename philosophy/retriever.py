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
from philosophy.schema import GraphPath, PhilosopherMatch, RetrievalBundle, RetrievedNode

#: 경로 중심성 → 랭킹 가산 스케일 — 보수적(경로 1개 통과 = +0.1). cosine 집계 합은 보통
#: 1.0+ 이라 근소 동률만 재정렬하고 뚜렷한 1위는 뒤집지 않는다.
_PATH_CENTRALITY_WEIGHT = 0.1
#: 임베딩 폴백(개념 링킹) 최소 cosine — 낮으면 시시한 오링킹이 되므로 문턱을 둔다.
_ENTITY_EMBED_MIN_SIM = 0.55


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

    # -- 엔티티 링킹 + 경로 탐색 (query-side GraphRAG) ------------------------
    def _concept_embed_fallback(self, name: str) -> str | None:
        """개념 임베딩 폴백 — 이름과 가장 닮은 concept 노드(문턱 이상) 1개, 없으면 None."""
        ids, vectors = self._ensure_embeddings()
        qv = embed.encode([name])[0]
        for nid, score in embed.top_k_similar(qv, ids, vectors, k=10):
            if score >= _ENTITY_EMBED_MIN_SIM and \
                    self.graph.node(nid) and self.graph.node(nid).get("type") == "concept":
                return nid
        return None

    def link_entities(self, names: list[str]) -> list[str]:
        """언급된 이름/개념 → 그래프 앵커 노드 id (문자열 우선 + 개념 임베딩 폴백)."""
        if not names:
            return []
        return self.graph.link_entities(names, embed_fallback=self._concept_embed_fallback)

    def _seed_ids(self, bundles: list[RetrievalBundle], *, per_bundle: int = 3,
                  total: int = 6) -> list[str]:
        """경로 끝점이 될 상위 시드 노드 id — 각 명제의 상위 이웃 + 전역 상위(점수 정렬)."""
        scored: dict[str, float] = {}
        for b in bundles:
            for n in b.neighbors[:per_bundle]:
                scored[n.id] = max(scored.get(n.id, 0.0), n.score or 0.0)
        ranked = sorted(scored, key=lambda nid: (-scored[nid], nid))
        return ranked[:total]

    def find_paths(self, anchors: list[str], bundles: list[RetrievalBundle], *,
                   max_paths: int = 4, max_len: int = 4) -> list[GraphPath]:
        """생각의 경로 — 앵커↔시드, 상위 시드끼리 최단 관계 체인(결정적)."""
        seeds = self._seed_ids(bundles)
        if not seeds:
            return []
        sources = list(dict.fromkeys([*anchors, *seeds]))
        return self.graph.find_paths(sources, seeds, max_paths=max_paths, max_len=max_len)

    # -- 철학자 랭킹 (원본 이식 + 경로 중심성 블렌드) --------------------------
    def rank_philosophers(self, bundles: list[RetrievalBundle],
                          top_k: int = 10, *,
                          paths: list[GraphPath] | None = None) -> list[PhilosopherMatch]:
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

        # 경로 중심성 블렌드 — 경로를 통과한 철학자에게 보수적 가산(기존 후보만 재정렬,
        # 새 철학자 주입 금지 → 뚜렷한 순위는 유지). canonical 단위, 경로당 1회 집계.
        if paths:
            centrality: dict[str, int] = {}
            for p in paths:
                seen_c: set[str] = set()
                for nid in p.nodes:
                    node = g.node(nid)
                    if node and node.get("type") == "philosopher":
                        c = g.canonical(nid)
                        if c not in seen_c:
                            seen_c.add(c)
                            centrality[c] = centrality.get(c, 0) + 1
            for cid, cnt in centrality.items():
                if cid in agg:  # 기존 cosine 후보에만 가산(주입 금지)
                    agg[cid]["score"] = round(
                        agg[cid]["score"] + _PATH_CENTRALITY_WEIGHT * cnt, 3)

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
