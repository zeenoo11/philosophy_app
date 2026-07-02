"""P5 — L4 서술 그라운딩 (환각 차단, SPEC §3.3).

오프라인: 프롬프트 구성 + 그라운딩 검사 로직(모순 탐지)을 항상 검증.
온라인: 실제 claude -p 생성이 확정 결론에 그라운딩되는지 — RUN_LLM_TESTS=1 일 때만.
정확성 점수는 매기지 않는다(trace 외 사실 금지 + 결론 무모순만).
"""
from __future__ import annotations

import os

import pytest

from engine.interpret import interpret
from engine.narrator import (build_prompt, build_report_prompt, check_grounding,
                             check_report_grounding, narrate, narrate_report)
from engine.pillars import BirthInput

pytestmark = pytest.mark.interpretation


def _block(pid="jeongtong_eokbu"):
    return interpret(BirthInput(1990, 6, 15, 14, 30))["by_preset"][pid]


def _result():
    return interpret(BirthInput(1990, 6, 15, 14, 30), gender="남", now_year=2026)


def test_prompt_embeds_verdict_and_grounding_rules():
    b = _block()
    p = build_prompt(b)
    assert b["strength"] in p
    assert b["yongsin"]["element"] in p
    assert b["deterministic"]["eight_chars"] in p
    assert "지어내지" in p          # 환각 차단 규칙 명시
    for c in b["claims"]:           # trace 근거가 프롬프트에 포함
        assert c["claim"] in p


def test_grounding_detects_contradiction():
    b = _block()  # 신약 / 용신 금
    good = f"이 사주는 {b['strength']}하며, 용신은 {b['yongsin']['element']}입니다."
    assert check_grounding(good, b) == []
    bad = "이 사주는 신강하며 용신은 화입니다."
    assert check_grounding(bad, b)  # 강약·용신 모두 모순 → 위반


def test_grounding_mangpa_rejects_yongsin_concept():
    b = _block("mangpa")
    violations = check_grounding("일간은 신약하고 용신은 토이다.", b)
    assert any("용신" in v for v in violations)


# ── 주제별 리포트 (서비스용) 그라운딩 ──────────────────────────────────────
def test_report_prompt_has_sections_and_rules():
    r = _result()
    p = build_report_prompt(r)
    for sec in ("한 줄 요약", "재물운", "애정·궁합", "올해 흐름", "유파별로 보면", "실천 팁"):
        assert sec in p
    assert "한자" in p                      # 한자 금지 규칙 명시
    assert r["by_preset"][r["primary_preset"]]["strength"] in p


def test_report_grounding_flags_violations():
    r = _result()
    prim = r["by_preset"][r["primary_preset"]]
    good = (f"{prim['strength']}. 용신은 {prim['yongsin']['element']}. "
            "성향 재물 직업 애정 건강 올해 팁 모두 다룸.")
    assert check_report_grounding(good, r) == []
    bad = "신강 성향 재물 직업 애정 건강 올해 팁 財星 많음."  # 강약틀림+용신누락+한자
    assert check_report_grounding(bad, r)


@pytest.mark.llm
@pytest.mark.skipif(not os.environ.get("RUN_LLM_TESTS"),
                    reason="claude -p 필요(외부/비용); RUN_LLM_TESTS=1 로 활성화")
def test_live_narration_is_grounded():
    narr = narrate(_block())
    assert narr.text, "빈 서술"
    assert narr.grounded, f"그라운딩 위반: {narr.violations}"


@pytest.mark.llm
@pytest.mark.skipif(not os.environ.get("RUN_LLM_TESTS"),
                    reason="claude -p 필요(외부/비용); RUN_LLM_TESTS=1 로 활성화")
def test_live_report_is_grounded_and_real_llm():
    narr = narrate_report(_result())
    assert narr.text and narr.grounded, f"위반: {narr.violations}"
    assert narr.meta.get("output_tokens"), "LLM 메타(토큰) 없음 — 실호출 의심"
