"""철학 × 사주 플랫폼 — Chainlit 라우터 (Chat Profiles).

하나의 채팅 앱에서 두 서비스를 프로필로 나눠 제공한다:
  🔮 사주 운세  → saju_service   (결정론 엔진 + LLM 리포트 + 궁합 매칭)
  🧭 철학 탐구  → philo_service  (7축 가치관 분석 + 사상 매칭 + 사용자 연결)

전역 데코레이터(@cl.on_*)는 이 파일만 갖고, 프로필에 따라 각 서비스
모듈로 위임한다. 두 서비스의 액션 콜백은 각 모듈 import 시 등록된다
(이름 충돌 없음 — 철학 쪽은 philo_ 접두사).

실행:
  채팅만:      uv run chainlit run app.py --port 8123
  랜딩 포함:   uv run uvicorn main:app --host 0.0.0.0 --port 8123
"""
from __future__ import annotations

import os

import chainlit as cl

import fusion
import mdutil
import reports_store
from engine import narrator, store
from philosophy import store as philo_store

import philo_service as philo  # noqa: E402 — import 부수효과로 philo_* 액션 등록
import saju_service as saju    # noqa: E402 — 사주 액션(category/preset/…) 등록

store.init_db()          # users/profiles/candidates — 멱등
philo_store.init_db()    # philo_diagnoses — 같은 DB 파일에 테이블 추가
reports_store.init_db()  # saju/philo/fusion 탐색 히스토리(/me 보고서)

PROFILE_SAJU = "🔮 사주 운세"
PROFILE_PHILO = "🧭 철학 탐구"


@cl.set_chat_profiles
async def chat_profiles():
    return [
        cl.ChatProfile(
            name=PROFILE_SAJU,
            markdown_description=(
                "**생년월일시로 보는 운세** — 결정론 사주 엔진 + 유파별 해석.\n"
                "신년운세 · 토정비결 · 애정/궁합 · 재물 · 평생운 · 인연 매칭"),
        ),
        cl.ChatProfile(
            name=PROFILE_PHILO,
            markdown_description=(
                "**가치관을 철학 지형에 위치시키는 graphRAG 진단** — SEP 지식그래프 3,600노드.\n"
                "명제 분해 · 유사 주장 회수 · 실제 저자 기준 철학자 랭킹 · 원문 인용 근거"),
            starters=[
                cl.Starter(label="사랑",
                           message="나는 사랑이 삶을 풍요롭게 하지만 동시에 결핍과 고통도 준다고 생각한다."),
                cl.Starter(label="정의",
                           message="사회의 정의는 가장 불리한 사람의 처지를 개선할 때에만 정당하다."),
                cl.Starter(label="자유",
                           message="개인의 자유는 타인에게 해를 끼치지 않는 한 무엇이든 할 수 있어야 한다."),
                cl.Starter(label="지식",
                           message="확실한 지식은 감각 경험이 아니라 이성적 추론에서 나온다."),
            ],
        ),
    ]


def _is_philo() -> bool:
    return (cl.user_session.get("chat_profile") or "") == PROFILE_PHILO


@cl.on_chat_start
async def on_chat_start():
    if _is_philo():
        await philo.start()
    else:
        await saju.start()


@cl.on_message
async def on_message(message: cl.Message):
    if _is_philo():
        await philo.on_message(message)
    else:
        await saju.on_message(message)


@cl.on_settings_update
async def on_settings_update(settings):
    if _is_philo():  # 철학: top-N·분해·회수만 / 사주: 성별·진태양시
        await philo.on_settings(settings)
    else:
        await saju.on_settings(settings)


# ── 사주 × 철학 통합 리포트 — 프로필 중립(양쪽 메뉴에서 진입) ────────────────
def _current_username() -> str | None:
    u = cl.user_session.get("user")
    return getattr(u, "identifier", None) if u else None


@cl.action_callback("fusion_report")
async def on_fusion_report(action: cl.Action):
    user = _current_username()
    if not user:
        await cl.Message(content="🔐 통합 리포트는 로그인해야 만들 수 있어요 — "
                                 "두 프로필의 기록을 한 계정에 모아야 하거든요.").send()
        return
    missing = fusion.missing_parts(user)
    if missing:
        await cl.Message(content="🔗 통합 리포트에 아직 재료가 부족해요:\n"
                                 + "\n".join(f"- {m}" for m in missing)).send()
        return
    async with cl.Step(name="🧮 두 렌즈의 재료 모으는 중… (사주 결정론 + 철학 진단)",
                       type="tool") as st:
        facts = await cl.make_async(fusion.gather_facts)(user)
        st.output = (f"命 {facts['saju']['eight_chars']} ({facts['saju']['strength']}) × "
                     f"哲 {facts['philo']['top_philosophers'][0].get('label')} 외 "
                     f"{len(facts['philo']['top_philosophers']) - 1}명")
    prompt = fusion.build_fusion_prompt(facts)
    summary = fusion.fusion_summary_table(facts)  # 결정론 요약 표 — LLM 비관여
    footer = fusion.fusion_footer(facts)
    head = f"# {fusion.FUSION_TITLE}\n\n{summary}\n\n"
    meta: dict = {}
    if narrator.supports_streaming():
        msg = cl.Message(content="")
        await msg.send()
        await msg.stream_token(head + "_✍️ 두 렌즈를 겹쳐 읽는 중…_\n\n")

        async def _on_token(tok: str):
            await msg.stream_token(tok.replace("~", "∼"))

        try:
            body = await narrator.stream_openrouter(
                prompt, on_token=_on_token, model=narrator.DEFAULT_MODEL, meta_out=meta)
        except Exception as e:  # noqa: BLE001
            await msg.remove()
            await cl.Message(content=f"⚠️ 통합 리포트 생성 실패: {e}").send()
            return
        msg.content = mdutil.clean_md(head + body) + footer
        await msg.update()
    else:
        async with cl.Step(name="✍️ 통합 리포트 작성 중…", type="llm") as st:
            try:
                data, wall = await cl.make_async(narrator.call_llm_json)(prompt, timeout=240)
            except Exception as e:  # noqa: BLE001
                st.output = f"실패: {e}"
                await cl.Message(content=f"⚠️ 통합 리포트 생성 실패: {e}").send()
                return
            body = (data.get("result") or "").strip()
            meta = narrator.llm_meta(data, wall)
            st.output = f"{meta.get('models')} · {meta.get('duration_ms')}ms"
        await cl.Message(content=mdutil.clean_md(head + body) + footer).send()
    reports_store.save_fusion_report(
        user, title=fusion.FUSION_TITLE,
        body=mdutil.clean_md(f"{summary}\n\n{body}") + footer)
    await cl.Message(content="💾 저장했어요 — [📖 내 기록 (/me)](/me) 에서 지금까지의 "
                             "모든 탐색(사주·철학·통합)을 언제든 다시 볼 수 있어요. "
                             "(채팅과 같은 아이디/비밀번호)").send()


# 로그인(선택) — CHAINLIT_AUTH_SECRET 가 설정된 경우에만 활성화한다.
# 미설정 시 익명으로 동작하며 프로필/후보/철학 좌표는 세션에만 보관.
# 계정은 두 서비스가 공유한다(users 테이블) — 한 번의 로그인으로
# 사주 프로필과 철학 프로필을 모두 갖는다.
if os.environ.get("CHAINLIT_AUTH_SECRET"):
    @cl.password_auth_callback
    def auth_callback(username: str, password: str):
        # 첫 로그인 시 자동 가입(store.authenticate). 실패하면 None → 로그인 거부.
        if username and password and store.authenticate(username, password):
            return cl.User(identifier=username)
        return None
