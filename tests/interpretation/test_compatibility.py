"""궁합(두 사람 합) — 구조/멱등성/그라운딩 검증 (정답 박제 금지, 산식만).

검증 목표:
  • 기본: 총점 0~100, 등급 문자열, 4개 부분항목 점수 0~100, 근거 비어있지 않음.
  • 멱등성: 같은 입력 → 같은 출력.
  • 천간합 케이스: 일간이 합(甲己合)인 두 입력 → 일간관계 label="천간합", 점수>=90.
  • 가중평균: 부분점수 가중합이 총점과 ±1 일치.
"""
from __future__ import annotations

import pytest

from engine import constants as C
from engine.compatibility import gunghap
from engine.pillars import BirthInput, compute_chart

pytestmark = pytest.mark.interpretation

_A = BirthInput(1990, 6, 15, 14, 30)
_B = BirthInput(1992, 3, 3, 9, 0)

# 천간합(甲己合) 일간이 성립하는 두 입력 — compute_chart 로 사전 확인된 사례.
#   1990-01-09 12:00 → 일간 甲(0), 1990-01-04 12:00 → 일간 己(5).
_HAP_A = BirthInput(1990, 1, 9, 12, 0)
_HAP_B = BirthInput(1990, 1, 4, 12, 0)

_PART_KEYS = ("일간관계", "띠관계", "일지관계", "오행보완")


def test_basic_structure_and_ranges():
    r = gunghap(_A, _B)
    assert 0 <= r["총점"] <= 100
    assert isinstance(r["등급"], str) and r["등급"]
    for key in _PART_KEYS:
        assert 0 <= r[key]["점수"] <= 100, f"{key} 점수 범위 벗어남"
        assert isinstance(r[key]["label"], str) and r[key]["label"]
    assert isinstance(r["근거"], list) and r["근거"], "근거가 비어있음"
    # a/b 메타
    assert r["a"]["eight_chars"] == compute_chart(_A).eight_chars()
    assert r["b"]["eight_chars"] == compute_chart(_B).eight_chars()
    assert isinstance(r["오행보완"]["보완오행"], list)


def test_idempotent():
    assert gunghap(_A, _B) == gunghap(_A, _B)


def test_cheongan_hap_case():
    """일간 甲·己 = 甲己合 → 일간관계 label='천간합', 점수>=90."""
    ca, cb = compute_chart(_HAP_A), compute_chart(_HAP_B)
    # 전제: 실제로 천간합이 성립하는 일간쌍인지 먼저 확인.
    assert frozenset({ca.day_master, cb.day_master}) in C.CHEONGAN_HAP
    r = gunghap(_HAP_A, _HAP_B)
    assert r["일간관계"]["label"] == "천간합"
    assert r["일간관계"]["점수"] >= 90


def test_weighted_average_matches_total():
    """부분점수 가중합(일간0.35·일지0.25·띠0.2·오행보완0.2)이 총점과 ±1."""
    for a, b in [(_A, _B), (_HAP_A, _HAP_B)]:
        r = gunghap(a, b)
        expected = round(
            r["일간관계"]["점수"] * 0.35
            + r["일지관계"]["점수"] * 0.25
            + r["띠관계"]["점수"] * 0.2
            + r["오행보완"]["점수"] * 0.2
        )
        assert abs(r["총점"] - expected) <= 1


def test_trace_present():
    """trace 가 동반되고 부분점수 입력을 담는다."""
    r = gunghap(_A, _B)
    tr = r["trace"]
    assert tr.rule_id == "gunghap.compose"
    assert tr.layer == "L1"
    assert set(tr.inputs) == {"일간", "일지", "띠", "오행보완"}
