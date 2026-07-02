"""L1 합충형파해 (合沖刑破害) — 차트 4기둥 간 관계 분석.

천간: 합(合)·충(沖). 지지: 육합·삼합·반합·방합·육충·형(刑)·파(破)·해(害).
모두 결정론 룩업(constants 의 관계 테이블) — 정답 있음.
"""
from __future__ import annotations

from itertools import combinations

from engine import constants as C


def _stem_h(i: int) -> str:
    return C.CHEONGAN_HANGUL[i]


def _branch_h(i: int) -> str:
    return C.JIJI_HANGUL[i]


def analyze(chart) -> dict[str, list[dict]]:
    """차트의 천간/지지 관계 전부 탐지. {관계명: [{pos, 글자, 화기?}, ...]}."""
    stems = [(p.position, p.stem) for p in chart.pillars]
    branches = [(p.position, p.branch) for p in chart.pillars]
    res: dict[str, list[dict]] = {
        "천간합": [], "천간충": [], "육합": [], "삼합": [], "반합": [],
        "방합": [], "육충": [], "형": [], "파": [], "해": [],
    }

    # ── 천간 합·충 (pairwise) ──
    for (pa, sa), (pb, sb) in combinations(stems, 2):
        key = frozenset((sa, sb))
        if sa != sb and key in C.CHEONGAN_HAP:
            res["천간합"].append({
                "pos": [pa, pb], "글자": [_stem_h(sa), _stem_h(sb)],
                "화기": C.OHAENG_HANGUL[C.CHEONGAN_HAP[key]],
            })
        if key in C.CHEONGAN_CHUNG:
            res["천간충"].append({
                "pos": [pa, pb], "글자": [_stem_h(sa), _stem_h(sb)],
            })

    # ── 지지 pairwise: 육합/충/파/해/형 ──
    for (pa, ba), (pb, bb) in combinations(branches, 2):
        key = frozenset((ba, bb))
        if ba != bb and key in C.JIJI_YUKHAP:
            res["육합"].append({
                "pos": [pa, pb], "글자": [_branch_h(ba), _branch_h(bb)],
                "화기": C.OHAENG_HANGUL[C.JIJI_YUKHAP[key]],
            })
        if key in C.JIJI_CHUNG:
            res["육충"].append({"pos": [pa, pb], "글자": [_branch_h(ba), _branch_h(bb)]})
        if key in C.JIJI_PA:
            res["파"].append({"pos": [pa, pb], "글자": [_branch_h(ba), _branch_h(bb)]})
        if key in C.JIJI_HAE:
            res["해"].append({"pos": [pa, pb], "글자": [_branch_h(ba), _branch_h(bb)]})
        # 형: 상형/삼형 구성쌍
        if ba != bb and key in C.HYEONG_PAIRS:
            res["형"].append({"pos": [pa, pb], "글자": [_branch_h(ba), _branch_h(bb)],
                             "종류": "상형/삼형"})
        # 자형: 같은 지지가 두 기둥에 (辰午酉亥)
        if ba == bb and ba in C.HYEONG_JAHYEONG:
            res["형"].append({"pos": [pa, pb], "글자": [_branch_h(ba), _branch_h(bb)],
                             "종류": "자형"})

    # ── 지지 삼합/반합/방합 (그룹) ──
    present = {b for _, b in branches}
    for name, (members, elem, wangji) in C.JIJI_SAMHAP.items():
        ms = set(members)
        if ms <= present:
            res["삼합"].append({"국": name, "글자": [_branch_h(x) for x in members],
                               "화기": C.OHAENG_HANGUL[elem]})
        elif wangji in present:
            half = ms & present
            if len(half) == 2:  # 왕지 포함 2지 = 반합
                res["반합"].append({"국": name, "글자": [_branch_h(x) for x in sorted(half)],
                                   "화기": C.OHAENG_HANGUL[elem]})
    for season, (members, elem) in C.JIJI_BANGHAP.items():
        if set(members) <= present:
            res["방합"].append({"계절": season, "글자": [_branch_h(x) for x in members],
                               "화기": C.OHAENG_HANGUL[elem]})

    return {k: v for k, v in res.items() if v}
