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
from engine.interpret import interpret
from engine.reports import DEFAULT_PRESET
from philosophy import store as philo_store

FUSION_TITLE = "🔗 두 렌즈로 본 나 — 사주 × 철학"


def missing_parts(username: str) -> list[str]:
    """통합 리포트에 부족한 재료 목록 — 비어 있으면 생성 가능."""
    missing = []
    if saju_store.get_profile(username) is None:
        missing.append("사주 프로필(🔮 프로필에서 생년월일시 입력)")
    diag = philo_store.get_diagnosis(username)
    if not diag or not diag.get("top_philosophers"):
        missing.append("철학 진단(🧭 프로필에서 가치관 한 문장)")
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


def _yongsin_str(s: dict) -> str:
    ys = s.get("yongsin") or {}
    return f"{ys.get('element', '?')} 기운({ys.get('family', '?')})" if ys else "미상"


def fusion_summary_table(facts: dict) -> str:
    """맨 앞의 '한눈에 보기' 표 — 결정론 값만, 시스템이 생성(LLM 비관여)."""
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


def build_fusion_prompt(facts: dict) -> str:
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


def fusion_footer(facts: dict) -> str:
    """결정론 근거 푸터 — LLM 비관여(사주 리포트와 같은 규약)."""
    s, p = facts["saju"], facts["philo"]
    b = facts["birth"]
    ys = s["yongsin"]
    phils = ", ".join(t.get("label", "?") for t in p["top_philosophers"][:3])
    return (f"\n\n---\n> 📎 **이 보고서의 근거** — 命: {b.year}-{b.month:02d}-{b.day:02d} "
            f"{b.hour:02d}:{b.minute:02d} ({facts.get('gender') or '성별 미지정'}) · "
            f"팔자 {s['eight_chars']} · {s['strength']} · 용신 {ys.get('element', '?')} · "
            f"기준 유파 표준(정통 억부) / 哲: \"{(p['query'] or '')[:40]}…\" → "
            f"{phils} (SEP 지식그래프 회수) · 두 값은 각 프로필에서 언제든 재현 가능")
