"""L3 조후(調候) 용신 정책 — 한난조습(寒暖燥濕) 균형 우선 (궁통보감 계열).

충실도 invariant (이 정책 고유):
  겨울(亥子丑) 출생 → 火(난방) 용신,  여름(巳午未) 출생 → 水(조후) 용신.
  戌(늦가을, 건조·한기 시작)은 겨울에 준해 火.  辰(늦봄 습)·봄(寅卯)·가을(申酉)은
  환절기/온화로 조후가 결정하지 않고 None → 정책 체인의 다음(억부 등)으로.

정밀화(한난조습 반영, 분기 성질 보존):
  용신 오행(火/水)은 계절 한난으로 결정되며 사주 내 분포와 무관하게 고정한다
  (← 억부와 갈리는 충실도 지점). 다만 용신 오행이 사주에 부재(presence==0)하면
  조후가 시급함을, 존재하면 보강 수준임을 claim 으로 구분한다.

⚠️ 본격 궁통보감 일간×월령 정밀표는 후속 과제. 월지 한난 분류는 johu_table 로 분리.
"""
from __future__ import annotations

from engine import constants as C
from engine.interp_types import YongsinResult, element_presence, relation
from engine.provenance import Claim, Trace
from engine.yongsin.johu_table import JOHU_TABLE

_HWA, _SU = 1, 4  # 火, 水


def select(chart, scored, preset):
    mb = chart.month.branch
    climate, yong_el, rule, season = JOHU_TABLE[mb]

    if yong_el is None:          # 환절기/온화 → 조후 미결정
        return None

    dm_el = C.CHEONGAN_OHAENG[chart.day_master]
    counts = element_presence(chart)
    yong_name = C.OHAENG_HANGUL[yong_el]
    family = relation(dm_el, yong_el)

    present = counts[yong_el] > 0
    # 조후 용신 오행의 부재 여부로 시급/보강 구분 (용신 선택 자체는 불변).
    urgency = "보강" if present else "시급"
    if climate == "한":
        deficit = "한기가 깊어 火로 데우는 것이"   # 寒 → 火
    else:
        deficit = "열기·건조가 심해 水로 식히는 것이"  # 暖燥 → 水

    trace = Trace(
        rule_id=rule, preset_id=preset.preset_id, layer="L3",
        inputs={
            "month_branch": C.JIJI_HANGUL[mb],
            "season": season,
            "한난": climate,
            "day_master": C.CHEONGAN_HANGUL[chart.day_master],
            "火수": counts[_HWA],
            "水수": counts[_SU],
            "용신부재": not present,
            "조후강도": urgency,
        },
        classical_source="궁통보감(欄江網) 조후용신",
    )
    claim = Claim(
        claim=(f"{season}({C.JIJI_HANGUL[mb]}월) 출생이라 {deficit} 조후의 "
               f"핵심이다. 사주에 {yong_name}이(가) "
               f"{'없어 조후가 시급' if not present else '있어 조후 보강'}하므로 "
               f"{yong_name}({family})을(를) 용신으로 삼아 한난을 조절한다."),
        trace=trace,
    )
    return YongsinResult(element=yong_el, element_name=yong_name, family=family,
                        policy="johu", strength=scored.strength,
                        trace=trace, claims=(claim,))
