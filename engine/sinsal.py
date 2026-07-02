"""L1 신살 (神煞) — 차트 기준 상징성(星) 산출. 결정론 룩업.

산출 = 결정론(어떤 신살이 어디에 붙는가). 그 신살을 해석에 '쓸지'(use_sinsal)는
프리셋의 해석 정책(L3) 소관이며 이 모듈은 관여하지 않는다.
"""
from __future__ import annotations

from engine import constants as C


def analyze(chart) -> dict:
    """차트의 신살 탐지.

    반환:
      일간기준: 천을귀인/양인/문창 (붙은 위치 목록)
      공망: 일주 기준 공망 지지 및 해당 위치
      십이신살: 년지/일지 기준 각 기둥의 신살 이름
    """
    dm = chart.day_master
    pillars = chart.pillars
    year_branch = chart.year.branch
    day_branch = chart.day.branch

    # ── 일간 기준 귀인/살 ──
    gwiin_set = set(C.CHEONEUL_GWIIN[dm])
    cheoneul = [p.position for p in pillars if p.branch in gwiin_set]

    yangin_branch = C.YANGIN.get(dm)
    yangin = ([p.position for p in pillars if p.branch == yangin_branch]
              if yangin_branch is not None else [])

    munchang_branch = C.MUNCHANG[dm]
    munchang = [p.position for p in pillars if p.branch == munchang_branch]

    # ── 공망 (일주 순중 공망) ──
    gm = C.gongmang(chart.day.gz60)
    gongmang_branches = [C.JIJI_HANGUL[b] for b in gm]
    gongmang_pos = [p.position for p in pillars
                    if p.branch in gm and p.position != "일"]

    # ── 십이신살 (년지/일지 기준) ──
    sibi_by_year = {p.position: C.sibi_sinsal_at(year_branch, p.branch) for p in pillars}
    sibi_by_day = {p.position: C.sibi_sinsal_at(day_branch, p.branch) for p in pillars}

    out = {
        "천을귀인": cheoneul,
        "양인": yangin,
        "문창귀인": munchang,
        "공망_지지": gongmang_branches,
        "공망_위치": gongmang_pos,
        "십이신살_년지기준": sibi_by_year,
        "십이신살_일지기준": sibi_by_day,
    }
    # 빈 목록 제거(귀인/살 류만; 십이신살 맵은 항상 유지)
    return {k: v for k, v in out.items()
            if v or k.startswith("십이신살") or k == "공망_지지"}
