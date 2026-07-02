"""L3 억부(抑扶) 용신 정책 — 신강이면 설기/극제, 신약이면 부조.

충실도 invariant (SPEC §3.2(b)):
  신강 → 용신 ∈ {식상, 재성, 관성},  신약 → 용신 ∈ {인성, 비겁}.
용신 오행은 후보 가족들 중 사주에 존재감이 큰 오행으로 결정(결정론).
"""
from __future__ import annotations

from engine import constants as C
from engine.interp_types import (YongsinResult, element_presence,
                                 family_element, relation)
from engine.provenance import Claim, Trace


def select(chart, scored, preset):
    dm_el = C.CHEONGAN_OHAENG[chart.day_master]
    counts = element_presence(chart)

    if scored.strength == "신강":
        fams, rule = ("관성", "식상", "재성"), "eokbu.strong.drain"
    elif scored.strength == "신약":
        fams, rule = ("인성", "비겁"), "eokbu.weak.support"
    else:  # 중화 — 가벼운 설기
        fams, rule = ("식상", "재성"), "eokbu.neutral.balance"

    # 후보 가족의 오행 중 존재감(분포) 최대를 용신으로 (동률 시 가족 우선순위)
    cand = sorted(((family_element(dm_el, f), f) for f in fams),
                  key=lambda ef: (-counts[ef[0]], fams.index(ef[1])))
    yong_el, family = cand[0]
    yong_name = C.OHAENG_HANGUL[yong_el]

    trace = Trace(
        rule_id=rule, preset_id=preset.preset_id, layer="L3",
        inputs={"strength": scored.strength, "ratio": round(scored.ratio, 3),
                "presence": dict(zip(C.OHAENG_HANGUL, counts)),
                "candidates": list(fams), "chosen_family": family},
        classical_source="적천수 / 자평진전 (억부용신)",
    )
    verb = "설기·극제" if scored.strength == "신강" else (
        "부조" if scored.strength == "신약" else "중화 조절")
    claim = Claim(
        claim=(f"{scored.strength}하므로 {family}({yong_name})으로 일간을 "
               f"{verb}하는 것이 용신이다."),
        trace=trace,
    )
    return YongsinResult(element=yong_el, element_name=yong_name, family=family,
                        policy="eokbu", strength=scored.strength,
                        trace=trace, claims=(claim,))
