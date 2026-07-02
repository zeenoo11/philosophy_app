"""철학 진단 영속 저장 — 사주와 같은 sqlite DB(SAJU_DB_PATH) 공유.

users 테이블(engine/store.py)의 계정을 그대로 쓰고, graphRAG 진단 결과만
philo_diagnoses 테이블에 얹는다. top_philosophers 는 JSON 배열
[{id, label, score, n_support}] — 사용자 간 '닮은 영혼'은 이 철학자 분포의
코사인 유사도(공통 철학자 가중)로 계산한다(결정론).
"""
from __future__ import annotations

import json
import math
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from engine.store import DEFAULT_DB  # 사주와 동일한 DB 경로 규약(SAJU_DB_PATH)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS philo_diagnoses (
    username          TEXT PRIMARY KEY,
    query             TEXT,
    top_philosophers  TEXT NOT NULL,
    summary           TEXT,
    updated_at        TEXT NOT NULL
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


def save_diagnosis(username: str, *, query: str,
                   top_philosophers: list[dict],
                   summary: str | None = None,
                   db_path: str | None = None) -> None:
    """최근 진단 저장(있으면 갱신). top_philosophers=[{id,label,score,n_support}]."""
    with closing(_connect(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO philo_diagnoses(username, query, top_philosophers, summary, updated_at)
            VALUES(?,?,?,?,?)
            ON CONFLICT(username) DO UPDATE SET
              query=excluded.query, top_philosophers=excluded.top_philosophers,
              summary=excluded.summary, updated_at=excluded.updated_at
            """,
            (username, query, json.dumps(top_philosophers, ensure_ascii=False),
             summary, _now()),
        )
        conn.commit()


def get_diagnosis(username: str, *, db_path: str | None = None) -> dict | None:
    with closing(_connect(db_path)) as conn:
        row = conn.execute(
            "SELECT * FROM philo_diagnoses WHERE username=?", (username,)).fetchone()
    if row is None:
        return None
    return {
        "query": row["query"],
        "top_philosophers": json.loads(row["top_philosophers"]),
        "summary": row["summary"],
        "updated_at": row["updated_at"],
    }


def list_diagnoses(*, exclude: str | None = None,
                   db_path: str | None = None) -> list[dict]:
    with closing(_connect(db_path)) as conn:
        rows = conn.execute("SELECT * FROM philo_diagnoses ORDER BY username").fetchall()
    out = []
    for r in rows:
        if exclude and r["username"] == exclude:
            continue
        out.append({"username": r["username"],
                    "top_philosophers": json.loads(r["top_philosophers"])})
    return out


# -- 사용자 연결: 철학자 분포 코사인 ------------------------------------------
def _vec(tops: list[dict]) -> dict[str, float]:
    return {t["id"]: float(t.get("score") or 0.0) for t in tops if t.get("id")}


def philosopher_similarity(a: list[dict], b: list[dict]) -> float:
    """두 사용자의 top 철학자 분포 코사인(0~100). 공통 철학자가 없으면 0."""
    va, vb = _vec(a), _vec(b)
    common = set(va) & set(vb)
    if not common:
        return 0.0
    dot = sum(va[k] * vb[k] for k in common)
    na = math.sqrt(sum(x * x for x in va.values()))
    nb = math.sqrt(sum(x * x for x in vb.values()))
    if na == 0 or nb == 0:
        return 0.0
    return max(0.0, min(1.0, dot / (na * nb))) * 100.0


def rank_similar_users(mine: list[dict], others: list[dict]) -> list[dict]:
    """[{username, match_rate, shared: [공통 철학자 라벨]}] — match_rate 내림차순."""
    my_ids = {t["id"]: t.get("label") for t in mine}
    rows = []
    for o in others:
        tops = o["top_philosophers"]
        shared = [t.get("label") or t["id"] for t in tops if t.get("id") in my_ids]
        rows.append({
            "username": o["username"],
            "match_rate": philosopher_similarity(mine, tops),
            "shared": shared[:3],
        })
    rows.sort(key=lambda x: x["match_rate"], reverse=True)
    return rows
