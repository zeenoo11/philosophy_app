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
from chainlit.input_widget import Slider, Switch

import mdutil
import reports_store
from engine import narrator
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
                              label="🤝 나와 닮은 영혼 찾기",
                              tooltip="철학자 분포가 겹치는 다른 사용자 랭킹"))
        acts.append(cl.Action(name="fusion_report", payload={},
                              label="🔗 사주×철학 통합 리포트",
                              tooltip="두 렌즈(사주·철학 진단)를 한 장의 보고서로"))
    return acts


async def start():
    cl.user_session.set("philo_topk", 8)
    cl.user_session.set("philo_split", True)
    cl.user_session.set("philo_retrieve_only", False)
    await cl.ChatSettings([
        Slider(id="philo_topk", label="가까운 철학자 top-N", initial=8, min=3, max=15, step=1),
        Switch(id="philo_split", label="입력을 명제로 분해 (영어 정규화)", initial=True),
        Switch(id="philo_retrieve_only", label="회수만 보기 (LLM 진단문 생략)", initial=False),
    ]).send()

    greeting = WELCOME
    user = _username()
    if user:
        saved = philo_store.get_diagnosis(user)
        if saved and saved.get("top_philosophers"):
            top = saved["top_philosophers"][0]
            greeting += (f"\n\n> 👋 다시 오셨어요, **{user}**님! 지난 진단에서 당신과 가장 "
                         f"가까운 철학자는 **{top.get('label')}** 였어요. 새 생각을 들려주세요. "
                         "*(진단은 자동 저장 — [📖 내 기록 (/me)](/me) 에서 다시 볼 수 있어요)*")
    await cl.Message(content=greeting).send()


async def on_settings(settings: dict):
    if "philo_topk" in settings:
        cl.user_session.set("philo_topk", int(settings["philo_topk"]))
    if "philo_split" in settings:
        cl.user_session.set("philo_split", bool(settings["philo_split"]))
    if "philo_retrieve_only" in settings:
        cl.user_session.set("philo_retrieve_only", bool(settings["philo_retrieve_only"]))


async def on_message(message: cl.Message):
    query = message.content.strip()
    if not query:
        return
    if _GREETING_RE.match(query):
        await cl.Message(content="반가워요! 진단하고 싶은 **가치관이나 생각**을 문장으로 "
                                 "들려주세요 — 예: *\"확실한 지식은 감각 경험이 아니라 "
                                 "이성적 추론에서 나온다\"*").send()
        return

    top_k = int(cl.user_session.get("philo_topk") or 8)
    split = cl.user_session.get("philo_split")
    split = True if split is None else bool(split)
    retrieve_only = bool(cl.user_session.get("philo_retrieve_only"))

    # 0) 지식그래프·임베딩 로드(최초 1회) — 이후 메시지는 즉시
    if _RAG is None:
        async with cl.Step(name="📚 지식그래프 로드 (SEP 3,600노드 + 임베딩)", type="run") as st:
            await cl.make_async(_load_rag)()
            st.output = "준비 완료"
    rag = _RAG

    # 1) graphRAG 진단 — 단계(분해→회수→랭킹→조립)를 Step 으로 펼친다
    async with cl.Step(name="🕸 graphRAG 회수·진단", type="tool") as parent:
        run = await cl.make_async(rag.diagnose)(query, split=split, top_k=top_k)
        for rec in run.steps:
            async with cl.Step(name=rec.name, type="tool") as cstep:
                cstep.output = f"`{rec.ms:.0f} ms`  {rec.summary}"
        diag = run.diagnosis
        top3 = ", ".join(p.label for p in diag.top_philosophers[:3]) or "(없음)"
        parent.output = f"가까운 철학자: {top3}"

    report = format_diagnosis(diag)

    # 2) 회수 근거(원문 인용 포함) — 접이식 Step (unsafe html 없이 안전하게)
    async with cl.Step(name="🔎 진단 근거 — 회수 결과 펼쳐보기", type="tool") as ev:
        ev.output = report

    if not diag.top_philosophers and not diag.similar_claims:
        await cl.Message(content="그래프에서 충분히 닿는 주장을 찾지 못했어요. "
                                 "생각을 조금 더 구체적인 **주장 형태**로 적어주시겠어요?").send()
        return

    value_line = ""
    if schwartz.has_signal(diag.value_scores):
        tops = schwartz.top_values(diag.value_scores)
        value_line = ("\n\n> 🎯 **가치 지향 (Schwartz)**: "
                      + " · ".join(f"{n} ({q})" for n, q, _s in tops)
                      + " — 8각 프로파일은 [📖 내 기록 (/me)](/me) 에서")
    footer = (value_line
              + f"\n\n---\n> 📎 **이 진단의 근거**: SEP 지식그래프(3,600노드·8,397엣지) · "
                f"명제 {len(diag.sub_claims)}개 · 유사주장 {len(diag.similar_claims)}건 · "
                f"대비입장 {len(diag.contrasting_claims)}건 · 가치층 promotes/demotes 집계 "
                f"— 원문 인용은 위 '진단 근거' 단계에서 확인")

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
        await msg.stream_token("_✍️ 진단문을 쓰는 중…_\n\n")

        async def _on_token(tok: str):
            await msg.stream_token(tok.replace("~", "∼"))

        try:
            body = await narrator.stream_openrouter(
                prompt, on_token=_on_token, model=narrator.DEFAULT_MODEL, meta_out=meta)
        except Exception as e:  # noqa: BLE001
            await msg.remove()
            await cl.Message(content=f"⚠️ 진단문 생성 실패: {e}\n\n{_clean_md(report)}").send()
            return
        msg.content = _clean_md(body) + footer
        await msg.update()
        _save_if_logged_in(query, diag, body)
        if _actions():
            await cl.Message(content="", actions=_actions()).send()
    else:
        async with cl.Step(name="✍️ 진단문 생성 중…", type="llm") as st:
            try:
                ans = await cl.make_async(rag.answer)(query, split=split, top_k=top_k)
            except Exception as e:  # noqa: BLE001
                st.output = f"실패: {e}"
                await cl.Message(content=f"⚠️ 진단문 생성 실패: {e}\n\n{_clean_md(report)}").send()
                return
            body, meta = ans.answer, ans.meta or {}
            st.output = f"{meta.get('models')} · {meta.get('duration_ms')}ms"
        await cl.Message(content=_clean_md(body) + footer, actions=_actions()).send()
        _save_if_logged_in(query, diag, body)

    async with cl.Step(name="ℹ️ 생성 정보 (모델·시간·비용)", type="llm") as mstep:
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
    user = _username()
    if not user:
        await cl.Message(content="🔐 로그인해야 쓸 수 있는 기능이에요.").send()
        return
    mine = philo_store.get_diagnosis(user)
    if not mine:
        await cl.Message(content="먼저 가치관을 들려주셔서 진단을 만들어주세요.").send()
        return
    others = philo_store.list_diagnoses(exclude=user)
    if not others:
        await cl.Message(content="아직 비교할 다른 사용자가 없어요. "
                                 "친구에게 이 플랫폼을 공유해보세요! 🌱").send()
        return
    rows = philo_store.rank_similar_users(mine["top_philosophers"], others)
    lines = ["## 🤝 나와 닮은 영혼", "",
             "| 순위 | 사용자 | 철학자 겹침 | 공유하는 철학자 |", "|---|---|---|---|"]
    for i, r in enumerate(rows[:10], 1):
        shared = ", ".join(r["shared"]) or "—"
        lines.append(f"| {i} | {r['username']} | {r['match_rate']:.0f}% | {shared} |")
    lines.append("\n> 📎 겹침 = 두 사람의 top 철학자 분포 코사인 유사도(결정론).")
    await cl.Message(content="\n".join(lines), actions=_actions()).send()
