"""궁합(宮合) — 두 사람 사주 합 결정론 모듈 (L1 합성).

자평(子平) 궁합의 통상 산식을 결정론적으로 점수화한다. 외부 '정답'을 박제하지
않고, 산식·범위만 고정한다. 각 항목은 0~100 부분점수를 내고, 최종점수는
가중평균(일간 0.35 · 일지 0.25 · 띠 0.2 · 오행보완 0.2)이다.

판정 입력은 두 차트의 결정론 글자(일간·년지·일지·오행분포)뿐이며,
모든 룩업은 engine.constants 의 테이블을 그대로 쓴다.
"""
from __future__ import annotations

from engine import constants as C
from engine.interp_types import element_presence
from engine.pillars import BirthInput, Chart, compute_chart
from engine.provenance import Trace


# ─────────────────────────────────────────────────────────────────────────
# 항목별 산출 (각 0~100)
# ─────────────────────────────────────────────────────────────────────────
def _day_master_relation(a_dm: int, b_dm: int) -> tuple[str, int]:
    """일간(日干) 관계 → (label, 부분점수)."""
    a_el = C.CHEONGAN_OHAENG[a_dm]
    b_el = C.CHEONGAN_OHAENG[b_dm]
    if frozenset({a_dm, b_dm}) in C.CHEONGAN_HAP:
        return "천간합", 95
    if C.saeng(a_el) == b_el or C.saeng(b_el) == a_el:   # 서로 생(生)
        return "상생", 85
    if a_el == b_el:                                       # 같은 오행 → 비화
        return "비화", 75
    if C.geuk(a_el) == b_el or C.geuk(b_el) == a_el:      # 서로 극(剋)
        return "상극", 45
    return "무관", 50


def _samhap_guk(branch: int) -> str | None:
    """지지가 속한 삼합국 이름(없으면 None)."""
    for guk, (members, _el, _wang) in C.JIJI_SAMHAP.items():
        if branch in members:
            return guk
    return None


def _tti_relation(a_br: int, b_br: int) -> tuple[str, int]:
    """띠(년지) 관계 → (label, 부분점수)."""
    pair = frozenset({a_br, b_br})
    if pair in C.JIJI_YUKHAP:
        return "육합", 85
    ga, gb = _samhap_guk(a_br), _samhap_guk(b_br)
    if ga is not None and ga == gb and a_br != b_br:     # 같은 삼합국
        return "삼합", 85
    if pair in C.JIJI_CHUNG:
        return "육충", 40
    if pair in C.HYEONG_PAIRS:
        return "형", 45
    return "무관", 60


def _ilji_relation(a_br: int, b_br: int) -> tuple[str, int]:
    """일지(배우자궁) 관계 → (label, 부분점수)."""
    pair = frozenset({a_br, b_br})
    if pair in C.JIJI_YUKHAP:
        return "육합", 90
    if pair in C.JIJI_CHUNG:
        return "육충", 35
    if pair in C.HYEONG_PAIRS:
        return "형", 45
    if a_br == b_br:
        return "같음", 70
    return "무관", 60


def _ohaeng_complement(pa: list[int], pb: list[int]) -> tuple[str, int, list[str]]:
    """오행 보완 → (label, 부분점수, 보완오행한글목록).

    한쪽이 부족(<=1)한 오행을 상대가 풍부(>=3)하게 가지면 보완 1쌍.
    """
    pairs: list[str] = []
    for el in range(5):
        a_lacks = pa[el] <= 1 and pb[el] >= 3
        b_lacks = pb[el] <= 1 and pa[el] >= 3
        if a_lacks or b_lacks:
            pairs.append(C.OHAENG_HANGUL[el])
    n = len(pairs)
    if n >= 2:
        score = 88
    elif n == 1:
        score = 70
    else:
        score = 50
    label = "상호보완" if n >= 1 else "보완없음"
    return label, score, pairs


# ─────────────────────────────────────────────────────────────────────────
# 합성
# ─────────────────────────────────────────────────────────────────────────
def _grade(total: int) -> str:
    if total >= 80:
        return "천생연분"
    if total >= 65:
        return "좋은 궁합"
    if total >= 50:
        return "무난"
    return "노력 필요"


def gunghap(birth_a: BirthInput, birth_b: BirthInput) -> dict:
    """두 사람의 사주 궁합 점수·등급·근거를 결정론으로 산출한다."""
    return gunghap_charts(compute_chart(birth_a), compute_chart(birth_b))


def gunghap_charts(ca: Chart, cb: Chart) -> dict:
    """이미 계산된 두 차트로 궁합을 산출한다 — ``gunghap`` 의 코어.

    입력이 ``BirthInput`` 대신 ``Chart`` 라는 점만 다르다. 1:N 매칭
    (engine.matching)에서 한쪽(나) 차트를 1회만 계산해 재사용하기 위함.
    """
    a_dm, b_dm = ca.day_master, cb.day_master

    # 1) 일간 관계
    dm_label, dm_score = _day_master_relation(a_dm, b_dm)
    # 2) 띠(년지) 관계
    tti_label, tti_score = _tti_relation(ca.year.branch, cb.year.branch)
    # 3) 일지(배우자궁) 관계
    ilji_label, ilji_score = _ilji_relation(ca.day.branch, cb.day.branch)
    # 4) 오행 보완
    pa, pb = element_presence(ca), element_presence(cb)
    oh_label, oh_score, oh_pairs = _ohaeng_complement(pa, pb)

    total = round(dm_score * 0.35 + ilji_score * 0.25
                  + tti_score * 0.2 + oh_score * 0.2)
    grade = _grade(total)

    # 근거 (한 줄 설명들)
    geungeo = [
        f"일간 {C.CHEONGAN_HANGUL[a_dm]}·{C.CHEONGAN_HANGUL[b_dm]} → {dm_label}({dm_score})",
        f"띠 {C.JIJI_HANGUL[ca.year.branch]}·{C.JIJI_HANGUL[cb.year.branch]} → {tti_label}({tti_score})",
        f"일지 {C.JIJI_HANGUL[ca.day.branch]}·{C.JIJI_HANGUL[cb.day.branch]} → {ilji_label}({ilji_score})",
    ]
    if oh_pairs:
        geungeo.append(f"오행보완 {'·'.join(oh_pairs)} → {oh_label}({oh_score})")
    else:
        geungeo.append(f"오행보완 없음 → {oh_label}({oh_score})")
    geungeo.append(f"총점 {total} → {grade}")

    trace = Trace(
        rule_id="gunghap.compose",
        preset_id="gunghap",
        layer="L1",
        inputs={
            "일간": dm_score,
            "일지": ilji_score,
            "띠": tti_score,
            "오행보완": oh_score,
        },
        classical_source="자평 궁합(일간·일지·삼합·오행보완)",
    )

    return {
        "a": {"eight_chars": ca.eight_chars(), "일간": C.CHEONGAN_HANGUL[a_dm]},
        "b": {"eight_chars": cb.eight_chars(), "일간": C.CHEONGAN_HANGUL[b_dm]},
        "일간관계": {"label": dm_label, "점수": dm_score},
        "띠관계": {"label": tti_label, "점수": tti_score},
        "일지관계": {"label": ilji_label, "점수": ilji_score},
        "오행보완": {"label": oh_label, "점수": oh_score, "보완오행": oh_pairs},
        "총점": int(total),
        "등급": grade,
        "근거": geungeo,
        "trace": trace,
    }
