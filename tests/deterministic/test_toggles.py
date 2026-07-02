"""L1 결정론 토글의 '유파 분기' 검증 (SPEC §0.2: 분기를 1급 기능으로).

  • 글자를 바꾸는 토글: jasi_rule, true_solar_time (edge 테스트에서 분기 확인)
  • 글자를 안 바꾸는 토글: sipiunseong/woryulbunya — 파생(운성/지장간)만 분기
이 구분 자체가 결정론 레이어의 불변식이다.
"""
from __future__ import annotations

import pytest

from engine import constants as C
from engine.pillars import BirthInput, DeterministicConfig, compute_chart

pytestmark = pytest.mark.deterministic


def test_sipiunseong_theories_diverge():
    """음간/戊己에서 십이운성 이론이 갈린다."""
    # 乙(음목) 寅: 음양순역=제왕 vs 동생동사=건록
    assert (C.sipiunseong(1, 2, "eumyang_sunyeok")
            != C.sipiunseong(1, 2, "dongsaeng_dongsa"))
    # 戊(양토) 子: 음양순역(火土동궁)=태 vs 수토동궁=제왕
    assert (C.sipiunseong(4, 0, "eumyang_sunyeok")
            != C.sipiunseong(4, 0, "sutodonggung"))


def test_woryulbunya_days_diverge_but_jeonggi_invariant():
    """월률분야 이론은 지장간 일수를 가르되, 정기(본기)는 유파 무관."""
    jp = C.WORYULBUNYA_THEORIES["japyeongjinjeon"]
    sm = C.WORYULBUNYA_THEORIES["sammyeongtonghoe"]
    # 申/巳/午 에서 일수 배분이 다름
    assert jp[8] != sm[8]   # 申: 戊7壬7庚16 vs 戊10壬3庚17
    assert jp[5] != sm[5]   # 巳
    # 정기(정답 있음)는 모든 지지에서 유파 무관 동일
    for b in range(12):
        assert C.jeonggi(b) == [s for s, _d, r in sm[b] if r == "정기"][0]


def test_eightchars_invariant_to_derived_toggles():
    """sipiunseong/woryulbunya 토글은 8글자를 바꾸지 않는다(파생만 영향)."""
    birth = BirthInput(1990, 6, 15, 14, 30)
    base = compute_chart(birth, DeterministicConfig(true_solar_time=False))
    for sip in ("eumyang_sunyeok", "dongsaeng_dongsa", "sutodonggung"):
        for wol in ("japyeongjinjeon", "sammyeongtonghoe", "myeongni_chumyeong"):
            ch = compute_chart(birth, DeterministicConfig(
                true_solar_time=False, sipiunseong_theory=sip, woryulbunya_theory=wol))
            assert ch.eight_chars() == base.eight_chars()


def test_unseong_actually_diverges_for_eum_ilgan():
    """음간 일간 차트에서 운성 맵이 이론별로 실제 분기한다."""
    birth = BirthInput(1990, 6, 15, 14, 30)  # 일간 辛(음금)
    a = compute_chart(birth, DeterministicConfig(true_solar_time=False,
                                                 sipiunseong_theory="eumyang_sunyeok"))
    b = compute_chart(birth, DeterministicConfig(true_solar_time=False,
                                                 sipiunseong_theory="dongsaeng_dongsa"))
    assert a.unseong() != b.unseong()
