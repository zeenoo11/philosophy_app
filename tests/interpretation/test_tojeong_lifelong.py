"""토정비결 작괘 + 평생운(생애단계·육친) — 구조/산식/멱등성 검증.

외부 정답(특정 괘번호가 '정답') 박제 금지. 검증 목표:
  • 작괘: 상괘 1~8, 중괘 1~6, 하괘 1~3, 괘번호 3자리, 음력 month_days∈{29,30}, 멱등.
  • 선천수 합: 태세수 == 천간선천수[(year-4)%10] + 지지선천수[(year-4)%12].
  • life_stages: 세 단계 키 존재 + 대운 분류 합 == 전체 대운 수.
  • yukchin: 형제/자식/부부/직업 키 + 각 facts/hint.
"""
from __future__ import annotations

import pytest

from engine.daeun import compute_daeun
from engine.lifelong import life_stages, yukchin
from engine.pillars import BirthInput, compute_chart
from engine.tojeong import (
    SEONCHEONSU_CHEONGAN,
    SEONCHEONSU_JIJI,
    tojeong_gwae,
)

pytestmark = pytest.mark.interpretation

_BIRTH = BirthInput(1998, 11, 11, 22, 0)
_YEAR = 2026

# 분산 표본 (계절·연대)
_BIRTHS = [
    BirthInput(1998, 11, 11, 22, 0),
    BirthInput(1990, 6, 15, 14, 30),
    BirthInput(1972, 1, 5, 23, 10),
    BirthInput(2003, 11, 20, 6, 45),
]


# ─────────────────────────────────────────────────────────────────────────
# 토정비결 작괘
# ─────────────────────────────────────────────────────────────────────────
def test_tojeong_gwae_ranges():
    """상괘 1~8, 중괘 1~6, 하괘 1~3, 괘번호 3자리, month_days∈{29,30}."""
    g = tojeong_gwae(_BIRTH, _YEAR)
    assert 1 <= g["상괘"] <= 8
    assert 1 <= g["중괘"] <= 6
    assert 1 <= g["하괘"] <= 3
    assert 100 <= g["괘번호"] <= 999
    assert g["괘번호"] == g["상괘"] * 100 + g["중괘"] * 10 + g["하괘"]
    assert g["음력"]["month_days"] in (29, 30)
    assert g["age"] == _YEAR - _BIRTH.year + 1


def test_tojeong_gwae_ranges_sample():
    for b in _BIRTHS:
        for yr in (2025, 2026):
            g = tojeong_gwae(b, yr)
            assert 1 <= g["상괘"] <= 8
            assert 1 <= g["중괘"] <= 6
            assert 1 <= g["하괘"] <= 3
            assert 100 <= g["괘번호"] <= 999
            assert g["음력"]["month_days"] in (29, 30)


def test_taese_su_formula():
    """선천수 합 검증: 태세수 == 천간선천수[(year-4)%10] + 지지선천수[(year-4)%12]."""
    g = tojeong_gwae(_BIRTH, _YEAR)
    expected = (SEONCHEONSU_CHEONGAN[(_YEAR - 4) % 10]
                + SEONCHEONSU_JIJI[(_YEAR - 4) % 12])
    assert g["태세수"] == expected


def test_jung_ha_su_grounded_in_chart():
    """중수/하수 = 사주 月柱/日柱 선천수 합."""
    chart = compute_chart(_BIRTH)
    g = tojeong_gwae(_BIRTH, _YEAR)
    assert g["중수"] == (SEONCHEONSU_CHEONGAN[chart.month.stem]
                        + SEONCHEONSU_JIJI[chart.month.branch])
    assert g["하수"] == (SEONCHEONSU_CHEONGAN[chart.day.stem]
                        + SEONCHEONSU_JIJI[chart.day.branch])


def test_tojeong_gwae_idempotent():
    a = tojeong_gwae(_BIRTH, _YEAR)
    b = tojeong_gwae(_BIRTH, _YEAR)
    # trace 객체 동일성 대신 핵심 산출값 비교
    for k in ("상괘", "중괘", "하괘", "괘번호", "태세수", "중수", "하수", "age"):
        assert a[k] == b[k]
    assert a["음력"] == b["음력"]


def test_tojeong_has_trace():
    g = tojeong_gwae(_BIRTH, _YEAR)
    assert g["trace"].rule_id == "tojeong.jakgwae"
    assert g["trace"].layer == "L1"


# ─────────────────────────────────────────────────────────────────────────
# 생애 단계
# ─────────────────────────────────────────────────────────────────────────
def _daeun_dict(chart, gender="남", count=8):
    dr = compute_daeun(chart, gender, count=count)
    return {
        "forward": dr.forward,
        "start_age": dr.start_age,
        "pillars": [{"age": a, "gz60": g, "name": n} for (a, g, n) in dr.pillars],
    }


def test_life_stages_keys_and_partition():
    """세 단계 키 존재 + 분류 합 == 전체 대운 수."""
    for b in _BIRTHS:
        chart = compute_chart(b)
        daeun = _daeun_dict(chart, "남", count=8)
        ls = life_stages(chart, daeun)
        assert set(ls.keys()) == {"초년", "중년", "말년"}
        total = sum(len(ls[k]["대운"]) for k in ls)
        assert total == len(daeun["pillars"])
        # 주요십신 길이 == 대운 길이
        for k in ls:
            assert len(ls[k]["주요십신"]) == len(ls[k]["대운"])


def test_life_stages_age_buckets():
    """각 단계의 나이가 경계 규칙(초년<29, 29<=중년<59, 말년>=59)을 지킨다."""
    chart = compute_chart(_BIRTH)
    daeun = _daeun_dict(chart, "여", count=10)
    ls = life_stages(chart, daeun)
    for item in ls["초년"]["대운"]:
        assert item["나이"] < 29
    for item in ls["중년"]["대운"]:
        assert 29 <= item["나이"] < 59
    for item in ls["말년"]["대운"]:
        assert item["나이"] >= 59


def test_life_stages_empty_daeun():
    chart = compute_chart(_BIRTH)
    ls = life_stages(chart, {"pillars": []})
    assert set(ls.keys()) == {"초년", "중년", "말년"}
    assert sum(len(ls[k]["대운"]) for k in ls) == 0


# ─────────────────────────────────────────────────────────────────────────
# 육친
# ─────────────────────────────────────────────────────────────────────────
def test_yukchin_keys_facts_hint():
    for b in _BIRTHS:
        chart = compute_chart(b)
        for gender in (None, "남", "여"):
            yc = yukchin(chart, gender)
            assert set(yc.keys()) == {"형제", "자식", "부부", "직업"}
            for key, block in yc.items():
                assert "facts" in block and isinstance(block["facts"], dict)
                assert "hint" in block and isinstance(block["hint"], str)
                assert block["hint"].strip()


def test_yukchin_gender_filters():
    """남=자식 관성/부부 재성, 여=자식 식상/부부 관성, None=둘 다."""
    chart = compute_chart(_BIRTH)
    male = yukchin(chart, "남")
    female = yukchin(chart, "여")
    none = yukchin(chart, None)
    assert male["자식"]["facts"]["자식성_가족"] == ["관성"]
    assert male["부부"]["facts"]["배우자성_가족"] == ["재성"]
    assert female["자식"]["facts"]["자식성_가족"] == ["식상"]
    assert female["부부"]["facts"]["배우자성_가족"] == ["관성"]
    assert set(none["자식"]["facts"]["자식성_가족"]) == {"식상", "관성"}
    assert set(none["부부"]["facts"]["배우자성_가족"]) == {"재성", "관성"}


def test_yukchin_jigeop_bowan_job_present():
    """직업 facts 의 부족_오행/보완_직업군이 채워진다."""
    chart = compute_chart(_BIRTH)
    facts = yukchin(chart)["직업"]["facts"]
    assert facts["부족_오행"] in ("목", "화", "토", "금", "수")
    assert isinstance(facts["보완_직업군"], list) and facts["보완_직업군"]


def test_yukchin_idempotent():
    chart = compute_chart(_BIRTH)
    assert yukchin(chart, "남") == yukchin(chart, "남")
    assert yukchin(chart, None) == yukchin(chart, None)
