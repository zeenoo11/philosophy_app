"""L3 통관(通關) 용신 정책 — 극(剋) 관계의 두 세력이 모두 강해 싸우면,
둘을 이어주는(生) 오행이 용신.

충실도 invariant (이 정책 고유):
  • 서로 극하는 두 오행 X(剋)Y 가 모두 강하면(각 2 이상) 전투(交戰)가 일어난다.
  • 이때 X 를 설하고 Y 를 생하는 중간 오행 Z = (X+1)%5 (X生Z, Z生Y) 가 통관신
    이 되어 싸움을 화해시킨다 → 용신 = Z.
싸우는 두 세력이 없으면 None → 정책 체인의 다음(억부 등)으로.

⚠️ 간이형(분포 임계 기반). 통관신의 투출·뿌리 등 정밀 판정은 후속 과제.
"""
from __future__ import annotations

from engine import constants as C
from engine.interp_types import YongsinResult, element_presence, relation
from engine.provenance import Claim, Trace

_FIGHT_THRESHOLD = 2   # 한 오행이 이 이상이면 '강한 세력'으로 간주


def select(chart, scored, preset):
    dm_el = C.CHEONGAN_OHAENG[chart.day_master]
    counts = element_presence(chart)

    # 극(剋) 쌍 X→Y (Y=(X+2)%5) 중 둘 다 강한 것들 → 합이 최대인 쌍 선택
    fights = []
    for x in range(5):
        y = C.geuk(x)                       # (x + 2) % 5
        if counts[x] >= _FIGHT_THRESHOLD and counts[y] >= _FIGHT_THRESHOLD:
            fights.append((counts[x] + counts[y], x, y))
    if not fights:
        return None  # 싸우는 두 세력 없음 → 통관 미해당

    # 합 최대 (동률 시 X 인덱스 우선 — 결정론)
    _total, x, y = max(fights, key=lambda t: (t[0], -t[1]))
    z = C.saeng(x)                          # (x + 1) % 5 — X生Z, Z生Y
    yong_name = C.OHAENG_HANGUL[z]
    family = relation(dm_el, z)

    trace = Trace(
        rule_id="tongwan.bridge", preset_id=preset.preset_id, layer="L3",
        inputs={"presence": dict(zip(C.OHAENG_HANGUL, counts)),
                "fight": f"{C.OHAENG_HANGUL[x]}剋{C.OHAENG_HANGUL[y]}",
                "fight_counts": [counts[x], counts[y]],
                "bridge": yong_name, "chosen_family": family},
        classical_source="적천수 / 자평진전 (통관용신)",
    )
    claim = Claim(
        claim=(f"{C.OHAENG_HANGUL[x]}({counts[x]})과(와) "
               f"{C.OHAENG_HANGUL[y]}({counts[y]})이(가) 극(剋)으로 교전하니, "
               f"둘을 이어 생(生)하는 {yong_name}({family})을(를) 통관 용신으로 "
               f"삼아 싸움을 화해시킨다."),
        trace=trace,
    )
    return YongsinResult(element=z, element_name=yong_name, family=family,
                         policy="tongwan", strength=scored.strength,
                         trace=trace, claims=(claim,))
