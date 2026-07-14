"""철학 탐구 서비스 — PhiloGraph graphRAG 가치관 진단 프로필 핸들러.

Graph-Project C_RAG 의 Chainlit 어댑터(chat_app.py)를 플랫폼 구조로 이식:
메시지(가치관 문장)마다 diagnose(분해→회수→저자 랭킹→진단 조립)를 1회 실행하고
단계를 cl.Step 으로 펼쳐 보인 뒤, 진단문을 LLM(공용 narrator — OpenRouter 스트리밍)
으로 생성한다. 회수 근거(인용문 포함 리포트)는 접이식 Step 으로 첨부.

로그인 상태면 최근 진단(top 철학자 분포)이 저장되고, 다른 사용자와의
'닮은 영혼'(철학자 분포 코사인) 랭킹을 볼 수 있다 — 사주 궁합 매칭과 대칭.
"""
from __future__ import annotations

import re
import threading

import chainlit as cl
from chainlit.input_widget import Select, Slider, Switch

import mdutil
import reports_store
from engine import i18n, narrator
from engine.i18n import is_en, t
from philosophy import store as philo_store
from philosophy import values as schwartz
from philosophy.diagnose import format_diagnosis
from philosophy.pipeline import PhiloRAG

# 무거운 리소스(그래프 19MB + 임베딩 npz + ONNX 모델)는 프로세스당 1회 로드.
_RAG: PhiloRAG | None = None
_RAG_LOCK = threading.Lock()

WELCOME = (
    "## 🧭 철학 탐구 — 가치관 진단\n"
    "당신의 **가치관·생각을 한 문장으로** 들려주세요. "
    "SEP(스탠퍼드 철학 백과) 기반 **지식그래프(3,600 노드)**에서 당신의 생각과 닿는 "
    "주장을 찾고, 그 주장의 **실제 저자**를 따라 가까운 철학자를 진단해드려요.\n\n"
    "- 예: *\"나는 사랑이 삶을 풍요롭게 하지만 동시에 결핍과 고통도 준다고 생각한다\"*\n"
    "- 긴 생각은 자동으로 **핵심 명제**로 분해해 각각 탐색해요.\n"
    "- 모든 진단에는 그래프에서 회수한 **원문 인용 근거**가 따라붙어요.\n"
    "- 로그인하면 진단이 저장되고, **나와 닮은 영혼**(철학자 분포가 겹치는 사용자)도 찾아요."
)

WELCOME_EN = (
    "## 🧭 Philosophy Explorer — Values Diagnosis\n"
    "Tell me your **values or a thought, in one sentence**. "
    "I search a **knowledge graph (3,600 nodes)** built from the SEP (Stanford "
    "Encyclopedia of Philosophy) for claims that touch your idea, and follow those "
    "claims' **actual authors** to diagnose your closest philosophers.\n\n"
    "- e.g. *\"I think love enriches life but at the same time brings lack and pain\"*\n"
    "- Long thoughts are automatically split into **core propositions**, each explored separately.\n"
    "- Every diagnosis comes with **verbatim source quotes** retrieved from the graph.\n"
    "- Log in to save your diagnoses and find **kindred souls** (users whose "
    "philosopher mix overlaps yours)."
)

_GREETING_RE = re.compile(r"^\s*(안녕|하이|hi|hello|ㅎㅇ|반가|테스트)[!~. ]*\s*$", re.I)


def _load_rag() -> PhiloRAG:
    """retriever(그래프+임베딩) 1회 로드 + 워밍업(ONNX 모델 다운로드/로딩 흡수)."""
    global _RAG
    with _RAG_LOCK:
        if _RAG is None:
            rag = PhiloRAG()
            rag.retriever.retrieve("warmup: love enriches life")
            _RAG = rag
    return _RAG


def _username() -> str | None:
    try:
        u = cl.user_session.get("user")
    except Exception:  # noqa: BLE001 — Chainlit 컨텍스트 밖(테스트 등)
        return None
    return getattr(u, "identifier", None) if u else None


def _clean_md(text: str) -> str:
    """마크다운 정리 — 플랫폼 공용 규약(mdutil: 물결표·굵게 정규화)."""
    return mdutil.clean_md(text)


def _actions() -> list[cl.Action]:
    acts = []
    if _username():
        acts.append(cl.Action(name="philo_match_users", payload={},
                              label=t("🤝 나와 닮은 영혼 찾기", "🤝 Find kindred souls"),
                              tooltip=t("철학자 분포가 겹치는 다른 사용자 랭킹",
                                        "Ranking of users whose philosopher mix overlaps yours")))
        acts.append(cl.Action(name="fusion_report", payload={},
                              label=t("🔗 사주×철학 통합 리포트",
                                      "🔗 Saju × Philosophy fusion report"),
                              tooltip=t("두 렌즈(사주·철학 진단)를 한 장의 보고서로",
                                        "Both lenses (saju + philosophy) in one report")))
    return acts


def _lang_action() -> cl.Action:
    """웰컴에 붙는 🌐 전환 버튼 — 콜백(set_lang)은 라우터(app.py)가 등록."""
    if is_en():
        return cl.Action(name="set_lang", payload={"lang": "ko"}, label="🌐 한국어")
    return cl.Action(name="set_lang", payload={"lang": "en"}, label="🌐 English")


async def _send_settings():
    """채팅 설정(⚙️) — 언어·top-N·분해·회수만. 언어가 바뀌면 라벨을 새 언어로 재전송."""
    split = cl.user_session.get("philo_split")
    await cl.ChatSettings([
        Select(id="lang", label="🌐 Language / 언어", values=["한국어", "English"],
               initial_index=1 if is_en() else 0),
        Slider(id="philo_topk", label=t("가까운 철학자 top-N", "Closest philosophers top-N"),
               initial=int(cl.user_session.get("philo_topk") or 8), min=3, max=15, step=1),
        Switch(id="philo_split", label=t("입력을 명제로 분해 (영어 정규화)",
                                         "Split input into propositions (English normalization)"),
               initial=True if split is None else bool(split)),
        Switch(id="philo_retrieve_only", label=t("회수만 보기 (LLM 진단문 생략)",
                                                 "Retrieval only (skip LLM narrative)"),
               initial=bool(cl.user_session.get("philo_retrieve_only"))),
    ]).send()


async def start():
    cl.user_session.set("philo_topk", 8)
    cl.user_session.set("philo_split", True)
    cl.user_session.set("philo_retrieve_only", False)
    await _send_settings()

    greeting = t(WELCOME, WELCOME_EN)
    user = _username()
    if user:
        saved = philo_store.get_diagnosis(user)
        if saved and saved.get("top_philosophers"):
            top = saved["top_philosophers"][0]
            greeting += t(
                (f"\n\n> 👋 다시 오셨어요, **{user}**님! 지난 진단에서 당신과 가장 "
                 f"가까운 철학자는 **{top.get('label')}** 였어요. 새 생각을 들려주세요. "
                 "*(진단은 자동 저장 — [📖 내 기록 (/me)](/me) 에서 다시 볼 수 있어요)*"),
                (f"\n\n> 👋 Welcome back, **{user}**! In your last diagnosis, your closest "
                 f"philosopher was **{top.get('label')}**. Tell me a new thought. "
                 "*(Diagnoses save automatically — revisit them at "
                 "[📖 My records (/me)](/me?lang=en))*"))
    await cl.Message(content=greeting, actions=[_lang_action()]).send()


async def on_settings(settings: dict):
    if "philo_topk" in settings:
        cl.user_session.set("philo_topk", int(settings["philo_topk"]))
    if "philo_split" in settings:
        cl.user_session.set("philo_split", bool(settings["philo_split"]))
    if "philo_retrieve_only" in settings:
        cl.user_session.set("philo_retrieve_only", bool(settings["philo_retrieve_only"]))
    new_lang = "en" if settings.get("lang") == "English" else "ko"
    if new_lang != (cl.user_session.get("lang") or "ko"):
        cl.user_session.set("lang", new_lang)
        i18n.set_lang(new_lang)
        await _send_settings()  # 설정 위젯 라벨도 새 언어로
        await cl.Message(content=t("🌐 이제 **한국어**로 안내할게요.",
                                   "🌐 Switched to **English** — replies will follow."),
                         actions=[_lang_action()]).send()


async def on_message(message: cl.Message):
    query = message.content.strip()
    if not query:
        return
    if _GREETING_RE.match(query):
        await cl.Message(content=t("반가워요! 진단하고 싶은 **가치관이나 생각**을 문장으로 "
                                   "들려주세요 — 예: *\"확실한 지식은 감각 경험이 아니라 "
                                   "이성적 추론에서 나온다\"*",
                                   "Nice to meet you! Tell me, in a sentence, a **value or "
                                   "idea** you'd like diagnosed — e.g. *\"Certain knowledge "
                                   "comes from rational reasoning, not sensory experience\"*")).send()
        return

    lang = cl.user_session.get("lang") or "ko"  # make_async(스레드) 경계 전파용
    top_k = int(cl.user_session.get("philo_topk") or 8)
    split = cl.user_session.get("philo_split")
    split = True if split is None else bool(split)
    retrieve_only = bool(cl.user_session.get("philo_retrieve_only"))

    # 0) 지식그래프·임베딩 로드(최초 1회) — 이후 메시지는 즉시
    if _RAG is None:
        async with cl.Step(name=t("📚 지식그래프 로드 (SEP 3,600노드 + 임베딩)",
                                  "📚 Loading knowledge graph (SEP 3,600 nodes + embeddings)"),
                           type="run") as st:
            await cl.make_async(_load_rag)()
            st.output = t("준비 완료", "Ready")
    rag = _RAG

    # 1) graphRAG 진단 — 단계(분해→회수→랭킹→조립)를 Step 으로 펼친다
    async with cl.Step(name=t("🕸 graphRAG 회수·진단", "🕸 graphRAG retrieval & diagnosis"),
                       type="tool") as parent:
        run = await cl.make_async(i18n.with_lang(rag.diagnose, lang))(
            query, split=split, top_k=top_k)
        for rec in run.steps:
            async with cl.Step(name=rec.name, type="tool") as cstep:
                cstep.output = f"`{rec.ms:.0f} ms`  {rec.summary}"
        diag = run.diagnosis
        top3 = ", ".join(p.label for p in diag.top_philosophers[:3]) or t("(없음)", "(none)")
        parent.output = t("가까운 철학자", "Closest philosophers") + f": {top3}"

    report = format_diagnosis(diag)

    # 2) 회수 근거(원문 인용 포함) — 접이식 Step (unsafe html 없이 안전하게)
    async with cl.Step(name=t("🔎 진단 근거 — 회수 결과 펼쳐보기",
                              "🔎 Diagnosis evidence — expand retrieval results"),
                       type="tool") as ev:
        ev.output = report

    if not diag.top_philosophers and not diag.similar_claims:
        await cl.Message(content=t("그래프에서 충분히 닿는 주장을 찾지 못했어요. "
                                   "생각을 조금 더 구체적인 **주장 형태**로 적어주시겠어요?",
                                   "I couldn't find claims in the graph that connect closely "
                                   "enough. Could you restate your thought as a more concrete "
                                   "**claim**?")).send()
        return

    value_line = ""
    if schwartz.has_signal(diag.value_scores):
        tops = schwartz.top_values(diag.value_scores)
        value_line = ("\n\n> 🎯 " + t("**가치 지향 (Schwartz)**", "**Value orientation (Schwartz)**")
                      + ": " + " · ".join(f"{n} ({q})" for n, q, _s in tops)
                      + t(" — 8각 프로파일은 [📖 내 기록 (/me)](/me) 에서",
                          " — see your octagon profile at [📖 My records (/me)](/me)"))
    footer = (value_line
              + "\n\n---\n> 📎 "
              + t(f"**이 진단의 근거**: SEP 지식그래프(3,600노드·8,397엣지) · "
                  f"명제 {len(diag.sub_claims)}개 · 유사주장 {len(diag.similar_claims)}건 · "
                  f"대비입장 {len(diag.contrasting_claims)}건 · 가치층 promotes/demotes 집계 "
                  f"— 원문 인용은 위 '진단 근거' 단계에서 확인",
                  f"**Evidence for this diagnosis**: SEP knowledge graph (3,600 nodes · 8,397 edges) · "
                  f"{len(diag.sub_claims)} propositions · {len(diag.similar_claims)} similar claims · "
                  f"{len(diag.contrasting_claims)} contrasting positions · value-layer "
                  f"promotes/demotes aggregation — see verbatim quotes in the "
                  f"'Diagnosis evidence' step above"))

    # 3) 회수만 모드 — 리포트가 곧 본문
    if retrieve_only:
        await cl.Message(content=_clean_md(report + footer), actions=_actions()).send()
        _save_if_logged_in(query, diag, report)
        return

    # 4) LLM 진단문 — OpenRouter 백엔드면 토큰 스트리밍(사주 리포트와 동일 UX)
    prompt = rag.build_prompt(diag)
    meta: dict = {}
    if narrator.supports_streaming():
        msg = cl.Message(content="")
        await msg.send()
        await msg.stream_token(t("_✍️ 진단문을 쓰는 중…_\n\n", "_✍️ Writing your diagnosis…_\n\n"))

        async def _on_token(tok: str):
            await msg.stream_token(tok.replace("~", "∼"))

        try:
            body = await narrator.stream_openrouter(
                prompt, on_token=_on_token, model=narrator.DEFAULT_MODEL, meta_out=meta)
        except Exception as e:  # noqa: BLE001
            await msg.remove()
            await cl.Message(content=t("⚠️ 진단문 생성 실패", "⚠️ Diagnosis generation failed")
                                     + f": {e}\n\n{_clean_md(report)}").send()
            return
        msg.content = _clean_md(body) + footer
        await msg.update()
        _save_if_logged_in(query, diag, body)
        if _actions():
            await cl.Message(content="", actions=_actions()).send()
    else:
        async with cl.Step(name=t("✍️ 진단문 생성 중…", "✍️ Generating diagnosis…"),
                           type="llm") as st:
            try:
                ans = await cl.make_async(i18n.with_lang(rag.answer, lang))(
                    query, split=split, top_k=top_k)
            except Exception as e:  # noqa: BLE001
                st.output = t("실패", "Failed") + f": {e}"
                await cl.Message(content=t("⚠️ 진단문 생성 실패", "⚠️ Diagnosis generation failed")
                                         + f": {e}\n\n{_clean_md(report)}").send()
                return
            body, meta = ans.answer, ans.meta or {}
            st.output = f"{meta.get('models')} · {meta.get('duration_ms')}ms"
        await cl.Message(content=_clean_md(body) + footer, actions=_actions()).send()
        _save_if_logged_in(query, diag, body)

    async with cl.Step(name=t("ℹ️ 생성 정보 (모델·시간·비용)",
                              "ℹ️ Generation info (model · time · cost)"), type="llm") as mstep:
        mstep.output = (f"{meta.get('models')} · {meta.get('duration_ms')}ms · "
                        f"${meta.get('cost_usd')}")


def _save_if_logged_in(query: str, diag, body: str | None) -> None:
    """최근 진단(닮은 영혼·8각 프로파일용) 갱신 + 탐색 히스토리(/me) 적재."""
    user = _username()
    if not user or not diag.top_philosophers:
        return
    tops = [{"id": p.id, "label": p.label, "score": p.score, "n_support": p.n_support}
            for p in diag.top_philosophers]
    philo_store.save_diagnosis(user, query=query, top_philosophers=tops,
                               summary=(body or "")[:200] or None,
                               value_scores=diag.value_scores)
    if body:
        reports_store.save_philo_report(user, query=query, body=body,
                                        top_philosophers=tops)


@cl.action_callback("philo_match_users")
async def on_philo_match_users(action: cl.Action):
    # 액션 콜백은 라우터(app.py)를 거치지 않는 별도 진입점 — 언어 동기화 필수.
    i18n.set_lang(cl.user_session.get("lang") or "ko")
    user = _username()
    if not user:
        await cl.Message(content=t("🔐 로그인해야 쓸 수 있는 기능이에요.",
                                   "🔐 This feature requires login.")).send()
        return
    mine = philo_store.get_diagnosis(user)
    if not mine:
        await cl.Message(content=t("먼저 가치관을 들려주셔서 진단을 만들어주세요.",
                                   "Please share your values first so I can build "
                                   "your diagnosis.")).send()
        return
    others = philo_store.list_diagnoses(exclude=user)
    if not others:
        await cl.Message(content=t("아직 비교할 다른 사용자가 없어요. "
                                   "친구에게 이 플랫폼을 공유해보세요! 🌱",
                                   "No other users to compare with yet. "
                                   "Share this platform with a friend! 🌱")).send()
        return
    rows = philo_store.rank_similar_users(mine["top_philosophers"], others)
    lines = ["## " + t("🤝 나와 닮은 영혼", "🤝 Kindred Souls"), "",
             t("| 순위 | 사용자 | 철학자 겹침 | 공유하는 철학자 |",
               "| Rank | User | Philosopher overlap | Shared philosophers |"),
             "|---|---|---|---|"]
    for i, r in enumerate(rows[:10], 1):
        shared = ", ".join(r["shared"]) or "—"
        lines.append(f"| {i} | {r['username']} | {r['match_rate']:.0f}% | {shared} |")
    lines.append("\n> 📎 " + t("겹침 = 두 사람의 top 철학자 분포 코사인 유사도(결정론).",
                               "Overlap = cosine similarity of the two users' "
                               "top-philosopher distributions (deterministic)."))
    await cl.Message(content="\n".join(lines), actions=_actions()).send()
