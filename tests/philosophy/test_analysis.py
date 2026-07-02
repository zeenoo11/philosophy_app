"""철학 분석 — LLM 비호출 부분(질문 로딩·JSON 파싱) 검증."""
import pytest

from philosophy.analysis import (_json_from, get_random_question,
                                 load_questions, question_by_id)
from philosophy.matching import AXES

pytestmark = pytest.mark.philosophy


def test_questions_cover_all_seven_axes():
    qs = load_questions()
    assert len(qs) == 21
    axes = {q["axis"] for q in qs}
    assert axes == set(AXES), f"모든 축에 질문이 있어야 한다: {axes}"
    ids = [q["id"] for q in qs]
    assert len(ids) == len(set(ids)), "질문 id 중복 금지"
    for q in qs:
        assert q["question"] and q["topic"]


def test_random_question_respects_exclude():
    qs = load_questions()
    all_ids = {q["id"] for q in qs}
    # 하나만 남기고 모두 제외 → 항상 그 질문
    keep = qs[0]["id"]
    got = get_random_question(exclude_ids=all_ids - {keep})
    assert got is not None and got["id"] == keep
    # 전부 제외 → None (대화 종료 신호)
    assert get_random_question(exclude_ids=all_ids) is None


def test_question_by_id():
    assert question_by_id(1)["axis"] == "agency"
    assert question_by_id(99999) is None


@pytest.mark.parametrize("raw,expected_key", [
    ('{"reply": "안녕", "next_question_id": 3}', "reply"),
    ('```json\n{"score": 7, "reason": "x"}\n```', "score"),
    ('설명이 앞에 있고 {"scores": {"agency": 5}} 뒤에도 산문', "scores"),
])
def test_json_from_lenient_parsing(raw, expected_key):
    parsed = _json_from(raw)
    assert parsed is not None and expected_key in parsed


@pytest.mark.parametrize("raw", ["", "그냥 텍스트", "{broken json", "[1,2,3]"])
def test_json_from_returns_none_on_garbage(raw):
    assert _json_from(raw) is None
