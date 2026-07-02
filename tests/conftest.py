"""공용 pytest 픽스처."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from engine.pillars import BirthInput

GOLDEN_PATH = Path(__file__).resolve().parent.parent / "fixtures" / "golden" / "cases.json"


@pytest.fixture(scope="session")
def golden_cases() -> list[dict]:
    """동결된 골든 코퍼스 (fixtures/golden/cases.json)."""
    return json.loads(GOLDEN_PATH.read_text(encoding="utf-8"))


@pytest.fixture(scope="session")
def sample_births() -> list[BirthInput]:
    """해석 레이어 검증용 표본 — 계절·연대 분산 (36건)."""
    out = []
    for year in (1955, 1972, 1988, 1995, 2003, 2014):
        for month in (1, 3, 5, 7, 9, 11):
            out.append(BirthInput(year, month, 15, 10, 0))
    return out
