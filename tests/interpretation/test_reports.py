"""카테고리 리포트 — 디스패치/카탈로그(오프라인) + 실제 생성·그라운딩(게이트).

오프라인: 카탈로그-레지스트리 정합, 미지정 카테고리 예외, 규칙 포함.
게이트(RUN_LLM_TESTS=1): 실제 claude -p(Sonnet) 리포트가 근거값에 그라운딩되는지.
"""
from __future__ import annotations

import os

import pytest

from engine import reports
from engine.pillars import BirthInput

pytestmark = pytest.mark.interpretation

_ME = BirthInput(1998, 11, 11, 22, 0)


def test_catalog_matches_registry():
    kinds = {k for k, _, _ in reports.CATALOG}
    assert kinds <= set(reports.REPORTS)
    for must in ("saeun", "tojeong", "aejeong", "gunghap", "wealth",
                 "pyeongsaeng", "today", "week", "health"):
        assert must in reports.REPORTS


def test_unknown_kind_raises():
    with pytest.raises(ValueError):
        reports.run_report("does_not_exist", _ME)


def test_gunghap_requires_partner():
    with pytest.raises(ValueError):
        reports.run_report("gunghap", _ME)  # partner 누락


def test_base_rules_ban_hanja_and_fabrication():
    assert "한자" in reports._BASE_RULES and "지어내지" in reports._BASE_RULES


def test_hanja_guard_charset_present():
    # 천간·지지·오행 한자가 가드 집합에 포함(궁합 한자 노출 재발 방지)
    for ch in "壬戊水財官":
        assert ch in reports._HANJA


def test_report_fns_absorb_year_kwarg():
    """run_report(kind, birth, year=...) 가 today/week/평생/궁합에서 크래시하지 않도록 흡수."""
    import inspect
    for fn in (reports.today_report, reports.week_report,
               reports.pyeongsaeng_report, reports.gunghap_report):
        assert "year" in inspect.signature(fn).parameters


@pytest.mark.llm
@pytest.mark.skipif(not os.environ.get("RUN_LLM_TESTS"),
                    reason="claude -p 필요(외부/비용); RUN_LLM_TESTS=1")
def test_live_saeun_report_grounded():
    rep = reports.run_report("saeun", _ME, year=2026, gender="남")
    assert rep.text and rep.meta.get("output_tokens"), "LLM 실호출 메타 없음"
    assert rep.grounded, f"그라운딩 위반: {rep.violations}"


@pytest.mark.llm
@pytest.mark.skipif(not os.environ.get("RUN_LLM_TESTS"),
                    reason="claude -p 필요(외부/비용); RUN_LLM_TESTS=1")
def test_live_gunghap_report_grounded():
    rep = reports.run_report("gunghap", _ME, partner=BirthInput(1996, 5, 20, 9, 30))
    assert rep.text and rep.grounded, f"위반: {rep.violations}"
