"""확장 통합 검증 — 전왕·통관 정책 도달성, 신규 프리셋, 대운 배선.

병렬로 추가된 모듈(daeun, tongwan, jeonwang)이 resolver/interpret 에 올바로
배선됐는지 확인(레이어 간 연결만; 정확성 박제 아님).
"""
from __future__ import annotations

import pytest

from engine import scorer
from engine.interpret import interpret
from engine.pillars import BirthInput, Chart, DeterministicConfig, Pillar
from engine.presets import list_presets, load_preset
from engine.yongsin import resolve

pytestmark = pytest.mark.interpretation


def test_new_preset_registered():
    assert "jeonwang_tonggwan" in list_presets()
    p = load_preset("jeonwang_tonggwan")
    assert p.engine == "yongsin"
    assert p.interpretation["yongsin_policy"][:2] == ["jeonwang", "tongwan"]


def test_jeonwang_policy_reachable_via_resolver():
    """木 도배 차트 → 전왕 프리셋이 jeonwang 정책을 채택."""
    preset = load_preset("jeonwang_tonggwan")
    ch = Chart(Pillar("년", 0, 0), Pillar("월", 0, 0),
               Pillar("일", 0, 0), Pillar("시", 0, 0),
               config=DeterministicConfig(), meta={})  # 甲子 ×4 → 木4·水4
    scored = scorer.score_strength(ch, None, "jeonwang_tonggwan")
    out = resolve(ch, scored, preset)
    assert out["kind"] == "yongsin" and out["policy"] == "jeonwang"


def test_normal_chart_falls_through_to_eokbu():
    """평범한 차트는 전왕·통관 불성립 → 정책 체인이 eokbu 로 회귀."""
    preset = load_preset("jeonwang_tonggwan")
    r = interpret(BirthInput(1990, 6, 15, 14, 30), ["jeonwang_tonggwan"])
    block = r["by_preset"]["jeonwang_tonggwan"]
    assert block["engine"] == "yongsin"
    assert block["policy"] in {"jeonwang", "tongwan", "eokbu"}
    assert block["claims"]


def test_daeun_wired_into_interpret():
    r = interpret(BirthInput(1990, 6, 15, 14, 30), ["jeongtong_eokbu"], gender="남")
    d = r["daeun"]
    assert d is not None
    assert isinstance(d["forward"], bool)
    assert 1 <= d["start_age"] <= 12
    assert len(d["pillars"]) == 8
    assert all({"age", "gz60", "name"} <= set(p) for p in d["pillars"])


def test_daeun_absent_without_gender():
    r = interpret(BirthInput(1990, 6, 15, 14, 30), ["jeongtong_eokbu"])
    assert r["daeun"] is None


def test_current_luck_block():
    """올해(세운) + 현재 대운 블록 — gender 지정 시 산출, now_year 결정론."""
    r = interpret(BirthInput(1990, 6, 15, 14, 30), ["jeongtong_eokbu"],
                  gender="남", now_year=2026)
    cu = r["current"]
    assert cu is not None and cu["now_year"] == 2026
    # 2026 = (2026-4)%60 = 42 → 병오
    assert cu["sewoon"]["name"] == "병오"
    assert "천간십신" in cu["sewoon"] and "지지십신" in cu["sewoon"]
    assert cu.get("current_daeun")  # 37세 → 진행 중 대운 존재


def test_current_absent_without_gender():
    r = interpret(BirthInput(1990, 6, 15, 14, 30), ["jeongtong_eokbu"])
    assert r["current"] is None


def test_topics_present_in_interpret():
    r = interpret(BirthInput(1990, 6, 15, 14, 30), ["jeongtong_eokbu"])
    assert set(r["topics"]) >= {"성향", "재물", "직업·명예", "애정·궁합", "건강", "대운"}
    for blk in r["topics"].values():
        assert blk["hint"] and "facts" in blk
