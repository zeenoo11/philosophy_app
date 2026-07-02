"""L3 병약(病藥) 용신 정책 — 사주의 '병'(과다 오행)을 제거하는 '약'을 용신으로.

충실도 invariant: 한 오행이 과다(병)일 때 그 오행을 극하는 오행이 용신(약)이다.
명확한 병이 없으면 None → 정책 체인의 다음으로.

⚠️ 간이형(과다 임계 기반). 정밀한 병약(기반·통관 포함)은 후속 과제.
"""
from __future__ import annotations

from engine import constants as C
from engine.interp_types import YongsinResult, element_presence, relation
from engine.provenance import Claim, Trace

_BYEONG_THRESHOLD = 4   # 8글자 중 한 오행이 4개 이상이면 '병'으로 간주


def select(chart, scored, preset):
    dm_el = C.CHEONGAN_OHAENG[chart.day_master]
    counts = element_presence(chart)
    byeong = max(range(5), key=lambda e: counts[e])
    if counts[byeong] < _BYEONG_THRESHOLD:
        return None  # 뚜렷한 병 없음

    yak_el = (byeong + 3) % 5   # 병을 극하는 오행 = 약
    yak_name = C.OHAENG_HANGUL[yak_el]
    family = relation(dm_el, yak_el)
    trace = Trace(
        rule_id="byeongyak.purge", preset_id=preset.preset_id, layer="L3",
        inputs={"byeong": C.OHAENG_HANGUL[byeong], "byeong_count": counts[byeong],
                "presence": dict(zip(C.OHAENG_HANGUL, counts))},
        classical_source="명리정종(병약설)",
    )
    claim = Claim(
        claim=(f"{C.OHAENG_HANGUL[byeong]} 과다({counts[byeong]}개)가 병이므로 "
               f"이를 극하는 {yak_name}({family})이(가) 약=용신이다."),
        trace=trace,
    )
    return YongsinResult(element=yak_el, element_name=yak_name, family=family,
                        policy="byeongyak", strength=scored.strength,
                        trace=trace, claims=(claim,))
