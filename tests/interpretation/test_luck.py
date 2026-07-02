"""L1 시기별 운세(세운/월운/일진/주간) — 규칙 충실도·일치·멱등성 검증.

외부 정답 박제 금지. 검증 목표:
  • 세운: gz=(year-4)%60 규칙 일치(2026=병오), 천간십신 존재.
  • 월운: 12개, 각 ganji 가 gz_from 으로 역산 가능, 寅월 천간=오호둔 일치.
  • 일진: gz60 == day_gz60 일치, score 25~95, 신살은 리스트.
  • 주간: 7개 연속(날짜 +1일).
  • 멱등성: 같은 입력 → 같은 출력.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

from engine import constants as C
from engine.luck import day_luck, month_luck, saeun, week_luck
from engine.pillars import BirthInput, compute_chart, day_gz60

pytestmark = pytest.mark.interpretation

# 검증용 표본 — 계절·연대 분산 (실제 차트 사용)
_BIRTHS = [
    BirthInput(1990, 6, 15, 14, 30),
    BirthInput(1988, 9, 15, 10, 0),
    BirthInput(1972, 1, 5, 23, 10),
    BirthInput(2003, 11, 20, 6, 45),
    BirthInput(1955, 3, 30, 18, 0),
]


def _charts():
    return [compute_chart(b) for b in _BIRTHS]


# ─────────────────────────────────────────────────────────────────────────
# 세운
# ─────────────────────────────────────────────────────────────────────────
def test_saeun_2026_is_byeongo():
    """2026 세운 = 병오 (gz=(2026-4)%60=42), 천간십신 존재."""
    for chart in _charts():
        s = saeun(chart, 2026)
        assert s["ganji"] == "병오"
        assert s["gz60"] == 42
        assert s["year"] == 2026
        assert s["천간십신"] in C.SIPSIN_NAMES
        assert s["지지십신"] in C.SIPSIN_NAMES
        assert s["오행"] in C.OHAENG_HANGUL


def test_saeun_rule_matches_for_range():
    """임의 연도 범위에서 gz=(year-4)%60 규칙·이름 일치."""
    chart = _charts()[0]
    for year in range(1990, 2031):
        s = saeun(chart, year)
        gz = (year - 4) % 60
        assert s["gz60"] == gz
        assert s["ganji"] == C.gz_name(gz)


# ─────────────────────────────────────────────────────────────────────────
# 월운
# ─────────────────────────────────────────────────────────────────────────
def test_month_luck_twelve_and_valid_ganji():
    """월운 12개, 각 ganji 가 gz_from(stem,branch)으로 역산 가능."""
    for chart in _charts():
        ml = month_luck(chart, 2026)
        assert len(ml) == 12
        for item in ml:
            gz = item["gz60"]
            # gz_from 역산: 이름이 (stem,branch) 조합과 일치
            assert C.gz_name(gz) == item["ganji"]
            assert C.gz_from(gz % 10, gz % 12) == gz
            assert item["천간십신"] in C.SIPSIN_NAMES
            assert item["지지십신"] in C.SIPSIN_NAMES


def test_month_luck_first_month_is_ohodun():
    """寅월(첫 달) 천간이 오호둔 = (2*연간+2)%10 과 일치, 월지=寅."""
    for chart in _charts():
        for year in (2024, 2025, 2026):
            ml = month_luck(chart, year)
            first = ml[0]
            assert first["월지"] == C.JIJI_HANGUL[2]   # 寅
            year_stem = (year - 4) % 10
            expected_stem = (2 * year_stem + 2) % 10
            assert first["gz60"] % 10 == expected_stem


def test_month_luck_branches_are_in_sequence():
    """월지가 寅(2)부터 +1로 12개 순행."""
    ml = month_luck(_charts()[0], 2026)
    branches = [item["gz60"] % 12 for item in ml]
    assert branches == [(2 + k) % 12 for k in range(12)]


# ─────────────────────────────────────────────────────────────────────────
# 일진
# ─────────────────────────────────────────────────────────────────────────
def test_day_luck_matches_day_gz60_and_score_range():
    """임의 날짜: gz60==day_gz60 일치, score 25~95, 신살은 리스트."""
    sample_dates = [(2026, 6, 19), (2026, 1, 1), (2024, 2, 29),
                    (1999, 12, 31), (2030, 7, 15)]
    for chart in _charts():
        for d in sample_dates:
            r = day_luck(chart, d)
            assert r["gz60"] == day_gz60(*d)
            assert r["ganji"] == C.gz_name(r["gz60"])
            assert isinstance(r["score"], int)
            assert 25 <= r["score"] <= 95
            assert isinstance(r["신살"], list)
            assert r["길흉"] in ("좋음", "보통", "주의")
            assert r["천간십신"] in C.SIPSIN_NAMES
            assert r["지지십신"] in C.SIPSIN_NAMES
            assert r["date"] == f"{d[0]:04d}-{d[1]:02d}-{d[2]:02d}"


def test_day_luck_gilhyung_consistent_with_score():
    """길흉 라벨이 score 임계와 일관."""
    chart = _charts()[0]
    start = date(2026, 1, 1)
    for k in range(60):
        d = start + timedelta(days=k)
        r = day_luck(chart, (d.year, d.month, d.day))
        if r["score"] >= 70:
            assert r["길흉"] == "좋음"
        elif r["score"] >= 45:
            assert r["길흉"] == "보통"
        else:
            assert r["길흉"] == "주의"


def test_day_luck_sinsal_subset():
    """신살 항목은 허용된 명칭 집합 안에 든다."""
    allowed = {"천을귀인", "양인", "문창", "도화", "역마", "화개"}
    chart = _charts()[0]
    start = date(2026, 1, 1)
    for k in range(120):
        d = start + timedelta(days=k)
        r = day_luck(chart, (d.year, d.month, d.day))
        assert set(r["신살"]) <= allowed


# ─────────────────────────────────────────────────────────────────────────
# 주간
# ─────────────────────────────────────────────────────────────────────────
def test_week_luck_seven_consecutive_days():
    """주간 7개, 날짜가 +1일씩 연속."""
    for chart in _charts():
        wl = week_luck(chart, (2026, 6, 19))
        assert len(wl) == 7
        start = date(2026, 6, 19)
        for k, item in enumerate(wl):
            expect = start + timedelta(days=k)
            assert item["date"] == expect.isoformat()
            # 각 일진의 gz60 도 일치
            assert item["gz60"] == day_gz60(expect.year, expect.month, expect.day)


def test_week_luck_crosses_month_boundary():
    """월/연 경계를 넘어도 7일 연속(누락·중복 없음)."""
    wl = week_luck(_charts()[0], (2026, 12, 29))
    dates = [item["date"] for item in wl]
    start = date(2026, 12, 29)
    assert dates == [(start + timedelta(days=k)).isoformat() for k in range(7)]


# ─────────────────────────────────────────────────────────────────────────
# 멱등성
# ─────────────────────────────────────────────────────────────────────────
def test_idempotent():
    for chart in _charts():
        assert saeun(chart, 2026) == saeun(chart, 2026)
        assert month_luck(chart, 2026) == month_luck(chart, 2026)
        assert day_luck(chart, (2026, 6, 19)) == day_luck(chart, (2026, 6, 19))
        assert week_luck(chart, (2026, 6, 19)) == week_luck(chart, (2026, 6, 19))
