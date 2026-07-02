"""해석 파이프라인 감사 개선(P1~P6) + 대운별(10년) 해석 — 오프라인 회귀 가드.

감사 문서: docs/interpretation-pipeline-audit.md.
검증 대상(LLM 비관여, 결정론 산출만):
  P1 용신 취용 트레이스(폴백 투명화) · P2 원국 변경 diff · P3 강약 경계 가시화 ·
  P4 카테고리 positive 그라운딩 · 대운별 타임라인/리포트.
"""
from __future__ import annotations

import os

import pytest

from engine import lifelong, reports, scorer
from engine.interpret import interpret
from engine.pillars import BirthInput, compute_chart
from engine.presets import load_preset
from engine.yongsin import resolve

pytestmark = pytest.mark.interpretation

_ME = BirthInput(1998, 11, 11, 22, 0)
_SPRING = BirthInput(1990, 4, 15, 10, 0)   # 조후 미성립→억부 폴백 유발 사례


def _scored(birth, pid):
    preset = load_preset(pid)
    chart = compute_chart(birth, preset.deterministic)
    return chart, scorer.score_strength(
        chart, preset.interpretation.get("sinkang_weights"), pid), preset


# ── P1: 용신 취용 트레이스 (폴백 투명화) ─────────────────────────────────
def test_resolve_records_configured_and_skipped():
    chart, scored, preset = _scored(_ME, "johu_centered")
    res = resolve(chart, scored, preset)
    assert isinstance(res["configured"], list) and isinstance(res["skipped"], list)
    if res["policy"]:
        assert res["policy"] in res["configured"]
        assert res["policy"] not in res["skipped"]


def test_interpret_exposes_yongsin_chain():
    b = interpret(_ME, ["johu_centered"], gender="남")["by_preset"]["johu_centered"]
    assert set(b["yongsin_chain"]) >= {"configured", "adopted", "skipped"}


def test_yongsin_trace_first_choice():
    b = interpret(_ME, ["jeongtong_eokbu"], gender="남")["by_preset"]["jeongtong_eokbu"]
    line = reports._yongsin_trace_basis(b)
    assert line and "억부" in line and "1순위" in line


def test_yongsin_trace_fallback_text():
    b = interpret(_SPRING, ["johu_centered"], gender="남")["by_preset"]["johu_centered"]
    line = reports._yongsin_trace_basis(b)
    assert line and "용신 취용" in line
    if b["yongsin_chain"]["skipped"]:           # 폴백 발생 시
        assert "미성립" in line and "채택" in line


# ── P2: 원국 변경 diff ───────────────────────────────────────────────────
def test_deterministic_diff_standard_empty():
    assert reports.deterministic_diff("jeongtong_eokbu") == []


def test_deterministic_diff_modern_traditional_nonempty():
    assert reports.deterministic_diff("sinpa_dongsaeng")     # 십이운성 변경
    assert reports.deterministic_diff("sammyeong_gobeop")    # 지장간/자시 변경


# ── P3: 강약 경계 가시화 ─────────────────────────────────────────────────
def test_strength_detail_exposed():
    det = interpret(_ME, ["jeongtong_eokbu"])["by_preset"]["jeongtong_eokbu"]["strength_detail"]
    assert "ratio" in det and len(det["bands"]) == 2


def test_strength_margin_near_boundary_for_me():
    # _ME 는 통근비율 ≈0.51 로 0.50 경계에 근접 → 경계 근접 안내가 떠야 함(감사 ④ 실증)
    b = interpret(_ME, ["jeongtong_eokbu"])["by_preset"]["jeongtong_eokbu"]
    line = reports._strength_margin_basis(b)
    assert line and "경계 근접" in line


# ── P4: 카테고리 positive grounding ─────────────────────────────────────
def test_grounding_positive_violation_detected():
    v = reports._grounding_violations("그냥 평범한 글", [], ["신강", "토"])
    assert "미반영:신강" in v and "미반영:토" in v


def test_natal_reports_require_strength():
    for kind in ("saeun", "pyeongsaeng", "wealth", "aejeong", "health"):
        prep = reports.run_report(kind, _ME, gender="남", prepare_only=True)
        assert any(s in prep["require"] for s in ("신강", "신약", "중화")), kind


def test_time_reports_have_no_require():
    for kind in ("today", "week", "tojeong"):
        prep = reports.run_report(kind, _ME, gender="남", prepare_only=True)
        assert prep["require"] == [], f"{kind} 는 require 비어야(오탐 방지)"


# ── 길이/근거/신뢰성 (DeepSeek 짧고 한자 누출 대응) ──────────────────────
def test_dehanja_transliterates_hanja_to_hangul():
    # 천간·지지·오행 + 십신·관계 한자 → 한글 음
    assert reports._dehanja("세운 丙午, 대운 戊辰, 오행 土水") == "세운 병오, 대운 무진, 오행 토수"
    assert reports._dehanja("財星과 三合, 旺盛") == "재성과 삼합, 왕성"


def test_cjk_guard_flags_uncovered_hanja():
    # _dehanja 맵에 없는 외래 한자가 남으면 그라운딩이 '한자노출'로 잡는다
    v = reports._grounding_violations("정상적인 한글 문장 龘", [], [])
    assert any("한자노출" in x for x in v)
    # 순수 한글은 통과
    assert reports._grounding_violations("순수한 한글 문장입니다", [], []) == []


def test_is_truncated_detects_short_body():
    assert reports.is_truncated("도중에 끊긴 짧은 글")
    assert reports.is_truncated("")
    assert not reports.is_truncated("가" * (reports._MIN_REPORT_CHARS + 10))


def test_base_rules_demand_length_and_basis():
    # 길이(섹션당 문장수)·근거 인용 지시가 규칙에 들어가 있어야
    assert "5~8문장" in reports._BASE_RULES
    assert "근거를 가져와" in reports._BASE_RULES


# ── 대운별(10년) 해석 ────────────────────────────────────────────────────
def test_daeun_registered():
    assert "daeun" in reports.REPORTS
    assert any(k == "daeun" for k, _, _ in reports.CATALOG)


def test_daeun_timeline_structure_and_yongsin_match():
    r = interpret(_ME, ["jeongtong_eokbu"], gender="남")
    chart = compute_chart(_ME, load_preset("jeongtong_eokbu").deterministic)
    tl = lifelong.daeun_timeline(chart, r["daeun"], r["by_preset"]["jeongtong_eokbu"]["yongsin"])
    assert len(tl) >= 6
    for x in tl:
        assert {"나이", "간지", "천간십신", "지지십신", "용신부합"} <= set(x)
    # 용신(토)과 같은 기운의 대운(무진·기사)이 '유리'로 라벨되어야
    assert any("유리" in x["용신부합"] for x in tl)


def test_daeun_timeline_no_yongsin_neutral():
    r = interpret(_ME, ["jeongtong_eokbu"], gender="남")
    chart = compute_chart(_ME, load_preset("jeongtong_eokbu").deterministic)
    tl = lifelong.daeun_timeline(chart, r["daeun"], None)
    assert all(x["용신부합"] == "중립" for x in tl)


def test_daeun_report_requires_gender():
    with pytest.raises(ValueError):
        reports.run_report("daeun", _ME, gender=None, prepare_only=True)


def test_daeun_report_prepare_ok():
    prep = reports.run_report("daeun", _ME, gender="남", prepare_only=True)
    assert prep["kind"] == "daeun"
    assert any("10년" in s for s in prep["sections"])
    assert "타임라인" in prep["facts"]


# ── 라이브(게이트) ──────────────────────────────────────────────────────
@pytest.mark.llm
@pytest.mark.skipif(not os.environ.get("RUN_LLM_TESTS"),
                    reason="LLM 필요(외부/비용); RUN_LLM_TESTS=1")
def test_live_daeun_report_grounded():
    rep = reports.run_report("daeun", _ME, gender="남")
    assert rep.text and rep.meta.get("output_tokens"), "LLM 실호출 메타 없음"
    assert rep.grounded, f"그라운딩 위반: {rep.violations}"
