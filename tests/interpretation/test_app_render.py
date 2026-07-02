"""서빙(Chainlit) 렌더 계층 단위 검증 — 입력 파싱 + 마크다운/메뉴 구성의 결정성.

LLM/브라우저 없이 순수 함수만 검증.
"""
from __future__ import annotations

import pytest

import saju_service as app  # 플랫폼화로 사주 UI 헬퍼는 saju_service 로 이동
from engine.interpret import interpret
from engine.pillars import BirthInput

pytestmark = pytest.mark.interpretation

_ME = BirthInput(1998, 11, 11, 22, 0)


def test_parse_birth_formats():
    assert app._parse_birth("1998-11-11 22:00") == BirthInput(1998, 11, 11, 22, 0)
    assert app._parse_birth("1990/6/15") == BirthInput(1990, 6, 15, 12, 0)
    assert app._parse_birth("출생 2000-01-01 09:05 입니다").hour == 9
    assert app._parse_birth("형식없음") is None


def test_md_chart_has_core_fields():
    r = interpret(_ME, gender="남", now_year=2026)
    md = app._md_chart(r)
    assert r["deterministic"]["eight_chars"] in md
    for kw in ("천간", "지지", "십신", "오행", "대운", "올해"):
        assert kw in md


def test_md_intro_lists_topics_and_menu_prompt():
    r = interpret(_ME)
    md = app._md_intro(r)
    for t in ("성향", "재물", "애정·궁합", "건강"):
        assert t in md
    # 사주 직후엔 '해석 방식'을 먼저 고르도록 안내한다
    assert "방식" in md


def test_menu_actions_cover_catalog():
    acts = app._menu_actions()
    kinds = {a.payload["kind"] for a in acts if a.name == "category"}
    assert {"saeun", "tojeong", "gunghap", "aejeong", "pyeongsaeng"} <= kinds
    # 해석 방식 바꾸기(간편 picker) 버튼이 메뉴에 포함되어야 한다
    assert any(a.name == "show_presets" for a in acts)


def test_simple_preset_menu_is_easy_and_maps_to_real_presets():
    """간편 3종은 (1) 3~5개, (2) 실제 프리셋과 1:1 매핑, (3) 한자·전문용어 노출 금지."""
    from engine.reports import (DEFAULT_PRESET, list_presets,
                                simple_preset_menu)
    known = set(list_presets())
    simple = simple_preset_menu()
    assert 3 <= len(simple) <= 5
    hanja = set("甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥木火土金水財官印食傷比劫殺")
    jargon = ("억부", "조후", "용신", "전왕", "통관", "병약", "신살", "동생동사", "십이운성")
    seen: set[str] = set()
    for pid, label, desc in simple:
        assert pid in known, f"간편 방식이 실제 프리셋과 매핑 안 됨: {pid}"
        assert pid not in seen, f"간편 방식 중복 매핑: {pid}"
        seen.add(pid)
        assert label and desc
        assert not (set(label) & hanja), f"간편 라벨에 한자 노출: {label}"
        for j in jargon:
            assert j not in label, f"간편 라벨에 전문용어 노출: {label}"
    # 맨 앞 = 기본값(표준)
    assert simple[0][0] == DEFAULT_PRESET


def test_simple_preset_actions_have_advanced_escape(monkeypatch):
    from engine.reports import simple_preset_menu
    monkeypatch.setattr(app, "_preset", lambda: "jeongtong_eokbu")  # 세션 없이
    acts = app._simple_preset_actions()
    names = {a.name for a in acts}
    assert "preset" in names                # 간편 선택 버튼
    assert "show_presets_full" in names      # 전문가용 더보기 탈출구
    assert sum(1 for a in acts if a.name == "preset") == len(simple_preset_menu())


def test_full_preset_actions_have_back_to_simple(monkeypatch):
    monkeypatch.setattr(app, "_preset", lambda: "jeongtong_eokbu")  # 세션 없이
    acts = app._preset_actions()
    assert sum(1 for a in acts if a.name == "preset") == len(app.preset_menu())
    # 전문가용 picker에서 '간단히 보기'로 돌아갈 수 있어야 한다
    assert any(a.name == "show_presets" for a in acts)


def test_preset_label_prefers_easy_name():
    # 간편 3종은 쉬운 라벨로 표시
    assert "표준" in app._preset_label("jeongtong_eokbu")
    # 간편에 없는 유파(병약)는 정식 display_name으로 폴백
    assert app._preset_label("byeongyak_sinbong") == app._preset_name("byeongyak_sinbong")


def test_preset_menu_includes_new_lineages():
    ids = {pid for pid, _name, _desc in app.preset_menu()}
    # 기존 4종 + 신규 3종(병약·삼명통회·신파)
    assert {"jeongtong_eokbu", "johu_centered", "jeonwang_tonggwan", "mangpa"} <= ids
    assert {"byeongyak_sinbong", "sammyeong_gobeop", "sinpa_dongsaeng"} <= ids
    # 라벨은 한글(한자 노출 금지) — display_name 에 천간/지지/오행 한자가 없어야 함
    hanja = set("甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥木火土金水")
    for _pid, name, _desc in app.preset_menu():
        assert not (set(name) & hanja), f"유파 라벨에 한자 노출: {name}"


def test_clean_md_fixes_tilde_and_bold():
    # ~ 취소선 방지
    assert app._clean_md("9세~19세 그리고 ~끝") == "9세∼19세 그리고 ∼끝"
    assert "~" not in app._clean_md("a~b~c~d")
    # ** x ** 안쪽 공백 정리
    assert app._clean_md("** 강조 **") == "**강조**"
    # 홀수 ** dangling 제거 → 짝수
    assert app._clean_md("**굵게** 그리고 **남은").count("**") == 2
    # 정상 굵게는 보존
    assert app._clean_md("이것은 **굵게** 입니다") == "이것은 **굵게** 입니다"


def test_keyword_routing_table():
    assert app._KEYWORDS["토정"] == "tojeong"
    assert app._KEYWORDS["궁합"] == "gunghap"
    assert app._KEYWORDS["오늘"] == "today"


def test_parse_gender():
    assert app._parse_gender("1998-11-11 22:00 남") == "남"
    assert app._parse_gender("1998-11-11 22:00 여자") == "여"
    assert app._parse_gender("male, 1990-06-15") == "남"
    assert app._parse_gender("1998-11-11 22:00") is None


def test_parse_input_lunar_and_solar():
    # 음력 → 양력 변환 (음 9/23 = 양 11/11)
    birth, info = app._parse_input("음력 1998-09-23 22:00 남")
    assert birth == BirthInput(1998, 11, 11, 22, 0)
    assert info["calendar"] == "음력"
    assert info["lunar"] == (1998, 9, 23, False) and info["solar"] == (1998, 11, 11)
    # 기본 = 양력
    _, info2 = app._parse_input("1998-11-11 22:00")
    assert info2["calendar"] == "양력"
    # 명시 양력
    _, info3 = app._parse_input("양력 1998-11-11")
    assert info3["calendar"] == "양력"


def test_parse_birth_validation_and_formats():
    # 비정상 날짜 → None (크래시 방지)
    assert app._parse_birth("1998-13-45 22:00") is None
    assert app._parse_birth("2000-02-30") is None
    assert app._parse_birth("1998-11-11 25:99") is None
    # YYYYMMDD 지원
    assert app._parse_birth("19981111") == BirthInput(1998, 11, 11, 12, 0)
    assert app._parse_birth("19981111 2200") == BirthInput(1998, 11, 11, 22, 0)
