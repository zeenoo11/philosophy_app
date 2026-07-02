"""P0 — L1 골든 코퍼스 대조 (정답 존재 레이어).

동결된 fixtures/golden/cases.json (생성 시 sxtwl 전수 일치 검증됨)에 대해
엔진 출력이 정확히 일치하는지 — 회귀 고정. 추가로 교과서적 앵커도 명시 검증.
"""
from __future__ import annotations

import json
import pathlib

import pytest

from engine.pillars import BirthInput, DeterministicConfig, compute_chart
from engine.pillars import day_gz60
from engine import constants as C

_CASES = json.loads(
    (pathlib.Path(__file__).resolve().parents[2] / "fixtures" / "golden" / "cases.json")
    .read_text(encoding="utf-8")
)

pytestmark = pytest.mark.deterministic


def _chart_for(case: dict):
    inp, conf = case["input"], case["config"]
    cfg = DeterministicConfig(
        true_solar_time=conf["true_solar_time"], jasi_rule=conf["jasi_rule"])
    return compute_chart(
        BirthInput(inp["year"], inp["month"], inp["day"], inp["hour"], inp["minute"]),
        cfg,
    )


@pytest.mark.parametrize("case", _CASES, ids=[c["id"] for c in _CASES])
def test_golden_pillars(case):
    ch = _chart_for(case)
    exp = case["expected"]
    assert ch.year.gz60 == exp["year"]["gz60"], f"{case['id']} 년주 불일치"
    assert ch.month.gz60 == exp["month"]["gz60"], f"{case['id']} 월주 불일치"
    assert ch.day.gz60 == exp["day"]["gz60"], f"{case['id']} 일주 불일치"
    assert ch.hour.gz60 == exp["hour"]["gz60"], f"{case['id']} 시주 불일치"
    assert ch.eight_chars() == exp["eight_chars"]


def test_golden_corpus_nonempty():
    assert len(_CASES) >= 10, "골든 코퍼스는 최소 10케이스 이상이어야 함"


def test_textbook_anchor_2000_01_01():
    """교과서 앵커: 2000-01-01 의 일주는 戊午(60-index 54)."""
    assert day_gz60(2000, 1, 1) == 54
    assert C.gz_name(54) == "무오"
