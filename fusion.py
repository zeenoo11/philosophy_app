"""사주 × 철학 통합 리포트 — 두 렌즈를 한 장의 보고서로.

재료(모두 저장된 결정론/진단 값 — 즉석 계산 아님이 아니라, 사주는 저장된
생년월일로 즉석 재계산(결정론이라 항상 동일), 철학은 최근 진단을 읽는다):
  命  engine.interpret — 팔자·일간·오행 분포·강약·용신·성향 힌트 (표준 프리셋)
  哲  philosophy.store — 가치관 문장·top 철학자·지지 주장

LLM 은 두 렌즈의 값 '안에서만' 공명/긴장을 서술하고, 근거 푸터는 결정론으로
붙인다(사주 리포트와 같은 규약).
"""
from __future__ import annotations

from engine import store as saju_store
from engine.i18n import ganji_en, is_en, stem_en, t, term
from engine.interpret import interpret
from engine.reports import DEFAULT_PRESET
from philosophy import store as philo_store

FUSION_TITLE = "🔗 두 렌즈로 본 나 — 사주 × 철학"
FUSION_TITLE_EN = "🔗 Me Through Two Lenses — Saju × Philosophy"


def fusion_title() -> str:
    """표시용 제목 — 언어 인지(표시 시점 호출). app.py 는 FUSION_TITLE 대신 이걸 쓸 것."""
    return t(FUSION_TITLE, FUSION_TITLE_EN)


def missing_parts(username: str) -> list[str]:
    """통합 리포트에 부족한 재료 목록 — 비어 있으면 생성 가능."""
    missing = []
    if saju_store.get_profile(username) is None:
        missing.append(t("사주 프로필(🔮 프로필에서 생년월일시 입력)",
                         "saju profile (enter your birth date/time in the 🔮 profile)"))
    diag = philo_store.get_diagnosis(username)
    if not diag or not diag.get("top_philosophers"):
        missing.append(t("철학 진단(🧭 프로필에서 가치관 한 문장)",
                         "philosophy diagnosis (share one sentence about your values "
                         "in the 🧭 profile)"))
    return missing


def gather_facts(username: str) -> dict | None:
    """두 렌즈의 재료 수집 → dict (부족하면 None — missing_parts 로 안내)."""
    prof = saju_store.get_profile(username)
    diag = philo_store.get_diagnosis(username)
    if prof is None or not diag or not diag.get("top_philosophers"):
        return None
    r = interpret(prof["birth"], [DEFAULT_PRESET], gender=prof.get("gender"))
    bp = r["by_preset"][DEFAULT_PRESET]
    d = bp["deterministic"]
    topics = r.get("topics") or {}
    return {
        "username": username,
        "birth": prof["birth"],
        "gender": prof.get("gender"),
        "saju": {
            "eight_chars": d["eight_chars"],
            "day_master": f"{d['day_master']}({d['day_master_element']})",
            "elements": d["element_distribution"],
            "strength": bp.get("strength"),
            "yongsin": bp.get("yongsin") or {},
            "nature_hint": (topics.get("성향") or {}).get("hint", ""),
        },
        "philo": {
            "query": diag.get("query") or "",
            "top_philosophers": diag["top_philosophers"][:5],
        },
    }


# ── 표시 변환(EN 전용) — facts 내부 값은 한국어 정체성 키 그대로 두고,
#    표시(표·프롬프트·푸터) 직전에만 로마자/영어 용어로 바꾼다(i18n 규약).
def _eight_chars_disp(eight_chars: str) -> str:
    """팔자 표시 — en 이면 간지 로마자('무인 계해 …' → 'Mu-in Gye-hae …')."""
    if not is_en():
        return eight_chars
    return " ".join(ganji_en(g) for g in eight_chars.split())


def _day_master_disp(day_master: str) -> str:
    """일간 표시 — '임(수)' → en 'Im (Water)'. 형식이 다르면 원문 그대로."""
    if not is_en():
        return day_master
    if len(day_master) == 4 and day_master[1] == "(" and day_master[3] == ")":
        return f"{stem_en(day_master[0])} ({term(day_master[2])})"
    return day_master


def _gender_disp(gender: str | None) -> str:
    return term(gender) if gender else t("성별 미지정", "gender unspecified")


def _yongsin_str(s: dict) -> str:
    ys = s.get("yongsin") or {}
    if is_en():
        return (f"{term(ys.get('element', '?'))} energy ({term(ys.get('family', '?'))})"
                if ys else "unknown")
    return f"{ys.get('element', '?')} 기운({ys.get('family', '?')})" if ys else "미상"


def fusion_summary_table(facts: dict) -> str:
    """맨 앞의 '한눈에 보기' 표 — 결정론 값만, 시스템이 생성(LLM 비관여)."""
    if is_en():
        return _fusion_summary_table_en(facts)
    s, p = facts["saju"], facts["philo"]
    b = facts["birth"]
    tops = p["top_philosophers"]
    phils = " · ".join(t.get("label", "?") for t in tops[:3])
    n_support = sum(int(t.get("n_support") or 0) for t in tops)
    q = (p["query"] or "").strip()
    if len(q) > 42:
        q = q[:42] + "…"
    return "\n".join([
        "## 📋 한눈에 보기",
        "",
        "| | 🔮 命 — 사주 렌즈 | 🧭 哲 — 철학 렌즈 |",
        "|---|---|---|",
        f"| 입력 | {b.year}-{b.month:02d}-{b.day:02d} {b.hour:02d}:{b.minute:02d}"
        f" ({facts.get('gender') or '성별 미지정'}) | “{q}” |",
        f"| 핵심 | 팔자 {s['eight_chars']} · 일간 {s['day_master']} | 가까운 철학자: {phils} |",
        f"| 나의 결 | {s['strength']} · 용신 {_yongsin_str(s)} | 유사 주장 {n_support}건이 근거"
        f" (SEP 지식그래프) |",
    ])


def _fusion_summary_table_en(facts: dict) -> str:
    """영어판 '한눈에 보기' 표 — 값은 i18n 로마자/용어로만(한글 없음)."""
    s, p = facts["saju"], facts["philo"]
    b = facts["birth"]
    tops = p["top_philosophers"]
    phils = " · ".join(t.get("label", "?") for t in tops[:3])
    n_support = sum(int(t.get("n_support") or 0) for t in tops)
    q = (p["query"] or "").strip()
    if len(q) > 42:
        q = q[:42] + "…"
    return "\n".join([
        "## 📋 At a Glance",
        "",
        "| | 🔮 命 — Saju Lens | 🧭 哲 — Philosophy Lens |",
        "|---|---|---|",
        f"| Input | {b.year}-{b.month:02d}-{b.day:02d} {b.hour:02d}:{b.minute:02d}"
        f" ({_gender_disp(facts.get('gender'))}) | “{q}” |",
        f"| Core | Eight characters {_eight_chars_disp(s['eight_chars'])} · Day Master "
        f"{_day_master_disp(s['day_master'])} | Closest philosophers: {phils} |",
        f"| My grain | {term(s.get('strength') or '?')} · Useful god {_yongsin_str(s)} | "
        f"Grounded in {n_support} similar claims (SEP knowledge graph) |",
    ])


def build_fusion_prompt(facts: dict) -> str:
    if is_en():
        return _build_fusion_prompt_en(facts)
    s, p = facts["saju"], facts["philo"]
    yongsin_str = _yongsin_str(s)
    phil_lines = "\n".join(
        f"- {t.get('label')} (점수 {t.get('score')}, 유사주장 {t.get('n_support')}건)"
        for t in p["top_philosophers"])
    return f"""당신은 동양 명리와 서양 철학을 함께 읽는 통합 해석가다.
아래 [命 사주 렌즈]는 결정론 계산값이고, [哲 철학 렌즈]는 사용자의 가치관 문장을
SEP 철학 지식그래프에서 진단한 결과다. 두 렌즈의 값 안에서만 서술하라.

[命 사주 렌즈 — 타고난 결]
- 팔자: {s['eight_chars']} · 일간 {s['day_master']}
- 오행 분포: {s['elements']}
- 강약: {s['strength']} · 용신(가장 이로운 기운): {yongsin_str}
- 성향 힌트: {s['nature_hint']}

[哲 철학 렌즈 — 살아온 생각]
- 가치관 문장: "{p['query']}"
- 가까운 철학자:
{phil_lines}

아래 섹션 제목 그대로, '한 사람'의 통합 보고서를 작성하라
(요약 표는 시스템이 이미 앞에 붙였다 — 다시 만들지 말 것):

## 🤝 두 렌즈가 겹치는 곳
먼저 아래 형식의 마크다운 표로 공명 지점 2~3행을 정리한다:

| 命 사주에서 | 哲 철학에서 | 만나는 지점 |
|---|---|---|

표 아래에 3~5문장으로 자연스럽게 풀어 설명한다. 양쪽 값을 직접 인용한다.

## ⚡ 두 렌즈가 어긋나는 곳
타고난 결(사주)과 살아온 생각(철학)이 긴장하는 지점을 4~6문장으로 정직하게 짚는다.
어긋남이 약하면 약하다고 말한다.

## 🪞 하나로 읽기
타고난 결 위에 살아온 생각이 어떻게 얹혀 지금의 '나'가 되었는지 한 문단(4~6문장)으로
종합한다. 용신({yongsin_str})이 철학적 성향과 어떻게 이어지는지 언급한다.

## 🌱 앞으로의 한 걸음
번호 목록 2개 — 1은 사주 근거, 2는 철학 근거를 각각 명시한 실천 제안.

작성 규칙(반드시 지킬 것):
- 전체를 부드러운 존댓말(-습니다/-어요)로 일관되게 쓴다. 반말·문어체 평서형(-했다/-이다) 금지.
- 별표 굵게(** **)를 절대 쓰지 않는다. 강조가 필요하면 '작은따옴표'로 감싼다.
- 반드시 한국어. 간지·오행은 한글로만(한자 금지). 철학자는 이름으로 지칭.
- 위 렌즈 값에 없는 사실(다른 간지·다른 철학자·구체 사건 예언)은 지어내지 말 것.
- 단정 대신 '∼한 결이 있어요' 수준의 어조. 참고자료 목록은 시스템이 따로 붙이므로 쓰지 말 것."""


def _build_fusion_prompt_en(facts: dict) -> str:
    """영어판 통합 프롬프트 — 섹션 구조는 한국어판과 동일, 출력은 한글/CJK 금지."""
    s, p = facts["saju"], facts["philo"]
    yongsin_str = _yongsin_str(s)
    elements = " · ".join(f"{term(k)} {v}" for k, v in s["elements"].items())
    phil_lines = "\n".join(
        f"- {t.get('label')} (score {t.get('score')}, {t.get('n_support')} similar claims)"
        for t in p["top_philosophers"])
    return f"""You are an integrative interpreter who reads Eastern Four Pillars (Saju) and Western philosophy together.
The [Saju lens] below holds deterministically computed values; the [Philosophy lens] holds
the diagnosis of the user's values statement against the SEP philosophy knowledge graph.
Stay strictly within the values of these two lenses.

[Saju lens — the grain you were born with]
- Eight characters: {_eight_chars_disp(s['eight_chars'])} · Day Master {_day_master_disp(s['day_master'])}
- Five-element distribution: {elements}
- Strength: {term(s.get('strength') or '?')} · Useful god (most helpful energy): {yongsin_str}
- Temperament hint (internal note in Korean — restate its meaning in English, never quote it): {s['nature_hint']}

[Philosophy lens — the thinking you have lived]
- Values statement: "{p['query']}"
- Closest philosophers:
{phil_lines}

Using exactly the section titles below, write an integrated report of 'one person'
(the summary table is already prepended by the system — do not create another):

## 🤝 Where the Two Lenses Overlap
First arrange 2-3 points of resonance as a markdown table in this format:

| In the Saju | In the Philosophy | Where They Meet |
|---|---|---|

Below the table, unpack it naturally in 3-5 sentences, quoting values from both lenses directly.

## ⚡ Where the Two Lenses Diverge
In 4-6 sentences, honestly name where the inborn grain (Saju) and the lived thinking
(philosophy) are in tension. If the tension is weak, say it is weak.

## 🪞 Reading Them as One
In one paragraph (4-6 sentences), synthesize how the lived thinking has settled over the
inborn grain to become the present 'me'. Mention how the useful god ({yongsin_str})
connects with the philosophical leaning.

## 🌱 One Step Forward
A numbered list of exactly 2 items — practical suggestions, item 1 explicitly grounded in
the Saju, item 2 explicitly grounded in the philosophy.

Writing rules (must be followed):
- Write the entire report in natural English. Do not output any Korean (Hangul), Chinese,
  or other CJK characters — refer to Saju terms only by the English names given above.
- Never use asterisk bold (** **). If emphasis is needed, wrap words in 'single quotes'.
- Refer to philosophers by name. Do not invent facts absent from the lens values above
  (no other pillars, no other philosophers, no concrete event predictions).
- Prefer a soft, suggestive tone ('there is a grain of ...') over flat assertions.
- Do not write a reference list — the system appends one separately."""


def fusion_footer(facts: dict) -> str:
    """결정론 근거 푸터 — LLM 비관여(사주 리포트와 같은 규약)."""
    if is_en():
        return _fusion_footer_en(facts)
    s, p = facts["saju"], facts["philo"]
    b = facts["birth"]
    ys = s["yongsin"]
    phils = ", ".join(t.get("label", "?") for t in p["top_philosophers"][:3])
    return (f"\n\n---\n> 📎 **이 보고서의 근거** — 命: {b.year}-{b.month:02d}-{b.day:02d} "
            f"{b.hour:02d}:{b.minute:02d} ({facts.get('gender') or '성별 미지정'}) · "
            f"팔자 {s['eight_chars']} · {s['strength']} · 용신 {ys.get('element', '?')} · "
            f"기준 유파 표준(정통 억부) / 哲: \"{(p['query'] or '')[:40]}…\" → "
            f"{phils} (SEP 지식그래프 회수) · 두 값은 각 프로필에서 언제든 재현 가능")


def _fusion_footer_en(facts: dict) -> str:
    """영어판 근거 푸터 — 값은 i18n 로마자/용어로만(한글 없음)."""
    s, p = facts["saju"], facts["philo"]
    b = facts["birth"]
    ys = s["yongsin"]
    phils = ", ".join(t.get("label", "?") for t in p["top_philosophers"][:3])
    return (f"\n\n---\n> 📎 **Sources of this report** — 命: {b.year}-{b.month:02d}-{b.day:02d} "
            f"{b.hour:02d}:{b.minute:02d} ({_gender_disp(facts.get('gender'))}) · "
            f"eight characters {_eight_chars_disp(s['eight_chars'])} · "
            f"{term(s.get('strength') or '?')} · useful god {term(ys.get('element', '?'))} · "
            f"reference school Standard (Classic Eokbu) / 哲: \"{(p['query'] or '')[:40]}…\" → "
            f"{phils} (retrieved from the SEP knowledge graph) · both values can be "
            f"reproduced anytime from your profiles")
