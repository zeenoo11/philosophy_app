"""L1 결정론 — 대운(大運) 규칙 검증.

정답(실존 인물 대운)을 박지 않고 '규칙'만 검증한다:
  • 방향 규칙: 양남음녀 順行 / 음남양녀 逆行 (年干 음양 × 성별)
  • 간지 연속성: 연속 대운 gz60 차이가 방향에 맞게 ±1 (mod 60)
  • 시작 간지: 月柱 gz60 에서 한 칸(방향대로) 이동한 값
  • 나이 진행: 시작나이 + 10*k, start_age ∈ 1..12
  • 멱등성 (같은 입력 → 동일 출력), trace 존재/정합
"""
from __future__ import annotations

import pytest

from engine.pillars import BirthInput, compute_chart
from engine import constants as C
from engine.daeun import compute_daeun
from engine.provenance import Trace

pytestmark = pytest.mark.deterministic

# 표본 출생(월 중순 → 사주연도 = 양력연도): 年干 음양이 명확.
#   1984 갑(양년), 1985 을(음년)
_YANG_YEAR = BirthInput(1984, 6, 15, 12, 0)   # 甲子年 → 年干 양
_EUM_YEAR = BirthInput(1985, 6, 15, 12, 0)    # 乙丑年 → 年干 음


def _chart(birth: BirthInput):
    return compute_chart(birth)


# ─────────────────────────────────────────────────────────────────────────
# 방향 규칙: 양남 順 / 음남 逆 / 양녀 逆 / 음녀 順
# ─────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("birth,gender,expected_forward", [
    (_YANG_YEAR, "남", True),    # 양남 → 順行
    (_EUM_YEAR, "남", False),    # 음남 → 逆行
    (_YANG_YEAR, "여", False),   # 양녀 → 逆行
    (_EUM_YEAR, "여", True),     # 음녀 → 順行
])
def test_direction_rule(birth, gender, expected_forward):
    """양남음녀 順行, 음남양녀 逆行."""
    ch = _chart(birth)
    # 표본 가정 확인: 年干 음양이 의도대로인지
    yang = C.CHEONGAN_EUMYANG[ch.year.stem] == 0
    assert yang == (birth is _YANG_YEAR)
    res = compute_daeun(ch, gender)
    assert res.forward is expected_forward
    assert res.trace.rule_id == ("daeun.forward" if expected_forward else "daeun.backward")


# ─────────────────────────────────────────────────────────────────────────
# 간지 연속성 + 시작 간지
# ─────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("birth,gender", [
    (_YANG_YEAR, "남"), (_EUM_YEAR, "남"),
    (_YANG_YEAR, "여"), (_EUM_YEAR, "여"),
    (BirthInput(1990, 6, 15, 14, 30), "남"),
    (BirthInput(2003, 11, 7, 9, 0), "여"),
])
def test_gz_continuity(birth, gender):
    """연속 대운 gz60 차이가 방향에 맞게 ±1 (mod 60), 첫 대운은 月柱에서 한 칸."""
    ch = _chart(birth)
    res = compute_daeun(ch, gender, count=8)
    step = 1 if res.forward else -1

    # 첫 대운 = 月柱 gz60 + step (mod 60)
    assert res.pillars[0][1] == (ch.month.gz60 + step) % 60

    gzs = [gz for (_age, gz, _name) in res.pillars]
    for a, b in zip(gzs, gzs[1:]):
        assert (b - a) % 60 == step % 60


# ─────────────────────────────────────────────────────────────────────────
# 나이 진행 + start_age 범위
# ─────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("month", range(1, 13))
def test_age_progression_and_range(month):
    """start_age ∈ 1..12, 이후 대운 나이 = start_age + 10*k."""
    ch = _chart(BirthInput(1992, month, 11, 8, 0))
    res = compute_daeun(ch, "남", count=8)
    assert 1 <= res.start_age <= 12
    ages = [age for (age, _gz, _name) in res.pillars]
    assert ages[0] == res.start_age
    for k, age in enumerate(ages):
        assert age == res.start_age + 10 * k


# ─────────────────────────────────────────────────────────────────────────
# count 파라미터 / 이름 정합
# ─────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("count", [1, 5, 8, 12])
def test_count_and_names(count):
    ch = _chart(BirthInput(1990, 6, 15, 14, 30))
    res = compute_daeun(ch, "남", count=count)
    assert len(res.pillars) == count
    for _age, gz, name in res.pillars:
        assert 0 <= gz < 60
        assert name == C.gz_name(gz)


# ─────────────────────────────────────────────────────────────────────────
# 멱등성 (결정론) + trace
# ─────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("birth,gender", [
    (BirthInput(1990, 6, 15, 14, 30), "남"),
    (BirthInput(1985, 6, 15, 12, 0), "여"),
    (BirthInput(2014, 1, 3, 23, 30), "남"),
])
def test_idempotent(birth, gender):
    """같은 입력 → 완전히 동일한 출력."""
    a = compute_daeun(_chart(birth), gender)
    b = compute_daeun(_chart(birth), gender)
    assert a.forward == b.forward
    assert a.start_age == b.start_age
    assert a.pillars == b.pillars


def test_trace_present_and_consistent():
    ch = _chart(BirthInput(1990, 6, 15, 14, 30))
    res = compute_daeun(ch, "남")
    assert isinstance(res.trace, Trace)
    assert res.trace.layer == "L1"
    assert res.trace.rule_id in ("daeun.forward", "daeun.backward")
    assert res.trace.classical_source == "자평진전(대운)"
    # trace 입력이 결과와 정합
    assert res.trace.inputs["forward"] is res.forward
    assert res.trace.inputs["daeunsu"] == res.start_age
    assert res.trace.inputs["month_gz60"] == ch.month.gz60


# ─────────────────────────────────────────────────────────────────────────
# 입력 검증
# ─────────────────────────────────────────────────────────────────────────
def test_invalid_gender():
    ch = _chart(BirthInput(1990, 6, 15, 14, 30))
    with pytest.raises(ValueError):
        compute_daeun(ch, "male")
