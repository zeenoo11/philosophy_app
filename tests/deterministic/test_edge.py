"""P2 — L1 엣지 매트릭스 (한국 특수사항). 대부분의 버그가 여기서 난다.

  입춘 절입 · 절기 경계 · 야자시 토글 · 진태양시 · 균시차 · tz 역사 · 서머타임.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

import pytest

from engine import astro, timeutil
from engine.pillars import BirthInput, DeterministicConfig, compute_chart

pytestmark = pytest.mark.deterministic
SEOUL = ZoneInfo("Asia/Seoul")
_CIVIL = DeterministicConfig(true_solar_time=False)


def _civil_around(year: int, jq: int, minutes: int) -> BirthInput:
    """절기 입절 시각 ±minutes 의 KST 민간시각으로 BirthInput 생성."""
    t = astro.solar_term_time(year, jq).astimezone(SEOUL) + timedelta(minutes=minutes)
    return BirthInput(t.year, t.month, t.day, t.hour, t.minute, 0)


# ── 입춘 절입: 연주 경계 (1/1 아님) ──
@pytest.mark.parametrize("year", [1984, 2000, 2024])
def test_ipchun_year_boundary(year):
    before = compute_chart(_civil_around(year, 3, -3), _CIVIL)
    after = compute_chart(_civil_around(year, 3, +3), _CIVIL)
    assert before.year.gz60 == (year - 1 - 4) % 60, "입춘 직전은 전년도 간지"
    assert after.year.gz60 == (year - 4) % 60, "입춘 직후는 당년도 간지"
    assert before.year.gz60 != after.year.gz60


# ── 절기 경계: 월주 경계 (경칩 → 寅월에서 卯월) ──
@pytest.mark.parametrize("year", [1990, 2010, 2024])
def test_solar_term_month_boundary(year):
    before = compute_chart(_civil_around(year, 5, -3), _CIVIL)   # 경칩 직전
    after = compute_chart(_civil_around(year, 5, +3), _CIVIL)    # 경칩 직후
    assert before.month.branch == 2, "경칩 직전은 寅월"
    assert after.month.branch == 3, "경칩 직후는 卯월"


# ── 야자시 / 조자시: 23–01시 유파별 상이 ──
def test_yajasi_toggle_diverges_at_2330():
    inp = BirthInput(1990, 6, 15, 23, 30)
    split = compute_chart(inp, DeterministicConfig(true_solar_time=False, jasi_rule="yajasi_split"))
    unified = compute_chart(inp, DeterministicConfig(true_solar_time=False, jasi_rule="jasi_unified"))
    # 일주: 통합법은 다음날로 → 60갑자 1칸 차이
    assert (unified.day.gz60 - split.day.gz60) % 60 == 1
    # 시지는 둘 다 子, 시간(천간)은 오자둔이 다른 일간에서 나오므로 상이
    assert split.hour.branch == 0 and unified.hour.branch == 0
    assert split.hour.stem != unified.hour.stem


def test_yajasi_toggle_same_at_0030():
    """00:30(조자시 이후)은 두 규칙이 동일해야 한다."""
    inp = BirthInput(1990, 6, 16, 0, 30)
    split = compute_chart(inp, DeterministicConfig(true_solar_time=False, jasi_rule="yajasi_split"))
    unified = compute_chart(inp, DeterministicConfig(true_solar_time=False, jasi_rule="jasi_unified"))
    assert split.day.gz60 == unified.day.gz60
    assert split.hour.gz60 == unified.hour.gz60


# ── 진태양시: 동경 135° vs 실제 ~127° → 약 30분, 시지 경계 이동 ──
def test_true_solar_time_shifts_hour_branch():
    inp = BirthInput(1990, 6, 13, 11, 0)
    on = compute_chart(inp, DeterministicConfig(true_solar_time=True, longitude_deg=127.0))
    off = compute_chart(inp, DeterministicConfig(true_solar_time=False))
    assert off.hour.branch == 6, "보정 없으면 11:00 은 午시"
    assert on.hour.branch == 5, "진태양시 보정 시 巳시로 이동"
    delta = off.meta["solar_wall"] - on.meta["solar_wall"]
    assert timedelta(minutes=28) < delta < timedelta(minutes=36), "약 32분(경도)±균시차"


# ── 균시차: 최대 ±16분, 부호 변동 ──
def test_equation_of_time_sign_and_magnitude():
    def eot_min(m, d):
        return astro.equation_of_time_seconds(datetime(2020, m, d, 3, tzinfo=timezone.utc)) / 60
    assert eot_min(2, 11) < -10        # 2월 중순 음(−14분대)
    assert eot_min(11, 3) > 14         # 11월 초 양(+16분대)
    for m, d in [(2, 11), (5, 14), (7, 26), (11, 3)]:
        assert abs(eot_min(m, d)) < 17  # 항상 ±16분대 이내


# ── 한국 표준시 변경 이력: UTC+9 하드코딩 금지 ──
def test_korea_tz_history_not_hardcoded_plus9():
    off = lambda y, m, d: timeutil.utc_offset_hours(datetime(y, m, d, 12))
    assert off(1910, 1, 1) == 8.5     # +08:30 시기
    assert off(1925, 1, 1) == 9.0     # +09:00 (일제)
    assert off(1955, 1, 1) == 8.5     # +08:30 복원
    assert off(1965, 1, 1) == 9.0     # +09:00 (1961~)
    assert off(2020, 1, 1) == 9.0
    # 역사적으로 여러 오프셋이 존재 → 단일 +9 가 아님
    seen = {off(y, 1, 1) for y in (1910, 1925, 1955, 1965, 2020)}
    assert len(seen) > 1 and 8.5 in seen


def test_korea_summer_time_years():
    off = lambda y, m, d: timeutil.utc_offset_hours(datetime(y, m, d, 12))
    assert off(1988, 7, 15) == 10.0   # 1987–88 서머타임 (+09→+10)
    assert off(1988, 1, 15) == 9.0    # 겨울은 +09
    assert off(1959, 7, 15) == 9.5    # +08:30 시기의 서머타임 (+08:30→+09:30)
    assert off(1959, 1, 15) == 8.5


def test_true_solar_time_handles_historical_offset():
    """진태양시는 UT+경도 기반이라 역사적 오프셋과 자동 정합(수동 135° 가정 금지)."""
    # 1910년(+8:30) 출생도 진태양시 계산이 예외 없이 동작
    ch = compute_chart(BirthInput(1910, 6, 15, 12, 0),
                       DeterministicConfig(true_solar_time=True, longitude_deg=127.0))
    assert 0 <= ch.hour.branch < 12
    assert ch.meta["utc_offset_hours"] == 8.5
