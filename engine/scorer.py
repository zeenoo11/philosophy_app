"""L2 스코어링 (strength-scorer) — 일간 강약(신강/신약).

규칙은 있으나 가중치는 프리셋(interpretation.sinkang_weights). 검증 목표는
'정확성'이 아니라 규칙 준수 + 단조성 invariant (SPEC §3.0, §3.2): 부조(비겁·인성)
세력이 늘면 강약 점수가 단조 증가해야 한다.

원리(통근 반영):
  • 천간(년월시): 비겁·인성이면 가중치만큼 부조.
  • 지지(년월일시): 지장간(여기·중기·정기)을 일수 비중으로 보아, 비겁·인성에
    해당하는 지장간 일수 비율만큼 부조(= 통근). 월지에 woljji, 일지에 ilji,
    나머지에 others 가중(프리셋).
강약 밴드(신강/중화/신약)는 결정론 상수. 임계 자체는 유파 파라미터다(정답 아님).
"""
from __future__ import annotations

from typing import TYPE_CHECKING

from engine import constants as C
from engine.interp_types import StrengthResult, relation
from engine.provenance import Claim, Trace

if TYPE_CHECKING:
    from engine.pillars import Chart

_DEFAULT_WEIGHTS = {"woljji": 3.0, "ilji": 1.5, "others": 1.0}
_SUPPORT = {"비겁", "인성"}            # 일간을 돕는 가족
# 강약 밴드 임계 — ⚠️ 고전 원전에 수치 출전이 없는 휴리스틱 상수다(통근비율을 3등분
# 하는 실용값). 0.50/0.35 근처 경계에서는 출생시각 1~2분·진태양시 보정만으로 신강↔
# 중화↔신약이 뒤집혀 용신 가족이 바뀔 수 있다 → 경계 근접도를 trace.inputs["bands"]로
# 노출하고 리포트가 '경계 근접'을 안내한다(감사 결함 ④, docs/schools.md §6 참조).
_STRONG_BAND, _WEAK_BAND = 0.50, 0.35


def _branch_support_fraction(dm_el: int, branch: int, theory: str) -> float:
    """지지 지장간 중 비겁·인성에 해당하는 일수 비율 (통근 정도 0~1)."""
    table = C.WORYULBUNYA_THEORIES[theory][branch]
    total = sum(days for _s, days, _r in table)
    support = sum(days for s, days, _r in table
                  if relation(dm_el, C.CHEONGAN_OHAENG[s]) in _SUPPORT)
    return support / total if total else 0.0


def score_strength(chart: Chart, weights: dict | None = None,
                   preset_id: str = "") -> "StrengthResult":
    w = {**_DEFAULT_WEIGHTS, **(weights or {})}
    theory = chart.config.woryulbunya_theory
    dm_el = C.CHEONGAN_OHAENG[chart.day_master]

    score = total = 0.0
    breakdown = {}

    # 천간 (일간 제외)
    for label, stem in (("년간", chart.year.stem), ("월간", chart.month.stem),
                        ("시간", chart.hour.stem)):
        el = C.CHEONGAN_OHAENG[stem]
        fam = relation(dm_el, el)
        sup = w["others"] if fam in _SUPPORT else 0.0
        score += sup
        total += w["others"]
        breakdown[label] = {"오행": C.OHAENG_HANGUL[el], "가족": fam,
                            "부조가중": round(sup, 2)}

    # 지지 (통근: 지장간 일수 비율)
    deukryeong = False
    for label, branch, wkey in (("년지", chart.year.branch, "others"),
                                ("월지", chart.month.branch, "woljji"),
                                ("일지", chart.day.branch, "ilji"),
                                ("시지", chart.hour.branch, "others")):
        frac = _branch_support_fraction(dm_el, branch, theory)
        weight = w[wkey]
        score += weight * frac
        total += weight
        if label == "월지":
            deukryeong = frac >= 0.5
        breakdown[label] = {"지지": C.JIJI_HANGUL[branch],
                            "통근비율": round(frac, 2), "부조가중": round(weight * frac, 2)}

    ratio = score / total if total else 0.0
    if ratio >= _STRONG_BAND:
        strength = "신강"
    elif ratio <= _WEAK_BAND:
        strength = "신약"
    else:
        strength = "중화"

    trace = Trace(
        rule_id=f"scorer.strength.{strength}", preset_id=preset_id, layer="L2",
        inputs={"ratio": round(ratio, 3), "score": round(score, 2),
                "total": round(total, 2), "deukryeong": deukryeong,
                "bands": [_WEAK_BAND, _STRONG_BAND], "weights": w},
        classical_source="자평진전(왕상휴수사·통근) / 적천수",
    )
    dm_name = C.CHEONGAN_HANGUL[chart.day_master]
    claim = Claim(
        claim=(f"일간 {dm_name}({C.OHAENG_HANGUL[dm_el]})은(는) 통근·부조 비율 "
               f"{ratio:.2f}로 {strength}"
               f"{' (득령)' if deukryeong else ' (실령)'}."),
        trace=trace,
    )
    return StrengthResult(strength=strength, score=score, total=total, ratio=ratio,
                          deukryeong=deukryeong, detail=breakdown,
                          trace=trace, claims=(claim,))
