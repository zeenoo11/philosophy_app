"""명제 분해 — 규칙 폴백 경로 (LLM 미호출)."""
import pytest

from philosophy.decompose import _decompose_rule, _strip_fences, decompose

pytestmark = pytest.mark.philosophy


def test_rule_splits_on_contrast():
    parts = _decompose_rule("사랑은 삶을 풍요롭게 한다 하지만 결핍과 고통도 준다", 4)
    assert len(parts) == 2
    assert "풍요롭게" in parts[0] and "결핍" in parts[1]


def test_rule_strips_opinion_frame():
    parts = _decompose_rule("나는 자유가 가장 중요하다고 생각해", 4)
    assert parts and not parts[0].startswith("나는")


def test_rule_respects_max_claims():
    text = "A는 옳다. B는 그르다. C는 애매하다. D는 확실하다. E는 모른다"
    assert len(_decompose_rule(text, 3)) == 3


def test_decompose_empty_and_fallback():
    assert decompose("", use_llm=False) == []
    assert decompose("Freedom matters most", use_llm=False) == ["Freedom matters most"]


def test_strip_fences():
    assert _strip_fences('```json\n["a"]\n```') == '["a"]'
    assert _strip_fences('["a"]') == '["a"]'
