# 哲命 — 철학×사주 플랫폼 컨테이너 이미지
# 빌드:  docker build -t philo-saju .          (linux/amd64 — sxtwl 휠이 amd64만 제공)
# 실행:  docker run -p 8123:8123 --env-file .env philo-saju
#        → /  랜딩 페이지   → /chat  채팅(프로필: 사주/철학)
#        (LLM 키 없으면 결정론 기능(차트·매칭)은 동작, LLM 리포트/철학 대화만 비활성)
# syntax=docker/dockerfile:1
FROM python:3.11-slim-bookworm

# ── 시스템 + Node.js + claude CLI (LLM 리포트의 claude -p 용) ──
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
 && apt-get install -y --no-install-recommends nodejs \
 && npm install -g @anthropic-ai/claude-code \
 && npm cache clean --force \
 && apt-get clean && rm -rf /var/lib/apt/lists/*

# ── uv (의존성 관리) ──
COPY --from=ghcr.io/astral-sh/uv:0.8.0 /uv /uvx /bin/

WORKDIR /app
ENV PYTHONUTF8=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    SAJU_TRACE=0 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PATH="/app/.venv/bin:$PATH"

# ── 의존성 먼저 설치 (소스 변경과 분리해 레이어 캐시) ──
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# ── 애플리케이션 소스 ──
COPY engine ./engine
COPY presets ./presets
COPY philosophy ./philosophy
COPY web ./web
COPY public ./public
COPY .chainlit ./.chainlit
COPY app.py main.py saju_service.py philo_service.py chainlit.md ./

# ── 천문력(de421.bsp) 베이크: 런타임 네트워크 없이 절기 계산 ──
RUN python -c "from engine.astro import _engine; _engine()"

EXPOSE 8123
HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
  CMD curl -fsS http://localhost:8123/ || exit 1

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8123"]
