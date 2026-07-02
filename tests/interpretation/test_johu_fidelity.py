"""P4 — 조후 유파 충실도. 이 정책 고유의 규칙만 검증(억부 규칙을 강요하지 않음).

  겨울(亥子丑)·戌 → 火 용신,  여름(巳午未) → 水 용신,
  辰(늦봄 습)·봄(寅卯)·가을(申酉) → 미결정(None).
  火/水 부재 시 "시급", 존재 시 "보강" (용신 오행 선택 자체는 불변).

⚠️ 외부 정답을 박제하지 않는다 — johu_table 의 정밀화 규칙 준수만 검증한다.
"""
from __future__ import annotations

import pytest

from engine import constants as C, scorer
from engine.pillars import Chart, DeterministicConfig, Pillar, compute_chart
from engine.presets import load_preset
from engine.yongsin import johu

pytestmark = pytest.mark.interpretation

_HWA, _SU = 1, 4  # 火, 水
_COLD = (11, 0, 1)   # 亥子丑
_HOT = (5, 6, 7)     # 巳午未


@pytest.fixture(scope="module")
def preset():
    return load_preset("johu_centered")


def _mk_chart(day_stem: int, month_branch: int, *, fill_stem: int, fill_branch: int) -> Chart:
    """합성 차트: 월지만 고정하고 나머지 7글자는 (fill_stem, fill_branch)로 채움.

    fill_* 로 사주 내 오행 분포(火/水 존재감)를 결정론적으로 통제한다.
    """
    cfg = DeterministicConfig()
    return Chart(
        year=Pillar("년", fill_stem, fill_branch),
        month=Pillar("월", fill_stem, month_branch),
        day=Pillar("일", day_stem, fill_branch),
        hour=Pillar("시", fill_stem, fill_branch),
        config=cfg,
    )


def _select(chart, preset):
    scored = scorer.score_strength(chart, None, "johu_centered")
    return johu.select(chart, scored, preset)


# ── 충실도 invariant: 실제 표본에서 계절 분기 + trace/claim 동반 ──────────────
def test_johu_invariants(sample_births, preset):
    saw_warm = saw_cool = saw_none = False
    for birth in sample_births:
        chart = compute_chart(birth, preset.deterministic)
        res = _select(chart, preset)
        mb = chart.month.branch
        if mb in _COLD:
            assert res is not None and res.element == _HWA
            saw_warm = True
        elif mb in _HOT:
            assert res is not None and res.element == _SU
            saw_cool = True
        else:                       # 환절기/온화
            assert res is None
            saw_none = True
        if res is not None:
            assert res.trace is not None and res.claims
            assert res.policy == "johu"
    assert saw_warm and saw_cool and saw_none


def test_signature_returns_yongsinresult_or_none(sample_births, preset):
    """select 시그니처/반환형 — YongsinResult | None 만."""
    from engine.interp_types import YongsinResult
    for birth in sample_births:
        chart = compute_chart(birth, preset.deterministic)
        res = _select(chart, preset)
        assert res is None or isinstance(res, YongsinResult)


# ── 계절별 용신 오행 + rule_id (월지 전수) ────────────────────────────────────
@pytest.mark.parametrize("mb", _COLD)
def test_cold_branches_pick_fire(mb, preset):
    chart = _mk_chart(0, mb, fill_stem=0, fill_branch=2)  # 甲/寅 → 火 부재
    res = _select(chart, preset)
    assert res is not None
    assert res.element == _HWA
    assert res.trace.rule_id == "johu.cold.warm"
    assert res.trace.inputs["한난"] == "한"


@pytest.mark.parametrize("mb", _HOT)
def test_hot_branches_pick_water(mb, preset):
    chart = _mk_chart(2, mb, fill_stem=2, fill_branch=6)  # 丙/午 → 水 부재
    res = _select(chart, preset)
    assert res is not None
    assert res.element == _SU
    assert res.trace.rule_id == "johu.hot.cool"
    assert res.trace.inputs["한난"] == "난"


def test_sul_branch_treated_as_warm(preset):
    """戌(10): 늦가을 건조·한기 시작 → 火, 겨울에 준하되 rule_id 구분."""
    chart = _mk_chart(0, 10, fill_stem=0, fill_branch=2)  # 甲/寅
    res = _select(chart, preset)
    assert res is not None
    assert res.element == _HWA
    assert res.trace.rule_id == "johu.late_autumn.warm"
    assert res.trace.inputs["한난"] == "한"


@pytest.mark.parametrize("mb", [4, 2, 3, 8, 9])  # 辰 寅卯 申酉
def test_transitional_branches_return_none(mb, preset):
    """辰(늦봄 습)·봄(寅卯)·가을(申酉)은 조후 미결정 → None (정책 체인 다음으로)."""
    chart = _mk_chart(0, mb, fill_stem=0, fill_branch=2)
    assert _select(chart, preset) is None


def test_jin_branch_is_none(preset):
    """辰(4) 단독 명시 — 늦봄 습은 조후가 결정하지 않는다."""
    chart = _mk_chart(0, 4, fill_stem=0, fill_branch=0)
    assert _select(chart, preset) is None


# ── 시급/보강: 용신 오행 부재 여부 (선택 자체는 불변) ─────────────────────────
def test_cold_without_fire_is_urgent(preset):
    """겨울인데 火 부재 → claim '시급', 용신은 여전히 火."""
    chart = _mk_chart(8, 0, fill_stem=8, fill_branch=0)  # 壬/子 → 火수=0
    res = _select(chart, preset)
    assert res is not None and res.element == _HWA
    assert res.trace.inputs["火수"] == 0
    assert res.trace.inputs["용신부재"] is True
    assert res.trace.inputs["조후강도"] == "시급"
    assert "시급" in res.claims[0].claim


def test_cold_with_fire_is_reinforcement(preset):
    """겨울이고 火 존재 → claim '보강', 용신은 여전히 火."""
    chart = _mk_chart(2, 0, fill_stem=2, fill_branch=6)  # 丙/午 → 火수>0
    res = _select(chart, preset)
    assert res is not None and res.element == _HWA
    assert res.trace.inputs["火수"] > 0
    assert res.trace.inputs["용신부재"] is False
    assert res.trace.inputs["조후강도"] == "보강"
    assert "보강" in res.claims[0].claim


def test_hot_without_water_is_urgent(preset):
    """여름인데 水 부재 → '시급', 용신은 여전히 水."""
    chart = _mk_chart(2, 6, fill_stem=2, fill_branch=6)  # 丙/午 → 水수=0
    res = _select(chart, preset)
    assert res is not None and res.element == _SU
    assert res.trace.inputs["水수"] == 0
    assert res.trace.inputs["조후강도"] == "시급"
    assert "시급" in res.claims[0].claim


def test_hot_with_water_is_reinforcement(preset):
    """여름이고 水 존재 → '보강', 용신은 여전히 水."""
    chart = _mk_chart(8, 6, fill_stem=8, fill_branch=11)  # 壬/亥 → 水수>0
    res = _select(chart, preset)
    assert res is not None and res.element == _SU
    assert res.trace.inputs["水수"] > 0
    assert res.trace.inputs["조후강도"] == "보강"
    assert "보강" in res.claims[0].claim


# ── 충실도 핵심: 조후 용신 오행은 분포와 무관하게 계절로 고정 ─────────────────
def test_fire_choice_is_invariant_to_presence(preset):
    """火 유무와 무관하게 겨울 용신은 火 (억부와 갈리는 조후 고유 성질)."""
    no_fire = _mk_chart(8, 0, fill_stem=8, fill_branch=0)
    much_fire = _mk_chart(2, 0, fill_stem=2, fill_branch=6)
    assert _select(no_fire, preset).element == _HWA
    assert _select(much_fire, preset).element == _HWA


def test_family_matches_day_master_relation(preset):
    """family 는 일간 오행 대비 용신 오행의 십신 가족과 일치."""
    from engine.interp_types import relation
    chart = _mk_chart(0, 0, fill_stem=0, fill_branch=2)  # 甲(목) 일간, 겨울 → 火
    res = _select(chart, preset)
    dm_el = C.CHEONGAN_OHAENG[chart.day_master]
    assert res.family == relation(dm_el, res.element)
