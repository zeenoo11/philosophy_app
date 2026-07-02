"""평생운(平生運) — 생애 단계(초년/중년/말년) + 육친(六親) facts.

순수 결정론: 사주 차트(+대운/성별) → 사람이 읽을 라벨/근거(facts). LLM 없음,
외부 정답 박제 없음. 각 항목 = {"facts": {...}, "hint": "평이한 한 줄"}.

  • life_stages : 대운을 생애 3단계(초년<29, 중년 29~58, 말년 59+)로 분류하고
                  각 단계의 주요 십신을 모은다.
  • yukchin     : 형제(비겁)/자식(관성·식상)/부부(배우자성+배우자궁)/직업(관·인·식
                  세력 + 부족오행 보완 직업군) 육친운 facts.

집계 로직은 engine.topics 의 _count_family/_positions_of_family 패턴을 참고해
자체 구현한다(topics.py 는 수정하지 않는다).
"""
from __future__ import annotations

from engine import constants as C
from engine.interp_types import FAMILIES, element_presence, family_element

# 생애 단계 경계 (세는나이 기준)
_CHONYEON_MAX = 29   # 초년: age < 29
_MALNYEON_MIN = 59   # 말년: age >= 59  (중년: 29 <= age < 59)

# 부족 오행 보완 직업군 키워드 (오행 index 0목 1화 2토 3금 4수)
_ELEMENT_JOB = {
    0: ["교육", "출판", "목재"],
    1: ["IT", "방송", "요식"],
    2: ["부동산", "중개", "농업"],
    3: ["금융", "기계", "의료"],
    4: ["유통", "무역", "수산"],
}


# ─────────────────────────────────────────────────────────────────────────
# 공용 집계 헬퍼 (결정론) — topics.py 패턴 참고, 자체 구현
# ─────────────────────────────────────────────────────────────────────────
def _stem_family_positions(chart, family: str) -> list[str]:
    """일간 제외 천간 중 해당 십신 가족이 나타나는 위치(년간/월간/시간)."""
    out = []
    for p in chart.pillars:
        if p.position == "일":
            continue
        if C.SIPSIN_FAMILY[C.sipsin(chart.day_master, p.stem)] == family:
            out.append(p.position + "간")
    return out


def _jijanggan_family_positions(chart, family: str) -> list[str]:
    """지지 지장간 중 해당 십신 가족이 나타나는 위치(년지/월지/일지/시지). 중복 허용."""
    theory = chart.config.woryulbunya_theory
    out = []
    for p in chart.pillars:
        for stem, _role in C.jijanggan(p.branch, theory):
            if C.SIPSIN_FAMILY[C.sipsin(chart.day_master, stem)] == family:
                out.append(p.position + "지")
    return out


def _count_family(chart, family: str) -> int:
    """천간(일간 제외) + 지장간에서 해당 십신 가족 등장 횟수."""
    return len(_stem_family_positions(chart, family)) + len(
        _jijanggan_family_positions(chart, family))


def _positions_of_family(chart, family: str) -> list[str]:
    """해당 가족이 등장하는 위치 라벨(중복 제거, 순서 유지)."""
    seen: list[str] = []
    for pos in _stem_family_positions(chart, family) + _jijanggan_family_positions(
            chart, family):
        if pos not in seen:
            seen.append(pos)
    return seen


def _ilji_jeonggi_sipsin(chart) -> str:
    """일지(배우자궁) 정기(본기)의 십신."""
    return C.sipsin(chart.day_master, C.jeonggi(chart.day.branch))


# ─────────────────────────────────────────────────────────────────────────
# 생애 단계 (초년/중년/말년)
# ─────────────────────────────────────────────────────────────────────────
def _stage_block(chart, group: list[dict]) -> dict:
    """대운 그룹 → {"대운":[{나이,간지}...], "주요십신":[십신...]}."""
    daeun_list = [{"나이": p["age"], "간지": p["name"]} for p in group]
    sipsin_list = [C.sipsin(chart.day_master, p["gz60"] % 10) for p in group]
    return {"대운": daeun_list, "주요십신": sipsin_list}


def life_stages(chart, daeun: dict) -> dict:
    """대운을 생애 3단계로 분류 + 각 단계 주요 십신.

    daeun = {"forward", "start_age", "pillars":[{"age","gz60","name"}, ...]}.
    초년(age<29) / 중년(29<=age<59) / 말년(age>=59).

    반환 {"초년":{...}, "중년":{...}, "말년":{...}}, 각 단계는 _stage_block 형식.
    """
    pillars = (daeun or {}).get("pillars") or []
    chonyeon: list[dict] = []
    jungnyeon: list[dict] = []
    malnyeon: list[dict] = []
    for p in pillars:
        age = p["age"]
        if age < _CHONYEON_MAX:
            chonyeon.append(p)
        elif age < _MALNYEON_MIN:
            jungnyeon.append(p)
        else:
            malnyeon.append(p)

    return {
        "초년": _stage_block(chart, chonyeon),
        "중년": _stage_block(chart, jungnyeon),
        "말년": _stage_block(chart, malnyeon),
    }


def daeun_timeline(chart, daeun: dict | None, yongsin: dict | None = None) -> list[dict]:
    """대운(10년)별 결정론 facts — 나이대·간지·천간/지지 십신 + 용신 부합 + hint.

    daeun  = interpret()['daeun'] (pillars: [{age, gz60, name}, ...]).
    yongsin = interpret() by_preset[pid]['yongsin'] = {'element_idx', 'family'} | None.

    각 대운의 천간 오행/십신이 용신과 같으면 '유리'로 라벨(결정론 — 좋다/나쁘다의
    서술 해석이 아니라 용신 부합 여부라는 규칙 산출). yongsin 없으면 '중립'.
    """
    dm = chart.day_master
    yel = yongsin.get("element_idx") if yongsin else None
    yfam = yongsin.get("family") if yongsin else None
    out: list[dict] = []
    for p in (daeun or {}).get("pillars", []):
        gz = p["gz60"]
        stem, branch = gz % 10, gz % 12
        cheon_sip = C.sipsin(dm, stem)
        ji_sip = C.sipsin(dm, C.jeonggi(branch))
        cheon_fam = C.SIPSIN_FAMILY[cheon_sip]
        cheon_el = C.CHEONGAN_OHAENG[stem]
        if yel is None:
            favor = "중립"
        elif cheon_el == yel:
            favor = "용신과 같은 기운(유리)"
        elif cheon_fam == yfam:
            favor = "용신 계열(유리)"
        else:
            favor = "중립"
        out.append({
            "나이": f"{p['age']}~{p['age'] + 9}세",
            "age": p["age"],
            "간지": p["name"],
            "천간십신": cheon_sip,
            "천간가족": cheon_fam,
            "지지십신": ji_sip,
            "지지가족": C.SIPSIN_FAMILY[ji_sip],
            "천간오행": C.OHAENG_HANGUL[cheon_el],
            "용신부합": favor,
            "hint": f"{cheon_sip}·{ji_sip} 기운의 10년 ({favor})",
        })
    return out


# ─────────────────────────────────────────────────────────────────────────
# 육친 (六親)
# ─────────────────────────────────────────────────────────────────────────
def _child_families(gender: str | None) -> list[str]:
    """자식성 가족. 전통: 남자=관성, 여자=식상. None 이면 둘 다."""
    if gender == "남":
        return ["관성"]
    if gender == "여":
        return ["식상"]
    return ["식상", "관성"]


def _spouse_families(gender: str | None) -> list[str]:
    """배우자성 가족. 전통: 남자=재성, 여자=관성. None 이면 둘 다."""
    if gender == "남":
        return ["재성"]
    if gender == "여":
        return ["관성"]
    return ["재성", "관성"]


def _hyeongje(chart) -> dict:
    """형제운 — 비겁(비견+겁재) 개수/위치."""
    count = _count_family(chart, "비겁")
    positions = _positions_of_family(chart, "비겁")
    if count == 0:
        hint = "형제·동료의 기운이 옅어 홀로 서는 힘이 두드러져요"
    elif count >= 3:
        hint = f"형제·동료의 기운이 {count}개로 강해 경쟁·협력이 잦은 편"
    else:
        hint = f"형제·동료와의 인연이 {count}개로 무난한 편"
    return {
        "facts": {"비겁_개수": count, "비겁_위치": positions},
        "hint": hint,
    }


def _jasik(chart, gender: str | None) -> dict:
    """자식운 — 남=관성, 여=식상, None 이면 둘 다."""
    families = _child_families(gender)
    counts = {fam: _count_family(chart, fam) for fam in families}
    positions = {fam: _positions_of_family(chart, fam) for fam in families}
    total = sum(counts.values())
    if total == 0:
        hint = "자식성의 기운이 옅어 자녀 인연은 정성으로 가꿀 부분"
    else:
        hint = f"자식성의 기운이 {total}개로 자녀와의 인연이 살아 있는 편"
    return {
        "facts": {
            "자식성_가족": families,
            "자식성_개수": counts,
            "자식성_위치": positions,
        },
        "hint": hint,
    }


def _bubu(chart, gender: str | None) -> dict:
    """부부운 — 배우자성(남=재성/여=관성/None=둘다) 유무 + 일지(배우자궁) 십신."""
    families = _spouse_families(gender)
    positions = {fam: _positions_of_family(chart, fam) for fam in families}
    present = any(positions[f] for f in families)
    ilji_sipsin = _ilji_jeonggi_sipsin(chart)
    ilji_branch = C.JIJI_HANGUL[chart.day.branch]
    if present:
        hint = f"배우자성이 자리해 인연의 기운이 있고, 배우자궁은 '{ilji_sipsin}' 성향"
    else:
        hint = f"배우자성이 옅어 인연은 적극적으로 찾을 필요, 배우자궁은 '{ilji_sipsin}' 성향"
    return {
        "facts": {
            "배우자성_가족": families,
            "배우자성_위치": positions,
            "배우자성_유무": present,
            "배우자궁_지지": ilji_branch,
            "배우자궁_십신": ilji_sipsin,
        },
        "hint": hint,
    }


def _jigeop(chart) -> dict:
    """직업운 — 관성/인성/식상 세력 + 부족오행 보완 직업군."""
    gwan = _count_family(chart, "관성")
    insung = _count_family(chart, "인성")
    siksang = _count_family(chart, "식상")

    # 부족(최소) 오행 → 보완 직업군
    pres = element_presence(chart)
    weak_idx = min(range(5), key=lambda i: (pres[i], i))
    weak_element = C.OHAENG_HANGUL[weak_idx]
    bowan_jobs = _ELEMENT_JOB[weak_idx]

    # 세력 가장 큰 축으로 방향 제시
    strengths = {"관성": gwan, "인성": insung, "식상": siksang}
    dominant = max(strengths, key=lambda k: (strengths[k], -["관성", "인성", "식상"].index(k)))
    _DIR = {"관성": "조직·체계 안에서 책임지는",
            "인성": "배움·자격을 바탕으로 한",
            "식상": "표현·재능을 펼치는"}
    if strengths[dominant] == 0:
        dir_hint = "특정 축에 치우치지 않는 다양한"
    else:
        dir_hint = _DIR[dominant]
    hint = (f"{dir_hint} 일에 인연 · 부족한 '{weak_element}' 기운을 보완하는 "
            f"{'/'.join(bowan_jobs)} 분야도 도움")

    return {
        "facts": {
            "관성_개수": gwan,
            "인성_개수": insung,
            "식상_개수": siksang,
            "부족_오행": weak_element,
            "보완_직업군": bowan_jobs,
        },
        "hint": hint,
    }


def yukchin(chart, gender: str | None = None) -> dict:
    """육친운 facts — 형제/자식/부부/직업.

    gender ∈ {"남","여",None}. None 이면 자식·배우자성을 양쪽 모두 본다.
    반환 {"형제":{facts,hint}, "자식":{...}, "부부":{...}, "직업":{...}}.
    """
    return {
        "형제": _hyeongje(chart),
        "자식": _jasik(chart, gender),
        "부부": _bubu(chart, gender),
        "직업": _jigeop(chart),
    }
