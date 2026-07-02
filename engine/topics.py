"""L4 주제별 해석 facts (topic-facts) — 사용자 친화 주제별 결정론 근거 수집.

일반 사용자가 이해할 주제(성향/재물/직업·명예/애정·궁합/건강/대운)별로, 사주
8글자·십신·오행·신살·관계에서 **결정론적으로** 산출한 근거(facts)를 모은다.

LLM 없음. 정답(외부 박제) 없음. 오직 규칙으로 산출한 사람이 읽을 라벨만 담는다.
각 주제 = {"facts": {...}, "hint": "한 줄 평이한 요지", "trace_inputs": {...}}.
hint 는 서술용 한 줄 요지일 뿐, 확정 결론(길흉 단정)이 아니다.

입력:
  chart   — engine.pillars.Chart (필수)
  scored  — engine.interp_types.StrengthResult | None (강약)
  yongsin — engine.interp_types.YongsinResult | None (용신 오행/가족)
  daeun   — dict | None (engine.interpret 의 daeun 블록 형태) 또는 None
"""
from __future__ import annotations

from engine import constants as C, relations
from engine import sinsal as sinsal_mod
from engine.interp_types import FAMILIES, element_presence, family_element

# 천간 위치(일간 제외) → 라벨
_STEM_POS_LABEL = {"년": "년간", "월": "월간", "시": "시간"}
# 지지 위치 → 라벨
_BRANCH_POS_LABEL = {"년": "년지", "월": "월지", "일": "일지", "시": "시지"}

# 사고(四庫, 묘고지) — 辰戌丑未 와 각 지지가 '고(庫)'로 갈무리하는 오행
#   辰=水庫, 戌=火庫, 丑=金庫, 未=木庫 (土는 묘고 없음 — 사고 자체가 土)
_MYOGO = {4: 4, 10: 1, 1: 3, 7: 0}  # branch -> 갈무리 오행 index

# 일반인용 hint 표현 (전문용어 대신 평이한 비유/경향)
_ELEM_META = {"목": "쭉쭉 자라는 나무", "화": "환히 타는 불", "토": "든든한 흙",
              "금": "단단한 쇠", "수": "유연한 물"}
_FAMILY_TENDENCY = {"비겁": "독립심·뚝심", "식상": "표현력·재능", "재성": "현실 감각·재물 관심",
                    "관성": "책임감·체계", "인성": "배움·신중함"}
_STRENGTH_FRIENDLY = {"신강": "기운이 단단해 추진력이 강한 편",
                      "신약": "기운은 살짝 약한 편이라 주변과 나눌 때 빛남",
                      "중화": "기운이 균형 잡힌 편"}
# 배우자궁(일지) 십신 → 인연 성향 (raw 지지 글자 대신 평이한 표현)
_SIPSIN_LOVE = {"비견": "독립적인", "겁재": "독립적인", "식신": "솔직·표현 분명한",
                "상관": "솔직·표현 분명한", "정재": "현실적·다정한", "편재": "현실적·다정한",
                "정관": "듬직·책임감 있는", "편관": "듬직·책임감 있는",
                "정인": "배려·보살핌의", "편인": "배려·보살핌의"}


# ─────────────────────────────────────────────────────────────────────────
# 공용 집계 헬퍼 (결정론)
# ─────────────────────────────────────────────────────────────────────────
def _stem_sipsin_items(chart) -> list[tuple[str, str]]:
    """일간 제외 천간의 (위치라벨, 십신). 예: [("년간","겁재"), ...]."""
    out = []
    for pos, sip in chart.stem_sipsin().items():
        if sip == "일원":
            continue
        out.append((_STEM_POS_LABEL[pos], sip))
    return out


def _branch_sipsin_items(chart) -> list[tuple[str, str]]:
    """모든 지지 지장간의 (위치라벨, 십신). 지지 1개당 여러 개일 수 있음."""
    out = []
    for pos, items in chart.branch_jijanggan_sipsin().items():
        for _stem_h, _role, sip in items:
            out.append((_BRANCH_POS_LABEL[pos], sip))
    return out


def _all_sipsin_items(chart) -> list[tuple[str, str]]:
    """천간(일간 제외) + 지지 지장간 전체의 (위치라벨, 십신)."""
    return _stem_sipsin_items(chart) + _branch_sipsin_items(chart)


def _family_counts(chart) -> dict[str, int]:
    """십신 가족별 등장 횟수 (천간 + 지장간 집계)."""
    counts = {fam: 0 for fam in FAMILIES}
    for _pos, sip in _all_sipsin_items(chart):
        counts[C.SIPSIN_FAMILY[sip]] += 1
    return counts


def _positions_of_family(chart, family: str) -> list[str]:
    """특정 가족(예 '재성')이 천간/지장간으로 등장하는 위치 라벨 목록(중복 제거, 순서 유지)."""
    seen: list[str] = []
    for pos, sip in _all_sipsin_items(chart):
        if C.SIPSIN_FAMILY[sip] == family and pos not in seen:
            seen.append(pos)
    return seen


def _count_family(chart, family: str) -> int:
    """특정 가족(예 '재성'=정재+편재) 등장 횟수 (천간 + 지장간)."""
    return sum(1 for _pos, sip in _all_sipsin_items(chart)
               if C.SIPSIN_FAMILY[sip] == family)


def _dominant_family(chart) -> str:
    """세력(등장 횟수)이 가장 큰 십신 가족. 동률은 FAMILIES 순서로 안정 선택."""
    counts = _family_counts(chart)
    return max(FAMILIES, key=lambda f: (counts[f], -FAMILIES.index(f)))


def _dominant_element(chart) -> str:
    """오행 분포에서 최다 오행 한글명. 동률은 목화토금수 순서로 안정 선택."""
    pres = element_presence(chart)
    idx = max(range(5), key=lambda i: (pres[i], -i))
    return C.OHAENG_HANGUL[idx]


def _day_master_label(chart) -> str:
    """일간 오행+음양 라벨, 예: '양목 갑' / '음금 신'."""
    dm = chart.day_master
    el = C.OHAENG_HANGUL[C.CHEONGAN_OHAENG[dm]]
    eumyang = "양" if C.CHEONGAN_EUMYANG[dm] == 0 else "음"
    return f"{eumyang}{el} {C.CHEONGAN_HANGUL[dm]}"


def _is_sinkang(scored) -> bool | None:
    if scored is None:
        return None
    return scored.strength == "신강"


def _yongsin_family(yongsin) -> str | None:
    return None if yongsin is None else yongsin.family


def _yongsin_element_name(yongsin) -> str | None:
    return None if yongsin is None else yongsin.element_name


# ─────────────────────────────────────────────────────────────────────────
# 주제 1: 성향
# ─────────────────────────────────────────────────────────────────────────
def _topic_seonghyang(chart, scored) -> dict:
    dm_label = _day_master_label(chart)
    dom_fam = _dominant_family(chart)
    dom_el = _dominant_element(chart)
    strength = None if scored is None else scored.strength

    facts = {
        "일간": dm_label,
        "강약": strength if strength is not None else "미산출(강약 입력 필요)",
        "최대세력_십신가족": dom_fam,
        "두드러진_오행": dom_el,
    }
    # 일반인용 hint: 비유 + 강약 + 경향 (용어 없이)
    dm = chart.day_master
    meta = _ELEM_META[C.OHAENG_HANGUL[C.CHEONGAN_OHAENG[dm]]]
    ey = "활달한" if C.CHEONGAN_EUMYANG[dm] == 0 else "차분한"
    parts = [f"{ey} '{meta}' 같은 사람"]
    if strength is not None:
        parts.append(_STRENGTH_FRIENDLY[strength])
    parts.append(f"{_FAMILY_TENDENCY[dom_fam]} 성향이 돋보임")
    hint = " · ".join(parts)
    return {
        "facts": facts,
        "hint": hint,
        "trace_inputs": {
            "day_master": C.CHEONGAN_HANGUL[chart.day_master],
            "day_master_element": C.OHAENG_HANGUL[C.CHEONGAN_OHAENG[chart.day_master]],
            "strength": strength,
            "family_counts": _family_counts(chart),
            "element_distribution": dict(zip(C.OHAENG_HANGUL, element_presence(chart))),
        },
    }


# ─────────────────────────────────────────────────────────────────────────
# 주제 2: 재물
# ─────────────────────────────────────────────────────────────────────────
def _topic_jaemul(chart, scored, yongsin) -> dict:
    count = _count_family(chart, "재성")
    positions = _positions_of_family(chart, "재성")
    jae_el_idx = family_element(C.CHEONGAN_OHAENG[chart.day_master], "재성")
    jae_el = C.OHAENG_HANGUL[jae_el_idx]

    yong_fam = _yongsin_family(yongsin)
    is_yongsin = (yong_fam == "재성") if yong_fam is not None else None

    sinkang = _is_sinkang(scored)
    # 신강이면 '재를 다룰 힘 있음', 신약이면 '재를 감당하기 버거움', 미산출이면 None
    if sinkang is None:
        handle = "미산출(강약 입력 필요)"
    elif sinkang:
        handle = "재를 다룰 힘 있음"
    else:
        handle = "재를 감당하기 다소 버거움"

    # 재고(財庫): 사고지(辰戌丑未) 중 갈무리 오행이 재성 오행인 지지
    jaego_positions = []
    for p in chart.pillars:
        if p.branch in _MYOGO and _MYOGO[p.branch] == jae_el_idx:
            jaego_positions.append(_BRANCH_POS_LABEL[p.position])

    facts = {
        "재성_개수": count,
        "재성_위치": positions,
        "재성_오행": jae_el,
        "재성_용신여부": is_yongsin if is_yongsin is not None else "미산출(용신 입력 필요)",
        "재물_감당력": handle,
        "재고_유무": bool(jaego_positions),
        "재고_위치": jaego_positions,
    }

    if count == 0:
        hint = "돈 다루는 기운이 약해, 재물보다 다른 강점이 부각돼요"
    else:
        bits = [f"돈 다루는 기운 {count}개"]
        if is_yongsin:
            bits.append("나에게 이로워 재물운이 좋은 편")
        if sinkang is True:
            bits.append("재물을 감당할 힘이 있음")
        elif sinkang is False:
            bits.append("욕심보다 관리가 관건")
        if jaego_positions:
            bits.append("한번 모으면 잘 쌓이는 편")
        hint = " · ".join(bits)

    return {
        "facts": facts,
        "hint": hint,
        "trace_inputs": {
            "jae_count": count,
            "jae_positions": positions,
            "jae_element": jae_el,
            "yongsin_family": yong_fam,
            "strength": None if scored is None else scored.strength,
            "jaego_branches": jaego_positions,
        },
    }


# ─────────────────────────────────────────────────────────────────────────
# 주제 3: 직업·명예
# ─────────────────────────────────────────────────────────────────────────
def _topic_jigeop(chart, yongsin) -> dict:
    gwan_count = _count_family(chart, "관성")
    gwan_positions = _positions_of_family(chart, "관성")
    in_count = _count_family(chart, "인성")
    in_positions = _positions_of_family(chart, "인성")
    sik_count = _count_family(chart, "식상")
    sik_positions = _positions_of_family(chart, "식상")

    yong_fam = _yongsin_family(yongsin)
    gwan_is_yongsin = (yong_fam == "관성") if yong_fam is not None else None

    facts = {
        "관성_개수": gwan_count,
        "관성_위치": gwan_positions,
        "인성_유무": in_count > 0,
        "인성_위치": in_positions,
        "식상_유무": sik_count > 0,
        "식상_위치": sik_positions,
        "관성_용신여부": gwan_is_yongsin if gwan_is_yongsin is not None else "미산출(용신 입력 필요)",
    }

    bits = []
    if gwan_count > 0:
        bits.append(f"책임·조직운 {gwan_count}개로 체계 잡힌 일에 인연")
        if gwan_is_yongsin:
            bits.append("그 기운이 나에게 이로워 직업운이 핵심")
    else:
        bits.append("조직보다 내 분야에서 빛나는 편")
    if in_count > 0:
        bits.append("배움·자격이 받쳐줌")
    if sik_count > 0:
        bits.append("표현력·재능 살아 있음")
    hint = " · ".join(bits)

    return {
        "facts": facts,
        "hint": hint,
        "trace_inputs": {
            "gwan_count": gwan_count,
            "gwan_positions": gwan_positions,
            "in_count": in_count,
            "sik_count": sik_count,
            "yongsin_family": yong_fam,
        },
    }


# ─────────────────────────────────────────────────────────────────────────
# 주제 4: 애정·궁합
# ─────────────────────────────────────────────────────────────────────────
def _spouse_star_families(gender: str | None) -> list[str]:
    """배우자성 가족. 전통: 남자=재성, 여자=관성. gender None 이면 둘 다."""
    if gender == "남":
        return ["재성"]
    if gender == "여":
        return ["관성"]
    return ["재성", "관성"]


def _topic_aejeong(chart, yongsin, gender: str | None = None) -> dict:
    # 일지(배우자궁)
    day_branch = chart.day.branch
    ilji_h = C.JIJI_HANGUL[day_branch]
    ilji_sipsin = chart.branch_jijanggan_sipsin()["일"]  # [(천간h, 역할, 십신), ...]
    ilji_jeonggi_sip = ilji_sipsin[-1][2] if ilji_sipsin else None  # 정기(본기) 십신

    # 배우자성 유무·위치 (전통 남=재성/여=관성, 모르면 둘 다)
    spouse_families = _spouse_star_families(gender)
    spouse_positions: dict[str, list[str]] = {}
    for fam in spouse_families:
        spouse_positions[fam] = _positions_of_family(chart, fam)

    # 일지의 합/충 (relations 에서 '일' 이 관여한 육합/육충 추출)
    rel = relations.analyze(chart)
    ilji_hap = [r for r in rel.get("육합", []) if "일" in r.get("pos", [])]
    ilji_chung = [r for r in rel.get("육충", []) if "일" in r.get("pos", [])]

    # 궁합 좋은 상대 일간 오행: 일간을 돕는 오행(인성 오행, 비겁=일간 오행) + 용신 오행
    dm_el_idx = C.CHEONGAN_OHAENG[chart.day_master]
    in_el = C.OHAENG_HANGUL[family_element(dm_el_idx, "인성")]
    bi_el = C.OHAENG_HANGUL[dm_el_idx]
    good_match = [in_el, bi_el]
    yong_name = _yongsin_element_name(yongsin)
    if yong_name is not None and yong_name not in good_match:
        good_match.append(yong_name)

    facts = {
        "배우자궁_지지": ilji_h,
        "배우자궁_십신": ilji_jeonggi_sip,
        "배우자성_가족": spouse_families,
        "배우자성_위치": spouse_positions,
        "배우자궁_합": [{"글자": r["글자"], "위치": r["pos"]} for r in ilji_hap],
        "배우자궁_충": [{"글자": r["글자"], "위치": r["pos"]} for r in ilji_chung],
        "궁합좋은_상대일간오행": good_match,
    }

    # hint
    spouse_present = any(spouse_positions[f] for f in spouse_families)
    love_trait = _SIPSIN_LOVE.get(ilji_jeonggi_sip, "좋은")
    bits = [f"{love_trait} 인연과 맞는 편"]
    if ilji_chung:
        bits.append("변동·갈등 신호 있어 소통이 중요")
    elif ilji_hap:
        bits.append("끌리는 인연의 기운")
    if not spouse_present:
        bits.append("인연은 적극적으로 찾을 필요")
    bits.append(f"{'·'.join(good_match)} 기운의 상대와 잘 맞음")
    hint = " · ".join(bits)

    return {
        "facts": facts,
        "hint": hint,
        "trace_inputs": {
            "ilji_branch": ilji_h,
            "ilji_jeonggi_sipsin": ilji_jeonggi_sip,
            "gender": gender,
            "spouse_families": spouse_families,
            "yongsin_element": yong_name,
            "good_match_elements": good_match,
        },
    }


# ─────────────────────────────────────────────────────────────────────────
# 주제 5: 건강
# ─────────────────────────────────────────────────────────────────────────
def _topic_geongang(chart) -> dict:
    pres = element_presence(chart)
    dist = dict(zip(C.OHAENG_HANGUL, pres))
    lacking = [C.OHAENG_HANGUL[i] for i in range(5) if pres[i] == 0]
    excessive = [C.OHAENG_HANGUL[i] for i in range(5) if pres[i] >= 4]

    rel = relations.analyze(chart)
    chung = [{"글자": r["글자"], "위치": r["pos"]} for r in rel.get("육충", [])]
    hyeong = [{"글자": r["글자"], "위치": r["pos"], "종류": r.get("종류", "")}
              for r in rel.get("형", [])]

    facts = {
        "오행분포": dist,
        "결핍_오행": lacking,
        "과다_오행": excessive,
        "충_지지": chung,
        "형_지지": hyeong,
    }

    bits = []
    if lacking:
        bits.append(f"{'·'.join(lacking)} 기운이 부족해 관련 부위 관리")
    if excessive:
        bits.append(f"{'·'.join(excessive)} 기운이 넘쳐 균형 주의")
    if chung or hyeong:
        bits.append("기운이 부딪혀 스트레스·과로·사고 주의")
    if not bits:
        bits.append("기운 균형이 비교적 좋은 편")
    hint = " · ".join(bits)

    return {
        "facts": facts,
        "hint": hint,
        "trace_inputs": {
            "element_distribution": dist,
            "lacking": lacking,
            "excessive": excessive,
            "chung_count": len(chung),
            "hyeong_count": len(hyeong),
        },
    }


# ─────────────────────────────────────────────────────────────────────────
# 주제 6: 대운
# ─────────────────────────────────────────────────────────────────────────
def _topic_daeun(daeun) -> dict:
    if not daeun:
        return {
            "facts": {},
            "hint": "성별 입력 시 대운 산출",
            "trace_inputs": {},
        }

    forward = daeun.get("forward")
    start_age = daeun.get("start_age")
    pillars = daeun.get("pillars") or []
    first3 = [{"나이": p["age"], "간지": p["name"]} for p in pillars[:3]]

    facts = {
        "방향": "순행" if forward else "역행",
        "대운수": start_age,
        "첫_대운": first3,
    }
    head = first3[0]["간지"] if first3 else ""
    hint = (f"10년 단위로 바뀌는 인생의 큰 흐름 — "
            f"{start_age}세부터 시작{(' (' + head + '운부터)') if head else ''}")
    return {
        "facts": facts,
        "hint": hint,
        "trace_inputs": {
            "forward": forward,
            "start_age": start_age,
            "count": len(pillars),
        },
    }


# ─────────────────────────────────────────────────────────────────────────
# 공개 API
# ─────────────────────────────────────────────────────────────────────────
def topic_facts(chart, scored=None, yongsin=None, daeun=None,
                gender: str | None = None) -> dict[str, dict]:
    """주제별 결정론 근거 facts 수집.

    반환: 주제key -> {"facts": {...}, "hint": "한 줄 요지", "trace_inputs": {...}}.
    주제key: 성향 / 재물 / 직업·명예 / 애정·궁합 / 건강 / 대운.

    scored=StrengthResult|None, yongsin=YongsinResult|None,
    daeun=dict|None (engine.interpret 의 daeun 블록). gender 는 배우자성 판정용
    선택 입력("남"/"여"); 미지정 시 재성·관성 모두를 본다.
    """
    return {
        "성향": _topic_seonghyang(chart, scored),
        "재물": _topic_jaemul(chart, scored, yongsin),
        "직업·명예": _topic_jigeop(chart, yongsin),
        "애정·궁합": _topic_aejeong(chart, yongsin, gender),
        "건강": _topic_geongang(chart),
        "대운": _topic_daeun(daeun),
    }
