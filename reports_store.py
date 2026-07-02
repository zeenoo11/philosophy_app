"""탐색 결과 히스토리 — 개인 보고서(/me)의 데이터 소스.

로그인 사용자의 사주 리포트·철학 진단·통합(사주×철학) 리포트를 시간순으로
저장한다. 사주와 같은 sqlite(SAJU_DB_PATH) 공유 — 한 계정의 모든 탐색이
한 파일에 쌓이고, /me 개인 페이지와 채팅의 '내 기록'이 여기서 읽는다.

(philosophy/store.py 의 philo_diagnoses 는 '최근 진단 1건' — 닮은 영혼 매칭용.
여기는 전체 히스토리. 책임이 달라 테이블을 분리한다.)
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from engine.store import DEFAULT_DB  # 플랫폼 공용 DB 경로 규약(SAJU_DB_PATH)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS saju_reports (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    username   TEXT NOT NULL,
    kind       TEXT NOT NULL,
    title      TEXT NOT NULL,
    body       TEXT NOT NULL,
    preset_id  TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_saju_reports_user ON saju_reports(username, id DESC);

CREATE TABLE IF NOT EXISTS philo_reports (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    username          TEXT NOT NULL,
    query             TEXT NOT NULL,
    body              TEXT NOT NULL,
    top_philosophers  TEXT,
    created_at        TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_philo_reports_user ON philo_reports(username, id DESC);

CREATE TABLE IF NOT EXISTS fusion_reports (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    username   TEXT NOT NULL,
    title      TEXT NOT NULL,
    body       TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_fusion_reports_user ON fusion_reports(username, id DESC);
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
    with closing(_connect(db_path)):
        pass


# ── 저장 ─────────────────────────────────────────────────────────────────
def save_saju_report(username: str, *, kind: str, title: str, body: str,
                     preset_id: str | None = None,
                     db_path: str | None = None) -> int:
    with closing(_connect(db_path)) as conn:
        cur = conn.execute(
            "INSERT INTO saju_reports(username, kind, title, body, preset_id, created_at)"
            " VALUES(?,?,?,?,?,?)",
            (username, kind, title, body, preset_id, _now()))
        conn.commit()
        return int(cur.lastrowid)


def save_philo_report(username: str, *, query: str, body: str,
                      top_philosophers: list[dict] | None = None,
                      db_path: str | None = None) -> int:
    with closing(_connect(db_path)) as conn:
        cur = conn.execute(
            "INSERT INTO philo_reports(username, query, body, top_philosophers, created_at)"
            " VALUES(?,?,?,?,?)",
            (username, query, body,
             json.dumps(top_philosophers or [], ensure_ascii=False), _now()))
        conn.commit()
        return int(cur.lastrowid)


def save_fusion_report(username: str, *, title: str, body: str,
                       db_path: str | None = None) -> int:
    with closing(_connect(db_path)) as conn:
        cur = conn.execute(
            "INSERT INTO fusion_reports(username, title, body, created_at) VALUES(?,?,?,?)",
            (username, title, body, _now()))
        conn.commit()
        return int(cur.lastrowid)


# ── 조회 (최신순) ─────────────────────────────────────────────────────────
def _rows_to_dicts(rows, json_fields: tuple[str, ...] = ()) -> list[dict]:
    out = []
    for r in rows:
        d = dict(r)
        for f in json_fields:
            if d.get(f):
                try:
                    d[f] = json.loads(d[f])
                except (TypeError, json.JSONDecodeError):
                    d[f] = []
        out.append(d)
    return out


def list_saju_reports(username: str, *, limit: int = 20,
                      db_path: str | None = None) -> list[dict]:
    with closing(_connect(db_path)) as conn:
        rows = conn.execute(
            "SELECT * FROM saju_reports WHERE username=? ORDER BY id DESC LIMIT ?",
            (username, limit)).fetchall()
    return _rows_to_dicts(rows)


def list_philo_reports(username: str, *, limit: int = 20,
                       db_path: str | None = None) -> list[dict]:
    with closing(_connect(db_path)) as conn:
        rows = conn.execute(
            "SELECT * FROM philo_reports WHERE username=? ORDER BY id DESC LIMIT ?",
            (username, limit)).fetchall()
    return _rows_to_dicts(rows, json_fields=("top_philosophers",))


def list_fusion_reports(username: str, *, limit: int = 5,
                        db_path: str | None = None) -> list[dict]:
    with closing(_connect(db_path)) as conn:
        rows = conn.execute(
            "SELECT * FROM fusion_reports WHERE username=? ORDER BY id DESC LIMIT ?",
            (username, limit)).fetchall()
    return _rows_to_dicts(rows)


def counts(username: str, *, db_path: str | None = None) -> dict:
    """개인 페이지 헤더용 — {'saju': n, 'philo': n, 'fusion': n}."""
    with closing(_connect(db_path)) as conn:
        out = {}
        for key, table in (("saju", "saju_reports"), ("philo", "philo_reports"),
                           ("fusion", "fusion_reports")):
            out[key] = conn.execute(
                f"SELECT COUNT(*) FROM {table} WHERE username=?",  # noqa: S608 — 고정 테이블명
                (username,)).fetchone()[0]
    return out
