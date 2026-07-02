"""사용자 인증·프로필·후보 영속 저장 — sqlite3 (표준 라이브러리, 새 의존성 0).

스키마:
  users(username PK, pw_hash, pw_salt, created_at)
  profiles(username PK→users, year/month/day/hour/minute, gender, updated_at)  ─ 본인 사주 1건
  candidates(id PK, owner→users, label, year/month/day/hour/minute, gender, created_at)  ─ 후보 N건

보안: 비밀번호는 평문 저장 금지. PBKDF2-HMAC-SHA256(salt 16B, 100k 반복) 해시만
저장하고, 검증은 hmac.compare_digest 로 상수시간 비교한다.
경로: 환경변수 SAJU_DB_PATH (기본 프로젝트 루트 saju.db). 함수마다 db_path 인자로
주입 가능(테스트는 임시 파일 사용). 연결은 매 호출 생성/종료(저빈도라 단순·안전).

note: 사주는 시(時)까지 의미가 있어 분까지만 저장하고 second/fold 는 보존하지 않는다.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import secrets
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

from engine.pillars import BirthInput

DEFAULT_DB = os.environ.get("SAJU_DB_PATH", "saju.db")
_ITERATIONS = 100_000

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    username   TEXT PRIMARY KEY,
    pw_hash    TEXT NOT NULL,
    pw_salt    TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS profiles (
    username   TEXT PRIMARY KEY REFERENCES users(username) ON DELETE CASCADE,
    year   INTEGER NOT NULL, month INTEGER NOT NULL, day INTEGER NOT NULL,
    hour   INTEGER NOT NULL DEFAULT 0, minute INTEGER NOT NULL DEFAULT 0,
    gender TEXT, updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS candidates (
    id    INTEGER PRIMARY KEY AUTOINCREMENT,
    owner TEXT NOT NULL REFERENCES users(username) ON DELETE CASCADE,
    label TEXT,
    year  INTEGER NOT NULL, month INTEGER NOT NULL, day INTEGER NOT NULL,
    hour  INTEGER NOT NULL DEFAULT 0, minute INTEGER NOT NULL DEFAULT 0,
    gender TEXT, created_at TEXT NOT NULL
);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _connect(db_path: str | None = None) -> sqlite3.Connection:
    """연결을 열고 스키마를 보장한다(IF NOT EXISTS → 멱등)."""
    p = Path(db_path or DEFAULT_DB)
    if p.parent and str(p.parent) not in ("", "."):
        p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    conn.executescript(_SCHEMA)
    return conn


def init_db(db_path: str | None = None) -> None:
    """스키마 명시 초기화(앱 기동 시 1회 호출 권장)."""
    with closing(_connect(db_path)):
        pass


# ─────────────────────────────────────────────────────────────────────────
# 인증
# ─────────────────────────────────────────────────────────────────────────
def _hash_pw(password: str, salt: bytes) -> str:
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, _ITERATIONS)
    return dk.hex()


def user_exists(username: str, *, db_path: str | None = None) -> bool:
    with closing(_connect(db_path)) as conn:
        row = conn.execute("SELECT 1 FROM users WHERE username=?", (username,)).fetchone()
    return row is not None


def create_user(username: str, password: str, *, db_path: str | None = None) -> bool:
    """신규 사용자 생성. 이미 존재하면 False(덮어쓰지 않음)."""
    salt = secrets.token_bytes(16)
    pw_hash = _hash_pw(password, salt)
    with closing(_connect(db_path)) as conn:
        try:
            conn.execute(
                "INSERT INTO users(username, pw_hash, pw_salt, created_at) VALUES(?,?,?,?)",
                (username, pw_hash, salt.hex(), _now()),
            )
            conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False


def verify_user(username: str, password: str, *, db_path: str | None = None) -> bool:
    """비밀번호 검증(상수시간 비교). 사용자가 없으면 False."""
    with closing(_connect(db_path)) as conn:
        row = conn.execute(
            "SELECT pw_hash, pw_salt FROM users WHERE username=?", (username,)
        ).fetchone()
    if row is None:
        return False
    actual = _hash_pw(password, bytes.fromhex(row["pw_salt"]))
    return hmac.compare_digest(row["pw_hash"], actual)


def authenticate(username: str, password: str, *, db_path: str | None = None) -> bool:
    """검증하되, 신규 username 이면 그 비밀번호로 자동 가입한다.

    (첫 로그인 시 자동 생성 정책 — Chainlit 에 별도 가입 UI 가 없으므로.)
    """
    if user_exists(username, db_path=db_path):
        return verify_user(username, password, db_path=db_path)
    return create_user(username, password, db_path=db_path)


# ─────────────────────────────────────────────────────────────────────────
# 프로필 (본인 사주 1건)
# ─────────────────────────────────────────────────────────────────────────
def save_profile(
    username: str,
    birth: BirthInput,
    *,
    gender: str | None = None,
    db_path: str | None = None,
) -> None:
    """본인 사주를 저장(있으면 갱신). username 은 users 에 존재해야 한다."""
    with closing(_connect(db_path)) as conn:
        conn.execute(
            """
            INSERT INTO profiles(username, year, month, day, hour, minute, gender, updated_at)
            VALUES(?,?,?,?,?,?,?,?)
            ON CONFLICT(username) DO UPDATE SET
              year=excluded.year, month=excluded.month, day=excluded.day,
              hour=excluded.hour, minute=excluded.minute,
              gender=excluded.gender, updated_at=excluded.updated_at
            """,
            (username, birth.year, birth.month, birth.day,
             birth.hour, birth.minute, gender, _now()),
        )
        conn.commit()


def get_profile(username: str, *, db_path: str | None = None) -> dict | None:
    """저장된 본인 사주를 {'birth': BirthInput, 'gender': str|None} 로 반환(없으면 None)."""
    with closing(_connect(db_path)) as conn:
        row = conn.execute("SELECT * FROM profiles WHERE username=?", (username,)).fetchone()
    if row is None:
        return None
    return {
        "birth": BirthInput(row["year"], row["month"], row["day"], row["hour"], row["minute"]),
        "gender": row["gender"],
    }


# ─────────────────────────────────────────────────────────────────────────
# 후보 (매칭 대상 N건)
# ─────────────────────────────────────────────────────────────────────────
def add_candidate(
    username: str,
    birth: BirthInput,
    *,
    label: str | None = None,
    gender: str | None = None,
    db_path: str | None = None,
) -> int:
    """후보 1건 추가 → 새 id 반환."""
    with closing(_connect(db_path)) as conn:
        cur = conn.execute(
            """INSERT INTO candidates(owner, label, year, month, day, hour, minute, gender, created_at)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (username, label, birth.year, birth.month, birth.day,
             birth.hour, birth.minute, gender, _now()),
        )
        conn.commit()
        return int(cur.lastrowid)


def list_candidates(username: str, *, db_path: str | None = None) -> list[dict]:
    """소유자의 후보 목록(추가순). 각 항목 {'id','label','birth','gender'}."""
    with closing(_connect(db_path)) as conn:
        rows = conn.execute(
            "SELECT * FROM candidates WHERE owner=? ORDER BY id", (username,)
        ).fetchall()
    return [
        {
            "id": r["id"],
            "label": r["label"],
            "birth": BirthInput(r["year"], r["month"], r["day"], r["hour"], r["minute"]),
            "gender": r["gender"],
        }
        for r in rows
    ]


def delete_candidate(username: str, cand_id: int, *, db_path: str | None = None) -> bool:
    """소유자의 후보 1건 삭제(소유 검증 포함). 삭제됐으면 True."""
    with closing(_connect(db_path)) as conn:
        cur = conn.execute(
            "DELETE FROM candidates WHERE id=? AND owner=?", (cand_id, username))
        conn.commit()
        return cur.rowcount > 0


def clear_candidates(username: str, *, db_path: str | None = None) -> int:
    """소유자의 후보 전체 삭제 → 삭제 건수."""
    with closing(_connect(db_path)) as conn:
        cur = conn.execute("DELETE FROM candidates WHERE owner=?", (username,))
        conn.commit()
        return cur.rowcount
