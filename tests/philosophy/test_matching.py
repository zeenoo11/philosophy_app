"""철학 사상 매칭·사용자 유사도 — 결정론 검증 (LLM 비호출)."""
import math

import pytest

from philosophy.matching import (AXES, find_matching_philosophies,
                                 load_philosophy_data, rank_similar_users,
                                 similarity)

pytestmark = pytest.mark.philosophy


def test_philo_csv_loads_all_axes():
    data = load_philosophy_data()
    assert len(data) == 12
    for item in data:
        assert len(item["scores"]) == len(AXES) == 7
        assert all(0 <= s <= 10 for s in item["scores"])
        assert item["philosophy"] and item["summary"]


def test_similarity_identity_and_extremes():
    v = [5.0] * 7
    assert similarity(v, v) == 100.0
    # 최대 거리(모든 축 0 ↔ 10) → 0%
    assert similarity([0.0] * 7, [10.0] * 7) == pytest.approx(0.0)


def test_similarity_is_symmetric_and_monotonic():
    a, near, far = [5.0] * 7, [6.0] * 7, [9.0] * 7
    assert similarity(a, near) == similarity(near, a)
    assert similarity(a, near) > similarity(a, far)


def test_similarity_length_mismatch_raises():
    with pytest.raises(ValueError):
        similarity([1.0] * 6, [1.0] * 7)


def test_exact_philosophy_scores_match_itself_first():
    """사상 자신의 좌표를 넣으면 그 사상이 1위(일치율 100)여야 한다."""
    for item in load_philosophy_data():
        ranked = find_matching_philosophies(item["scores"])
        assert ranked[0]["philosophy"] == item["philosophy"]
        assert ranked[0]["match_rate"] == pytest.approx(100.0)


def test_ranking_sorted_descending():
    ranked = find_matching_philosophies([5.0] * 7)
    rates = [r["match_rate"] for r in ranked]
    assert rates == sorted(rates, reverse=True)
    assert len(ranked) == 12


def test_rank_similar_users():
    me = [8.0, 9.0, 5.0, 6.0, 5.0, 4.0, 7.0]
    others = [
        {"username": "twin", "scores": me, "top_philosophy": "스토아주의"},
        {"username": "opposite", "scores": [10 - s for s in me], "top_philosophy": None},
    ]
    rows = rank_similar_users(me, others)
    assert rows[0]["username"] == "twin"
    assert rows[0]["match_rate"] == pytest.approx(100.0)
    assert rows[-1]["username"] == "opposite"
    assert rows[0]["match_rate"] > rows[-1]["match_rate"]


def test_match_rate_linear_formula():
    """일치율 = (1 - d/√700)·100 — 공식 고정(회귀 방지)."""
    a, b = [0.0] * 7, [3.0] * 7
    d = math.dist(a, b)
    expected = (1 - d / math.sqrt(700)) * 100
    assert similarity(a, b) == pytest.approx(expected)
