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


def build_fusion_prompt(facts: dict) -> str:
    s, p = facts["saju"], facts["philo"]
    ys = s["yongsin"]
    yongsin_str = f"{ys.get('element', '?')} 기운({ys.get('family', '?')})" if ys else "미상"
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

아래 섹션 제목 그대로, '한 사람'의 통합 보고서를 작성하라:

## 🤝 두 렌즈가 겹치는 곳
사주의 성향(강약·오행·성향 힌트)과 철학 진단(철학자들의 입장)이 서로 공명하는
지점 2~3가지를, 양쪽 값을 직접 인용하며 풀어낸다.

## ⚡ 두 렌즈가 어긋나는 곳
타고난 결(사주)과 살아온 생각(철학)이 긴장하는 지점을 정직하게 짚는다.
어긋남이 약하면 약하다고 말한다.

## 🪞 하나로 읽기
타고난 결 위에 살아온 생각이 어떻게 얹혀 지금의 '나'가 되었는지 한 문단으로
종합한다. 용신({yongsin_str})이 철학적 성향과 어떻게 이어지는지 언급한다.

## 🌱 앞으로의 한 걸음
두 렌즈를 함께 고려한 실천적 제안 2가지 — 사주 근거 1개, 철학 근거 1개를 각각 인용.

작성 규칙:
- 반드시 한국어. 간지·오행은 한글로만(한자 금지). 철학자는 이름으로 지칭.
- 위 렌즈 값에 없는 사실(다른 간지·다른 철학자·구체 사건 예언)은 지어내지 말 것.
- 섹션당 4~7문장. 어조는 존중하며 안내하듯이. 단정 대신 '~한 결이 있다' 수준.
- 참고자료 목록은 시스템이 따로 붙이므로 쓰지 말 것."""


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
