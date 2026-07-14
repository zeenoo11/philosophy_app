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
from engine.i18n import branch_en, ganji_en, is_en, stem_en, t, term
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

# ── EN 짝 테이블 — t() 는 각 _topic_* 함수 안(표시 시점)에서만 호출한다 ──────
_ELEM_META_EN = {"목": "a tree growing straight and tall", "화": "a brightly burning flame",
                 "토": "steady, dependable earth", "금": "firm, tempered metal",
                 "수": "flowing, adaptable water"}
_FAMILY_TENDENCY_EN = {"비겁": "independence and grit", "식상": "expressiveness and talent",
                       "재성": "practical sense and an eye for money",
                       "관성": "responsibility and order",
                       "인성": "love of learning and prudence"}
_STRENGTH_FRIENDLY_EN = {"신강": "solid inner energy that gives you strong drive",
                         "신약": "energy on the gentler side — you shine when sharing with others",
                         "중화": "nicely balanced energy"}
_SIPSIN_LOVE_EN = {"비견": "independent", "겁재": "independent",
                   "식신": "candid, clearly expressive", "상관": "candid, clearly expressive",
                   "정재": "practical, affectionate", "편재": "practical, affectionate",
                   "정관": "dependable, responsible", "편관": "dependable, responsible",
                   "정인": "caring, nurturing", "편인": "caring, nurturing"}
_POS_LABEL_EN = {"년간": "Year Stem", "월간": "Month Stem", "시간": "Hour Stem",
                 "년지": "Year Branch", "월지": "Month Branch", "일지": "Day Branch",
                 "시지": "Hour Branch"}
_HYEONG_KIND_EN = {"상형/삼형": "mutual/three-way punishment", "자형": "self-punishment"}


def _pos(label: str) -> str:
    """위치 라벨 표시 — en 이면 'Year Stem' 등, ko 면 원문 그대로."""
    return t(label, _POS_LABEL_EN.get(label, label))


def _rel_items(items: list[dict], kind: bool = False) -> list[dict]:
    """합/충/형 항목의 표시용 사본 — {글자, 위치(, 종류)} 를 언어에 맞게."""
    out = []
    for r in items:
        d = {t("글자", "branches"): [branch_en(x) if is_en() else x for x in r["글자"]],
             t("위치", "positions"): [term(p) for p in r["pos"]]}
        if kind:
            k = r.get("종류", "")
            d[t("종류", "kind")] = t(k, _HYEONG_KIND_EN.get(k, k))
        out.append(d)
    return out


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
    """일간 오행+음양 라벨, 예: '양목 갑' / '음금 신' (en: 'Yang Wood (Gap)')."""
    dm = chart.day_master
    el = C.OHAENG_HANGUL[C.CHEONGAN_OHAENG[dm]]
    eumyang = "양" if C.CHEONGAN_EUMYANG[dm] == 0 else "음"
    if is_en():
        return (f"{'Yang' if eumyang == '양' else 'Yin'} {term(el)} "
                f"({stem_en(C.CHEONGAN_HANGUL[dm])})")
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
        t("일간", "day_master"): dm_label,
        t("강약", "strength"): (term(strength) if strength is not None
                              else t("미산출(강약 입력 필요)",
                                     "not computed (strength input needed)")),
        t("최대세력_십신가족", "dominant_ten_god_family"): term(dom_fam),
        t("두드러진_오행", "dominant_element"): term(dom_el),
    }
    # 일반인용 hint: 비유 + 강약 + 경향 (용어 없이)
    dm = chart.day_master
    el_name = C.OHAENG_HANGUL[C.CHEONGAN_OHAENG[dm]]
    meta = _ELEM_META[el_name]
    yang = C.CHEONGAN_EUMYANG[dm] == 0
    ey = "활달한" if yang else "차분한"
    parts = [t(f"{ey} '{meta}' 같은 사람",
               f"{'An outgoing' if yang else 'A calm'} person — "
               f"like {_ELEM_META_EN[el_name]}")]
    if strength is not None:
        parts.append(t(_STRENGTH_FRIENDLY[strength], _STRENGTH_FRIENDLY_EN[strength]))
    parts.append(t(f"{_FAMILY_TENDENCY[dom_fam]} 성향이 돋보임",
                   f"{_FAMILY_TENDENCY_EN[dom_fam]} stand out"))
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
        handle = t("미산출(강약 입력 필요)", "not computed (strength input needed)")
    elif sinkang:
        handle = t("재를 다룰 힘 있음", "has the strength to handle wealth")
    else:
        handle = t("재를 감당하기 다소 버거움", "carrying wealth can feel a bit heavy")

    # 재고(財庫): 사고지(辰戌丑未) 중 갈무리 오행이 재성 오행인 지지
    jaego_positions = []
    for p in chart.pillars:
        if p.branch in _MYOGO and _MYOGO[p.branch] == jae_el_idx:
            jaego_positions.append(_BRANCH_POS_LABEL[p.position])

    facts = {
        t("재성_개수", "wealth_star_count"): count,
        t("재성_위치", "wealth_star_positions"): [_pos(p) for p in positions],
        t("재성_오행", "wealth_star_element"): term(jae_el),
        t("재성_용신여부", "wealth_star_is_useful_god"): (
            is_yongsin if is_yongsin is not None
            else t("미산출(용신 입력 필요)", "not computed (useful god input needed)")),
        t("재물_감당력", "wealth_capacity"): handle,
        t("재고_유무", "has_wealth_vault"): bool(jaego_positions),
        t("재고_위치", "wealth_vault_positions"): [_pos(p) for p in jaego_positions],
    }

    if count == 0:
        hint = t("돈 다루는 기운이 약해, 재물보다 다른 강점이 부각돼요",
                 "The money-handling energy runs faint here — strengths other than "
                 "wealth take the spotlight")
    else:
        bits = [t(f"돈 다루는 기운 {count}개",
                  f"{count} wealth star{'s' if count != 1 else ''} for handling money")]
        if is_yongsin:
            bits.append(t("나에게 이로워 재물운이 좋은 편",
                          "it works in your favor, so money luck runs strong"))
        if sinkang is True:
            bits.append(t("재물을 감당할 힘이 있음",
                          "you have the strength to carry wealth"))
        elif sinkang is False:
            bits.append(t("욕심보다 관리가 관건",
                          "management matters more than ambition"))
        if jaego_positions:
            bits.append(t("한번 모으면 잘 쌓이는 편",
                          "once gathered, it tends to stack up nicely"))
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
        t("관성_개수", "authority_star_count"): gwan_count,
        t("관성_위치", "authority_star_positions"): [_pos(p) for p in gwan_positions],
        t("인성_유무", "has_resource_star"): in_count > 0,
        t("인성_위치", "resource_star_positions"): [_pos(p) for p in in_positions],
        t("식상_유무", "has_output_star"): sik_count > 0,
        t("식상_위치", "output_star_positions"): [_pos(p) for p in sik_positions],
        t("관성_용신여부", "authority_star_is_useful_god"): (
            gwan_is_yongsin if gwan_is_yongsin is not None
            else t("미산출(용신 입력 필요)", "not computed (useful god input needed)")),
    }

    bits = []
    if gwan_count > 0:
        bits.append(t(f"책임·조직운 {gwan_count}개로 체계 잡힌 일에 인연",
                      f"{gwan_count} authority star{'s' if gwan_count != 1 else ''} — "
                      f"a natural fit for structured, responsible work"))
        if gwan_is_yongsin:
            bits.append(t("그 기운이 나에게 이로워 직업운이 핵심",
                          "that energy favors you, making career luck a centerpiece"))
    else:
        bits.append(t("조직보다 내 분야에서 빛나는 편",
                      "you shine in your own field more than inside an organization"))
    if in_count > 0:
        bits.append(t("배움·자격이 받쳐줌", "learning and credentials back you up"))
    if sik_count > 0:
        bits.append(t("표현력·재능 살아 있음", "expressiveness and talent are alive and well"))
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
        t("배우자궁_지지", "spouse_palace_branch"): (
            branch_en(ilji_h) if is_en() else ilji_h),
        t("배우자궁_십신", "spouse_palace_ten_god"): (
            term(ilji_jeonggi_sip) if ilji_jeonggi_sip else ilji_jeonggi_sip),
        t("배우자성_가족", "spouse_star_families"): [term(f) for f in spouse_families],
        t("배우자성_위치", "spouse_star_positions"): {
            term(f): [_pos(p) for p in ps] for f, ps in spouse_positions.items()},
        t("배우자궁_합", "spouse_palace_combines"): _rel_items(ilji_hap),
        t("배우자궁_충", "spouse_palace_clashes"): _rel_items(ilji_chung),
        t("궁합좋은_상대일간오행", "compatible_day_master_elements"): [
            term(e) for e in good_match],
    }

    # hint
    spouse_present = any(spouse_positions[f] for f in spouse_families)
    love_trait = _SIPSIN_LOVE.get(ilji_jeonggi_sip, "좋은")
    love_trait_en = _SIPSIN_LOVE_EN.get(ilji_jeonggi_sip, "good")
    bits = [t(f"{love_trait} 인연과 맞는 편",
              f"A natural fit with {love_trait_en} partners")]
    if ilji_chung:
        bits.append(t("변동·갈등 신호 있어 소통이 중요",
                      "signs of change and friction — communication is key"))
    elif ilji_hap:
        bits.append(t("끌리는 인연의 기운", "an energy that draws people in"))
    if not spouse_present:
        bits.append(t("인연은 적극적으로 찾을 필요",
                      "love is best sought out actively"))
    bits.append(t(f"{'·'.join(good_match)} 기운의 상대와 잘 맞음",
                  f"partners with {'·'.join(term(e) for e in good_match)} "
                  f"energy suit you well"))
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
    chung = _rel_items(rel.get("육충", []))
    hyeong = _rel_items(rel.get("형", []), kind=True)

    facts = {
        t("오행분포", "element_distribution"): (
            {term(k): v for k, v in dist.items()} if is_en() else dist),
        t("결핍_오행", "lacking_elements"): [term(x) for x in lacking],
        t("과다_오행", "excessive_elements"): [term(x) for x in excessive],
        t("충_지지", "clashing_branches"): chung,
        t("형_지지", "punishment_branches"): hyeong,
    }

    bits = []
    if lacking:
        bits.append(t(f"{'·'.join(lacking)} 기운이 부족해 관련 부위 관리",
                      f"{'·'.join(term(x) for x in lacking)} energy runs low — "
                      f"tend to the related areas"))
    if excessive:
        bits.append(t(f"{'·'.join(excessive)} 기운이 넘쳐 균형 주의",
                      f"{'·'.join(term(x) for x in excessive)} energy overflows — "
                      f"mind the balance"))
    if chung or hyeong:
        bits.append(t("기운이 부딪혀 스트레스·과로·사고 주의",
                      "colliding energies — watch stress, overwork, and accidents"))
    if not bits:
        bits.append(t("기운 균형이 비교적 좋은 편",
                      "your elemental balance is in fairly good shape"))
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
            "hint": t("성별 입력 시 대운 산출",
                      "Provide gender to compute the 10-year luck cycles"),
            "trace_inputs": {},
        }

    forward = daeun.get("forward")
    start_age = daeun.get("start_age")
    pillars = daeun.get("pillars") or []
    first3 = [{t("나이", "age"): p["age"],
               t("간지", "ganji"): (ganji_en(p["name"]) if is_en() else p["name"])}
              for p in pillars[:3]]

    facts = {
        t("방향", "direction"): term("순행") if forward else term("역행"),
        t("대운수", "start_age"): start_age,
        t("첫_대운", "first_cycles"): first3,
    }
    head = pillars[0]["name"] if pillars else ""
    hint = t(
        (f"10년 단위로 바뀌는 인생의 큰 흐름 — "
         f"{start_age}세부터 시작{(' (' + head + '운부터)') if head else ''}"),
        (f"The grand current of life that turns every 10 years — "
         f"begins at age {start_age}"
         f"{(' (opening with the ' + ganji_en(head) + ' cycle)') if head else ''}"),
    )
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
