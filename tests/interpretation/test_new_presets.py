"""신규 유파 프리셋(병약·삼명통회·신파) — 설정 충실도 + 차분 기대 (SPEC §6).

근거: docs/schools.md. **정확성(정답) 테스트가 아니다** — 정답 없는 L3 영역이므로
'프리셋이 선언한 분기를 실제로 거는가'(차분 기대)와 '정책 우선순위·토글을 지키는가'
(유파 충실도)만 검증한다. 토글 자체의 글자 분기는 tests/deterministic/test_toggles.py 가 담당.
"""
from __future__ import annotations

import pytest

from engine.interpret import interpret
from engine.pillars import BirthInput, compute_chart
from engine.presets import load_preset

pytestmark = pytest.mark.interpretation

_CONCENTRATED = BirthInput(1998, 11, 11, 22, 0)   # 토(土) 과다 → 병약 발동 케이스
_EUM_DAYMASTER = BirthInput(1992, 12, 5, 10, 0)    # 일간 乙(음간) → 동생동사 분기 케이스


# ── 설정 충실도 (프리셋이 선언한 대로인가) ──────────────────────────────
def test_byeongyak_preset_config():
    p = load_preset("byeongyak_sinbong")
    assert p.interpretation["yongsin_policy"][0] == "byeongyak"   # 병약 1순위
    assert "명리정종" in p.lineage


def test_sammyeong_preset_config():
    p = load_preset("sammyeong_gobeop")
    assert p.deterministic.woryulbunya_theory == "sammyeongtonghoe"   # 지장간 사령 분기
    assert p.interpretation.get("use_sinsal") is True
    assert "삼명통회" in p.lineage


def test_sinpa_preset_config():
    p = load_preset("sinpa_dongsaeng")
    assert p.deterministic.sipiunseong_theory == "dongsaeng_dongsa"   # 십이운성 분기
    assert "적천수" in p.lineage


# ── 차분 기대 (선언한 분기가 실제로 걸리는가) ───────────────────────────
def test_byeongyak_diverges_from_eokbu_on_concentrated_chart():
    """한 오행 과다(병)인 사주: 병약 프리셋은 byeongyak 정책, 억부 프리셋은 eokbu 정책."""
    eb = interpret(_CONCENTRATED, ["jeongtong_eokbu"], gender="남")["by_preset"]["jeongtong_eokbu"]
    by = interpret(_CONCENTRATED, ["byeongyak_sinbong"], gender="남")["by_preset"]["byeongyak_sinbong"]
    assert eb["policy"] == "eokbu"
    assert by["policy"] == "byeongyak"


def test_sinpa_diverges_unseong_on_eum_daymaster():
    """음간 일간: 동생동사(신파)와 음양순역(정통)의 십이운성이 갈린다(8글자는 동일)."""
    c_jt = compute_chart(_EUM_DAYMASTER, load_preset("jeongtong_eokbu").deterministic)
    c_sp = compute_chart(_EUM_DAYMASTER, load_preset("sinpa_dongsaeng").deterministic)
    assert c_jt.eight_chars() == c_sp.eight_chars()      # 결정론 8글자는 프리셋 무관 동일
    assert c_jt.unseong() != c_sp.unseong()              # 십이운성은 갈린다(차분 기대)
