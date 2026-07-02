"""P4 — 차분 기대 (SPEC §3.2(c)). 갈려야 할 곳에서만 갈리는가.

  • 결정론 레이어(8글자)는 프리셋 무관 항상 합의.
  • 용신은 정책이 다르면 갈릴 수 있다 — 분기는 버그가 아니라 1급 기능(§0.2).
정확성(어느 용신이 맞나)은 검증하지 않는다.
"""
from __future__ import annotations

import pytest

from engine.interpret import interpret
from engine.pillars import BirthInput

pytestmark = pytest.mark.interpretation

_YONGSIN_PRESETS = ["jeongtong_eokbu", "johu_centered"]


def test_deterministic_always_agrees(sample_births):
    for birth in sample_births:
        r = interpret(birth, _YONGSIN_PRESETS)
        assert r["agreement"]["deterministic"] == "full", \
            f"{birth} 결정론 분기 — 같은 토글인데 8글자가 다름"


def test_yongsin_diverges_and_agrees_across_sample(sample_births):
    """표본 전체에서 용신이 갈리는 케이스와 합의하는 케이스가 모두 존재."""
    agrees = [interpret(b, _YONGSIN_PRESETS)["agreement"]["yongsin"] for b in sample_births]
    assert "diverged" in agrees, "용신 분기가 한 번도 안 일어남 (정책 분기 미작동)"
    assert "full" in agrees, "용신 합의 케이스가 없음"


def test_mangpa_diverges_in_engine_kind():
    """맹파는 엔진 종류 자체가 달라 용신형과 구조적으로 분기."""
    r = interpret(BirthInput(1984, 1, 20, 6, 0))
    engines = {pid: b["engine"] for pid, b in r["by_preset"].items()}
    assert engines["jeongtong_eokbu"] == "yongsin"
    assert engines["mangpa"] == "structure"
