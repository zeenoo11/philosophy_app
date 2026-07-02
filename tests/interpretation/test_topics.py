"""L4 주제별 facts (topics) — 구조/그라운딩/멱등성 검증 (SPEC §3.2 정신).

정확성(외부 정답) 금지. 검증 목표:
  • 6개 주제 key 가 모두 존재, 각 주제에 facts/hint/trace_inputs 존재.
  • 그라운딩: 재물의 재성_개수 = 실제 차트의 재성(정재+편재) 십신 개수(직접 셈).
              건강의 결핍_오행 = 실제 오행분포가 0인 오행.
  • 멱등성: 같은 입력 → 같은 출력.
  • yongsin / daeun None 일 때도 동작.
"""
from __future__ import annotations

import pytest

from engine import constants as C, scorer
from engine.daeun import compute_daeun
from engine.interp_types import element_presence
from engine.pillars import BirthInput, compute_chart
from engine.presets import list_presets, load_preset
from engine.topics import topic_facts
from engine.yongsin import resolve

pytestmark = pytest.mark.interpretation

_EXPECTED_KEYS = {"성향", "재물", "직업·명예", "애정·궁합", "건강", "대운"}

# 검증용 표본 — 계절·연대 분산
_BIRTHS = [
    BirthInput(1990, 6, 15, 14, 30),
    BirthInput(1988, 9, 15, 10, 0),
    BirthInput(1972, 1, 5, 23, 10),
    BirthInput(2003, 11, 20, 6, 45),
    BirthInput(1955, 3, 30, 18, 0),
]


def _charts():
    return [compute_chart(b) for b in _BIRTHS]


def _scored(chart):
    return scorer.score_strength(chart)


def _yongsin_for(chart):
    """첫 프리셋으로 용신 산출(없을 수 있음)."""
    pid = list_presets()[0]
    preset = load_preset(pid)
    s = scorer.score_strength(chart, preset.interpretation.get("sinkang_weights"), pid)
    l3 = resolve(chart, s, preset)
    return l3["result"] if l3["kind"] == "yongsin" else None


def _count_jaeseong_directly(chart) -> int:
    """재성(정재+편재) 개수를 천간(일간 제외)+지장간에서 '직접' 센다 (독립 검증)."""
    n = 0
    for pos, sip in chart.stem_sipsin().items():
        if sip in ("정재", "편재"):
            n += 1
    for _pos, items in chart.branch_jijanggan_sipsin().items():
        for _stem_h, _role, sip in items:
            if sip in ("정재", "편재"):
                n += 1
    return n


# ─────────────────────────────────────────────────────────────────────────
# 구조
# ─────────────────────────────────────────────────────────────────────────
def test_all_topics_present_with_facts_hint():
    for chart in _charts():
        tf = topic_facts(chart, scored=_scored(chart))
        assert set(tf.keys()) == _EXPECTED_KEYS
        for key, block in tf.items():
            assert "facts" in block, f"{key}: facts 누락"
            assert "hint" in block, f"{key}: hint 누락"
            assert "trace_inputs" in block, f"{key}: trace_inputs 누락"
            assert isinstance(block["facts"], dict)
            assert isinstance(block["hint"], str) and block["hint"].strip()
            assert isinstance(block["trace_inputs"], dict)


def test_works_without_scored_yongsin_daeun():
    """yongsin/daeun/scored 모두 None 이어도 6주제 산출."""
    for chart in _charts():
        tf = topic_facts(chart)  # 전부 기본 None
        assert set(tf.keys()) == _EXPECTED_KEYS
        for block in tf.values():
            assert block["facts"] is not None
            assert block["hint"].strip()


# ─────────────────────────────────────────────────────────────────────────
# 그라운딩 (규칙 ↔ 실제 차트 일치)
# ─────────────────────────────────────────────────────────────────────────
def test_jaemul_count_grounded_in_chart():
    """재물 facts 의 재성_개수 = 직접 센 재성(정재+편재) 개수."""
    for chart in _charts():
        tf = topic_facts(chart, scored=_scored(chart))
        reported = tf["재물"]["facts"]["재성_개수"]
        actual = _count_jaeseong_directly(chart)
        assert reported == actual, (
            f"{chart.eight_chars()}: 재성_개수 {reported} != 직접 셈 {actual}")


def test_geongang_lacking_grounded_in_distribution():
    """건강 facts 의 결핍_오행 = 실제 오행분포가 0인 오행 집합."""
    for chart in _charts():
        tf = topic_facts(chart)
        reported = set(tf["건강"]["facts"]["결핍_오행"])
        pres = element_presence(chart)
        actual = {C.OHAENG_HANGUL[i] for i in range(5) if pres[i] == 0}
        assert reported == actual, (
            f"{chart.eight_chars()}: 결핍 {reported} != 분포0 {actual}")


def test_jaemul_positions_consistent_with_count():
    """재성_위치(중복 제거)는 재성_개수 이하이며, 개수>0이면 위치 비어있지 않음."""
    for chart in _charts():
        tf = topic_facts(chart)["재물"]["facts"]
        assert len(tf["재성_위치"]) <= tf["재성_개수"]
        if tf["재성_개수"] > 0:
            assert tf["재성_위치"]


def test_seonghyang_day_master_label_matches_chart():
    """성향의 일간 라벨이 실제 일간 한글을 포함."""
    for chart in _charts():
        tf = topic_facts(chart, scored=_scored(chart))
        label = tf["성향"]["facts"]["일간"]
        assert C.CHEONGAN_HANGUL[chart.day_master] in label


# ─────────────────────────────────────────────────────────────────────────
# 용신 / 대운 연동
# ─────────────────────────────────────────────────────────────────────────
def test_yongsin_family_flags_reflected():
    """용신이 주어지면 재성/관성 용신여부가 bool 로 채워지고 가족과 일치."""
    for chart in _charts():
        yong = _yongsin_for(chart)
        if yong is None:
            continue
        tf = topic_facts(chart, scored=_scored(chart), yongsin=yong)
        assert tf["재물"]["facts"]["재성_용신여부"] == (yong.family == "재성")
        assert tf["직업·명예"]["facts"]["관성_용신여부"] == (yong.family == "관성")
        # 궁합 좋은 오행에 용신 오행 포함
        assert yong.element_name in tf["애정·궁합"]["facts"]["궁합좋은_상대일간오행"]


def test_daeun_topic_with_and_without():
    chart = _charts()[0]
    # 없을 때
    none_block = topic_facts(chart)["대운"]
    assert none_block["facts"] == {}
    assert "성별" in none_block["hint"]
    # 있을 때
    dr = compute_daeun(chart, "남")
    daeun = {"forward": dr.forward, "start_age": dr.start_age,
             "pillars": [{"age": a, "gz60": g, "name": n} for (a, g, n) in dr.pillars]}
    block = topic_facts(chart, daeun=daeun)["대운"]
    assert block["facts"]["대운수"] == dr.start_age
    assert block["facts"]["방향"] in ("순행", "역행")
    assert len(block["facts"]["첫_대운"]) == min(3, len(dr.pillars))


def test_gender_filters_spouse_star():
    """gender='남' → 배우자성=재성, '여' → 관성, None → 둘 다."""
    chart = _charts()[0]
    assert topic_facts(chart, gender="남")["애정·궁합"]["facts"]["배우자성_가족"] == ["재성"]
    assert topic_facts(chart, gender="여")["애정·궁합"]["facts"]["배우자성_가족"] == ["관성"]
    assert set(topic_facts(chart)["애정·궁합"]["facts"]["배우자성_가족"]) == {"재성", "관성"}


# ─────────────────────────────────────────────────────────────────────────
# 멱등성
# ─────────────────────────────────────────────────────────────────────────
def test_idempotent():
    for chart in _charts():
        s = _scored(chart)
        yong = _yongsin_for(chart)
        dr = compute_daeun(chart, "여")
        daeun = {"forward": dr.forward, "start_age": dr.start_age,
                 "pillars": [{"age": a, "gz60": g, "name": n} for (a, g, n) in dr.pillars]}
        a = topic_facts(chart, scored=s, yongsin=yong, daeun=daeun, gender="여")
        b = topic_facts(chart, scored=s, yongsin=yong, daeun=daeun, gender="여")
        assert a == b
