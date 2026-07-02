"""교차출처 oracle 어댑터 — sxtwl(寿星天文历) 래퍼.

규약 (스모크로 확정, SPEC §3.1(e)):
  • sxtwl 의 모든 시각은 중국표준시(CST=UTC+8). JD2DD → naive → CST → UTC 변환.
  • 절기 인덱스: 0동지 1소한 … target_λ=(270+15·jq)%360.
  • getJieQiByYear(Y) 는 입춘(Y) → 입춘(Y+1) 구간(干支年)의 절기를 시간순 반환.

이 모듈은 '정답'이 아니라 독립 출처다. 간지 합치는 assert(불일치=엔진 버그),
sub-theory(월률분야 등) 합법적 분기는 diff 리포트로 다룬다(SPEC §3.1(e)).
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import sxtwl

from engine import constants as C

CST = timezone(timedelta(hours=8))


def _jd_to_utc(jd: float) -> datetime:
    dd = sxtwl.JD2DD(jd)
    sec = float(dd.s)
    naive_cst = datetime(int(dd.Y), int(dd.M), int(dd.D), int(dd.h), int(dd.m),
                         int(sec), int((sec % 1) * 1e6), tzinfo=CST)
    return naive_cst.astimezone(timezone.utc)


def sxtwl_pillars(year: int, month: int, day: int, hour: int) -> tuple[int, int, int, int]:
    """(년, 월, 일, 시) 60갑자 인덱스 — sxtwl 기준 (민간시/자정경계).

    hour 는 0~23 정수(분 무시). 시주는 getShiGz(일간, hour) 사용.
    """
    sd = sxtwl.fromSolar(year, month, day)
    yg, mg, dg = sd.getYearGZ(), sd.getMonthGZ(), sd.getDayGZ()
    sh = sxtwl.getShiGz(dg.tg, hour, False)
    return (
        C.gz_from(yg.tg, yg.dz),
        C.gz_from(mg.tg, mg.dz),
        C.gz_from(dg.tg, dg.dz),
        C.gz_from(sh.tg, sh.dz),
    )


def sxtwl_terms(year: int) -> list[tuple[int, datetime]]:
    """干支年(입춘 Y → 입춘 Y+1) 구간의 (jq_index, UTC시각) 시간순 목록."""
    return [(info.jqIndex, _jd_to_utc(info.jd)) for info in sxtwl.getJieQiByYear(year)]


def sxtwl_ipchun_utc(year: int) -> datetime:
    """해당 연도 입춘(立春, jq3) UTC 시각 — getJieQiByYear(Y)[0]."""
    for jq, t in sxtwl_terms(year):
        if jq == 3:
            return t
    raise RuntimeError(f"입춘 미발견 year={year}")  # pragma: no cover
