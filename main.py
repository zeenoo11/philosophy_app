"""플랫폼 진입점 — FastAPI 랜딩(/) + Chainlit 채팅(/chat) 마운트.

실행:
  uv run uvicorn main:app --host 0.0.0.0 --port 8123
  → http://localhost:8123/      랜딩 페이지 (두 서비스 소개)
  → http://localhost:8123/chat  채팅 (프로필: 🔮 사주 운세 / 🧭 철학 탐구)

채팅만 필요하면 `uv run chainlit run app.py` 로 app.py 를 직접 실행해도 된다.
"""
from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from chainlit.utils import mount_chainlit

WEB_DIR = Path(__file__).parent / "web"

app = FastAPI(title="哲命 — 철학×사주 플랫폼")


@app.get("/", include_in_schema=False)
async def landing() -> FileResponse:
    return FileResponse(WEB_DIR / "index.html", media_type="text/html")


@app.get("/app", include_in_schema=False)
async def chat_shell() -> FileResponse:
    """哲命 셸(nav) 안에 채팅(/chat iframe)을 임베드한 페이지 — 랜딩 CTA 의 목적지."""
    return FileResponse(WEB_DIR / "app.html", media_type="text/html")


@app.get("/health", include_in_schema=False)
async def health() -> dict:
    return {"status": "ok"}


# Chainlit 을 /chat 하위 경로로 마운트 — 랜딩의 CTA 가 이 경로로 진입한다.
mount_chainlit(app=app, target="app.py", path="/chat")
