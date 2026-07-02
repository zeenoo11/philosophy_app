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

from engine import store
from philosophy import store as philo_store

import philo_service as philo  # noqa: E402 — import 부수효과로 philo_* 액션 등록
import saju_service as saju    # noqa: E402 — 사주 액션(category/preset/…) 등록

store.init_db()        # users/profiles/candidates — 멱등
philo_store.init_db()  # philo_profiles — 같은 DB 파일에 테이블 추가

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
