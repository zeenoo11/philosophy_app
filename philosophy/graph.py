"""PhiloGraph — SEP 철학 지식그래프(unified_graph.json) 로더 + 인덱스.

Graph-Project C_RAG의 GraphRetriever 중 '그래프' 책임만 분리 이식:
asserts(철학자→claim) 인덱스, opposes 인덱스, 인접 인덱스(BFS 확장용),
canonical 통합, source_quote 조인. 순수 파이썬 — GNN/torch 불필요.

데이터: philosophy/data/unified_graph.json (3,600 노드 / 8,397 엣지 —
SEP 31개 article 기반, Graph-Project A_KG/extract 산출물).
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from philosophy.schema import GraphPath, RetrievalBundle, RetrievedNode

DATA_DIR = Path(__file__).parent / "data"
GRAPH_JSON = DATA_DIR / "unified_graph.json"

#: 텍스트 회수(임베딩) 대상 노드 타입 — 의미 단위인 claim/concept.
#: (philosopher 는 저자 랭킹으로, sentence 는 source_quote 로 간접 노출)
EMBED_TYPES = ("claim", "concept")

#: 경로 관계 가중 — 저자/대립(asserts·opposes)이 의미 근거로 가장 강하다.
#: 값이 클수록 '좋은' 간선(비용은 역수). adj 일반 관계는 낮게 둬 hub 남용을 억제.
REL_WEIGHT = {
    "asserts": 1.0, "opposes": 1.0, "grounds": 0.8, "precedent_of": 0.7,
    "quotes": 0.6, "about": 0.6, "example_of": 0.5, "broader": 0.5,
    "related_to": 0.4, "promotes": 0.3, "demotes": 0.3,
}
_REL_DEFAULT = 0.4
#: 경로 중간 노드로 쓰지 않는 타입 — 가치층(value)은 별도 분석축이라 hub 로 남용되면
#: 'benevolence 를 통해 모든 게 연결' 같은 시시한 경로를 만든다(끝점도 허용 안 함).
_PATH_EXCLUDE_TYPES = ("value",)

# 엔티티 링킹용 토큰화 — 이름/개념 표면형에서 무의미 토큰 제거.
_NAME_STOPWORDS = frozenset({
    "the", "of", "de", "van", "von", "da", "di", "la", "le", "el",
    "and", "on", "in", "a", "an",
})


def _norm_name(s: str) -> str:
    """표면형 정규화 — 소문자화, 영문/숫자만 남기고 공백 정리."""
    return re.sub(r"[^a-z0-9]+", " ", (s or "").lower()).strip()


def _name_tokens(s: str) -> list[str]:
    """정규화 토큰(길이 2+, 불용어 제외) — 순서 유지."""
    return [w for w in _norm_name(s).split()
            if len(w) > 1 and w not in _NAME_STOPWORDS]


def _surname_token(label: str) -> str | None:
    """철학자 label 의 성(surname) 토큰 — 'Kant, Immanuel'→kant, 'Friedrich Nietzsche'→nietzsche,
    'Aristotle'→aristotle. 순서 무관 매칭(질의의 마지막 토큰과 대조)에 쓴다."""
    if "," in label:  # 'Surname, First' — 콤마 앞이 성
        head = _name_tokens(label.split(",", 1)[0])
        return head[-1] if head else None
    toks = _name_tokens(label)
    return toks[-1] if toks else None


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
        self._value_idx: dict[str, list[tuple[str, int, float]]] | None = None

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
    def value_index(self) -> dict[str, list[tuple[str, int, float]]]:
        """claim_id → [(value_key, +1|-1, weight)] — Schwartz 가치층(promotes/demotes).

        value_key 는 'self_direction' 형태(value:: 접두사 제거). Graph-Project
        Plan 3 이 구체화한 value_signature 엣지 597건이 원천.
        """
        if self._value_idx is None:
            idx: dict[str, list[tuple[str, int, float]]] = {}
            for e in self.edges:
                r = e.get("relation")
                if r not in ("promotes", "demotes"):
                    continue
                tgt = e.get("target") or ""
                tn = self.nodes.get(tgt)
                if tn is None or tn.get("type") != "value":
                    continue
                key = tgt.split("::", 1)[-1]
                sign = 1 if r == "promotes" else -1
                try:
                    w = float(e.get("weight") or 0.5)
                except (TypeError, ValueError):
                    w = 0.5
                idx.setdefault(e.get("source"), []).append((key, sign, w))
            self._value_idx = idx
        return self._value_idx

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

    @property
    def entity_index(self) -> dict[str, dict[str, list[str]]]:
        """엔티티 링킹 인덱스 — 사용자가 언급한 이름을 그래프 노드로 잇는다.

        {'phil_surname': {surname_token → [phil_node_id]},
         'concept_norm': {정규화 label → [concept_node_id]}}.
        철학자는 성(surname) 토큰으로(어순 무관), 개념은 정규화 label 완전일치로.
        같은 인물의 여러 article-scoped 노드가 모두 담긴다(경로 앵커는 subgraph 별로
        필요하므로) — 정렬된 결정적 목록.
        """
        if getattr(self, "_entity_idx", None) is None:
            phil: dict[str, list[str]] = {}
            concept: dict[str, list[str]] = {}
            for nid in sorted(self.nodes):
                n = self.nodes[nid]
                typ = n.get("type")
                if typ == "philosopher":
                    sur = _surname_token(n.get("label", ""))
                    if sur:
                        phil.setdefault(sur, []).append(nid)
                elif typ == "concept":
                    key = _norm_name(n.get("label", ""))
                    if key:
                        concept.setdefault(key, []).append(nid)
            self._entity_idx = {"phil_surname": phil, "concept_norm": concept}
        return self._entity_idx

    def link_entities(self, names, *, embed_fallback=None,
                      max_hits_per_name: int = 12) -> list[str]:
        """사용자가 언급한 이름/개념 → 그래프 노드 id 목록 (경로 추론 앵커).

        절차(문자열 우선, 임베딩 폴백):
          1) 철학자 성(surname) 매칭 — 질의의 마지막 유의 토큰이 성 인덱스에 있으면 채택
             (같은 인물의 모든 article-scoped 노드 — subgraph 별 앵커).
          2) 개념 label 완전일치.
          3) 둘 다 실패 & embed_fallback 제공 시 임베딩 폴백(개념 노드 1개) — 조용히.
        전부 실패하면 그 이름은 건너뛴다. 반환은 dedup(첫 등장 순서) 결과.
        """
        idx = self.entity_index
        out: list[str] = []
        seen: set[str] = set()

        def _add(ids: list[str]) -> None:
            for nid in ids[:max_hits_per_name]:
                if nid not in seen:
                    seen.add(nid)
                    out.append(nid)

        for name in names or []:
            toks = _name_tokens(name)
            hit: list[str] = []
            if toks:  # 1) 철학자 성 매칭 (어순 무관 — 마지막 토큰)
                hit = idx["phil_surname"].get(toks[-1], [])
            if not hit:  # 2) 개념 완전일치
                hit = idx["concept_norm"].get(_norm_name(name), [])
            if not hit and embed_fallback is not None:  # 3) 임베딩 폴백
                try:
                    fb = embed_fallback(name)
                except Exception:  # noqa: BLE001 — 폴백 실패는 조용히(현행 폴백 규약)
                    fb = None
                if fb:
                    hit = [fb]
            if hit:
                _add(hit)
        return out

    # -- 경로 탐색 (query-side GraphRAG — 생각의 경로) ------------------------
    @property
    def dir_adj_index(self) -> dict[str, list[tuple[str, str, bool]]]:
        """방향 보존 인접 인덱스 — node_id → [(neighbor_id, relation, forward)].

        forward=True 면 원 간선이 node→neighbor(정방향), False 면 neighbor→node(역방향).
        경로를 'A —asserts→ X ←asserts— B' 처럼 화살표로 렌더하기 위해 방향을 남긴다.
        same_as 는 제외(어순·중복 통합용 메타 간선).
        """
        if getattr(self, "_dir_adj", None) is None:
            idx: dict[str, list[tuple[str, str, bool]]] = {}
            for e in self.edges:
                r = e.get("relation", "")
                if r == "same_as":
                    continue
                src, tgt = e.get("source"), e.get("target")
                if src and tgt:
                    idx.setdefault(src, []).append((tgt, r, True))
                    idx.setdefault(tgt, []).append((src, r, False))
            self._dir_adj = idx
        return self._dir_adj

    def _excluded(self, nid: str) -> bool:
        return self.nodes.get(nid, {}).get("type") in _PATH_EXCLUDE_TYPES

    def _shortest_path(self, source: str, targets: set[str], *,
                       max_len: int) -> GraphPath | None:
        """source 에서 targets 중 하나까지 최단 경로(홉 수 최소) — 결정론적 BFS.

        홉 계층을 넓히며 각 노드의 최단-홉 부분경로를 한 번 확정(global visited)한다.
        같은 홉이면 관계 가중 합이 큰 경로를, 그마저 같으면 노드열이 사전순으로 작은
        경로를 택한다(간선 이웃 정렬 순회 + tie-break). 중간 노드는 제외 타입 배제.
        간선 가중은 REL_WEIGHT, 경로 점수는 (평균 가중 × 길이 감쇠 0.5^(홉-1)).
        """
        if source in targets or source not in self.dir_adj_index:
            return None
        adj = self.dir_adj_index
        best: dict[str, tuple[list[str], list[tuple[str, bool]]]] = {
            source: ([source], [])}
        visited: set[str] = {source}   # 최단-홉 부분경로가 확정된 노드
        frontier = [source]
        for _hop in range(max_len):
            reached: dict[str, tuple[list[str], list[tuple[str, bool]]]] = {}
            found: list[GraphPath] = []
            for nid in frontier:
                nodes_so_far, rels_so_far = best[nid]
                for neighbor, rel, forward in sorted(adj.get(nid, [])):
                    new_rels = rels_so_far + [(rel, forward)]
                    if neighbor in targets:  # 도달 — 이 계층이 최단 홉
                        found.append(self._make_path(nodes_so_far + [neighbor], new_rels))
                        continue
                    if neighbor in visited or self._excluded(neighbor):
                        continue
                    cand = (nodes_so_far + [neighbor], new_rels)
                    cur = reached.get(neighbor)
                    if cur is None or self._better(cand, cur):
                        reached[neighbor] = cand
            if found:  # 최단 홉 계층에서 최선 1개(점수↓, 노드열↑)를 결정적으로 채택
                found.sort(key=lambda p: (-p.score, p.nodes))
                return found[0]
            if not reached:
                return None
            visited.update(reached)
            best.update(reached)
            frontier = sorted(reached)
        return None

    def _better(self, a, b) -> bool:
        """같은 홉 수의 두 부분경로 중 a 가 더 나은가 — 가중합↑, 동률이면 노드열 사전순↓."""
        wa, wb = self._weight_sum(a[1]), self._weight_sum(b[1])
        if wa != wb:
            return wa > wb
        return a[0] < b[0]

    @staticmethod
    def _weight_sum(rels: list[tuple[str, bool]]) -> float:
        return sum(REL_WEIGHT.get(r, _REL_DEFAULT) for r, _f in rels)

    def _make_path(self, nodes: list[str], rels: list[tuple[str, bool]]) -> GraphPath:
        w = self._weight_sum(rels)
        hops = max(len(rels), 1)
        score = round((w / hops) * (0.5 ** (hops - 1)), 4)
        return GraphPath(nodes=list(nodes), rels=list(rels), score=score)

    def find_paths(self, sources, targets, *, max_paths: int = 5,
                   max_len: int = 4) -> list[GraphPath]:
        """sources↔targets 최단 경로들 — 결정적. 상위 max_paths(길이↑, 점수↓, 노드열↑ 정렬).

        각 (source, target-set) 에서 최단 1개를 뽑고, 전역에서 중복 제거 후 정렬·절단.
        그래프가 작아(3.5k 노드) 소수의 앵커·시드에 대해 ms 단위로 끝난다.
        """
        src = [s for s in dict.fromkeys(sources) if s in self.nodes]
        tgt = {t for t in targets if t in self.nodes}
        if not src or not tgt:
            return []
        found: dict[tuple, GraphPath] = {}
        for s in sorted(src):
            others = tgt - {s}
            if not others:
                continue
            p = self._shortest_path(s, others, max_len=max_len)
            if p is not None and len(p.nodes) >= 2:
                found[tuple(p.nodes)] = p
        ranked = sorted(found.values(),
                        key=lambda p: (len(p.nodes), -p.score, p.nodes))
        return ranked[:max_paths]

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
