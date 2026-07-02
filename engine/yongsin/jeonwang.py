"""L3 전왕(專旺) 용신 정책 — 한 세력이 압도하면 억부 대신 그 세를 따른다(順勢).

충실도 invariant (이 정책 고유):
  • 종왕/종강: 비겁+인성(일간 세력)이 8글자 중 6 이상으로 압도 → 그 세를 용신으로
    삼는다(억부의 설기·극제를 쓰지 않음). 용신 = 더 많은 쪽 가족(동률 시 인성).
  • 종격(외격): 일간 외의 한 오행 X 가 5 이상으로 압도하고 위 조건 미해당 →
    일간을 버리고 그 X 의 세를 따른다(從). 용신 = relation(dm_el, X) 가족.
압도 세력이 없으면 None → 정책 체인의 다음(억부 등)으로.

⚠️ 간이형(분포 임계 기반). 정밀한 종격 판정(투출·뿌리·합화 등)은 후속 과제.
"""
from __future__ import annotations

from engine import constants as C
from engine.interp_types import (YongsinResult, element_presence,
                                 family_element, relation)
from engine.provenance import Claim, Trace

_SELF_THRESHOLD = 6     # 비겁+인성 합 (8글자 중) → 종왕/종강
_FOLLOW_THRESHOLD = 5   # 일간 외 단일 오행 → 종격(외격)


def select(chart, scored, preset):
    dm_el = C.CHEONGAN_OHAENG[chart.day_master]
    counts = element_presence(chart)

    bigeop_el = dm_el
    insung_el = family_element(dm_el, "인성")
    self_count = counts[bigeop_el] + counts[insung_el]

    presence = dict(zip(C.OHAENG_HANGUL, counts))

    # ── 종왕/종강: 일간 세력(비겁+인성)이 압도 ───────────────────────────
    if self_count >= _SELF_THRESHOLD:
        # 더 많은 쪽 가족 (비겁 우선, 동률이면 인성)
        if counts[bigeop_el] >= counts[insung_el]:
            yong_el, family, sub = bigeop_el, "비겁", "종왕(從旺)"
        else:
            yong_el, family, sub = insung_el, "인성", "종강(從強)"
        yong_name = C.OHAENG_HANGUL[yong_el]
        trace = Trace(
            rule_id="jeonwang.dominant_self", preset_id=preset.preset_id,
            layer="L3",
            inputs={"presence": presence, "self_count": self_count,
                    "bigeop": counts[bigeop_el], "insung": counts[insung_el],
                    "chosen_family": family, "subtype": sub},
            classical_source="적천수 / 자평진전 (전왕·종왕종강)",
        )
        claim = Claim(
            claim=(f"비겁·인성이 {self_count}개로 압도하니 {sub}으로 보아, "
                   f"억부 대신 그 세를 따라 {family}({yong_name})을(를) "
                   f"용신으로 삼는다(順勢)."),
            trace=trace,
        )
        return YongsinResult(element=yong_el, element_name=yong_name,
                             family=family, policy="jeonwang",
                             strength=scored.strength, trace=trace,
                             claims=(claim,))

    # ── 종격(외격): 일간 외 단일 오행이 압도 ─────────────────────────────
    follow = [e for e in range(5)
              if e != dm_el and counts[e] >= _FOLLOW_THRESHOLD]
    if follow:
        # 가장 강한 오행을 따른다 (동률 시 인덱스 우선 — 결정론)
        x = max(follow, key=lambda e: (counts[e], -e))
        family = relation(dm_el, x)
        yong_name = C.OHAENG_HANGUL[x]
        trace = Trace(
            rule_id="jeonwang.follow", preset_id=preset.preset_id, layer="L3",
            inputs={"presence": presence, "follow_element": yong_name,
                    "follow_count": counts[x], "chosen_family": family},
            classical_source="적천수 / 자평진전 (종격·외격)",
        )
        claim = Claim(
            claim=(f"일간 외 {yong_name}이(가) {counts[x]}개로 압도하니 "
                   f"일간을 버리고 그 세를 따라(從) {family}({yong_name})을(를) "
                   f"용신으로 삼는다."),
            trace=trace,
        )
        return YongsinResult(element=x, element_name=yong_name, family=family,
                             policy="jeonwang", strength=scored.strength,
                             trace=trace, claims=(claim,))

    return None  # 압도 세력 없음 → 전왕 미해당
