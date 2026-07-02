"""출처추적(provenance) 계약 (SPEC §2.2).

모든 해석 문장(L3/L4 출력)은 trace 를 들고 다녀야 한다. trace 없는 문장은
출력 금지(SPEC §0.3, §3.2(d) CI 게이트). 이 계약 타입은 L1 에서 쓰이지 않지만
해석 레이어의 1급 인터페이스이므로 결정론 코어와 함께 고정해 둔다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class Trace:
    """해석 문장의 출처 메타데이터."""
    rule_id: str                 # 예: "eokbu.weak.support"
    preset_id: str               # 어떤 프리셋(유파)에서 나왔는가
    layer: str                   # "L2" | "L3" | "L4"
    inputs: dict[str, Any] = field(default_factory=dict)   # 판정 입력값
    classical_source: str = ""   # 고전 근거 (예: "적천수 / 서락오 주석")


@dataclass(frozen=True)
class Claim:
    """trace 를 동반한 단일 해석 주장."""
    claim: str
    trace: Trace
