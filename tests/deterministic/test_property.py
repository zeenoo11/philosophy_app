"""P1 — L1 속성 기반 테스트 (구조적 불변식). 정답이 아니라 '구조'를 검증.

  • 일주 60갑자 연속성 (끊김/중복 없음)
  • 천간/지지 인덱스 범위
  • 오호둔(五虎遁)·오자둔(五鼠遁) — 결정론 규칙
  • 년주 = (사주연도−4) mod 60 정합
"""
from __future__ import annotations

from datetime import date, datetime, timedelta

import pytest
from hypothesis import given, settings, strategies as st

from engine.pillars import (BirthInput, DeterministicConfig, compute_chart,
                            day_gz60, _hour_branch)

pytestmark = pytest.mark.deterministic

# 에페메리스(de421) 안전 범위
_LO, _HI = datetime(1910, 1, 1), datetime(2050, 12, 31)
_CIVIL = DeterministicConfig(true_solar_time=False)

# 오호둔: 년간 → 寅월 천간 / 오자둔: 일간 → 子시 천간
OHODUN = {0: 2, 5: 2, 1: 4, 6: 4, 2: 6, 7: 6, 3: 8, 8: 8, 4: 0, 9: 0}
OZADUN = {0: 0, 5: 0, 1: 2, 6: 2, 2: 4, 7: 4, 3: 6, 8: 6, 4: 8, 9: 8}


@given(st.dates(date(1700, 1, 1), date(2300, 12, 31)))
def test_day_pillar_60cycle_continuity(d):
    """연속한 두 날의 일주는 60갑자에서 정확히 1칸 차이."""
    nxt = d + timedelta(days=1)
    a = day_gz60(d.year, d.month, d.day)
    b = day_gz60(nxt.year, nxt.month, nxt.day)
    assert (b - a) % 60 == 1


@settings(max_examples=40, deadline=None)
@given(st.datetimes(_LO, _HI))
def test_pillar_ranges(dt):
    """모든 기둥의 천간 0..9, 지지 0..11, 60갑자 0..59."""
    ch = compute_chart(BirthInput(dt.year, dt.month, dt.day, dt.hour, dt.minute), _CIVIL)
    for p in ch.pillars:
        assert 0 <= p.stem < 10
        assert 0 <= p.branch < 12
        assert 0 <= p.gz60 < 60


@settings(max_examples=40, deadline=None)
@given(st.datetimes(_LO, _HI))
def test_year_pillar_matches_saju_year(dt):
    """년주 60갑자 = (사주연도 − 4) mod 60."""
    ch = compute_chart(BirthInput(dt.year, dt.month, dt.day, dt.hour, dt.minute), _CIVIL)
    saju_year = ch.meta["saju_year"]
    assert ch.year.gz60 == (saju_year - 4) % 60


@pytest.mark.parametrize("hour", range(24))
def test_hour_branch_mapping(hour):
    """시지: 子=23–01, 이후 2시간 단위."""
    expected = ((hour + 1) // 2) % 12
    assert _hour_branch(datetime(2000, 1, 1, hour, 30)) == expected


@pytest.mark.parametrize("year", range(1920, 2051, 7))
def test_ohodun_invariant(year):
    """寅월(입춘~경칩) 출생의 월간은 오호둔으로 년간에서 결정된다."""
    ch = compute_chart(BirthInput(year, 2, 10, 12, 0), _CIVIL)
    assert ch.month.branch == 2, "2/10 은 寅월이어야 함"
    assert ch.month.stem == OHODUN[ch.year.stem]


@pytest.mark.parametrize("year,month,day", [
    (1955, 5, 20), (1980, 8, 8), (2001, 3, 3), (2024, 11, 15), (1947, 7, 1),
])
def test_ojadun_invariant(year, month, day):
    """子시(00:00–01:00) 출생의 시간은 오자둔으로 일간에서 결정된다."""
    ch = compute_chart(BirthInput(year, month, day, 0, 30), _CIVIL)
    assert ch.hour.branch == 0, "00:30 은 子시여야 함"
    assert ch.hour.stem == OZADUN[ch.day.stem]
