"""PhiloGraph — SEP 철학 지식그래프(unified_graph.json) 로더 + 인덱스.

Graph-Project C_RAG의 GraphRetriever 중 '그래프' 책임만 분리 이식:
asserts(철학자→claim) 인덱스, opposes 인덱스, 인접 인덱스(BFS 확장용),
canonical 통합, source_quote 조인. 순수 파이썬 — GNN/torch 불필요.

데이터: philosophy/data/unified_graph.json (3,600 노드 / 8,397 엣지 —
SEP 31개 article 기반, Graph-Project A_KG/extract 산출물).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from philosophy.schema import RetrievalBundle, RetrievedNode

DATA_DIR = Path(__file__).parent / "data"
GRAPH_JSON = DATA_DIR / "unified_graph.json"

#: 텍스트 회수(임베딩) 대상 노드 타입 — 의미 단위인 claim/concept.
#: (philosopher 는 저자 랭킹으로, sentence 는 source_quote 로 간접 노출)
EMBED_TYPES = ("claim", "concept")


def build_text(node: dict) -> str:
    """노드 → 임베딩 텍스트 (Graph-Project B_GNN dataloader/embeddings.py 와 동일 규칙)."""
    t = node.get("type")
    label = node.get("label", "")
    sq = node.get("source_quote", "") or ""
    aliases = node.get("aliases") or []
    alias_str = ", ".join(aliases)
    if t == "philosopher":
        text = f"{label}; aliases: {alias_str}" if alias_str else label
    elif t in ("claim", "concept"):
        text = f"{label}. Context: {sq}" if sq else label
    elif t == "sentence":
        text = sq or label
    else:
        text = f"{label}. {sq}"
    return text.strip() or label or "[empty]"


class PhiloGraph:
    def __init__(self, path: Path | str = GRAPH_JSON):
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        self.nodes: dict[str, dict] = {n["id"]: n for n in data["nodes"]}
        self.edges: list[dict] = data["edges"]
        self._asserts_idx: dict[str, list[tuple[str, str]]] | None = None
        self._opposes_idx: dict[str, list[str]] | None = None
        self._adj_idx: dict[str, list[tuple[str, str]]] | None = None

    # -- 기본 조회 ----------------------------------------------------------
    def node(self, node_id: str) -> dict | None:
        return self.nodes.get(node_id)

    def canonical(self, node_id: str) -> str:
        """same_as 통합 대표 id — canonical_id 가 없거나 'None' 문자열이면 자기 자신."""
        c = self.nodes.get(node_id, {}).get("canonical_id")
        return c if c and c != "None" else node_id

    def stats(self) -> dict:
        from collections import Counter

        return {
            "nodes": len(self.nodes),
            "edges": len(self.edges),
            "types": dict(Counter(n["type"] for n in self.nodes.values())),
        }

    # -- 인덱스 (lazy) -------------------------------------------------------
    @property
    def asserts_index(self) -> dict[str, list[tuple[str, str]]]:
        """claim_id → [(phil_id, phil_label)] — 철학자→claim asserts 엣지."""
        if self._asserts_idx is None:
            idx: dict[str, list[tuple[str, str]]] = {}
            for e in self.edges:
                if e.get("relation") != "asserts":
                    continue
                src, tgt = e.get("source"), e.get("target")
                sp = self.nodes.get(src)
                if sp is not None and sp.get("type") == "philosopher":
                    idx.setdefault(tgt, []).append((src, sp.get("label", src)))
            self._asserts_idx = idx
        return self._asserts_idx

    @property
    def opposes_index(self) -> dict[str, list[str]]:
        """node_id → 반대 입장 노드 id들 (opposes 엣지, 양방향)."""
        if self._opposes_idx is None:
            idx: dict[str, list[str]] = {}
            for e in self.edges:
                if e.get("relation") != "opposes":
                    continue
                src, tgt = e.get("source"), e.get("target")
                if src and tgt:
                    idx.setdefault(src, []).append(tgt)
                    idx.setdefault(tgt, []).append(src)
            self._opposes_idx = idx
        return self._opposes_idx

    @property
    def adj_index(self) -> dict[str, list[tuple[str, str]]]:
        """node_id → [(neighbor_id, relation)] 양방향 인접 인덱스. same_as 제외."""
        if self._adj_idx is None:
            idx: dict[str, list[tuple[str, str]]] = {}
            for e in self.edges:
                r = e.get("relation", "")
                if r == "same_as":
                    continue
                src, tgt = e.get("source"), e.get("target")
                if src and tgt:
                    idx.setdefault(src, []).append((tgt, r))
                    idx.setdefault(tgt, []).append((src, r))
            self._adj_idx = idx
        return self._adj_idx

    # -- 임베딩 대상 ---------------------------------------------------------
    def embed_targets(self) -> list[tuple[str, str]]:
        """(node_id, 임베딩 텍스트) — claim/concept. 결정적 순서(id 정렬)."""
        out = [
            (nid, build_text(n))
            for nid, n in self.nodes.items()
            if n.get("type") in EMBED_TYPES
        ]
        out.sort(key=lambda x: x[0])
        return out

    # -- 번들 보강 (C_RAG GraphRetriever 이식) --------------------------------
    def attach_source_quotes(self, bundle: RetrievalBundle) -> None:
        for n in bundle.all_nodes():
            raw = self.nodes.get(n.id)
            if raw is not None:
                n.source_quote = raw.get("source_quote")

    def expand_neighbors(self, bundle: RetrievalBundle, *,
                         depth: int = 1, max_nodes: int = 50) -> None:
        """회수 노드에서 BFS 1~depth 홉 이웃 확장 — 쿼리 관련도 가중 상위 max_nodes.

        relevance = (출발 시드의 텍스트 cosine) × 0.5^hop. 결정적(정렬) 동작.
        (원본 C_RAG retriever._expand_neighbors 그대로)
        """
        if depth <= 0:
            return
        adj = self.adj_index
        decay = 0.5

        seen = {n.id for n in bundle.all_nodes()}
        frontier: dict[str, float] = {}
        for n in bundle.neighbors:
            frontier[n.id] = max(n.score or 0.0, 0.0)
        for n in bundle.all_nodes():
            frontier.setdefault(n.id, 0.3)

        cand: dict[str, float] = {}
        for _hop in range(1, depth + 1):
            next_frontier: dict[str, float] = {}
            for nid in sorted(frontier):
                r = frontier[nid] * decay
                for neighbor_id, _relation in adj.get(nid, []):
                    if neighbor_id in seen:
                        continue
                    if r > cand.get(neighbor_id, -1.0):
                        cand[neighbor_id] = r
                        next_frontier[neighbor_id] = max(next_frontier.get(neighbor_id, 0.0), r)
            seen.update(next_frontier)
            frontier = next_frontier

        ranked = sorted(cand.items(), key=lambda kv: (-kv[1], kv[0]))[:max_nodes]
        bundle.expanded_nodes = [
            RetrievedNode(
                id=nid,
                type=self.nodes.get(nid, {}).get("type", "unknown"),
                label=self.nodes.get(nid, {}).get("label", nid),
                article=self.nodes.get(nid, {}).get("article"),
                score=round(r, 3),
            )
            for nid, r in ranked
        ]


@lru_cache(maxsize=1)
def get_graph() -> PhiloGraph:
    """프로세스당 1회 로드(19MB JSON) — 세션 간 공유."""
    return PhiloGraph()
