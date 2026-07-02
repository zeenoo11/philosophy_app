"""P3 — 교차출처 차분 (oracle 검증, SPEC §3.1(e)).

자체 엔진(산술/skyfield) ⟷ 독립 라이브러리(sxtwl) 동시 투입:
  • 간지·절기가 일치해야 하는 부분 → assert (불일치 = 자체 엔진 버그)
  • 합법적으로 갈리는 sub-theory → diff 리포트 (test_toggles.py)

단일 만세력 앱을 정답으로 박제하지 않는다(SPEC §7 안티패턴1): sxtwl(간지)와
skyfield(절기 천문)라는 '복수 독립 출처'의 합치로 검증한다.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
import sxtwl

from engine import astro, constants as C
from engine.pillars import BirthInput, DeterministicConfig, compute_chart, day_gz60
from tests.oracle import sxtwl_pillars, sxtwl_terms

pytestmark = [pytest.mark.deterministic, pytest.mark.oracle]
_CIVIL = DeterministicConfig(true_solar_time=False)


def test_day_pillar_full_sweep_matches_sxtwl():
    """1905–2045 전 일자의 일주가 sxtwl 과 완전 일치 (앵커+JDN 검증)."""
    d, end = date(1905, 1, 1), date(2045, 12, 31)
    mism = []
    while d <= end:
        mine = day_gz60(d.year, d.month, d.day)
        dg = sxtwl.fromSolar(d.year, d.month, d.day).getDayGZ()
        if mine != C.gz_from(dg.tg, dg.dz):
            mism.append(d.isoformat())
        d += timedelta(days=1)
    assert not mism, f"일주 불일치 {len(mism)}건, 최초: {mism[:5]}"


def test_full_pillars_sample_matches_sxtwl():
    """월중(절기 경계 회피) 표본의 4기둥 전부 sxtwl 과 일치."""
    mism = []
    for year in range(1920, 2041, 8):
        for month in range(1, 13):
            ch = compute_chart(BirthInput(year, month, 12, 10, 0), _CIVIL)
            mine = (ch.year.gz60, ch.month.gz60, ch.day.gz60, ch.hour.gz60)
            theirs = sxtwl_pillars(year, month, 12, 10)
            if mine != theirs:
                mism.append((year, month,
                             [C.gz_name(g) for g in mine],
                             [C.gz_name(g) for g in theirs]))
    assert not mism, f"기둥 불일치 {len(mism)}건: {mism[:3]}"


def _max_term_diff(years) -> tuple[float, int]:
    worst, n = 0.0, 0
    for year in years:
        for jq, t_sx in sxtwl_terms(year):
            diff = abs((astro.solar_term_time(t_sx.year, jq) - t_sx).total_seconds())
            worst, n = max(worst, diff), n + 1
    return worst, n


@pytest.mark.astro
def test_solar_terms_agree_skyfield_vs_sxtwl_well_constrained():
    """절기 입절: 자체 천문(skyfield) ⟷ sxtwl 합치 (<30초, ΔT 확정 구간).

    두 독립 천문엔진의 합치 = '정답'의 신뢰 근거. 잔차(~15초)는 모델/ΔT 미세차.
    """
    worst, n = _max_term_diff((1950, 1980, 2000, 2010, 2020, 2030))
    assert worst < 30.0, f"확정구간 절기 최대차 {worst:.1f}s 과대"
    print(f"\n[diff 리포트] 확정구간 절기 {n}개, skyfield↔sxtwl 최대차 {worst:.1f}s")


@pytest.mark.astro
def test_solar_terms_agree_future_extrapolation():
    """미래 외삽 구간(2040~2049): ΔT 예측 모델 차이로 잔차 증가하나 분 단위 미만.

    이 잔차는 엔진 버그가 아니라 ΔT 외삽의 본질적 한계(만세력 공통). 사주 판정에는
    무해(절기 ±2분 이내 출생은 어느 만세력도 모호). 상한만 확인한다.
    """
    worst, n = _max_term_diff((2040, 2045, 2049))
    assert worst < 120.0, f"외삽구간 절기 최대차 {worst:.1f}s — ΔT 한계 초과 의심"
    print(f"\n[diff 리포트] 외삽구간 절기 {n}개, skyfield↔sxtwl 최대차 {worst:.1f}s")


@pytest.mark.astro
def test_engine_month_consistent_with_sxtwl_terms():
    """엔진의 월지가 sxtwl 절기 구간과 정합 (절기 직후 1시간)."""
    for year in (2000, 2024):
        for jq, t_sx in sxtwl_terms(year):
            if jq % 2 == 0:
                continue  # 中氣는 월 변경 없음 → 節(홀수)만
            t_after = (t_sx + timedelta(hours=1)).astimezone(ZoneInfo("Asia/Seoul"))
            ch = compute_chart(
                BirthInput(t_after.year, t_after.month, t_after.day, t_after.hour, t_after.minute),
                DeterministicConfig(true_solar_time=False))
            expected_branch = (2 + ((jq - 3) // 2)) % 12  # 입춘(jq3)=寅(2) 기준
            assert ch.month.branch == expected_branch, \
                f"{year} jq{jq}: 월지 {ch.month.branch} != {expected_branch}"
