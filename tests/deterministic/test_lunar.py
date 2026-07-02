"""음력↔양력 변환 (sxtwl) — 결정론. 알려진 값 + 왕복."""
from __future__ import annotations

import pytest

from engine.lunar import lunar_to_solar, solar_to_lunar

pytestmark = pytest.mark.deterministic


def test_known_conversion():
    # 음력 1998-09-23 = 양력 1998-11-11 (사용자 예시)
    assert lunar_to_solar(1998, 9, 23) == (1998, 11, 11)
    lun = solar_to_lunar(1998, 11, 11)
    assert (lun["year"], lun["month"], lun["day"], lun["leap"]) == (1998, 9, 23, False)


@pytest.mark.parametrize("y,m,d", [(2000, 1, 1), (1990, 6, 15), (2024, 2, 4), (1972, 8, 8)])
def test_roundtrip(y, m, d):
    lun = solar_to_lunar(y, m, d)
    assert lunar_to_solar(lun["year"], lun["month"], lun["day"], lun["leap"]) == (y, m, d)
