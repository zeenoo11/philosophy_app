"""해석 레이어(L2/L3) 공용 타입 — 순환참조 방지를 위해 분리.

핵심: 오행 관계(십신 가족) 계산 + 결과 dataclass. 모든 결과는 trace 를 동반한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from engine import constants as C
from engine.provenance import Claim, Trace

# 오행 인덱스(목0 화1 토2 금3 수4) 기준, 일간 오행 대비 관계 → 십신 가족
FAMILIES = ("비겁", "식상", "재성", "관성", "인성")


def element_presence(chart) -> list[int]:
    """8글자(천간 + 지지 정기) 오행 분포 [목,화,토,금,수]."""
    counts = [0] * 5
    for p in chart.pillars:
        counts[C.CHEONGAN_OHAENG[p.stem]] += 1
        counts[C.JIJI_OHAENG[p.branch]] += 1
    return counts


def relation(dm_el: int, el: int) -> str:
    """일간 오행(dm_el) 대비 el 의 십신 가족."""
    return FAMILIES[(el - dm_el) % 5]


def family_element(dm_el: int, family: str) -> int:
    """일간 오행 대비 특정 가족의 오행 인덱스."""
    return (dm_el + FAMILIES.index(family)) % 5


@dataclass(frozen=True)
class StrengthResult:
    """L2 — 일간 강약."""
    strength: str            # 신강 | 신약 | 중화
    score: float             # 부조(비겁+인성) 가중합
    total: float             # 전체 가중합
    ratio: float             # score / total
    deukryeong: bool         # 득령(월령이 일간을 부조)
    detail: dict
    trace: Trace
    claims: tuple[Claim, ...] = ()


@dataclass(frozen=True)
class YongsinResult:
    """L3 — 용신(정책형)."""
    element: int             # 용신 오행 인덱스
    element_name: str
    family: str              # 용신의 십신 가족 (충실도 invariant 대상)
    policy: str              # eokbu | johu | byeongyak
    strength: str
    trace: Trace
    claims: tuple[Claim, ...] = ()


@dataclass(frozen=True)
class StructureResult:
    """L3 — 구조형(맹파 등, 용신 미사용)."""
    binju: dict              # 빈주(體=일주 主 / 賓=객신)
    jugong: dict             # 주공(主公)
    cheyong: dict            # 체용(體用)
    sang: str                # 상(象) 라벨
    trace: Trace
    claims: tuple[Claim, ...] = ()
