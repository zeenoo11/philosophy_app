"""철학 프로필 영속 저장 — 사주와 같은 sqlite DB(SAJU_DB_PATH) 를 공유한다.

users 테이블(engine/store.py)의 계정을 그대로 쓰고, 철학 7축 결과만
philo_profiles 테이블에 얹는다 — 한 계정으로 사주·철학 프로필을 모두 갖는
'하나의 플랫폼' 구조. scores 는 JSON 배열 텍스트(AXES 순서)로 저장해
축 구성이 바뀌어도 스키마 마이그레이션 없이 수용한다.
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from engine.store import DEFAULT_DB  # 사주와 동일한 DB 경로 규약(SAJU_DB_PATH)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS philo_profiles (
    username        TEXT PRIMARY KEY,
    scores          TEXT NOT NULL,
    top_philosophy  TEXT,
    reasoning       TEXT,
    updated_at      TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect(db_path: str | None = None) -> sqlite3.Connection:
    p = Path(db_path or DEFAULT_DB)
    if p.parent and str(p.parent) not in ("", "."):
        p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.executescript(_SCHEMA)
    return conn


def init_db(db_path: str | None = None) -> None:
    """스키마 보장(멱등) — 앱 기동 시 1회 호출."""
    with closing(_connect(db_path)):
        pass


def save_philo_profile(username: str, scores: list[float], *,
                       top_philosophy: str | None = None,
                       reasoning: str | None = None,
                       db_path: str | None = None) -> None:
    """분석 결과 저장(있으면 갱신)."""
    with closing(_connect(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO philo_profiles(username, scores, top_philosophy, reasoning, updated_at)
            VALUES(?,?,?,?,?)
            ON CONFLICT(username) DO UPDATE SET
              scores=excluded.scores, top_philosophy=excluded.top_philosophy,
              reasoning=excluded.reasoning, updated_at=excluded.updated_at
            """,
            (username, json.dumps(scores), top_philosophy, reasoning, _now()),
        )
        conn.commit()


def get_philo_profile(username: str, *, db_path: str | None = None) -> dict | None:
    """저장된 결과 → {'scores': [7], 'top_philosophy', 'reasoning', 'updated_at'} | None."""
    with closing(_connect(db_path)) as conn:
        row = conn.execute(
            "SELECT * FROM philo_profiles WHERE username=?", (username,)).fetchone()
    if row is None:
        return None
    return {
        "scores": json.loads(row["scores"]),
        "top_philosophy": row["top_philosophy"],
        "reasoning": row["reasoning"],
        "updated_at": row["updated_at"],
    }


def list_philo_profiles(*, exclude: str | None = None,
                        db_path: str | None = None) -> list[dict]:
    """모든 사용자의 철학 프로필(사용자 연결용). exclude 는 본인 제외."""
    with closing(_connect(db_path)) as conn:
        rows = conn.execute("SELECT * FROM philo_profiles ORDER BY username").fetchall()
    out = []
    for r in rows:
        if exclude and r["username"] == exclude:
            continue
        out.append({
            "username": r["username"],
            "scores": json.loads(r["scores"]),
            "top_philosophy": r["top_philosophy"],
        })
    return out
