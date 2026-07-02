"""음력 ↔ 양력 변환 (sxtwl). 엔진은 항상 양력(solar)으로 계산하므로, 음력 입력은
이 모듈로 양력으로 바꿔 BirthInput 에 넣는다. 윤달(leap)은 선택.
"""
from __future__ import annotations

import sxtwl


def lunar_to_solar(year: int, month: int, day: int, leap: bool = False) -> tuple[int, int, int]:
    """음력(year, month, day, 윤달?) → 양력 (year, month, day)."""
    d = sxtwl.fromLunar(year, month, day, leap)
    return d.getSolarYear(), d.getSolarMonth(), d.getSolarDay()


def solar_to_lunar(year: int, month: int, day: int) -> dict:
    """양력 → 음력 {year, month, day, leap}."""
    d = sxtwl.fromSolar(year, month, day)
    return {"year": d.getLunarYear(), "month": d.getLunarMonth(),
            "day": d.getLunarDay(), "leap": bool(d.isLunarLeap())}
