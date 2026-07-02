"""P4 — L2 스코어러 단조성 invariant (SPEC §3.0). 내적 일관성만 검증.

부조(비겁·인성) 세력이 늘면 강약 비율(ratio)이 단조 증가해야 한다.
"""
from __future__ import annotations

import pytest

from engine import scorer
from engine.pillars import Chart, DeterministicConfig, Pillar

pytestmark = pytest.mark.interpretation
_CFG = DeterministicConfig()


def _chart(day, year, month, hour) -> Chart:
    """(천간,지지) 튜플들로 차트 구성 — 단조성 실험용."""
    return Chart(
        year=Pillar("년", *year), month=Pillar("월", *month),
        day=Pillar("일", *day), hour=Pillar("시", *hour),
        config=_CFG, meta={},
    )


def test_strength_monotonic_in_support():
    """일간(甲木) 차트에서 시주를 재성(土)→비겁(木)으로 바꾸면 ratio 증가."""
    # 일간 甲子. 비교 대상은 시주만 교체 (모두 유효 간지: 같은 음양)
    drain = _chart(day=(0, 0), year=(4, 6), month=(4, 6), hour=(4, 6))   # 시 戊午(재성 土)
    support = _chart(day=(0, 0), year=(4, 6), month=(4, 6), hour=(0, 0))  # 시 甲子(비겁 木)
    s_drain = scorer.score_strength(drain)
    s_support = scorer.score_strength(support)
    assert s_support.ratio > s_drain.ratio


def test_strength_bands_consistent():
    """ratio 와 강약 라벨의 정합 (밴드 경계 일관)."""
    # 전부 인성·비겁으로 둘러싼 甲木 → 신강
    strong = _chart(day=(0, 0), year=(0, 0), month=(8, 0), hour=(0, 0))  # 甲子/壬子/甲子
    s = scorer.score_strength(strong)
    assert s.strength == "신강" and s.ratio >= 0.5
    # 전부 재성·관성으로 둘러싼 甲木 → 신약
    weak = _chart(day=(0, 0), year=(6, 8), month=(6, 8), hour=(6, 8))    # 庚申(관성 金)
    s2 = scorer.score_strength(weak)
    assert s2.strength == "신약" and s2.ratio <= 0.35


def test_scorer_emits_trace():
    s = scorer.score_strength(_chart((0, 0), (4, 6), (4, 6), (4, 6)), preset_id="x")
    assert s.trace.layer == "L2" and s.trace.preset_id == "x"
    assert s.claims and all(c.trace for c in s.claims)
