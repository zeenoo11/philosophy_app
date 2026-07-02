"""해석 레이어 분리 검증 (구조). 해석 '정확성'은 검증하지 않는다(정답 없음).

  • 프리셋 레지스트리가 로드되고 결정론/해석 정책이 분리돼 있는가
  • 결정론 레이어는 프리셋 무관 동일한가 (SPEC §3.2(c) 차분 기대)
  • 출처추적(trace) 계약 타입이 존재하는가
"""
from __future__ import annotations

import pytest

from engine.presets import list_presets, load_preset
from engine.pillars import BirthInput, DeterministicConfig, compute_chart
from engine.provenance import Claim, Trace

pytestmark = pytest.mark.interpretation


def test_all_presets_load():
    ids = list_presets()
    assert {"jeongtong_eokbu", "johu_centered", "mangpa"} <= set(ids)
    for pid in ids:
        p = load_preset(pid)
        assert isinstance(p.deterministic, DeterministicConfig)
        assert p.lineage, f"{pid} 에 lineage(고전 근거) 누락"


def test_preset_engine_types():
    assert load_preset("jeongtong_eokbu").engine == "yongsin"
    assert load_preset("johu_centered").engine == "yongsin"
    assert load_preset("mangpa").engine == "structure"


def test_yongsin_policy_diverges_between_presets():
    """억부 vs 조후: 용신 정책 우선순위가 갈린다(해석 분기의 출처)."""
    eokbu_p = load_preset("jeongtong_eokbu").interpretation["yongsin_policy"]
    johu_p = load_preset("johu_centered").interpretation["yongsin_policy"]
    assert eokbu_p[0] == "eokbu" and johu_p[0] == "johu"
    assert eokbu_p != johu_p


def test_deterministic_layer_is_preset_agnostic():
    """SPEC §3.2(c): 동일 결정론 토글을 쓰는 프리셋은 8글자가 반드시 동일.

    억부/조후는 결정론 토글이 같으므로 차트가 동일해야 한다(용신만 갈림).
    """
    birth = BirthInput(1990, 6, 15, 14, 30)
    a = compute_chart(birth, load_preset("jeongtong_eokbu").deterministic)
    b = compute_chart(birth, load_preset("johu_centered").deterministic)
    assert a.eight_chars() == b.eight_chars()
    assert (a.year.gz60, a.month.gz60, a.day.gz60, a.hour.gz60) == \
           (b.year.gz60, b.month.gz60, b.day.gz60, b.hour.gz60)


def test_provenance_contract_exists():
    """모든 해석 문장이 들고 다닐 trace 계약 타입(SPEC §2.2)."""
    tr = Trace(rule_id="eokbu.weak.support", preset_id="jeongtong_eokbu", layer="L3",
               inputs={"sinkang_score": 2.1, "threshold": 3.0},
               classical_source="적천수 / 서락오 주석")
    claim = Claim(claim="신약하여 인성·비겁의 도움이 필요", trace=tr)
    assert claim.trace.layer == "L3"
    assert claim.trace.rule_id.startswith("eokbu")
