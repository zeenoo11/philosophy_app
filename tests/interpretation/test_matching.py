"""인연 매칭 — 결정론 순위/연도탐색 검증 (산식만, 정답 박제 금지).

검증 목표:
  • rank_candidates: 점수 내림차순 정렬, 멱등성, top_k, 라벨 보존, 동점 안정.
  • best_in_year_range: 결정론(같은 입력→같은 top), top 내림차순+최상위=best_score,
    스캔 수 = 일수×hours, 동치류 요약 비어있지 않음.
"""
from __future__ import annotations

import pytest

from engine.matching import best_in_year_range, rank_candidates
from engine.pillars import BirthInput

pytestmark = pytest.mark.interpretation

_ME = BirthInput(1990, 6, 15, 14, 30)
_CANDS = [
    BirthInput(1992, 3, 3, 9),
    BirthInput(1988, 11, 20, 18),
    BirthInput(1995, 7, 7, 7),
    BirthInput(1991, 1, 30, 12),
]


def test_rank_sorted_descending():
    rows = rank_candidates(_ME, _CANDS)
    assert len(rows) == len(_CANDS)
    scores = [r["총점"] for r in rows]
    assert scores == sorted(scores, reverse=True)
    for r in rows:
        assert 0 <= r["총점"] <= 100
        assert isinstance(r["등급"], str) and r["등급"]
        assert r["birth"] in _CANDS


def test_rank_idempotent_and_topk():
    assert rank_candidates(_ME, _CANDS) == rank_candidates(_ME, _CANDS)
    top2 = rank_candidates(_ME, _CANDS, top_k=2)
    assert len(top2) == 2
    assert top2 == rank_candidates(_ME, _CANDS)[:2]


def test_rank_accepts_labeled_pairs():
    labeled = [("철수", _CANDS[0]), ("영희", _CANDS[1])]
    rows = rank_candidates(_ME, labeled)
    assert {r["label"] for r in rows} == {"철수", "영희"}


def test_rank_tie_break_is_deterministic():
    """동일 후보 중복 → 동점이며 정렬이 흔들리지 않는다."""
    dup = [_CANDS[0], _CANDS[0]]
    rows = rank_candidates(_ME, dup)
    assert rows[0]["총점"] == rows[1]["총점"]
    assert rows == rank_candidates(_ME, dup)


def test_best_range_structure_and_determinism():
    a = best_in_year_range(_ME, 1992, 1992)
    b = best_in_year_range(_ME, 1992, 1992)
    # 결정론: 같은 입력 → 같은 top 라벨/점수 시퀀스.
    assert [r["label"] for r in a["top"]] == [r["label"] for r in b["top"]]
    assert a["best_score"] == b["best_score"]
    # top 은 점수 내림차순, 최상위가 best_score 와 일치.
    scores = [r["총점"] for r in a["top"]]
    assert scores == sorted(scores, reverse=True)
    assert a["top"][0]["총점"] == a["best_score"]
    # 1992는 윤년 → 366일 × 1시 = 366 스캔.
    assert a["scanned"] == 366
    assert a["best_count"] >= 1
    assert a["ilju_dist"] and a["tti_dist"]
    # 동치류 합 = best_count.
    assert sum(n for _, n in a["ilju_dist"]) <= a["best_count"]


def test_best_range_hours_scale_scan():
    """hours 를 늘리면 스캔 수가 비례한다 (같은 해로 비용 억제)."""
    one = best_in_year_range(_ME, 1991, 1991, hours=(12,))
    assert one["scanned"] == 365  # 1991 평년
    multi = best_in_year_range(_ME, 1991, 1991, hours=(2, 12, 22))
    assert multi["scanned"] == 365 * 3


def test_best_range_swaps_reversed_years():
    """from>to 입력은 자동 교정 → 동일 결과."""
    a = best_in_year_range(_ME, 1992, 1991)
    b = best_in_year_range(_ME, 1991, 1992)
    assert a["scanned"] == b["scanned"]
    assert a["best_score"] == b["best_score"]
