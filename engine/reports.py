"""카테고리별 운세 리포트 생성기 (서비스용) — 상용 운세 섹션 구조 + claude -p(Sonnet).

각 카테고리(신년운세·평생운세·애정운·궁합·오늘·주간·토정비결·재물·건강)는:
  ① 결정론 모듈(interpret/luck/tojeong/lifelong/compatibility)에서 근거 facts 수집
  ② 카테고리별 섹션 프롬프트로 claude -p(Sonnet) 1회 호출
  ③ 핵심 확정값 그라운딩 검사 + MLflow 트레이싱
'정통운세' 스타일(총론·재물·직장·가정/건강·이성·월별 등)을 일반인 언어로 재현하되,
모든 서술은 결정론 데이터에 근거하고 단정적 운명론은 피한다.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date as _date

from engine import compatibility, constants as C, i18n, lifelong, luck, tojeong
from engine.i18n import branch_en, ganji_en, is_en, stem_en, t, term
from engine.interpret import interpret
from engine.narrator import DEFAULT_MODEL, call_llm_json, llm_meta
from engine.pillars import BirthInput, compute_chart
from engine.presets import list_presets, load_preset
from engine.tracing import llm_span

_BASE_RULES = (
    "[작성 규칙]\n"
    "- 한자(漢字)를 절대 쓰지 마세요. 오행도 한글로(火 X → '화/불기운' O). 괄호 안에도 "
    "천간·지지·오행·십신을 한자로 표기하지 마세요(壬·戊·水·火·財星 등 전부 금지). "
    "전문용어는 쉬운 한글 뜻만 괄호로. "
    "예: 재성(내가 다루는 돈), 관성(직책·책임), 비겁(동료 기운), 용신(나에게 가장 이로운 기운).\n"
    "- 아래 '확정 데이터'에 없는 글자·숫자·사실을 지어내지 마세요. 강약·용신·점수, 그리고 "
    "**사주 글자(특히 일지/배우자궁)**는 데이터에 적힌 그대로 쓰고 다른 간지로 바꿔 말하지 마세요.\n"
    "- 확정 데이터에 '강약'(신강/신약/중화)이 있으면 본문 어딘가에 그 단어를 **그대로 최소 "
    "한 번** 쓰고 바로 뒤에 쉬운 뜻을 괄호로 푸세요(예: '신강(기운이 강한 편)'). '용신'이 "
    "있으면 그 오행 글자(목/화/토/금/수 중 해당 한글)도 **한 번은 그대로** 쓰고 쉽게 풀어주세요"
    "(예: '용신은 토(흙·안정의 기운)'). — 사용자가 풀이의 근거를 확인할 수 있게.\n"
    "- 단정적 운명론·미신적 협박을 피하고 '~한 경향', '~에 유리/주의' 처럼 부드럽게.\n"
    "- **근거를 가져와 설명하세요.** 막연한 일반론·덕담 금지. 각 섹션마다 그렇게 보는 이유를 "
    "아래 '확정 데이터'의 구체적 값(사주 8글자·십신·강약·용신·세운/대운/일진 간지·신살·점수 "
    "등)을 **직접 짚으며** 풀어주세요. 예: '일지에 도화가 있어 매력이 드러나는 편이고…', "
    "'올해 세운(병오)의 편재 기운이라 돈이 들어오되 나가기도…', '용신인 토(흙·안정)와 같은 "
    "기운의 시기라 유리…'. 근거 → 그 뜻 → 생활 속 행동 순으로 이어가세요.\n"
    "- **분량을 넉넉히.** 각 섹션 제목을 그대로 쓰고 **섹션당 5~8문장**으로 충실하게(짧게 "
    "끊지 마세요). 각 섹션 끝에 바로 쓸 수 있는 **실천 조언 1~2가지**(구체적 행동)를 덧붙이세요. "
    "전체적으로 풍부하고 읽는 맛이 있게, 그러나 같은 말 반복은 피하고 섹션마다 다른 근거로.\n"
    "- **읽기 쉽게 쪼개세요.** 섹션 하나를 통짜 문단으로 쓰지 말고 **2~3개의 짧은 문단**으로 "
    "나누고, 각 문단 첫 줄에 그 문단의 핵심을 담은 **굵은 미니 소제목** 한 줄을 따로 "
    "붙이세요(예: **타고난 그릇**, **올해의 물길**, **이렇게 해보세요**). 미니 소제목은 "
    "굵은 글씨 한 줄만 — '#' 헤딩은 섹션 제목에만 씁니다. 실천 조언도 소제목을 단 "
    "마지막 문단으로.\n"
)

# 영어 리포트 작성 규칙 — 한글/한자 완전 금지 + 로마자 간지 + 동일한 그라운딩 요구
_BASE_RULES_EN = (
    "[Writing rules]\n"
    "- Write ENTIRELY in natural English. Never use Korean (Hangul) or Chinese (Hanja/CJK) "
    "characters anywhere — not even in parentheses. Use the romanized names from the confirmed "
    "data exactly as written (e.g. 'Im-sul', 'Byeong-o').\n"
    "- Gloss technical terms in plain English on first use, e.g. Wealth star (money you handle), "
    "Authority (duty and career), Companions (peer energy), useful god (the element that helps "
    "this chart most).\n"
    "- Never invent a fact, letter, or number that is not in the confirmed data below. Copy the "
    "strength verdict, useful god, scores, and chart letters (especially the day branch / spouse "
    "palace) exactly as given — never substitute different ganji.\n"
    "- If the confirmed data has a strength verdict ('Strong Day Master' / 'Weak Day Master' / "
    "'Balanced Day Master'), use that exact phrase at least once and gloss it right after in "
    "parentheses (e.g. 'Strong Day Master (your core energy runs strong)'). If a useful god is "
    "given, name its element word (Wood/Fire/Earth/Metal/Water) at least once and explain it "
    "simply — so readers can verify the basis of the reading.\n"
    "- Avoid deterministic fatalism and superstition-flavored threats; prefer soft phrasing like "
    "'tends to', 'favorable for', 'worth caution'.\n"
    "- **Ground every claim.** No vague generalities or empty blessings. In each section, point "
    "directly at concrete values from the confirmed data (the eight characters, Ten Gods, "
    "strength, useful god, year/decade/day ganji, stars, scores), then explain what they mean, "
    "then give a concrete action — evidence, meaning, action, in that order.\n"
    "- **Be generous with length.** Keep the section headers exactly as given and write 5-8 full "
    "sentences per section, ending each section with 1-2 practical tips (specific actions). "
    "Rich and readable overall, but do not repeat yourself — cite different evidence per section.\n"
    "- **Break it up for the eye.** Never write a section as one solid block: split it into "
    "2-3 short paragraphs, each opened by its own **bold mini-heading** line that captures "
    "that paragraph's point (e.g. **Your Innate Vessel**, **This Year's Current**, "
    "**Try This**). Mini-headings are a single bold line — never '#' headings, which are "
    "reserved for section titles. Make the practical tips the final mini-headed paragraph.\n"
)


def _base_rules() -> str:
    return _BASE_RULES_EN if is_en() else _BASE_RULES

# 본문 한자 노출 가드 (쉬운 말 약속 위반 탐지) — 천간·지지·오행·십신 한자
_HANJA = set("甲乙丙丁戊己庚辛壬癸子丑寅卯辰巳午未申酉戌亥木火土金水財官印食傷比劫殺")

# 천간·지지·오행 한자 → 한글 1:1 음역(의미 손실 없음). 긴 리포트가 간지를 근거로
# 인용하다 한자를 흘리면(예: 丁亥卯·木) 여기서 한글로 자동 교정 → '쉬운 말' 유지 +
# 그라운딩 오탐 방지. 십신·살 한자(財官印食傷比劫殺)는 교정하지 않고 _HANJA 가드로
# 잡는다(전문용어를 그대로 쓴 신호이므로 검토 대상으로 남긴다).
_HANJA_TO_HANGUL = dict(
    list(zip(C.CHEONGAN_HANJA, C.CHEONGAN_HANGUL))
    + list(zip(C.JIJI_HANJA, C.JIJI_HANGUL))
    + list(zip(C.OHAENG_HANJA, C.OHAENG_HANGUL)))
# 사주 도메인에서 모델이 흘리기 쉬운 한자(단일 한글 음 — 한국어 사주 문맥에서 안전).
# 십신·관계·신살·일반어까지 한글로 교정 → 사용자는 한자를 보지 않는다. (남는 외래 한자는
# 아래 CJK 가드가 잡는다.)
_HANJA_TO_HANGUL.update({
    "財": "재", "官": "관", "印": "인", "食": "식", "傷": "상", "比": "비", "劫": "겁",
    "星": "성", "殺": "살", "神": "신", "貴": "귀", "人": "인", "刃": "인", "祿": "록",
    "庫": "고", "墓": "묘", "桃": "도", "花": "화", "驛": "역", "馬": "마",
    "合": "합", "沖": "충", "冲": "충", "刑": "형", "破": "파", "害": "해", "會": "회",
    "旺": "왕", "盛": "성", "衰": "쇠", "強": "강", "强": "강", "弱": "약",
    "方": "방", "面": "면", "中": "중", "和": "화", "三": "삼", "六": "육",
})


def _dehanja(text: str) -> str:
    """한자 누출을 한글 음으로 교정(사주 도메인 맵). 맵에 없는 한자는 그대로(가드가 잡음).

    EN 모드에선 교정하지 않는다 — 한자를 한글로 바꾸면 영어 본문에 한글이 섞이는
    더 나쁜 결과가 되므로, 그대로 두고 그라운딩 가드(CJK 검출)가 잡게 한다.
    """
    if not text or is_en():
        return text or ""
    return "".join(_HANJA_TO_HANGUL.get(ch, ch) for ch in text)


# ── EN 표시 헬퍼 — 결정론 값(간지·월·길흉·오행분포)을 영어 표기로 ────────────
_MONTH_EN = {f"{m}월": n for m, n in zip(range(1, 13),
             ("Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"))}
_GILHYUNG_EN = {"좋음": "good", "보통": "fair", "주의": "caution"}


def _g(ganji_ko: str) -> str:
    """간지 표시 — en 로마자('Byeong-o'), ko 원문."""
    return ganji_en(ganji_ko) if is_en() else ganji_ko


def _month_label(ko: str) -> str:
    return _MONTH_EN.get(ko, ko) if is_en() else ko


def _gil(ko: str) -> str:
    return _GILHYUNG_EN.get(ko, ko) if is_en() else ko


def _sinsal_list(names: list[str] | tuple[str, ...]) -> str:
    """신살 이름 나열 — en 이면 용어 번역, 비면 '없음/none'."""
    return ", ".join(term(s) for s in names) or t("없음", "none")


def _eight(eight_chars: str) -> str:
    """8글자('무인 계해 임술 신해') — en 이면 각 간지를 로마자로."""
    if not is_en():
        return eight_chars
    return " ".join(ganji_en(p) for p in eight_chars.split())


def _dist(dist: dict) -> str:
    """오행 분포 dict — ko 는 기존 repr 그대로, en 은 'Wood 1 · Fire 0 · …'."""
    if not is_en():
        return f"{dist}"
    return " · ".join(f"{term(k)} {v}" for k, v in dist.items())


# 완성된 다섹션 리포트는 보통 1500자+. 이보다 훨씬 짧으면 LLM 이 도중에 끊긴 것(DeepSeek
# 간헐적 조기 종료)으로 보고 재생성한다. _MIN_REPORT_CHARS 미만이면 잘림으로 판정.
_MIN_REPORT_CHARS = 700
_MAX_LLM_TRIES = 3


def is_truncated(text: str) -> bool:
    """리포트 본문이 비정상적으로 짧으면(도중 끊김) True."""
    return len(_dehanja((text or "").strip())) < _MIN_REPORT_CHARS


@dataclass(frozen=True)
class Report:
    kind: str
    title: str
    text: str            # 리포트 본문 + 맨 아래 '📎 해석 근거' 푸터 포함
    grounded: bool
    violations: tuple[str, ...]
    facts: str
    meta: dict = field(default_factory=dict)
    basis: tuple[str, ...] = ()
    source: str = ""


DEFAULT_PRESET = "jeongtong_eokbu"


def _chart(birth: BirthInput, preset_id: str = DEFAULT_PRESET):
    return compute_chart(birth, load_preset(preset_id).deterministic)


_STRENGTHS = ("신강", "신약", "중화")


def _forbid(strength: str) -> list[str]:
    """그라운딩 '모순 금지' 목록 — 확정 강약과 다른 강약 라벨(등장 시 위반).

    EN 모드에선 영어 라벨('Weak Day Master' 등)로 검사한다 — 본문이 영어이므로.
    """
    others = [s for s in _STRENGTHS if s != strength]
    return [term(s) for s in others] if is_en() else others


def _verdict_basis(strength: str, yong: str | None) -> str:
    """근거 푸터용 강약·용신 한 줄."""
    if is_en():
        out = f"Day Master strength: {term(strength)}"
        if yong:
            out += f" · useful god (most helpful energy): {yong}"
        return out
    return f"일간 강약: {strength}" + (f" · 용신(가장 이로운 기운): {yong}" if yong else "")


# 용신 정책 한글 라벨 (취용 트레이스 노출용)
_POLICY_KO = {"eokbu": "억부", "johu": "조후", "byeongyak": "병약",
              "jeonwang": "전왕", "tongwan": "통관"}
# 강약이 기준선에 이만큼 가까우면 '경계 근접'으로 안내(출생시각 민감) — 감사 결함 ④
_BAND_NEAR = 0.05


def _yongsin_trace_basis(block: dict) -> str | None:
    """용신 취용 과정 한 줄 — '1순위 X 미성립 → Y 채택'(감사 ②⑤).

    block = interpret() by_preset[pid]. 채택 정책이 1순위면 '(1순위) 채택',
    상위 순위가 미성립해 폴백했으면 건너뛴 정책을 밝힌다. 유파를 골랐는데
    실제로는 억부로 떨어진 경우를 사용자가 알 수 있게 한다.
    """
    chain = block.get("yongsin_chain")
    if not chain:
        return None
    adopted = chain.get("adopted")
    skipped = chain.get("skipped") or []
    ko = lambda n: term(_POLICY_KO.get(n, n))  # noqa: E731 — en 이면 용어 번역
    if adopted is None:
        return t("용신 취용: 상위 순위 정책이 모두 미성립 — 이 사주엔 뚜렷한 용신이 없음",
                 "Useful-god selection: no higher-priority policy applied — this chart has "
                 "no clear useful god")
    if skipped:
        return t(f"용신 취용: {'·'.join(ko(s) for s in skipped)}(상위 순위) 미성립 "
                 f"→ {ko(adopted)} 채택",
                 f"Useful-god selection: {' · '.join(ko(s) for s in skipped)} (higher priority) "
                 f"did not apply → adopted {ko(adopted)}")
    return t(f"용신 취용: {ko(adopted)}(1순위) 채택",
             f"Useful-god selection: adopted {ko(adopted)} (first priority)")


def _strength_margin_basis(block: dict) -> str | None:
    """강약이 기준선 경계에 가까우면 취약성 안내(감사 ④). 아니면 None."""
    det = block.get("strength_detail") or {}
    ratio, bands = det.get("ratio"), det.get("bands") or []
    if ratio is None or len(bands) != 2:
        return None
    lo, hi = bands
    dist = min(abs(ratio - lo), abs(ratio - hi))
    if dist <= _BAND_NEAR:
        return t(f"⚠️ 강약 경계 근접 — 통근비율 {ratio:.2f}이(가) 기준선({lo}/{hi})에 "
                 f"{dist:.2f}까지 가까워, 출생시각·진태양시 보정에 따라 강약(따라서 용신)이 "
                 f"달라질 수 있어요",
                 f"⚠️ Near the strength boundary — the rooting ratio {ratio:.2f} is within "
                 f"{dist:.2f} of the threshold ({lo}/{hi}), so birth time or true-solar-time "
                 f"correction could flip the strength verdict (and thus the useful god)")
    return None


_EOKBU_SRC = "정통 자평 · 억부 중심 (자평진전·적천수)"
_EOKBU_SRC_EN = "Classic Japyeong · Eokbu-centered (Ziping classics)"


# 결정론 토글 라벨(ko, en) — 유파를 바꾸면 '원국(사주 원판)'이 달라지는 항목들(감사 ③).
_DET_FIELDS = {
    "woryulbunya_theory": ("지장간(숨은 기운) 계산법", "hidden-stem (jijanggan) method"),
    "sipiunseong_theory": ("십이운성(기운의 단계) 계산법", "twelve life-stages method"),
    "jasi_rule": ("자시(밤 11~1시) 날짜 처리", "midnight-hour (Ja-si) date handling"),
    "true_solar_time": ("진태양시 보정", "true solar time correction"),
    "longitude_deg": ("기준 경도", "reference longitude"),
}
# 하위 호환 별칭(예전 이름) — 한글 라벨 dict
_DET_FIELD_KO = {f: ko for f, (ko, _en) in _DET_FIELDS.items()}


def deterministic_diff(preset_id: str, base: str = DEFAULT_PRESET) -> list[str]:
    """preset_id 의 결정론 토글이 base(기본=표준)와 다른 항목의 라벨 목록(현재 언어).

    비어 있지 않으면 '강조점 차이'가 아니라 **원국 계산 입력 자체가 달라짐**을 뜻한다
    (지장간→통근→강약, 십이운성→차트 출력 등). 앱이 이를 사용자에게 경고/재렌더한다.
    """
    if preset_id == base:
        return []
    a, b = load_preset(base).deterministic, load_preset(preset_id).deterministic
    return [t(ko, en) for f, (ko, en) in _DET_FIELDS.items() if getattr(a, f) != getattr(b, f)]


def _source_label(preset_id: str) -> str:
    """리포트 근거 푸터의 '해석 기준 유파' 라벨 (한글 display_name 사용 — 한자 노출 방지)."""
    if preset_id == DEFAULT_PRESET:
        return t(_EOKBU_SRC, _EOKBU_SRC_EN)
    return i18n.preset_display_name(preset_id, load_preset(preset_id).display_name)


def _verdict_line(birth: BirthInput, gender, year,
                  preset_id: str = DEFAULT_PRESET) -> tuple[str, str, str | None, list[str]]:
    """선택 유파의 강약·용신 + 오행분포 한 줄 + (확정 강약, 용신표기, 트레이스 푸터줄).

    4번째 반환값(trace_basis) = 용신 취용 과정·강약 경계 근접 등 투명성 푸터 줄
    (감사 ②④⑤). 각 리포트가 basis 에 그대로 펼쳐 넣는다.
    """
    preset = load_preset(preset_id)
    r = interpret(birth, [preset_id], gender=gender, now_year=year)
    b = r["by_preset"][preset_id]
    d = b["deterministic"]
    # 네 기둥·일지를 명시(모델이 8글자 문자열을 오파싱해 일지를 틀리게 읽는 환각 방지)
    pil = d["pillars"]
    if is_en():
        pillars_txt = " / ".join(
            f"{term(pos)} pillar {ganji_en(pil[pos]['stem'] + pil[pos]['branch'])}"
            for pos in ("년", "월", "일", "시") if pos in pil)
        ilji = branch_en(pil["일"]["branch"]) if "일" in pil else ""
        line = (f"- Interpretation school: "
                f"{i18n.preset_display_name(preset_id, preset.display_name)}\n"
                f"- Four pillars: {pillars_txt} "
                f"(eight characters: {_eight(d['eight_chars'])})\n"
                f"- Day Master (you): {stem_en(d['day_master'])} "
                f"({term(d['day_master_element'])}), and the day branch (your seat / spouse "
                f"palace) is '{ilji}' — use exactly this letter for the day branch\n"
                f"- Strength {term(b['strength'])}, "
                f"element distribution {_dist(d['element_distribution'])}")
    else:
        pillars_txt = " / ".join(f"{pos}주 {pil[pos]['stem']}{pil[pos]['branch']}"
                                 for pos in ("년", "월", "일", "시") if pos in pil)
        ilji = pil["일"]["branch"] if "일" in pil else ""
        line = (f"- 해석 유파: {preset.display_name}\n"
                f"- 사주 네 기둥: {pillars_txt} (8글자 {d['eight_chars']})\n"
                f"- 일간(나 자신): {d['day_master']}({d['day_master_element']}), "
                f"일지(나의 자리·배우자궁)는 '{ilji}' — 이 글자를 일지로 정확히 쓸 것\n"
                f"- 강약 {b['strength']}, 오행분포 {d['element_distribution']}")
    yong = None
    if b.get("yongsin"):
        el, fam = b["yongsin"]["element"], b["yongsin"]["family"]
        yong = f"{term(el)} ({term(fam)})" if is_en() else f"{el}({fam})"
        line += t(f", 용신 {yong}", f", useful god {yong}")
    trace_basis = [x for x in (_yongsin_trace_basis(b), _strength_margin_basis(b)) if x]
    return line, b["strength"], yong, trace_basis


def _build_prompt(title: str, intro: str, sections: list[str], facts: str) -> str:
    secs = "\n".join(f"## {s}" for s in sections)
    if is_en():
        return (f"You are a warm, plain-spoken fortune counselor writing for everyday readers. "
                f"You are writing the '{title}' report.\n{intro}\n\n{_base_rules()}\n"
                f"[Section format]\n{secs}\n\n[Confirmed data]\n{facts}\n\n[Report]")
    return (f"당신은 일반인에게 쉽고 따뜻하게 풀어주는 운세 상담가입니다. '{title}' 리포트를 씁니다.\n"
            f"{intro}\n\n{_base_rules()}\n[섹션 형식]\n{secs}\n\n"
            f"[확정 데이터]\n{facts}\n\n[리포트]")


def _basis_footer(basis: list[str], source: str) -> str:
    """리포트 맨 아래 '해석 근거'(결정론 계산값 + 기준 유파) 푸터."""
    if not basis:
        return ""
    foot = t("\n\n---\n**📎 이 풀이의 근거** (엔진이 계산한 사주 값)\n",
             "\n\n---\n**📎 Basis of this reading** (values computed by the engine)\n") + \
           "\n".join(f"- {b}" for b in basis)
    if source:
        foot += t(f"\n\n*해석 기준: {source}*", f"\n\n*Interpretation basis: {source}*")
    return foot


def _grounding_violations(text: str, forbid: list[str],
                          require: list[str] = ()) -> list[str]:
    """본문 그라운딩 위반 목록.

    - forbid  : 등장하면 안 되는 문자열(확정과 모순되는 강약 등) — negative check.
    - require : **반드시 등장**해야 하는 확정값(강약·용신 오행) — positive check.
                비결정 생성물이 결정론 근거를 실제로 반영했는지 검증한다(감사 ①).
    - 한자 노출(쉬운 말 약속 위반) 점검. EN 모드에선 대소문자 무시 + 한글 노출도 위반.
    """
    if is_en():
        hay = text.lower()
        hit = lambda s: s and s.lower() in hay          # noqa: E731
        miss = lambda s: s and s.lower() not in hay      # noqa: E731
    else:
        hit = lambda s: s and s in text                  # noqa: E731
        miss = lambda s: s and s not in text             # noqa: E731
    violations = [t(f"모순:{f}", f"contradicts:{f}") for f in forbid if hit(f)]
    violations += [t(f"미반영:{r}", f"missing:{r}") for r in require if miss(r)]
    # 한자 노출 — _dehanja 교정 후에도 남은 모든 CJK 한자(외래·드문 글자) 탐지(쉬운 말 위반).
    cjk = sorted({c for c in text if 0x3400 <= ord(c) <= 0x9FFF})
    if cjk:
        violations.append(t("한자노출:", "hanja:") + "".join(cjk[:6]))
    if is_en():  # 영어 본문에 한글이 남아 있으면 그 자체가 위반
        hangul = sorted({c for c in text if 0xAC00 <= ord(c) <= 0xD7A3})
        if hangul:
            violations.append("hangul:" + "".join(hangul[:6]))
    return violations


def _require_values(strength: str, yong: str | None, *, with_yong: bool) -> list[str]:
    """positive grounding 요구값 — 강약 라벨 + (옵션) 용신 오행 글자.

    yong 은 '토(관성)' / 'Earth (Authority)' 형태 → 오행 표기만 요구(가족명 변형은 허용).
    EN 모드에선 강약도 영어 라벨('Strong Day Master' 등)로 요구한다."""
    req = [term(strength) if is_en() else strength]
    if with_yong and yong:
        req.append(yong.split("(")[0].strip())
    return req


def finalize_report(prep: dict, text: str, meta: dict) -> Report:
    """스트리밍 등으로 LLM 본문(text)을 받은 뒤 그라운딩 검사 + 근거 푸터를 붙여 Report 완성."""
    text = _dehanja((text or "").strip())
    violations = _grounding_violations(text, prep.get("forbid", []), prep.get("require", []))
    text_with_basis = text + _basis_footer(prep.get("basis", []), prep.get("source", ""))
    return Report(kind=prep["kind"], title=prep["title"], text=text_with_basis,
                  grounded=not violations, violations=tuple(violations),
                  facts=prep.get("facts", ""), meta=meta or {},
                  basis=tuple(prep.get("basis", [])), source=prep.get("source", ""))


def _run(kind: str, title: str, intro: str, sections: list[str], facts: str,
         forbid: list[str] = (), *, require: list[str] = (), basis: list[str] = (),
         source: str = "", model: str = DEFAULT_MODEL, timeout: int = 240,
         trace: bool = True, prepare_only: bool = False):
    """forbid = 본문에 등장하면 안 되는 문자열(확정과 모순되는 강약 등). 부재는 무방.
    require = 본문에 **반드시 등장**해야 하는 확정값(강약·용신) — positive 그라운딩(감사 ①).
    basis/source = 본문 뒤에 붙는 '해석 근거' 푸터(결정론 값, LLM 비관여).
    prepare_only=True → LLM 호출 없이 프롬프트·근거만 담은 dict 반환(스트리밍용)."""
    prompt = _build_prompt(title, intro, sections, facts)
    if prepare_only:
        return {"kind": kind, "title": title, "prompt": prompt, "facts": facts,
                "forbid": list(forbid), "require": list(require), "basis": list(basis),
                "source": source, "sections": list(sections)}
    with llm_span(f"report:{kind}", {"kind": kind, "prompt": prompt}, enabled=trace) as span:
        # 짧게 잘린 생성(조기 종료)이면 재시도 — 마지막엔 가장 긴 결과 채택
        text, data, wall, tries = "", {}, 0.0, 0
        for tries in range(1, _MAX_LLM_TRIES + 1):
            data, wall = call_llm_json(prompt, model=model, timeout=timeout)
            cand = _dehanja((data.get("result") or "").strip())
            if len(cand) > len(text):
                text = cand
            if not is_truncated(text):
                break
        violations = _grounding_violations(text, list(forbid), list(require))
        meta = {**llm_meta(data, wall), "tries": tries}
        span.set_outputs({"report": text})
        span.set_attributes({**meta, "grounded": not violations, "violations": violations})
    text_with_basis = text + _basis_footer(list(basis), source)
    return Report(kind=kind, title=title, text=text_with_basis, grounded=not violations,
                  violations=tuple(violations), facts=facts, meta=meta,
                  basis=tuple(basis), source=source)


# ─────────────────────────────────────────────────────────────────────────
# 카테고리별 facts + 리포트
# ─────────────────────────────────────────────────────────────────────────
def saeun_report(birth, year=2026, *, gender=None, preset_id=DEFAULT_PRESET, **kw) -> Report:
    """신년운세(세운) — 총론·재물·직장/사업·가정/건강·이성/대인 + 월별."""
    ch = _chart(birth, preset_id)
    vline, strength, yong, tbasis = _verdict_line(birth, gender, year, preset_id)
    se = luck.saeun(ch, year)
    months = luck.month_luck(ch, year)
    mtxt = "\n".join(
        t(f"    {m['양력월_근사']} {m['ganji']}: 천간 {m['천간십신']}/지지 {m['지지십신']}",
          f"    {_month_label(m['양력월_근사'])} {_g(m['ganji'])}: stem {term(m['천간십신'])} / "
          f"branch {term(m['지지십신'])}")
        for m in months)
    facts = t(f"{vline}\n- {year} 세운(올해 간지): {se['ganji']} — 천간 {se['천간십신']}, "
              f"지지 {se['지지십신']}, 오행 {se['오행']}\n- 월별 세운(12달):\n{mtxt}",
              f"{vline}\n- {year} yearly ganji: {_g(se['ganji'])} — stem {term(se['천간십신'])}, "
              f"branch {term(se['지지십신'])}, element {term(se['오행'])}\n"
              f"- Monthly flow (12 months):\n{mtxt}")
    sections = [t("📜 총론", "📜 Overview"), t("💰 재물운", "💰 Wealth"),
                t("🏆 직장·사업운", "🏆 Career & Business"),
                t("🏡 가정·건강운", "🏡 Home & Health"),
                t("💕 이성·대인관계", "💕 Love & Relationships"),
                t("🗓️ 월별 흐름(상·하반기 요약)", "🗓️ Month-by-Month Flow (H1/H2 summary)")]
    basis = [_verdict_basis(strength, yong),
             t(f"{year} 세운(올해 간지): {se['ganji']} — 천간십신 {se['천간십신']}",
               f"{year} yearly ganji: {_g(se['ganji'])} — stem god {term(se['천간십신'])}"),
             t("월별 세운 12달 + 오행 분포로 흐름 산출",
               "Flow derived from 12 monthly ganji + element distribution")]
    return _run("saeun", t(f"{year} 신년운세", f"{year} New Year Fortune"),
                t(f"{year}년 한 해의 흐름을 풀어주세요.",
                  f"Interpret the flow of the year {year}."),
                sections, facts, _forbid(strength),
                require=_require_values(strength, yong, with_yong=True),
                basis=basis + tbasis, source=_source_label(preset_id), **kw)


def pyeongsaeng_report(birth, *, gender=None, year=None, preset_id=DEFAULT_PRESET, **kw) -> Report:
    """평생운세 — 초년·중년·말년 + 형제·자식·부부·직업. (year 인자는 무시)"""
    ch = _chart(birth, preset_id)
    r = interpret(birth, [preset_id], gender=gender)
    vline, strength, yong, tbasis = _verdict_line(birth, gender, None, preset_id)
    stages_txt = t("(대운 정보 없음 — 성별 미입력)",
                   "(no decade-cycle info — gender not given)")
    _stage_en = {"초년": "Early years", "중년": "Middle years", "말년": "Later years"}
    _yk_en = {"형제": "Siblings", "자식": "Children", "부부": "Spouse", "직업": "Career"}
    if r.get("daeun"):
        st = lifelong.life_stages(ch, r["daeun"])
        stages_txt = "\n".join(
            t(f"    {k}: " + ", ".join(f"{p['나이']}세 {p['간지']}" for p in v["대운"]),
              f"    {_stage_en.get(k, k)}: "
              + ", ".join(f"age {p['나이']} {_g(p['간지'])}" for p in v["대운"]))
            for k, v in st.items())
    yk = lifelong.yukchin(ch, gender)
    yk_txt = "\n".join(
        t(f"    [{k}] {v['hint']}", f"    [{_yk_en.get(k, k)}] {v['hint']}")
        for k, v in yk.items())
    facts = t(f"{vline}\n- 생애 단계(대운):\n{stages_txt}\n- 육친운:\n{yk_txt}",
              f"{vline}\n- Life stages (decade cycles):\n{stages_txt}\n"
              f"- Family & relations (Ten-God reading):\n{yk_txt}")
    sections = [t("🌱 초년운", "🌱 Early Years"), t("🌳 중년운", "🌳 Middle Years"),
                t("🍂 말년운", "🍂 Later Years"), t("👪 형제운", "👪 Siblings"),
                t("🍼 자식운", "🍼 Children"), t("💑 부부운", "💑 Marriage"),
                t("💼 직업운", "💼 Career")]
    basis = [_verdict_basis(strength, yong),
             t("대운(10년 주기)을 초년·중년·말년 단계로 구분",
               "Decade cycles grouped into early / middle / later life stages"),
             t("형제·자식·부부·직업은 십신(관계 기운)으로 산출",
               "Siblings, children, marriage, and career derived from the Ten Gods")]
    return _run("pyeongsaeng", t("평생운세", "Lifetime Fortune"),
                t("타고난 한평생의 큰 흐름을 풀어주세요.",
                  "Interpret the big arc of this person's whole life."),
                sections, facts, _forbid(strength),
                require=_require_values(strength, yong, with_yong=True),
                basis=basis + tbasis, source=_source_label(preset_id), **kw)


def daeun_report(birth, *, gender=None, year=None, preset_id=DEFAULT_PRESET, **kw) -> Report:
    """대운별(10년) 해석 — 생애 10년 단위 큰 흐름 + 용신 부합 시기. (성별 필수, year 무시)

    대운은 성별(순행/역행)에 의존하므로 gender 가 없으면 산출 불가 → ValueError.
    """
    if gender not in ("남", "여"):
        raise ValueError(t("대운(10년) 해석은 성별이 필요해요 — 순행/역행이 성별로 갈려요.",
                           "Decade-cycle reading needs a gender — forward/reverse order "
                           "depends on it."))
    ch = _chart(birth, preset_id)
    r = interpret(birth, [preset_id], gender=gender)
    vline, strength, yong, tbasis = _verdict_line(birth, gender, None, preset_id)
    daeun = r["daeun"]
    yongsin = r["by_preset"][preset_id].get("yongsin")
    tl = lifelong.daeun_timeline(ch, daeun, yongsin)
    arrow = "순행" if daeun["forward"] else "역행"
    cur = (r.get("current") or {}).get("current_daeun")
    _ages = lambda a: str(a).replace("세", "")  # noqa: E731 — EN 나이 표기용
    cur_txt = t(f"{cur['age']}세 {cur['name']}(천간십신 {cur['천간십신']})" if cur
                else "(아직 첫 대운 시작 전)",
                f"age {cur['age']} {_g(cur['name'])} (stem god {term(cur['천간십신'])})" if cur
                else "(first decade cycle has not started yet)")
    tl_txt = "\n".join(
        t(f"    {x['나이']} {x['간지']}: 천간 {x['천간십신']}({x['천간가족']}) / "
          f"지지 {x['지지십신']}({x['지지가족']}) · {x['용신부합']}",
          f"    ages {_ages(x['나이'])} {_g(x['간지'])}: stem {term(x['천간십신'])} "
          f"({term(x['천간가족'])}) / branch {term(x['지지십신'])} ({term(x['지지가족'])}) · "
          f"{x['용신부합']}") for x in tl)
    facts = t(f"{vline}\n- 대운 방향: {arrow} (첫 대운 {daeun['start_age']}세부터), 성별 {gender}\n"
              f"- 지금 진행 중인 대운: {cur_txt}\n- 대운 10년 단위 타임라인:\n{tl_txt}",
              f"{vline}\n- Cycle direction: {term(arrow)} (first cycle from age "
              f"{daeun['start_age']}), gender {term(gender)}\n"
              f"- Current decade cycle: {cur_txt}\n- Decade timeline:\n{tl_txt}")
    sections = [t("⏳ 대운이란? (10년의 큰 날씨)", "⏳ What Is a Decade Cycle? (10-year weather)"),
                t("📍 지금 나의 대운", "📍 My Current Decade"),
                t("🌊 10년씩 인생 흐름 (대운별로)", "🌊 Life in 10-Year Waves"),
                t("🔀 흐름이 바뀌는 전환점", "🔀 Turning Points"),
                t("🧭 시기별 핵심 조언", "🧭 Advice by Period")]
    intro = t("10년 단위로 바뀌는 인생의 큰 흐름(대운)을 풀어주세요. "
              "특히 '🌊 10년씩 인생 흐름' 섹션에서는 아래 타임라인을 나이대 순서대로 따라가며 "
              "각 10년이 어떤 결인지 한 줄씩 짚고, '용신과 같은 기운(유리)'인 시기를 콕 집어주세요. "
              "간지(갑자·을축 등)는 반드시 한글로만 쓰고 절대 한자(甲子 등)로 바꾸지 마세요. "
              "나이는 '간지'보다 '나이대(예: 29~38세)' 중심으로 말해 읽기 쉽게.",
              "Interpret the big 10-year waves of this life (decade cycles). In the "
              "'🌊 Life in 10-Year Waves' section, walk the timeline below in age order, "
              "give each decade a one-line character, and single out the periods marked "
              "'same energy as your useful god (favorable)'. Write ganji only in the "
              "romanized form given (e.g. 'Gap-ja') — never in Chinese characters. Speak "
              "in age ranges (e.g. 'ages 29-38') rather than ganji so it reads easily.")
    basis = [_verdict_basis(strength, yong),
             t(f"대운 {arrow}, 첫 대운 {daeun['start_age']}세부터 10년 주기",
               f"Decade cycles {term(arrow)}, first cycle from age {daeun['start_age']}"),
             t(f"지금 진행 중인 대운: {cur_txt}", f"Current decade cycle: {cur_txt}"),
             t("각 대운 천간·지지 십신 + 용신 부합 여부로 시기 유불리 산출",
               "Each decade judged by its stem/branch Ten Gods + useful-god match")]
    return _run("daeun", t("대운별(10년) 해석", "Decade Luck Cycles (10-Year Flow)"), intro,
                sections, facts, _forbid(strength),
                require=_require_values(strength, yong, with_yong=False),
                basis=basis + tbasis, source=_source_label(preset_id), **kw)


def aejeong_report(birth, year=2026, *, gender=None, preset_id=DEFAULT_PRESET, **kw) -> Report:
    """애정운/반쪽찾기 — 총론·좋은 달·주의 달 + 인연 조언."""
    ch = _chart(birth, preset_id)
    vline, strength, yong, tbasis = _verdict_line(birth, gender, year, preset_id)
    r = interpret(birth, [preset_id], gender=gender, now_year=year)
    love = r["topics"]["애정·궁합"]
    months = luck.month_luck(ch, year)
    love_fams = {"정재", "편재", "정관", "식신", "상관"}
    good = [_month_label(m["양력월_근사"]) for m in months
            if m["천간십신"] in love_fams or m["지지십신"] in love_fams]
    none_txt = t("특정월 두드러지지 않음", "no single month stands out")
    facts = t(f"{vline}\n- 애정 근거: {love['hint']} / {love['facts']}\n"
              f"- {year} 인연·만남 유리한 달(애정 관련 기운): {', '.join(good) or none_txt}",
              f"{vline}\n- Love basis: {love['hint']} / {love['facts']}\n"
              f"- {year} months favorable for bonds & meetings (love-related energy): "
              f"{', '.join(good) or none_txt}")
    sections = [t("💕 올해 애정 총론", "💕 This Year's Love Overview"),
                t("🌸 인연·만남이 좋은 시기", "🌸 Good Periods for Meeting Someone"),
                t("⚠️ 조심할 시기", "⚠️ Periods to Be Careful"),
                t("💍 솔로/커플 맞춤 조언", "💍 Tailored Advice (Single / Couple)")]
    basis = [_verdict_basis(strength, yong),
             t(f"배우자궁(일지)·배우자성: {love['hint']}",
               f"Spouse palace (day branch) & spouse star: {love['hint']}"),
             t(f"{year} 애정 유리한 달: {', '.join(good) or '특정월 미두드러짐'}",
               f"{year} favorable love months: {', '.join(good) or none_txt}")]
    return _run("aejeong", t(f"{year} 애정운·반쪽찾기", f"{year} Love & Soulmate"),
                t("올해 사랑과 인연의 흐름을 풀어주세요.",
                  "Interpret this year's flow of love and meaningful bonds."),
                sections, facts, _forbid(strength),
                require=_require_values(strength, yong, with_yong=False),
                basis=basis + tbasis, source=_source_label(preset_id), **kw)


def today_report(birth, *, on=None, gender=None, year=None, preset_id=DEFAULT_PRESET, **kw) -> Report:
    """오늘의 운세 — 일진 기반 총평·금전·애정·건강·주의. (year 인자는 무시)"""
    ch = _chart(birth, preset_id)
    d = on or _date.today().isoformat()
    parts = tuple(int(x) for x in d.split("-"))
    dl = luck.day_luck(ch, parts)
    vline, strength, yong, tbasis = _verdict_line(birth, gender, parts[0], preset_id)
    facts = t(f"{vline}\n- 오늘({dl['date']}) 일진: {dl['ganji']} — 천간 {dl['천간십신']}, "
              f"지지 {dl['지지십신']}, 신살 {', '.join(dl['신살']) or '없음'}, "
              f"점수 {dl['score']}/100({dl['길흉']})",
              f"{vline}\n- Today's ({dl['date']}) day pillar: {_g(dl['ganji'])} — stem "
              f"{term(dl['천간십신'])}, branch {term(dl['지지십신'])}, stars "
              f"{_sinsal_list(dl['신살'])}, score {dl['score']}/100 ({_gil(dl['길흉'])})")
    sections = [t("🌅 오늘 총평", "🌅 Today Overview"), t("💰 금전·일", "💰 Money & Work"),
                t("💕 애정·인연", "💕 Love & Bonds"), t("🩺 건강·주의", "🩺 Health & Caution"),
                t("🍀 오늘의 팁", "🍀 Today's Tip")]
    basis = [t(f"오늘 일진(날짜 간지): {dl['ganji']} — 천간십신 {dl['천간십신']}",
               f"Today's day pillar: {_g(dl['ganji'])} — stem god {term(dl['천간십신'])}"),
             t(f"신살: {', '.join(dl['신살']) or '없음'} · 점수 {dl['score']}/100({dl['길흉']})",
               f"Stars: {_sinsal_list(dl['신살'])} · score {dl['score']}/100 "
               f"({_gil(dl['길흉'])})"),
             _verdict_basis(strength, yong)]
    return _run("today", t(f"오늘의 운세 ({dl['date']})", f"Today's Fortune ({dl['date']})"),
                t("오늘 하루의 기운을 풀어주세요.", "Interpret the energy of this one day."),
                sections, facts, _forbid(strength), basis=basis + tbasis,
                source=t("자평 일진(日辰) · 신살", "Ziping day pillar (Iljin) · symbolic stars"),
                **kw)


def week_report(birth, *, start=None, gender=None, year=None, preset_id=DEFAULT_PRESET, **kw) -> Report:
    """주간 운세 — 7일 일진 흐름. (year 인자는 무시)"""
    ch = _chart(birth, preset_id)
    s = start or _date.today().isoformat()
    parts = tuple(int(x) for x in s.split("-"))
    days = luck.week_luck(ch, parts)
    dtxt = "\n".join(
        t(f"    {x['date']} {x['ganji']}: {x['score']}점({x['길흉']}), "
          f"신살 {', '.join(x['신살']) or '-'}",
          f"    {x['date']} {_g(x['ganji'])}: {x['score']} pts ({_gil(x['길흉'])}), "
          f"stars {', '.join(term(s2) for s2 in x['신살']) or '-'}") for x in days)
    vline, strength, yong, tbasis = _verdict_line(birth, gender, parts[0], preset_id)
    facts = t(f"{vline}\n- 이번 주 일진:\n{dtxt}",
              f"{vline}\n- This week's day pillars:\n{dtxt}")
    sections = [t("📅 이번 주 총평", "📅 Week Overview"),
                t("📈 가장 좋은 날", "📈 Best Days"),
                t("📉 조심할 날", "📉 Days to Be Careful"),
                t("🎯 주간 전략", "🎯 Weekly Strategy")]
    basis = [t("이번 주 7일 일진(날짜 간지)별 신살·점수 산출",
               "Stars & scores computed for each of this week's 7 day pillars"),
             t(f"기간: {days[0]['date']} ~ {days[-1]['date']}",
               f"Period: {days[0]['date']} ~ {days[-1]['date']}"),
             _verdict_basis(strength, yong)]
    return _run("week", t("주간 운세", "Weekly Fortune"),
                t("이번 주 7일의 흐름을 풀어주세요.", "Interpret the flow of these 7 days."),
                sections, facts, _forbid(strength), basis=basis + tbasis,
                source=t("자평 일진(日辰) · 신살", "Ziping day pillar (Iljin) · symbolic stars"),
                **kw)


def tojeong_report(birth, year=2026, *, gender=None, preset_id=DEFAULT_PRESET, **kw) -> Report:
    """토정비결 — 작괘(괘번호) + 올해 총론·재물·신상."""
    ch = _chart(birth, preset_id)
    g = tojeong.tojeong_gwae(birth, year)
    vline, strength, yong, tbasis = _verdict_line(birth, gender, year, preset_id)
    se = luck.saeun(ch, year)
    facts = t(f"{vline}\n- {year} 토정비결 괘: {g['괘번호']} (상괘 {g['상괘']}·중괘 {g['중괘']}·하괘 {g['하괘']}), "
              f"세는나이 {g['age']}세, 음력 생월 {g['음력']['month']}월 {g['음력']['day']}일\n"
              f"- {year} 세운: {se['ganji']}(천간 {se['천간십신']})\n"
              f"- 참고: 괘 풀이는 작괘 결과와 사주에 근거한 해석이며 전통 괘사 원문이 아님",
              f"{vline}\n- {year} Tojeong Bigyeol hexagram: {g['괘번호']} (upper {g['상괘']} · "
              f"middle {g['중괘']} · lower {g['하괘']}), Korean age {g['age']}, lunar birth "
              f"month {g['음력']['month']}, day {g['음력']['day']}\n"
              f"- {year} yearly ganji: {_g(se['ganji'])} (stem {term(se['천간십신'])})\n"
              f"- Note: the hexagram reading interprets the cast numbers plus the Saju chart — "
              f"it is not a quotation of the traditional verse text")
    sections = [t("🔮 올해 총운(괘 풀이)", "🔮 Year Overview (Hexagram Reading)"),
                t("💰 재물운", "💰 Wealth"),
                t("🧭 신상·관재(주의할 일)", "🧭 Personal Matters & Things to Watch"),
                t("🌟 한 해 길잡이", "🌟 Guide for the Year")]
    basis = [t(f"토정비결 괘: {g['괘번호']} (상괘 {g['상괘']}·중괘 {g['중괘']}·하괘 {g['하괘']})",
               f"Tojeong hexagram: {g['괘번호']} (upper {g['상괘']} · middle {g['중괘']} · "
               f"lower {g['하괘']})"),
             t(f"작괘: 세는나이 {g['age']}세 + 음력 생월·생일(선천수 기반)",
               f"Cast from Korean age {g['age']} + lunar birth month/day (innate numbers)"),
             t(f"{year} 세운: {se['ganji']} · {_verdict_basis(strength, yong)}",
               f"{year} yearly ganji: {_g(se['ganji'])} · {_verdict_basis(strength, yong)}")]
    return _run("tojeong", t(f"{year} 토정비결", f"{year} Tojeong Bigyeol"),
                t(f"{year}년 토정비결 괘({g['괘번호']})로 한 해를 풀어주세요.",
                  f"Interpret the year {year} through Tojeong Bigyeol hexagram {g['괘번호']}. "
                  f"Tojeong Bigyeol is Korea's beloved New Year divination classic."),
                sections, facts, _forbid(strength),
                basis=basis + tbasis,
                source=t("토정비결 작괘법(선천수) + 사주 보조",
                         "Tojeong Bigyeol hexagram casting + Saju support"), **kw)


def gunghap_report(birth, *, partner=None, gender=None, year=None,
                   preset_id=DEFAULT_PRESET, **kw) -> Report:
    """궁합 — 두 사람 합 점수 + 항목별 + 조언. (year·preset_id 인자는 무시 — 궁합은 유파 무관)"""
    if partner is None:
        raise ValueError(t("궁합은 상대방 생년월일시(partner=BirthInput)가 필요합니다",
                           "Compatibility needs the partner's birth date & time "
                           "(partner=BirthInput)"))
    g = compatibility.gunghap(birth, partner)
    facts = t(f"- 나: {g['a']['eight_chars']} (일간 {g['a']['일간']})\n"
              f"- 상대: {g['b']['eight_chars']} (일간 {g['b']['일간']})\n"
              f"- 총점 {g['총점']}/100 ({g['등급']})\n"
              f"- 일간관계 {g['일간관계']['label']}({g['일간관계']['점수']}), "
              f"일지 {g['일지관계']['label']}({g['일지관계']['점수']}), "
              f"띠 {g['띠관계']['label']}({g['띠관계']['점수']}), "
              f"오행보완 {g['오행보완']['label']}({g['오행보완']['점수']})\n"
              f"- 근거: {'; '.join(g['근거'])}",
              f"- Me: {_eight(g['a']['eight_chars'])} (Day Master {stem_en(g['a']['일간'])})\n"
              f"- Partner: {_eight(g['b']['eight_chars'])} "
              f"(Day Master {stem_en(g['b']['일간'])})\n"
              f"- Total {g['총점']}/100 ({term(g['등급'])})\n"
              f"- Day-stem relation {term(g['일간관계']['label'])} ({g['일간관계']['점수']}), "
              f"day-branch {term(g['일지관계']['label'])} ({g['일지관계']['점수']}), "
              f"zodiac {term(g['띠관계']['label'])} ({g['띠관계']['점수']}), "
              f"element complement {term(g['오행보완']['label'])} ({g['오행보완']['점수']})\n"
              f"- Basis: {'; '.join(g['근거'])}")
    sections = [t("💞 궁합 총평", "💞 Compatibility Overview"),
                t("🔗 두 사람의 결(일간·일지)", "🔗 How Your Textures Meet (day stem & branch)"),
                t("⚖️ 서로 채워주는 기운(오행)", "⚖️ Energies You Fill In for Each Other"),
                t("💡 관계를 위한 조언", "💡 Advice for the Relationship")]
    basis = [t(f"총점 {g['총점']}/100 ({g['등급']})",
               f"Total {g['총점']}/100 ({term(g['등급'])})"),
             t(f"일간 {g['일간관계']['label']} · 일지 {g['일지관계']['label']} · "
               f"띠 {g['띠관계']['label']} · 오행보완 {g['오행보완']['label']}",
               f"Day stem {term(g['일간관계']['label'])} · day branch "
               f"{term(g['일지관계']['label'])} · zodiac {term(g['띠관계']['label'])} · "
               f"element complement {term(g['오행보완']['label'])}"),
             t("가중: 일간 35% · 일지 25% · 띠 20% · 오행보완 20%",
               "Weights: day stem 35% · day branch 25% · zodiac 20% · elements 20%")]
    return _run("gunghap", t("궁합", "Compatibility"),
                t("두 사람의 궁합을 풀어주세요.",
                  "Interpret how these two people match."),
                sections, facts, (), basis=basis,
                source=t("자평 궁합 (일간·일지·삼합·오행보완)",
                         "Ziping compatibility (day stem/branch · harmonies · elements)"),
                **kw)


def wealth_report(birth, year=2026, *, gender=None, preset_id=DEFAULT_PRESET, **kw) -> Report:
    """재물운(부자되기) — 재물 그릇·올해 재물·관리 전략."""
    ch = _chart(birth, preset_id)
    vline, strength, yong, tbasis = _verdict_line(birth, gender, year, preset_id)
    r = interpret(birth, [preset_id], gender=gender, now_year=year)
    wealth = r["topics"]["재물"]
    se = luck.saeun(ch, year)
    facts = t(f"{vline}\n- 재물 근거: {wealth['hint']} / {wealth['facts']}\n"
              f"- {year} 세운: {se['ganji']}(천간 {se['천간십신']})",
              f"{vline}\n- Wealth basis: {wealth['hint']} / {wealth['facts']}\n"
              f"- {year} yearly ganji: {_g(se['ganji'])} (stem {term(se['천간십신'])})")
    sections = [t("💰 나의 재물 그릇", "💰 My Wealth Vessel"),
                t(f"📈 {year} 재물 흐름", f"📈 {year} Money Flow"),
                t("🏦 모으고 지키는 전략", "🏦 Strategies to Build & Protect"),
                t("⚠️ 돈 주의보", "⚠️ Money Cautions")]
    basis = [_verdict_basis(strength, yong),
             t(f"재물 그릇(재성): {wealth['hint']}",
               f"Wealth vessel (Wealth stars): {wealth['hint']}"),
             t(f"{year} 세운: {se['ganji']} — 천간십신 {se['천간십신']}",
               f"{year} yearly ganji: {_g(se['ganji'])} — stem god {term(se['천간십신'])}")]
    return _run("wealth", t(f"{year} 재물운", f"{year} Wealth Fortune"),
                t("타고난 재물 성향과 올해 재물운을 풀어주세요.",
                  "Interpret this person's innate money nature and this year's wealth flow."),
                sections, facts, _forbid(strength),
                require=_require_values(strength, yong, with_yong=True),
                basis=basis + tbasis, source=_source_label(preset_id), **kw)


def health_report(birth, year=2026, *, gender=None, preset_id=DEFAULT_PRESET, **kw) -> Report:
    """건강운 — 오행 균형 기반 약한 곳·올해 건강·관리."""
    ch = _chart(birth, preset_id)
    vline, strength, yong, tbasis = _verdict_line(birth, gender, year, preset_id)
    r = interpret(birth, [preset_id], gender=gender, now_year=year)
    health = r["topics"]["건강"]
    facts = t(f"{vline}\n- 건강 근거: {health['hint']} / {health['facts']}",
              f"{vline}\n- Health basis: {health['hint']} / {health['facts']}")
    sections = [t("🩺 타고난 체질·약한 곳", "🩺 Innate Constitution & Weak Spots"),
                t(f"📅 {year} 건강 흐름", f"📅 {year} Health Flow"),
                t("🌿 생활 관리법", "🌿 Daily Care")]
    basis = [_verdict_basis(strength, yong),
             t(f"오행 균형·결핍·충형: {health['hint']}",
               f"Element balance, gaps, clashes: {health['hint']}")]
    return _run("health", t(f"{year} 건강운", f"{year} Health Fortune"),
                t("타고난 건강 경향과 올해 주의점을 풀어주세요.",
                  "Interpret innate health tendencies and this year's cautions."),
                sections, facts, _forbid(strength),
                require=_require_values(strength, yong, with_yong=False),
                basis=basis + tbasis, source=_source_label(preset_id), **kw)


# 메뉴 카탈로그 (앱에서 노출) — 한국어 원본. 언어 인지형 접근은 catalog() 사용.
CATALOG = [
    ("saeun", "🎊 2026 신년운세", "올 한 해 종합 + 월별 흐름"),
    ("tojeong", "🔮 2026 토정비결", "작괘로 보는 올해 길흉"),
    ("aejeong", "💕 애정운·반쪽찾기", "올해 사랑·인연과 좋은 달"),
    ("gunghap", "💞 궁합", "두 사람 궁합 (상대 생일 필요)"),
    ("wealth", "💰 재물운", "재물 그릇과 올해 돈 흐름"),
    ("pyeongsaeng", "📜 평생운세", "초년·중년·말년 + 가족·직업"),
    ("daeun", "⏳ 대운(10년) 흐름", "10년마다 바뀌는 인생 큰 흐름·시기 운"),
    ("today", "🌅 오늘의 운세", "오늘 일진 풀이"),
    ("week", "📅 주간 운세", "이번 주 7일 흐름"),
    ("health", "🩺 건강운", "체질과 올해 건강"),
]

_CATALOG_EN = {
    "saeun": ("🎊 2026 New Year Fortune", "The whole year + month-by-month flow"),
    "tojeong": ("🔮 2026 Tojeong Bigyeol", "The year's luck by hexagram casting"),
    "aejeong": ("💕 Love & Soulmate", "This year's love, bonds, and good months"),
    "gunghap": ("💞 Compatibility", "Two people's match (partner's birth needed)"),
    "wealth": ("💰 Wealth", "Your money vessel and this year's flow"),
    "pyeongsaeng": ("📜 Lifetime Fortune", "Early/middle/later years + family & career"),
    "daeun": ("⏳ Decade Cycles", "Life's big 10-year waves and their timing"),
    "today": ("🌅 Today's Fortune", "Today's day-pillar reading"),
    "week": ("📅 Weekly Fortune", "This week's 7-day flow"),
    "health": ("🩺 Health", "Constitution and this year's health"),
}


def catalog() -> list[tuple[str, str, str]]:
    """언어 인지형 메뉴 카탈로그 — ko 는 CATALOG 그대로, en 은 영어 라벨/설명."""
    if not is_en():
        return list(CATALOG)
    return [(k, *_CATALOG_EN.get(k, (label, desc))) for k, label, desc in CATALOG]

REPORTS = {
    "saeun": saeun_report, "tojeong": tojeong_report, "aejeong": aejeong_report,
    "gunghap": gunghap_report, "wealth": wealth_report, "pyeongsaeng": pyeongsaeng_report,
    "daeun": daeun_report,
    "today": today_report, "week": week_report, "health": health_report,
}


# 유파(프리셋) 선택 메뉴 노출 순서 — 기본(정통 억부)을 맨 앞에. presets/ 와 자동 동기화.
_PRESET_ORDER = ["jeongtong_eokbu", "johu_centered", "jeonwang_tonggwan",
                 "byeongyak_sinbong", "sammyeong_gobeop", "sinpa_dongsaeng", "mangpa"]


def preset_menu() -> list[tuple[str, str, str]]:
    """유파 선택 메뉴(전문가용 전체): (preset_id, 한글 display_name, description).

    presets/ 디렉터리와 자동 동기화 — 새 YAML을 추가하면 메뉴에도 자동 노출된다(SPEC §0.4).
    일반인용 간편 메뉴는 simple_preset_menu() 참고.
    """
    known = set(list_presets())
    ids = [p for p in _PRESET_ORDER if p in known]
    ids += [p for p in list_presets() if p not in ids]   # 순서 미지정분은 뒤에
    return [(pid,
             i18n.preset_display_name(pid, load_preset(pid).display_name),
             i18n.preset_description(pid, load_preset(pid).description)) for pid in ids]


# ── 일반인용 간편 해석 방식(3종) ──────────────────────────────────────────
# 전문 유파 7종은 일반인에게 너무 어렵다(억부·조후·전왕·병약·삼명통회·신파·맹파).
# 그래서 '표준/현대/전통' 3개 묶음으로 줄여 사주 입력 직후 고르게 한다(설명도 쉬운 말).
# 각 묶음 = 대표 프리셋 1개로 매핑(전부 presets/ 에 실재 — test로 보증). 7종 전부는
# 전문가용 더보기(preset_menu())로 계속 접근 가능. preset_id 별 강약·용신 분기는 그대로다.
SIMPLE_PRESETS: list[tuple[str, str, str]] = [
    ("jeongtong_eokbu", "🌿 표준 (기본)",
     "한국에서 가장 널리 쓰는 방식이에요. 잘 모르겠으면 이걸 고르세요."),
    ("sinpa_dongsaeng", "✨ 현대식",
     "요즘 새로 정리된 방식이에요. 기운의 흐름과 균형을 중시해요."),
    ("sammyeong_gobeop", "📜 전통식",
     "옛 고전을 따라 특별한 기운(신살) 같은 전통 요소를 풍부하게 봐요."),
]


def simple_preset_menu() -> list[tuple[str, str, str]]:
    """일반인용 간편 해석 방식 메뉴: (preset_id, 쉬운 라벨, 쉬운 설명). 앱 버튼용.

    전문가용 전체 7종은 preset_menu(). 맨 앞이 기본값(DEFAULT_PRESET, 표준)이다.
    EN 모드에선 영어 라벨/설명(i18n.SIMPLE_PRESET_EN)으로 바뀐다.
    """
    if not is_en():
        return list(SIMPLE_PRESETS)
    return [(pid, *i18n.SIMPLE_PRESET_EN.get(pid, (label, desc)))
            for pid, label, desc in SIMPLE_PRESETS]


def run_report(kind: str, birth: BirthInput, **kw) -> Report:
    """카테고리 kind 의 리포트 생성.

    kw: year/gender/partner/on/start/model/timeout/trace + **preset_id**(해석 유파).
    preset_id 미지정 시 DEFAULT_PRESET(정통 억부). 궁합은 유파 무관(무시).
    """
    if kind not in REPORTS:
        raise ValueError(t(f"알 수 없는 운세 카테고리: {kind}",
                           f"Unknown fortune category: {kind}"))
    return REPORTS[kind](birth, **kw)
