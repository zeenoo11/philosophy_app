"""P4 — 맹파(구조형) 충실도. 용신을 쓰지 않고 주공/체용/상을 산출함을 검증.

대조군이므로 억부/조후의 용신 invariant 대상이 아니다(다른 유파 규칙 강요 금지).
"""
from __future__ import annotations

import pytest

from engine import scorer
from engine.interpret import interpret
from engine.pillars import BirthInput, compute_chart
from engine.presets import load_preset
from engine.yongsin import resolve, structure

pytestmark = pytest.mark.interpretation


def test_mangpa_produces_structure_not_yongsin(sample_births):
    preset = load_preset("mangpa")
    for birth in sample_births[:10]:
        chart = compute_chart(birth, preset.deterministic)
        res = structure.analyze_structure(chart, preset)
        assert res.jugong and "가족" in res.jugong
        assert res.cheyong and "체" in res.cheyong and "용" in res.cheyong
        assert res.sang
        assert res.trace is not None and res.claims


def test_mangpa_bypasses_yongsin_layer():
    preset = load_preset("mangpa")
    chart = compute_chart(BirthInput(1990, 6, 15, 14, 30), preset.deterministic)
    scored = scorer.score_strength(chart, None, "mangpa")
    out = resolve(chart, scored, preset)
    assert out["kind"] == "structure"
    assert out["policy"] is None


def test_mangpa_in_interpret_has_no_yongsin():
    r = interpret(BirthInput(1990, 6, 15, 14, 30))
    block = r["by_preset"]["mangpa"]
    assert block["engine"] == "structure"
    assert "yongsin" not in block
    assert block["structure"]["jugong"] and block["structure"]["sang"]
