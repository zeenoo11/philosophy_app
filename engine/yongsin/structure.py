"""L3 구조형 엔진 (맹파 등) — 용신을 우회하고 주공/상/빈주/체용으로 국을 읽음.

대조군: '하나의 정답'이 아니라 '유파별 분기'를 드러내는 1급 기능(SPEC §0.2).
용신/기신 체계를 쓰지 않으므로 억부/조후의 invariant 대상이 아니다.

⚠️ 간이형. 단건업 맹파의 정밀한 주공·체용 판정(궁위·자합 등)은 후속 과제.
"""
from __future__ import annotations

from engine import constants as C
from engine.interp_types import (StructureResult, element_presence, relation)
from engine.provenance import Claim, Trace


def analyze_structure(chart, preset):
    dm_el = C.CHEONGAN_OHAENG[chart.day_master]
    counts = element_presence(chart)

    # 빈주(賓主): 일주=체(主), 년·월·시=빈(賓)
    binju = {
        "체(主)": chart.day.name,
        "빈(賓)": [chart.year.name, chart.month.name, chart.hour.name],
    }
    # 주공(主公): 십신 가족별 세력 합산 후 최강 가족
    fam_strength: dict[str, int] = {}
    for e in range(5):
        fam_strength[relation(dm_el, e)] = fam_strength.get(relation(dm_el, e), 0) + counts[e]
    jugong_fam = max(fam_strength, key=fam_strength.get)
    jugong = {"가족": jugong_fam, "세력": fam_strength[jugong_fam]}

    # 체용(體用): 체=일간 오행, 용=일간 제외 최강 오행
    others = [(counts[e], e) for e in range(5) if e != dm_el]
    yong_el = max(others)[1]
    cheyong = {"체": C.OHAENG_HANGUL[dm_el], "용": C.OHAENG_HANGUL[yong_el]}

    # 상(象): 지배적 흐름 라벨 (간이)
    s = fam_strength
    if s.get("식상", 0) >= 2 and s.get("재성", 0) >= 2:
        sang = "식상생재(食傷生財)"
    elif s.get("재성", 0) >= 2 and s.get("관성", 0) >= 2:
        sang = "재생관(財生官)"
    elif s.get("관성", 0) >= 2 and s.get("인성", 0) >= 2:
        sang = "관인상생(官印相生)"
    elif s.get("인성", 0) >= 2 and s.get("비겁", 0) >= 2:
        sang = "인비(印比) 신왕"
    else:
        sang = f"{jugong_fam} 중심"

    trace = Trace(
        rule_id="structure.mangpa.basic", preset_id=preset.preset_id, layer="L3",
        inputs={"jugong": jugong_fam, "cheyong": cheyong,
                "presence": dict(zip(C.OHAENG_HANGUL, counts))},
        classical_source="단건업 맹파명리(주공·체용)",
    )
    claim = Claim(
        claim=(f"체는 일주 {chart.day.name}, 주공은 {jugong_fam}이며 "
               f"상(象)은 {sang}으로 본다(용신 미사용)."),
        trace=trace,
    )
    return StructureResult(binju=binju, jugong=jugong, cheyong=cheyong, sang=sang,
                          trace=trace, claims=(claim,))
