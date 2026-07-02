"""Diagnosis 빌더 — Graph-Project C_RAG(rag/stages/diagnose.py) 이식.

build_diagnosis: bundle들 + 철학자 랭킹 → Diagnosis
format_diagnosis: Diagnosis → 사람이 읽는 진단 리포트(LLM user content 겸 근거 패널)
원본과의 차이: Schwartz 가치 프로파일(value_scores — Plan 3 다운스트림) 반영.
"""
from __future__ import annotations

from collections import Counter

from philosophy import values as schwartz
from philosophy.schema import Diagnosis, PhilosopherMatch, RetrievalBundle, RetrievedNode


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
    )


def format_diagnosis(d: Diagnosis) -> str:
    # 전개 순서: 유사한 주장 → 가까운 철학자 → (학파) → 대비되는 입장.
    L = ["# 가치관 진단", f"\n질의: {d.query}"]
    if d.sub_claims:
        L.append("분해된 명제: " + "  |  ".join(d.sub_claims))

    L.append(f"\n## 유사한 주장 (회수 top {len(d.similar_claims)})")
    for i, n in enumerate(d.similar_claims, 1):
        quote = f'  ·  "{n.source_quote}"' if n.source_quote else ""
        L.append(f"{i}. **{n.label}**  ·  유사도 **{(n.score or 0):.2f}**  ·  `{n.id}`{quote}")

    L.append(f"\n## 가장 가까운 철학자 (top {len(d.top_philosophers)})")
    for i, p in enumerate(d.top_philosophers, 1):
        arts = f"  ·  {', '.join(p.articles[:3])}" if p.articles else ""
        L.append(f"{i}. **{p.label}**  ·  점수 **{p.score}**  ·  유사주장 {p.n_support}건{arts}")
        for c in p.support_claims:
            L.append(f"   - {c}")

    if d.predicted_community >= 0:
        L.append(f"\n## 추정 학파 c{d.predicted_community} — 대표 사상")
        for i, c in enumerate(d.school_concepts, 1):
            quote = f'  ·  "{c.source_quote}"' if c.source_quote else ""
            L.append(f"{i}. **{c.label}**  ·  `{c.id}`{quote}")

    if d.contrasting_claims:
        L.append("\n## 당신과 대비되는 입장 (opposes)")
        for i, n in enumerate(d.contrasting_claims, 1):
            L.append(f"{i}. **{n.label}**  ·  `{n.id}`")

    section = schwartz.format_values_section(d.value_scores)
    if section:
        L.append(section)
    return "\n".join(L)
