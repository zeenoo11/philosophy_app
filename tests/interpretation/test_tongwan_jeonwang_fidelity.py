"""P4 — 전왕(專旺)·통관(通關) 유파 충실도. 정확성이 아니라 '규칙 준수'만 검증.

  • 전왕: 비겁+인성 ≥ 6 → 종왕/종강(용신 ∈ {비겁, 인성}).
          일간 외 단일 오행 ≥ 5 → 종격(follow). 압도 세력 없으면 None.
  • 통관: X극Y 두 세력이 각각 2 이상이면 통관신 Z=(X+1)%5 가 용신. 싸움 없으면 None.
모든 용신 결과는 trace 를 동반(orphan 금지). 외부 정답을 박제하지 않고 규칙만 검증.

차트는 조건을 강제하도록 직접 구성한다. 간지는 같은 음양이어야 유효
(짝-짝 또는 홀-홀). element_presence = 8글자(천간 + 지지 정기) 오행 분포.
"""
from __future__ import annotations

import pytest

from engine import constants as C, scorer
from engine.interp_types import element_presence
from engine.pillars import Chart, DeterministicConfig, Pillar
from engine.yongsin import jeonwang, tongwan

pytestmark = pytest.mark.interpretation

_CFG = DeterministicConfig()


class _Preset:
    """정책 select() 는 preset.preset_id 만 사용 → 경량 더블로 충분."""
    preset_id = "test_tongwan_jeonwang"


_PRESET = _Preset()


def _chart(day, year, month, hour) -> Chart:
    """(천간,지지) 튜플 4개로 차트 구성 (간지는 같은 음양이어야 유효)."""
    return Chart(
        year=Pillar("년", *year), month=Pillar("월", *month),
        day=Pillar("일", *day), hour=Pillar("시", *hour),
        config=_CFG, meta={},
    )


def _scored(chart):
    return scorer.score_strength(chart, None, _PRESET.preset_id)


# ── 오행 인덱스: 목0 화1 토2 금3 수4 ─────────────────────────────────────
_MOK, _HWA, _TO, _GEUM, _SU = 0, 1, 2, 3, 4

# 자주 쓰는 간지(같은 음양 = 유효)
_GAB_JA = (0, 0)     # 甲子: 木(천) 水(지)  — 둘 다 양
_GAB_IN = (0, 2)     # 甲寅: 木 木          — 둘 다 양
_GYEONG_SIN = (6, 8) # 庚申: 金 金          — 둘 다 양
_GAB_SIN = (0, 8)    # 甲申: 木 金          — 둘 다 양
_MU_JIN = (4, 4)     # 戊辰: 土 土          — 둘 다 양
_BYEONG_O = (2, 6)   # 丙午: 火 火          — 둘 다 양
_IM_JA = (8, 0)      # 壬子: 水 水          — 둘 다 양


# ─────────────────────────────────────────────────────────────────────────
# 전왕(專旺)
# ─────────────────────────────────────────────────────────────────────────
def test_jeonwang_dominant_self_returns_bigeop_or_insung():
    """비겁·인성으로 도배 → 종왕/종강. 용신 가족 ∈ {비겁, 인성}."""
    # 일간 甲(木). 甲子 ×4 → 木4(비겁) + 水4(인성) = self 8.
    chart = _chart(day=_GAB_JA, year=_GAB_JA, month=_GAB_JA, hour=_GAB_JA)
    counts = element_presence(chart)
    assert counts[_MOK] + counts[_SU] >= 6  # 조건 강제 확인

    res = jeonwang.select(chart, _scored(chart), _PRESET)
    assert res is not None
    assert res.policy == "jeonwang"
    assert res.family in {"비겁", "인성"}
    assert res.trace is not None and res.trace.layer == "L3"
    assert res.trace.rule_id == "jeonwang.dominant_self"
    assert res.claims and all(c.trace is not None for c in res.claims)


def test_jeonwang_dominant_self_tie_prefers_bigeop():
    """비겁=인성 동률이면 비겁 우선 (규칙: 비겁 우선)."""
    # 甲子 ×4 → 木4 == 水4 (동률).
    chart = _chart(day=_GAB_JA, year=_GAB_JA, month=_GAB_JA, hour=_GAB_JA)
    res = jeonwang.select(chart, _scored(chart), _PRESET)
    assert res is not None and res.family == "비겁"
    assert res.element == _MOK  # 일간(甲)=木 = 비겁 오행


def test_jeonwang_dominant_self_insung_when_more():
    """인성이 비겁보다 많으면 인성 (동률 아님)."""
    # 일간 甲(木). 인성=水, 비겁=木.
    # day 甲子(木1水1) + 壬子 ×3(水6) → 水7 > 木1, self=8.
    chart = _chart(day=_GAB_JA, year=_IM_JA, month=_IM_JA, hour=_IM_JA)
    counts = element_presence(chart)
    assert counts[_SU] > counts[_MOK]

    res = jeonwang.select(chart, _scored(chart), _PRESET)
    assert res is not None and res.family == "인성"
    assert res.element == _SU


def test_jeonwang_follow_outer_element():
    """일간 외 한 오행이 5개 이상 → 종격(follow). 그 오행을 따른다."""
    # 일간 甲(木). 庚申 ×3 (金6) + 甲申(木1金1) → 金7, 木1, 水0.
    # self(木+水)=1 < 6 → follow 분기.
    chart = _chart(day=_GAB_SIN, year=_GYEONG_SIN, month=_GYEONG_SIN,
                   hour=_GYEONG_SIN)
    counts = element_presence(chart)
    assert counts[_GEUM] >= 5
    assert counts[_MOK] + counts[_SU] < 6  # 종왕/종강 미해당 확인

    res = jeonwang.select(chart, _scored(chart), _PRESET)
    assert res is not None
    assert res.trace.rule_id == "jeonwang.follow"
    assert res.element == _GEUM
    # relation(木, 金) = 관성 (金이 木을 극 → 관성)
    assert res.family == "관성"
    assert res.claims and all(c.trace is not None for c in res.claims)


def test_jeonwang_ordinary_chart_returns_none():
    """압도 세력이 없는 평범한 차트 → None (전왕 미해당)."""
    # 일간 甲(木). 木·火·土·金 고루 분포, 어떤 오행도 5 미만, self<6.
    # 甲寅(木2) / 丙午(火2) / 戊辰(土2) / 庚申(金2) → 각 2개.
    chart = _chart(day=_GAB_IN, year=_BYEONG_O, month=_MU_JIN, hour=_GYEONG_SIN)
    counts = element_presence(chart)
    assert max(counts) < 5
    assert counts[_MOK] + counts[_SU] < 6

    assert jeonwang.select(chart, _scored(chart), _PRESET) is None


# ─────────────────────────────────────────────────────────────────────────
# 통관(通關)
# ─────────────────────────────────────────────────────────────────────────
def test_tongwan_bridge_between_fighting_forces():
    """X극Y 두 세력이 각각 2+ → 통관신 Z=(X+1)%5 가 용신."""
    # 木(4) 극 土(4) 교전. X=木(0), Y=土(2), Z=(0+1)%5=火(1).
    # 甲寅 ×2 (木4) + 戊辰 ×2 (土4).
    chart = _chart(day=_GAB_IN, year=_GAB_IN, month=_MU_JIN, hour=_MU_JIN)
    counts = element_presence(chart)
    assert counts[_MOK] >= 2 and counts[_TO] >= 2  # 교전 조건 강제

    res = tongwan.select(chart, _scored(chart), _PRESET)
    assert res is not None
    assert res.policy == "tongwan"
    assert res.trace.rule_id == "tongwan.bridge"
    # 핵심 규칙: 통관신 = (X+1)%5  (X=木 → 火)
    x = _MOK
    assert res.element == (x + 1) % 5 == _HWA
    assert res.trace is not None and res.trace.layer == "L3"
    assert res.claims and all(c.trace is not None for c in res.claims)


def test_tongwan_picks_strongest_fight():
    """여러 교전이 가능하면 (counts[X]+counts[Y]) 최대 쌍을 택한다."""
    # 金(2)극木... 구성: 木 극 土 가 가장 큰 교전이 되도록.
    # 甲寅 ×2 (木4), 戊辰(土2), 庚申(金2).
    #   木극土: 4+2=6 (최대),  金극木: 2+4=6 ... 동률 시 X 인덱스 작은 木(0) 우선.
    # → X=木(0), Z=火(1).
    chart = _chart(day=_GAB_IN, year=_GAB_IN, month=_MU_JIN, hour=_GYEONG_SIN)
    res = tongwan.select(chart, _scored(chart), _PRESET)
    assert res is not None
    # 동률 교전 → X 인덱스 우선(木) → Z=火
    assert res.element == _HWA


def test_tongwan_no_fight_returns_none():
    """극(剋) 관계의 두 강세력이 없으면 None (통관 미해당)."""
    # 木4 火2 뿐: 木극土(土0)·火극金(金0) 모두 한쪽이 0 → 교전 없음.
    chart = _chart(day=_GAB_IN, year=_GAB_IN, month=_BYEONG_O, hour=_GAB_IN)
    counts = element_presence(chart)
    # 어떤 극 쌍도 둘 다 2 이상은 아님
    fight = any(counts[x] >= 2 and counts[C.geuk(x)] >= 2 for x in range(5))
    assert not fight

    assert tongwan.select(chart, _scored(chart), _PRESET) is None


# ─────────────────────────────────────────────────────────────────────────
# 멱등성 (SPEC §3.2(a))
# ─────────────────────────────────────────────────────────────────────────
def test_jeonwang_is_deterministic():
    chart = _chart(day=_GAB_JA, year=_GAB_JA, month=_GAB_JA, hour=_GAB_JA)
    r1 = jeonwang.select(chart, _scored(chart), _PRESET)
    r2 = jeonwang.select(chart, _scored(chart), _PRESET)
    assert (r1.element, r1.family) == (r2.element, r2.family)


def test_tongwan_is_deterministic():
    chart = _chart(day=_GAB_IN, year=_GAB_IN, month=_MU_JIN, hour=_MU_JIN)
    r1 = tongwan.select(chart, _scored(chart), _PRESET)
    r2 = tongwan.select(chart, _scored(chart), _PRESET)
    assert (r1.element, r1.family) == (r2.element, r2.family)
