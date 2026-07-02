"""P4 — 억부 유파 충실도 (SPEC §3.2(b)). 정확성이 아니라 '규칙 준수'만 검증.

  신강 → 용신 ∈ {식상, 재성, 관성} (설기/극제)
  신약 → 용신 ∈ {인성, 비겁} (부조)
  중화 → 제약 없음
모든 용신 결과는 trace 를 동반(orphan 금지). 양쪽 분기가 실제로 발생함도 확인.
"""
from __future__ import annotations

import pytest

from engine import scorer
from engine.pillars import compute_chart
from engine.presets import load_preset
from engine.yongsin import eokbu

pytestmark = pytest.mark.interpretation

_DRAIN = {"식상", "재성", "관성"}
_SUPPORT = {"인성", "비겁"}


def test_eokbu_invariants(sample_births):
    preset = load_preset("jeongtong_eokbu")
    weights = preset.interpretation.get("sinkang_weights")
    seen = set()
    for birth in sample_births:
        chart = compute_chart(birth, preset.deterministic)
        scored = scorer.score_strength(chart, weights, "jeongtong_eokbu")
        res = eokbu.select(chart, scored, preset)

        if scored.strength == "신강":
            assert res.family in _DRAIN, f"{birth} 신강인데 용신가족={res.family}"
        elif scored.strength == "신약":
            assert res.family in _SUPPORT, f"{birth} 신약인데 용신가족={res.family}"
        seen.add(scored.strength)

        # orphan 금지
        assert res.trace is not None and res.trace.layer == "L3"
        assert res.claims and all(c.trace is not None for c in res.claims)

    # 양쪽 분기(신강·신약)가 실제로 검증되었는지 — 규칙이 한쪽만 타지 않음
    assert "신강" in seen and "신약" in seen, f"분기 미발생: {seen}"


def test_eokbu_is_deterministic(sample_births):
    """같은 (차트, 프리셋)은 항상 동일 용신 (멱등성, SPEC §3.2(a))."""
    preset = load_preset("jeongtong_eokbu")
    for birth in sample_births[:8]:
        chart = compute_chart(birth, preset.deterministic)
        s1 = scorer.score_strength(chart, None, "jeongtong_eokbu")
        s2 = scorer.score_strength(chart, None, "jeongtong_eokbu")
        r1 = eokbu.select(chart, s1, preset)
        r2 = eokbu.select(chart, s2, preset)
        assert (r1.element, r1.family) == (r2.element, r2.family)
