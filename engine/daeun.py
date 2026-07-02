"""L1 결정론 — 대운(大運, 10년 주기) 산출.

표준 자평(子平) 관례:
  • 방향(順逆): 양남음녀 順行, 음남양녀 逆行. '양/음'은 年干(year stem)의 음양.
      forward = (年干 양 and 남) or (年干 음 and 여)
  • 간지 진행: 月柱(月支) 60갑자에서 출발, 順行 +1 / 逆行 -1 (mod 60), 10년 단위.
  • 대운수(첫 대운 시작 나이):
      順行 → 출생시각부터 '다음 節'까지의 일수,
      逆行 → '이전 節'부터 출생시각까지의 일수.
      일수 / 3 (3일=1년 관례), round() 후 최소 1.
  • 節(절기로 月이 바뀌는 지점) = astro.solar_term_time 의 홀수 jq(1,3,5,…,23).

순수 결정론: 같은 입력 → 같은 출력. 해석(길흉)은 이 레이어에 없다.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

from engine import astro, constants as C
from engine.provenance import Trace

# 節(월 경계) = 홀수 jq_index. (jq 규약: 0동지 1소한 2대한 3입춘 …, 홀수가 立節)
_JEOL_JQ = tuple(range(1, 24, 2))   # (1, 3, 5, 7, 9, 11, 13, 15, 17, 19, 21, 23)

_SECONDS_PER_DAY = 86400.0


@dataclass(frozen=True)
class DaeunResult:
    forward: bool
    start_age: int
    pillars: list          # [(age:int, gz60:int, name:str), ...]
    trace: Trace


def _jeol_times(year: int) -> list[datetime]:
    """해당 연도의 모든 節(월 경계) 입절 UTC 시각."""
    return [astro.solar_term_time(year, jq) for jq in _JEOL_JQ]


def _all_jeol_around(year: int) -> list[datetime]:
    """출생 전후(±1년)의 節 시각을 정렬해 모은다 (경계 누락 방지)."""
    times: list[datetime] = []
    for y in (year - 1, year, year + 1):
        times.extend(_jeol_times(y))
    times.sort()
    return times


def _next_jeol(t_utc: datetime) -> datetime:
    """t_utc 직후의 가장 가까운 節 (t_utc 초과)."""
    for jt in _all_jeol_around(t_utc.year):
        if jt > t_utc:
            return jt
    raise RuntimeError("다음 節을 찾지 못함")  # pragma: no cover


def _prev_jeol(t_utc: datetime) -> datetime:
    """t_utc 직전의 가장 가까운 節 (t_utc 미만)."""
    for jt in reversed(_all_jeol_around(t_utc.year)):
        if jt < t_utc:
            return jt
    raise RuntimeError("이전 節을 찾지 못함")  # pragma: no cover


def _daeunsu(t_utc: datetime, forward: bool) -> tuple[int, float]:
    """(대운수, 경계까지의 일수). 順行=다음 節까지, 逆行=이전 節부터."""
    if forward:
        delta = _next_jeol(t_utc) - t_utc
    else:
        delta = t_utc - _prev_jeol(t_utc)
    days = delta.total_seconds() / _SECONDS_PER_DAY
    su = max(1, round(days / 3.0))
    return su, days


def compute_daeun(chart, gender: str, count: int = 8) -> DaeunResult:
    """차트 + 성별 → 대운(大運) 리스트.

    gender ∈ {"남", "여"}. count = 생성할 대운 개수(기본 8).
    """
    if gender not in ("남", "여"):
        raise ValueError(f"gender 는 '남'/'여' 여야 합니다: {gender!r}")

    year_stem = chart.year.stem
    yang_year = C.CHEONGAN_EUMYANG[year_stem] == 0   # 0=양, 1=음
    male = gender == "남"
    # 양남음녀 順行, 음남양녀 逆行
    forward = (yang_year and male) or ((not yang_year) and (not male))

    t_utc = chart.meta["t_utc"]
    start_age, days = _daeunsu(t_utc, forward)

    month_gz = chart.month.gz60
    step = 1 if forward else -1

    pillars: list[tuple[int, int, str]] = []
    for k in range(count):
        gz = (month_gz + step * (k + 1)) % 60
        age = start_age + 10 * k
        pillars.append((age, gz, C.gz_name(gz)))

    trace = Trace(
        rule_id="daeun.forward" if forward else "daeun.backward",
        preset_id="",
        layer="L1",
        inputs={
            "direction": "順行" if forward else "逆行",
            "forward": forward,
            "year_stem": year_stem,
            "year_stem_eumyang": "양" if yang_year else "음",
            "gender": gender,
            "daeunsu": start_age,
            "days_to_boundary": round(days, 4),
            "month_gz60": month_gz,
            "month_name": C.gz_name(month_gz),
            "count": count,
        },
        classical_source="자평진전(대운)",
    )

    return DaeunResult(
        forward=forward,
        start_age=start_age,
        pillars=pillars,
        trace=trace,
    )
