"""Schwartz 기본가치 프로파일 — Graph-Project Plan 3(value_signature 층)의 다운스트림.

원 계획(docs/plans/PLAN_schwartz_value_layer.md §6.1)이 예고한 'C_RAG 진단 확장':
회수된 유사 claim 의 promotes/demotes 엣지(value 노드 10종, weight 0.2~0.9)를
질의 유사도로 가중 집계해 **사용자 가치 프로파일(10차원)** 을 만들고,
circumplex(원형) 인접 가치를 접어 **8각 레이더 축**으로 표시한다.

집계는 결정론(그래프 엣지 × cosine 가중) — LLM 비관여. 가치 표명이 감지되지
않으면 빈 프로파일을 정직하게 반환한다(원 계획의 abstain 정신 — 형이상학적
주장은 가치 중립이 정상).
"""
from __future__ import annotations

from engine.i18n import t
from philosophy.graph import PhiloGraph, get_graph
from philosophy.schema import RetrievalBundle

#: circumplex 순서 (Schwartz 1992) — 인접 = 동기적 친화, 대각 = 갈등.
SCHWARTZ_ORDER = [
    "self_direction", "stimulation", "hedonism", "achievement", "power",
    "security", "conformity", "tradition", "benevolence", "universalism",
]

VALUE_KR = {
    "self_direction": "자기주도", "stimulation": "자극", "hedonism": "쾌락",
    "achievement": "성취", "power": "권력", "security": "안전",
    "conformity": "동조", "tradition": "전통", "benevolence": "자애",
    "universalism": "보편",
}

QUADRANT_KR = {
    "self_direction": "변화 개방", "stimulation": "변화 개방", "hedonism": "변화 개방",
    "achievement": "자기 고양", "power": "자기 고양",
    "security": "보존", "conformity": "보존", "tradition": "보존",
    "benevolence": "자기 초월", "universalism": "자기 초월",
}

# 영어 표시 라벨 — 내부 키(영문 snake)·한국어 라벨은 정체성 키라 불변,
# 표시 시점(t)에만 선택된다 (engine/i18n 설계 원칙).
VALUE_EN = {
    "self_direction": "Self-Direction", "stimulation": "Stimulation", "hedonism": "Hedonism",
    "achievement": "Achievement", "power": "Power", "security": "Security",
    "conformity": "Conformity", "tradition": "Tradition", "benevolence": "Benevolence",
    "universalism": "Universalism",
}

_QUADRANT_EN = {
    "변화 개방": "Openness to Change", "자기 고양": "Self-Enhancement",
    "보존": "Conservation", "자기 초월": "Self-Transcendence",
}

_OCTAGON_EN = {
    "자기주도": "Self-Direction", "자극·쾌락": "Stimulation·Hedonism", "성취": "Achievement",
    "권력": "Power", "안전": "Security", "전통·동조": "Tradition·Conformity",
    "자애": "Benevolence", "보편": "Universalism",
}


def _vlabel(key: str) -> str:
    """가치 표시 라벨 — ko 면 VALUE_KR, en 이면 VALUE_EN."""
    return t(VALUE_KR[key], VALUE_EN[key])


def _qlabel(key: str) -> str:
    q = QUADRANT_KR[key]
    return t(q, _QUADRANT_EN.get(q, q))

#: 8각 레이더 축 — circumplex 순서 유지, 인접 가치 2쌍을 병합(평균).
#: 대각이 이론적 대립과 마주본다: 자기주도↔안전, 성취↔자애, 자극·쾌락↔전통·동조.
OCTAGON_AXES: list[tuple[str, tuple[str, ...]]] = [
    ("자기주도", ("self_direction",)),
    ("자극·쾌락", ("stimulation", "hedonism")),
    ("성취", ("achievement",)),
    ("권력", ("power",)),
    ("안전", ("security",)),
    ("전통·동조", ("tradition", "conformity")),
    ("자애", ("benevolence",)),
    ("보편", ("universalism",)),
]


def _value_key(node_id: str) -> str:
    """value::self_direction → self_direction."""
    return node_id.split("::", 1)[-1]


def score_values(bundles: list[RetrievalBundle],
                 graph: PhiloGraph | None = None) -> dict[str, float]:
    """회수 결과 → 10차원 raw 프로파일 {value: 부동소수}.

    각 회수 노드(neighbors + expanded)의 promotes(+)/demotes(−) 엣지를
    (엣지 weight × 노드 유사도) 로 누적. 전부 0이면 가치 표명 없음.
    """
    g = graph or get_graph()
    raw = {v: 0.0 for v in SCHWARTZ_ORDER}
    idx = g.value_index
    for b in bundles:
        for n in [*b.neighbors, *b.expanded_nodes]:
            sim = max(n.score or 0.0, 0.0)
            if sim == 0.0:
                continue
            for vkey, sign, w in idx.get(n.id, []):
                if vkey in raw:
                    raw[vkey] += sign * w * sim
    return {k: round(v, 4) for k, v in raw.items()}


def has_signal(raw: dict[str, float]) -> bool:
    return any(abs(v) > 1e-9 for v in (raw or {}).values())


def to_octagon(raw: dict[str, float]) -> list[tuple[str, float]] | None:
    """10차원 raw → 8각 축 [(한글라벨, 0~10)]. 신호 없으면 None.

    demotes 우세(음수) 축은 0 으로 바닥 처리하고, 최대 축을 10 으로 하는
    상대 스케일 — '무엇이 상대적으로 두드러지는가'를 보는 그림이다.
    """
    if not has_signal(raw):
        return None
    merged = []
    for label, keys in OCTAGON_AXES:
        vals = [raw.get(k, 0.0) for k in keys]
        merged.append((label, sum(vals) / len(vals)))
    top = max(v for _, v in merged)
    if top <= 0:
        return None
    return [(t(label, _OCTAGON_EN.get(label, label)), round(max(0.0, v) / top * 10.0, 2))
            for label, v in merged]


def top_values(raw: dict[str, float], *, k: int = 3) -> list[tuple[str, str, float]]:
    """지향 상위 k — [(표시라벨, 사분면, raw점수)] (양수만, 라벨은 현재 언어)."""
    pos = sorted(((v, k_) for k_, v in raw.items() if v > 0), reverse=True)
    return [(_vlabel(k_), _qlabel(k_), round(v, 2)) for v, k_ in pos[:k]]


def demoted_values(raw: dict[str, float], *, k: int = 2) -> list[tuple[str, float]]:
    """배척(음수) 상위 k — [(표시라벨, raw점수)] (라벨은 현재 언어)."""
    neg = sorted(((v, k_) for k_, v in raw.items() if v < 0))
    return [(_vlabel(k_), round(v, 2)) for v, k_ in neg[:k]]


def format_values_section(raw: dict[str, float]) -> str:
    """format_diagnosis 용 마크다운 섹션 — 신호 없으면 빈 문자열."""
    if not has_signal(raw):
        return ""
    L = ["\n## " + t("가치 프로파일 (Schwartz 기본가치)", "Value Profile (Schwartz Basic Values)")]
    tops = top_values(raw)
    if tops:
        L.append(t("지향: ", "Oriented toward: ")
                 + " · ".join(f"{n}({q}) +{s}" for n, q, s in tops))
    demo = demoted_values(raw)
    if demo:
        L.append(t("배척: ", "Averse to: ") + " · ".join(f"{n} {s}" for n, s in demo))
    return "\n".join(L)
