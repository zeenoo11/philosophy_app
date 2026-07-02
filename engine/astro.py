"""L1 천문 계산 (skyfield) — 자체 엔진. sxtwl 과 독립.

제공:
  solar_longitude_deg(dt_utc)        태양 겉보기 황경 (of-date), 절기/년/월 경계의 진리원
  solar_term_time(year, jq_index)    절기 입절(立節) UTC 시각 (황경 15° 교차, bisection)
  true_solar_datetime(dt_utc, lon)   진태양시(LAST) 벽시계 — 시주/일 경계용
  equation_of_time_seconds(dt_utc)   균시차 (검증/리포트용)

절기 = 태양 황경이 15°의 배수를 지나는 순간 (표 룩업 아님, 천문 계산).
jq_index 규약(sxtwl 호환): 0동지 1소한 … target_λ = (270 + 15·jq_index) % 360.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from functools import lru_cache
from pathlib import Path

from skyfield.api import Loader

_EPH_DIR = Path(__file__).resolve().parent / "_ephemeris"


@lru_cache(maxsize=1)
def _engine():
    """(timescale, earth, sun) 싱글턴. de421.bsp 는 최초 1회 캐시."""
    load = Loader(str(_EPH_DIR))
    ts = load.timescale()              # builtin 윤초 (네트워크 불필요)
    eph = load("de421.bsp")            # 최초 1회 ~17MB 다운로드/캐시
    return ts, eph["earth"], eph["sun"]


def _as_utc(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        raise ValueError("astro 입력 datetime 은 반드시 tz-aware 여야 한다")
    return dt.astimezone(timezone.utc)


def solar_longitude_deg(dt_utc: datetime) -> float:
    """태양 겉보기 황경 (of-date 황도좌표계), 0~360 도."""
    ts, earth, sun = _engine()
    t = ts.from_datetime(_as_utc(dt_utc))
    astro = earth.at(t).observe(sun).apparent()
    _, lon, _ = astro.ecliptic_latlon(epoch="date")
    return lon.degrees % 360.0


def target_longitude(jq_index: int) -> float:
    """절기 인덱스 → 목표 태양황경."""
    return (270.0 + 15.0 * jq_index) % 360.0


# 절기별 근사 (월, 일) — bisection 브래킷용 (연도별 ±2일 변동을 ±6일로 포괄)
_APPROX_MD = {
    0: (12, 22), 1: (1, 6), 2: (1, 20), 3: (2, 4), 4: (2, 19), 5: (3, 6),
    6: (3, 20), 7: (4, 5), 8: (4, 20), 9: (5, 6), 10: (5, 21), 11: (6, 6),
    12: (6, 21), 13: (7, 7), 14: (7, 23), 15: (8, 8), 16: (8, 23), 17: (9, 8),
    18: (9, 23), 19: (10, 8), 20: (10, 23), 21: (11, 7), 22: (11, 22), 23: (12, 7),
}


def _ang_diff(dt_utc: datetime, target: float) -> float:
    """λ(t) − target 를 (−180, 180] 로 환산 (교차점에서 0, 부호 증가)."""
    return ((solar_longitude_deg(dt_utc) - target + 180.0) % 360.0) - 180.0


@lru_cache(maxsize=8192)
def solar_term_time(year: int, jq_index: int) -> datetime:
    """절기 입절 UTC 시각 — 태양황경 target 교차 순간 (bisection, ~1초 정밀).

    (year, jq_index) 캐시 — 같은 해 재계산 회피(차트 대량 계산 성능).
    """
    target = target_longitude(jq_index)
    month, day = _APPROX_MD[jq_index]
    center = datetime(year, month, day, tzinfo=timezone.utc)
    lo, hi = center - timedelta(days=6), center + timedelta(days=6)
    flo, fhi = _ang_diff(lo, target), _ang_diff(hi, target)
    # 브래킷 보장: 부호가 같으면 윈도우 확대
    widen = 0
    while flo > 0 or fhi < 0:
        widen += 1
        if widen > 6:
            raise RuntimeError(f"절기 브래킷 실패 year={year} jq={jq_index}")
        lo -= timedelta(days=4)
        hi += timedelta(days=4)
        flo, fhi = _ang_diff(lo, target), _ang_diff(hi, target)
    for _ in range(60):
        mid = lo + (hi - lo) / 2
        fmid = _ang_diff(mid, target)
        if fmid < 0:
            lo = mid
        else:
            hi = mid
        if (hi - lo) < timedelta(seconds=0.5):
            break
    return lo + (hi - lo) / 2


def _sun_apparent_ra_gast(dt_utc: datetime) -> tuple[float, float]:
    """(태양 겉보기 적경[hours, of-date], 그리니치 겉보기 항성시[hours])."""
    ts, earth, sun = _engine()
    t = ts.from_datetime(_as_utc(dt_utc))
    astro = earth.at(t).observe(sun).apparent()
    ra, _dec, _dist = astro.radec(epoch="date")
    return ra.hours, t.gast


def true_solar_datetime(dt_utc: datetime, longitude_deg: float) -> datetime:
    """진태양시(국지 겉보기 태양시, LAST) 벽시계 — naive datetime 반환.

    LAST = 국지평균시(LMT) + 균시차(EoT).  LMT = UT + 경도/15h.
    동쪽 경도 양수. 반환값은 tz 없는 '태양 벽시계'(시주/일경계 판정용).
    """
    dt_utc = _as_utc(dt_utc)
    ra_hours, gast = _sun_apparent_ra_gast(dt_utc)
    lmt = dt_utc + timedelta(hours=longitude_deg / 15.0)
    lmt_tod = lmt.hour + lmt.minute / 60 + lmt.second / 3600 + lmt.microsecond / 3.6e9
    # 국지 겉보기 태양시 (시각): 국지 시각각 + 12h
    lst_local = (gast + longitude_deg / 15.0) % 24.0
    local_ha = lst_local - ra_hours
    last_tod = (local_ha + 12.0) % 24.0
    eot_hours = ((last_tod - lmt_tod + 12.0) % 24.0) - 12.0   # (−0.5,0.5)h 로 환원
    last = lmt + timedelta(hours=eot_hours)
    return last.replace(tzinfo=None)


def equation_of_time_seconds(dt_utc: datetime) -> float:
    """균시차 (겉보기 − 평균 태양시), 초 단위. 검증/리포트용."""
    dt_utc = _as_utc(dt_utc)
    ra_hours, gast = _sun_apparent_ra_gast(dt_utc)
    ut_tod = dt_utc.hour + dt_utc.minute / 60 + dt_utc.second / 3600 + dt_utc.microsecond / 3.6e9
    ast_greenwich = ((gast - ra_hours) + 12.0) % 24.0  # 그리니치 겉보기 태양시
    eot = ((ast_greenwich - ut_tod + 12.0) % 24.0) - 12.0
    return eot * 3600.0
