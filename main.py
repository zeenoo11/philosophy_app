"""플랫폼 진입점 — FastAPI 랜딩(/) + 채팅(/chat·/app) + 개인 보고서(/me).

실행:
  uv run uvicorn main:app --host 0.0.0.0 --port 8123
  → http://localhost:8123/      랜딩 페이지 (두 서비스 소개)
  → http://localhost:8123/app   哲命 셸 안의 채팅
  → http://localhost:8123/chat  채팅 원본 (프로필: 🔮 사주 운세 / 🧭 철학 탐구)
  → http://localhost:8123/me    개인 보고서 — 저장된 탐색 기록 (HTTP Basic, 채팅 계정)

채팅만 필요하면 `uv run chainlit run app.py` 로 app.py 를 직접 실행해도 된다.
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from chainlit.utils import mount_chainlit

from engine import store

WEB_DIR = Path(__file__).parent / "web"

app = FastAPI(title="哲命 — 철학×사주 플랫폼")
_basic = HTTPBasic(auto_error=False)


_NO_CACHE = {"Cache-Control": "no-cache"}  # 가벼운 셸 HTML — 변경 즉시 반영


@app.get("/", include_in_schema=False)
async def landing() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html", media_type="text/html", headers=_NO_CACHE)


@app.get("/app", include_in_schema=False)
async def chat_shell() -> FileResponse:
    """哲命 셸(nav) 안에 채팅(/chat iframe)을 임베드한 페이지 — 랜딩 CTA 의 목적지."""
    return FileResponse(WEB_DIR / "app.html", media_type="text/html", headers=_NO_CACHE)


@app.get("/health", include_in_schema=False)
async def health() -> dict:
    return {"status": "ok"}


@app.get("/me", include_in_schema=False)
async def me(credentials: HTTPBasicCredentials | None = Depends(_basic),
             lang: str = "ko") -> HTMLResponse:
    """개인 보고서 — 채팅과 같은 계정(HTTP Basic). 익명 모드면 안내만. ?lang=en 지원."""
    if not os.environ.get("CHAINLIT_AUTH_SECRET"):
        if lang == "en":
            return HTMLResponse(
                "<meta charset='utf-8'><body style='background:#141824;color:#e9e4d6;"
                "font-family:sans-serif;display:grid;place-items:center;height:100vh'>"
                "<p>🔐 Login mode is off — set <code>CHAINLIT_AUTH_SECRET</code> in the "
                "server <code>.env</code> to enable per-account records and this page."
                "</p></body>", status_code=503)
        return HTMLResponse(
            "<meta charset='utf-8'><body style='background:#141824;color:#e9e4d6;"
            "font-family:sans-serif;display:grid;place-items:center;height:100vh'>"
            "<p>🔐 로그인 모드가 꺼져 있어요 — 서버 <code>.env</code> 에 "
            "<code>CHAINLIT_AUTH_SECRET</code> 을 설정하면 계정별 기록·개인 보고서가 열립니다."
            "</p></body>", status_code=503)
    if (credentials is None
            or not credentials.username
            or not store.verify_user(credentials.username, credentials.password)):
        # 브라우저 인증 프롬프트 유도 (계정은 채팅 로그인과 동일)
        raise HTTPException(status_code=401,
                            detail=("Sign in with the same ID/password as the chat"
                                    if lang == "en" else "채팅과 같은 아이디/비밀번호로 접속하세요"),
                            headers={"WWW-Authenticate": 'Basic realm="cheolmyeong-me"'})
    # timing-safe 비밀번호 비교는 verify_user(PBKDF2 + compare_digest)가 담당.
    from me_page import render_me_page

    return HTMLResponse(render_me_page(credentials.username,
                                       lang="en" if lang == "en" else "ko"))


# Chainlit 을 /chat 하위 경로로 마운트 — 랜딩의 CTA 가 이 경로로 진입한다.
mount_chainlit(app=app, target="app.py", path="/chat")
