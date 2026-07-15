"""Diagnosis 빌더 — Graph-Project C_RAG(rag/stages/diagnose.py) 이식.

build_diagnosis: bundle들 + 철학자 랭킹 → Diagnosis
format_diagnosis: Diagnosis → 사람이 읽는 진단 리포트(LLM user content 겸 근거 패널)
원본과의 차이: Schwartz 가치 프로파일(value_scores — Plan 3 다운스트림) 반영.
"""
from __future__ import annotations

from collections import Counter

from engine.i18n import t
from philosophy import values as schwartz
from philosophy.schema import (
    Diagnosis, GraphPath, PhilosopherMatch, RetrievalBundle, RetrievedNode,
)


def _person_name(label: str) -> str:
    """'Kant, Immanuel' → 'Immanuel Kant' (읽기 좋은 어순). 콤마 없으면 그대로."""
    if "," in label:
        sur, first = label.split(",", 1)
        return f"{first.strip()} {sur.strip()}".strip()
    return label


def _truncate(s: str, n: int = 68) -> str:
    s = " ".join((s or "").split())
    return s if len(s) <= n else s[: n - 1].rstrip() + "…"


def _path_node_display(node: dict | None, nid: str) -> str:
    """경로 노드 표시 — 철학자는 이름, 그 외(주장·개념)는 '따옴표로 감싼 짧은 라벨'.

    노드 코드(id)는 절대 노출하지 않는다 — 사람이 읽는 타이핑된 체인용.
    """
    if node is None:
        return _truncate(nid, 40)
    if node.get("type") == "philosopher":
        return _person_name(node.get("label", nid))
    return "'" + _truncate(node.get("label") or node.get("source_quote") or nid) + "'"


def render_path(path: GraphPath) -> str:
    """GraphPath → 'A —asserts→ \"주장 X\" ←asserts— B' 형태의 읽기 쉬운 체인.

    forward=True 면 정방향 화살표(—rel→), False 면 역방향(←rel—). 방향으로 누가 무엇을
    주장/반대하는지 드러낸다. 노드 코드 비노출(라벨만).
    """
    from philosophy.graph import get_graph

    g = get_graph()
    disp = [_path_node_display(g.node(nid), nid) for nid in path.nodes]
    if not disp:
        return ""
    out = disp[0]
    for i, (rel, forward) in enumerate(path.rels):
        arrow = f" —{rel}→ " if forward else f" ←{rel}— "
        out += arrow + disp[i + 1]
    return out


def _merge_nodes(nodes: list[RetrievedNode], limit: int) -> list[RetrievedNode]:
    """id 기준 dedup(최고 score 유지) 후 score 내림차순."""
    best: dict[str, RetrievedNode] = {}
    for n in nodes:
        cur = best.get(n.id)
        if cur is None or (n.score or 0) > (cur.score or 0):
            best[n.id] = n
    return sorted(best.values(), key=lambda n: n.score or 0, reverse=True)[:limit]


def build_diagnosis(
    query: str,
    sub_claims: list[str],
    bundles: list[RetrievalBundle],
    top_philosophers: list[PhilosopherMatch],
    value_scores: dict | None = None,
    paths: list[GraphPath] | None = None,
    anchors: list[str] | None = None,
) -> Diagnosis:
    comms = [b.predicted_community for b in bundles if b.predicted_community >= 0]
    pred_comm = Counter(comms).most_common(1)[0][0] if comms else -1
    school = _merge_nodes(
        [c for b in bundles if b.predicted_community == pred_comm for c in b.community_concepts],
        limit=6,
    )
    similar = _merge_nodes([n for b in bundles for n in b.neighbors], limit=10)
    contrast = _merge_nodes([o for b in bundles for o in b.opposes_claims], limit=5)
    return Diagnosis(
        query=query,
        sub_claims=sub_claims,
        top_philosophers=top_philosophers,
        predicted_community=pred_comm,
        school_concepts=school,
        similar_claims=similar,
        contrasting_claims=contrast,
        value_scores=value_scores or {},
        paths=paths or [],
        anchors=anchors or [],
    )


def format_diagnosis(d: Diagnosis) -> str:
    # 전개 순서: 유사한 주장 → 가까운 철학자 → (학파) → 대비되는 입장.
    L = ["# " + t("가치관 진단", "Values Diagnosis"),
         "\n" + t("질의", "Query") + f": {d.query}"]
    if d.sub_claims:
        L.append(t("분해된 명제", "Decomposed propositions") + ": "
                 + "  |  ".join(d.sub_claims))

    L.append("\n## " + t(f"유사한 주장 (회수 top {len(d.similar_claims)})",
                         f"Similar Claims (top {len(d.similar_claims)} retrieved)"))
    for i, n in enumerate(d.similar_claims, 1):
        quote = f'  ·  "{n.source_quote}"' if n.source_quote else ""
        L.append(f"{i}. **{n.label}**  ·  " + t("유사도", "similarity")
                 + f" **{(n.score or 0):.2f}**  ·  `{n.id}`{quote}")

    L.append("\n## " + t(f"가장 가까운 철학자 (top {len(d.top_philosophers)})",
                         f"Closest Philosophers (top {len(d.top_philosophers)})"))
    for i, p in enumerate(d.top_philosophers, 1):
        arts = f"  ·  {', '.join(p.articles[:3])}" if p.articles else ""
        L.append(f"{i}. **{p.label}**  ·  " + t("점수", "score") + f" **{p.score}**  ·  "
                 + t(f"유사주장 {p.n_support}건", f"{p.n_support} similar claims") + arts)
        for c in p.support_claims:
            L.append(f"   - {c}")

    if d.paths:
        L.append("\n## " + t("🕸 생각의 경로 (Path of Thought)",
                             "🕸 Path of Thought"))
        L.append(t("당신의 생각을 잇는 그래프 위 관계 체인 — 화살표는 누가 무엇을 "
                   "주장(asserts)·반대(opposes)하는지를 가리킵니다:",
                   "Relation chains on the graph that connect your idea — arrows show who "
                   "asserts or opposes what:"))
        for i, p in enumerate(d.paths, 1):
            L.append(f"{i}. {render_path(p)}")

    if d.predicted_community >= 0:
        L.append("\n## " + t(f"추정 학파 c{d.predicted_community} — 대표 사상",
                             f"Predicted School c{d.predicted_community} — Representative Ideas"))
        for i, c in enumerate(d.school_concepts, 1):
            quote = f'  ·  "{c.source_quote}"' if c.source_quote else ""
            L.append(f"{i}. **{c.label}**  ·  `{c.id}`{quote}")

    if d.contrasting_claims:
        L.append("\n## " + t("당신과 대비되는 입장 (opposes)",
                             "Positions Contrasting Yours (opposes)"))
        for i, n in enumerate(d.contrasting_claims, 1):
            L.append(f"{i}. **{n.label}**  ·  `{n.id}`")

    section = schwartz.format_values_section(d.value_scores)
    if section:
        L.append(section)
    return "\n".join(L)
