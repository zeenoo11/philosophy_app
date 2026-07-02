"""철학 탐구 서비스 — 플랫폼 '🧭 철학 탐구' 프로필 핸들러.

legacy(Streamlit·LangChain) 철학 앱을 사주와 같은 스택으로 재구축:
대화 유도·점수화는 philosophy.analysis(LLM, OpenRouter/claude 자동),
사상 매칭·사용자 연결은 philosophy.matching(결정론), 영속은
philosophy.store(사주와 같은 sqlite).

흐름:
  1) 첫 질문(랜덤) → 답할 때마다 현재 축을 0~10 으로 점수화(누적)
  2) LLM 이 공감 멘트 + 다음 질문을 골라 대화를 잇는다
  3) 답변 3개부터 '분석 시작' — 7축 좌표 + 닮은/정반대 사상 + 근거 푸터
  4) 로그인 상태면 결과가 저장되고, 다른 사용자와의 철학 유사도 랭킹
     ('나와 닮은 영혼')을 볼 수 있다 — 사주의 궁합 매칭과 대칭 구조.
"""
from __future__ import annotations

import re

import chainlit as cl

from philosophy import analysis, matching
from philosophy import store as philo_store
from philosophy.matching import AXES, AXIS_LABELS

MIN_ANSWERS = 3   # 분석을 열어주는 최소 답변 수(적으면 축 커버리지가 빈약)

WELCOME = (
    "## 🧭 철학 탐구\n"
    "당신의 생각·고민·가치관을 자유롭게 들려주세요. 대화가 쌓이면 **7가지 축**"
    "(주체성·판단 근거·지향점·세계관·시간·형이상학·사회성)으로 분석해서\n"
    "**당신과 가장 닮은 철학 사상**을 찾아드려요.\n\n"
    "- 답변 3개부터 `분석 시작` 버튼(또는 '분석'이라고 입력)으로 리포트를 볼 수 있어요.\n"
    "- 로그인하면 결과가 저장되고, **나와 철학이 닮은 사용자**도 찾아볼 수 있어요."
)


def _username() -> str | None:
    u = cl.user_session.get("user")
    return getattr(u, "identifier", None) if u else None


def _messages() -> list[dict]:
    return cl.user_session.get("philo_messages") or []


def _answers_count() -> int:
    return sum(1 for m in _messages() if m["role"] == "user")


def _add_cost(meta: dict) -> float:
    cost = cl.user_session.get("philo_cost") or 0.0
    if meta and meta.get("cost_usd"):
        try:
            cost += float(meta["cost_usd"])
        except (TypeError, ValueError):
            pass
    cl.user_session.set("philo_cost", cost)
    return cost


def _analysis_actions() -> list[cl.Action]:
    acts = [cl.Action(name="philo_analyze", payload={}, label="🧐 분석 시작",
                      tooltip="지금까지의 대화로 7축 철학 좌표를 계산")]
    if _username():
        acts.append(cl.Action(name="philo_match_users", payload={},
                              label="🤝 나와 닮은 영혼 찾기",
                              tooltip="다른 사용자와의 철학 유사도 랭킹"))
    acts.append(cl.Action(name="philo_restart", payload={}, label="🔄 새 대화"))
    return acts


async def _ask_question(q: dict, *, prefix: str = "") -> None:
    """질문 1개를 전송하고 현재 축·물은 질문을 세션에 기록."""
    asked: set[int] = cl.user_session.get("philo_asked") or set()
    asked.add(q["id"])
    cl.user_session.set("philo_asked", asked)
    cl.user_session.set("philo_axis", q.get("axis"))
    body = f"{prefix}**{q['question']}**\n\n*{q.get('context', '')}*"
    msgs = _messages()
    msgs.append({"role": "assistant", "content": q["question"]})
    cl.user_session.set("philo_messages", msgs)
    await cl.Message(content=body).send()


async def start():
    cl.user_session.set("philo_messages", [])
    cl.user_session.set("philo_axis_scores", {a: [] for a in AXES})
    cl.user_session.set("philo_asked", set())
    cl.user_session.set("philo_axis", None)
    cl.user_session.set("philo_cost", 0.0)

    greeting = WELCOME
    user = _username()
    if user:
        saved = philo_store.get_philo_profile(user)
        if saved and saved.get("top_philosophy"):
            greeting += (f"\n\n> 👋 다시 오셨어요, **{user}**님! 지난 분석에서 당신은 "
                         f"**{saved['top_philosophy']}** 와 가장 닮아 있었어요. "
                         "새 대화로 다시 탐색해볼까요?")
    await cl.Message(content=greeting).send()

    first = analysis.get_random_question()
    if first:
        await _ask_question(first, prefix="첫 질문이에요 🌱\n\n")


async def on_message(message: cl.Message):
    text = message.content.strip()

    # '분석' 요청 — 대화가 충분하면 바로 리포트
    if re.fullmatch(r"(분석|분석\s*시작|결과|리포트)\s*", text):
        await run_analysis()
        return

    msgs = _messages()
    msgs.append({"role": "user", "content": text})
    cl.user_session.set("philo_messages", msgs)

    # ① 현재 축 기준 턴 점수화(누적) — 결정론 아닌 LLM 평가라 Step 으로 투명화
    axis = cl.user_session.get("philo_axis")
    if axis in AXIS_LABELS:
        async with cl.Step(name=f"🧮 답변 분석 중… ({AXIS_LABELS[axis][2]})",
                           type="tool") as step:
            score, meta = await cl.make_async(analysis.analyze_turn)(text, axis)
            _add_cost(meta)
            if score is not None:
                axis_scores = cl.user_session.get("philo_axis_scores") or {a: [] for a in AXES}
                axis_scores.setdefault(axis, []).append(score)
                cl.user_session.set("philo_axis_scores", axis_scores)
                left, right, label = AXIS_LABELS[axis]
                step.output = f"{label}: {score:.0f}/10 ({left} 0 ↔ 10 {right})"
            else:
                step.output = "점수화 보류(모호한 답변)"

    # ② 공감 + 다음 질문
    asked: set[int] = cl.user_session.get("philo_asked") or set()
    async with cl.Step(name="💭 다음 질문 고르는 중…", type="llm") as step:
        reply, next_q, meta = await cl.make_async(analysis.chat_turn)(msgs, asked_ids=asked)
        _add_cost(meta)
        step.output = f"다음 질문: {next_q['topic'] if next_q else '없음(소진)'}"

    n = _answers_count()
    if next_q:
        msgs = _messages()
        msgs.append({"role": "assistant", "content": reply})
        cl.user_session.set("philo_messages", msgs)
        await cl.Message(content=reply).send()
        tail = f"\n\n> 💬 답변 {n}개째" + (" — 이제 분석해볼 수 있어요!" if n == MIN_ANSWERS else "")
        actions = _analysis_actions() if n >= MIN_ANSWERS else []
        await _ask_question(next_q, prefix="")
        if actions:
            await cl.Message(content=tail.strip("\n"), actions=actions).send()
    else:
        await cl.Message(content=f"{reply}\n\n모든 질문을 다 나눴어요. 이제 분석해볼까요?",
                         actions=_analysis_actions()).send()


def _bar(score: float, *, width: int = 20) -> str:
    pos = max(0, min(width, round(score / 10 * width)))
    return "─" * pos + "●" + "─" * (width - pos)


def _final_scores() -> tuple[list[float], list[str]]:
    """축별 최종 점수 — 누적 턴 평균 우선, 빈 축은 전체 분석값/중립(5) 폴백.

    반환: (AXES 순서 점수 리스트, 커버된 축 라벨 리스트)
    """
    axis_scores: dict = cl.user_session.get("philo_axis_scores") or {}
    full = cl.user_session.get("philo_full_scores") or {}
    out, covered = [], []
    for a in AXES:
        turns = axis_scores.get(a) or []
        if turns:
            out.append(sum(turns) / len(turns))
            covered.append(a)
        elif a in full:
            out.append(full[a])
            covered.append(a)
        else:
            out.append(5.0)
    return out, covered


async def run_analysis():
    if _answers_count() == 0:
        await cl.Message(content="아직 나눈 이야기가 없어요. 먼저 질문에 답해주세요 🌱").send()
        return
    msgs = _messages()

    # 전체 분석(LLM) — reasoning + 턴 점수가 없는 축의 폴백 점수
    async with cl.Step(name="🧐 대화 전체를 되짚는 중…", type="llm") as step:
        result, meta = await cl.make_async(analysis.analyze_full)(msgs)
        cost = _add_cost(meta)
        step.output = (f"{meta.get('models')} · {meta.get('duration_ms')}ms · "
                       f"${meta.get('cost_usd')}") if meta else "완료"
    reasoning = ""
    if result:
        cl.user_session.set("philo_full_scores", result["scores"])
        reasoning = result.get("reasoning", "")

    scores, covered = _final_scores()
    ranked = matching.find_matching_philosophies(scores)
    top, top3, bottom = ranked[0], ranked[:3], ranked[-1]

    md = [f"# 🧭 나의 철학 분석 리포트",
          f"\n## 🏛 당신은 **[{top['philosophy']}]** 와 가장 닮았어요 "
          f"({top['match_rate']:.0f}%)"]
    if reasoning:
        md.append(f"\n> 💬 **AI의 분석**: {reasoning}")
    md.append("\n### 🤝 나의 소울메이트 철학 TOP 3")
    for i, m in enumerate(top3, 1):
        md.append(f"**{i}위. {m['philosophy']}** ({m['match_rate']:.0f}%) — {m['summary']}")
    md.append(f"\n### ⚡ 나와 정반대\n**{bottom['philosophy']}** "
              f"({bottom['match_rate']:.0f}%) — {bottom['summary']}\n"
              f"> 이 철학을 가진 사람과의 대화는 아주 흥미로울 거예요!")
    md.append("\n## 📊 나의 철학적 좌표 (7축, 0~10)")
    for a, s in zip(AXES, scores):
        left, right, label = AXIS_LABELS[a]
        mark = "" if a in covered else " *(답변 부족 — 중립 처리)*"
        md.append(f"**{label}**: {s:.1f}{mark}\n`{left} |{_bar(s)}| {right}`")
    md.append(f"\n---\n> 📎 **이 분석의 근거**: 답변 {_answers_count()}개 · "
              f"축별 점수 = 턴별 LLM 평가(0~10)의 평균, 빈 축은 전체 분석/중립(5) 폴백 · "
              f"매칭 = 사상 DB {len(matching.load_philosophy_data())}종과 7축 유클리드 "
              f"거리의 선형 일치율 · 누적 비용 ${cost:.4f}")

    user = _username()
    if user:
        philo_store.save_philo_profile(user, scores,
                                       top_philosophy=top["philosophy"],
                                       reasoning=reasoning or None)
        md.append(f"\n> 💾 **{user}**님의 철학 프로필로 저장했어요 — "
                  "'나와 닮은 영혼 찾기'에 쓰여요.")
    else:
        md.append("\n> 로그인하면 결과가 저장되고, 나와 철학이 닮은 사용자를 찾을 수 있어요.")

    md.append("\n> 🔮 동양의 렌즈로도 나를 보고 싶다면 — 좌측 상단 프로필에서 "
              "**사주 운세**를 선택해보세요.")
    await cl.Message(content="\n".join(md), actions=_analysis_actions()).send()


@cl.action_callback("philo_analyze")
async def on_philo_analyze(action: cl.Action):
    await run_analysis()


@cl.action_callback("philo_restart")
async def on_philo_restart(action: cl.Action):
    await start()


@cl.action_callback("philo_match_users")
async def on_philo_match_users(action: cl.Action):
    user = _username()
    if not user:
        await cl.Message(content="🔐 로그인해야 쓸 수 있는 기능이에요.").send()
        return
    mine = philo_store.get_philo_profile(user)
    if not mine:
        await cl.Message(content="먼저 '분석 시작'으로 내 철학 좌표를 만들어주세요.").send()
        return
    others = philo_store.list_philo_profiles(exclude=user)
    if not others:
        await cl.Message(content="아직 비교할 다른 사용자가 없어요. "
                                 "친구에게 이 플랫폼을 공유해보세요! 🌱").send()
        return
    rows = matching.rank_similar_users(mine["scores"], others)
    lines = ["## 🤝 나와 닮은 영혼", "",
             "| 순위 | 사용자 | 철학 일치율 | 대표 사상 |", "|---|---|---|---|"]
    for i, r in enumerate(rows[:10], 1):
        lines.append(f"| {i} | {r['username']} | {r['match_rate']:.0f}% | "
                     f"{r['top_philosophy'] or '—'} |")
    lines.append("\n> 📎 일치율 = 두 사람의 7축 좌표 간 유클리드 거리의 선형 환산(결정론).")
    await cl.Message(content="\n".join(lines), actions=_analysis_actions()).send()
