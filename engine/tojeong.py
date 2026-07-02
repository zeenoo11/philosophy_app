"""토정비결(土亭祕訣) 작괘(作卦) — 선천수(先天數) 기반 표준 작괘법.

순수 결정론: 입력(생년월일시 + 대상연도) → 출력(상괘/중괘/하괘 + 괘번호).
괘 해석문(괘사, 占辭)은 별도 LLM/원전 텍스트로 생성한다. 본 모듈은 작괘
(괘번호 산출)만 결정론으로 수행하며, 외부 정답(특정 괘번호가 '정답')을 박제하지
않는다.

작괘 산식 (선천수 기반):
  • 태세수 = 천간선천수[太歲干] + 지지선천수[太歲支]   (그 해 干支)
  • 중수   = 천간선천수[月干]   + 지지선천수[月支]      (사주 月柱)
  • 하수   = 천간선천수[日干]   + 지지선천수[日支]      (사주 日柱)
  • 상괘 = (세는나이 + 태세수) % 8   (0 → 8)
  • 중괘 = (음력 생월 대소(29/30) + 중수) % 6   (0 → 6)
  • 하괘 = (음력 생일 + 하수) % 3   (0 → 3)
  • 괘번호 = 상괘*100 + 중괘*10 + 하괘
"""
from __future__ import annotations

import sxtwl

from engine import constants as C
from engine.pillars import BirthInput, compute_chart
from engine.provenance import Trace

# ─────────────────────────────────────────────────────────────────────────
# 선천수(先天數) 테이블 — 고정
# ─────────────────────────────────────────────────────────────────────────
# 천간(甲0 … 癸9)
SEONCHEONSU_CHEONGAN: tuple[int, ...] = (9, 8, 7, 6, 5, 9, 8, 7, 6, 5)
# 지지(子0 … 亥11)
SEONCHEONSU_JIJI: tuple[int, ...] = (9, 8, 7, 6, 5, 4, 9, 8, 7, 6, 5, 4)


def _lunar_month_days(lunar_year: int, lunar_month: int, is_leap: bool) -> int:
    """해당 음력월의 일수(대소: 29 또는 30).

    sxtwl.getLunarMonthNum 우선, 실패 시 fromLunar 로 30일 존재 여부 확인.
    반드시 29 또는 30 을 반환한다.
    """
    try:
        n = int(sxtwl.getLunarMonthNum(lunar_year, lunar_month, is_leap))
        if n in (29, 30):
            return n
    except Exception:
        pass
    # 폴백: 음력 30일이 실제 존재하면 大(30), 아니면 小(29)
    try:
        d30 = sxtwl.fromLunar(lunar_year, lunar_month, 30, is_leap)
        if int(d30.getLunarDay()) == 30:
            return 30
    except Exception:
        pass
    return 29


def tojeong_gwae(birth: BirthInput, year: int) -> dict:
    """토정비결 작괘 — 대상 연도(year)의 상·중·하괘 및 괘번호 산출.

    birth : 출생 정보(양력 기준 BirthInput)
    year  : 운세를 보는 대상 연도(해당 연도의 太歲 사용)

    반환 dict 키: year, age, 상괘, 중괘, 하괘, 괘번호, 음력, 태세수, 중수, 하수, trace.
    괘 해석문(괘사)은 본 모듈 밖(LLM/원전 텍스트)에서 생성한다.
    """
    # 세는나이(한국식): 대상연도 - 출생연도 + 1
    age = year - birth.year + 1

    # 음력 변환 (출생 양력 → 음력)
    d = sxtwl.fromSolar(birth.year, birth.month, birth.day)
    lunar_day = int(d.getLunarDay())        # 1~30
    lunar_month = int(d.getLunarMonth())
    is_leap = bool(d.isLunarLeap())
    lunar_year = int(d.getLunarYear())

    # 음력 생월 대소(29/30)
    month_days = _lunar_month_days(lunar_year, lunar_month, is_leap)

    # 사주 차트(월건/일진 간지용)
    chart = compute_chart(birth)

    # 太歲 干支: 대상 연도의 60갑자 (year-4 기준)
    taese_stem = (year - 4) % 10
    taese_branch = (year - 4) % 12

    # 선천수 합산
    taese_su = SEONCHEONSU_CHEONGAN[taese_stem] + SEONCHEONSU_JIJI[taese_branch]
    jung_su = (SEONCHEONSU_CHEONGAN[chart.month.stem]
               + SEONCHEONSU_JIJI[chart.month.branch])
    ha_su = (SEONCHEONSU_CHEONGAN[chart.day.stem]
             + SEONCHEONSU_JIJI[chart.day.branch])

    # 상·중·하괘 (0 → 각 모듈러 최대값)
    sang = (age + taese_su) % 8 or 8
    jung = (month_days + jung_su) % 6 or 6
    ha = (lunar_day + ha_su) % 3 or 3

    gwae_no = sang * 100 + jung * 10 + ha

    eumlyeok = {
        "month": lunar_month,
        "day": lunar_day,
        "leap": is_leap,
        "month_days": month_days,
    }

    trace = Trace(
        rule_id="tojeong.jakgwae",
        preset_id="",
        layer="L1",
        inputs={
            "year": year,
            "age": age,
            "태세간지": C.gz_name((year - 4) % 60),
            "태세수": taese_su,
            "중수": jung_su,
            "하수": ha_su,
            "month_gz": chart.month.name,
            "day_gz": chart.day.name,
            "음력": eumlyeok,
            "상괘": sang,
            "중괘": jung,
            "하괘": ha,
            "괘번호": gwae_no,
        },
        classical_source="토정비결 작괘법(선천수)",
    )

    return {
        "year": year,
        "age": age,
        "상괘": sang,
        "중괘": jung,
        "하괘": ha,
        "괘번호": gwae_no,
        "음력": eumlyeok,
        "태세수": taese_su,
        "중수": jung_su,
        "하수": ha_su,
        "trace": trace,
    }
