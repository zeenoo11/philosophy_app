"""사용자 인증·프로필·후보 저장 — sqlite CRUD/보안 검증 (임시 DB).

검증 목표:
  • authenticate: 첫 로그인 자동 생성 → 재로그인 검증 → 틀린 비번 거부.
  • 비밀번호 평문 미저장(해시만).
  • 프로필 roundtrip + upsert(갱신).
  • 후보 CRUD + 사용자 간 격리.
"""
from __future__ import annotations

import sqlite3

import pytest

from engine import store
from engine.pillars import BirthInput

pytestmark = pytest.mark.interpretation


@pytest.fixture
def db(tmp_path):
    return str(tmp_path / "test.db")


def test_authenticate_creates_then_verifies(db):
    assert store.authenticate("alice", "pw123", db_path=db) is True   # 첫 로그인 = 자동 생성
    assert store.user_exists("alice", db_path=db)
    assert store.authenticate("alice", "pw123", db_path=db) is True    # 재로그인 OK
    assert store.authenticate("alice", "wrong", db_path=db) is False   # 틀린 비번 거부


def test_password_not_stored_plaintext(db):
    store.authenticate("bob", "supersecret", db_path=db)
    con = sqlite3.connect(db)
    row = con.execute("SELECT pw_hash, pw_salt FROM users WHERE username='bob'").fetchone()
    con.close()
    assert "supersecret" not in row[0] and "supersecret" not in row[1]
    assert len(row[0]) == 64  # sha256 hex


def test_profile_roundtrip_and_upsert(db):
    store.authenticate("carol", "pw", db_path=db)
    assert store.get_profile("carol", db_path=db) is None
    store.save_profile("carol", BirthInput(1990, 6, 15, 14, 30), gender="여", db_path=db)
    p = store.get_profile("carol", db_path=db)
    assert p["birth"] == BirthInput(1990, 6, 15, 14, 30)
    assert p["gender"] == "여"
    # 갱신(upsert): 같은 사용자 재저장 → 덮어씀.
    store.save_profile("carol", BirthInput(1991, 1, 1, 0, 0), gender="남", db_path=db)
    p2 = store.get_profile("carol", db_path=db)
    assert p2["birth"] == BirthInput(1991, 1, 1, 0, 0)
    assert p2["gender"] == "남"


def test_candidates_crud(db):
    store.authenticate("dave", "pw", db_path=db)
    cid = store.add_candidate("dave", BirthInput(1992, 3, 3, 9), label="철수", db_path=db)
    store.add_candidate("dave", BirthInput(1988, 11, 20, 18), label="영희", db_path=db)
    rows = store.list_candidates("dave", db_path=db)
    assert len(rows) == 2
    assert rows[0]["label"] == "철수"
    assert rows[0]["birth"] == BirthInput(1992, 3, 3, 9)
    assert store.delete_candidate("dave", cid, db_path=db) is True
    assert len(store.list_candidates("dave", db_path=db)) == 1
    assert store.clear_candidates("dave", db_path=db) == 1
    assert store.list_candidates("dave", db_path=db) == []


def test_candidates_isolated_per_user(db):
    store.authenticate("u1", "pw", db_path=db)
    store.authenticate("u2", "pw", db_path=db)
    store.add_candidate("u1", BirthInput(1992, 3, 3, 9), db_path=db)
    assert len(store.list_candidates("u1", db_path=db)) == 1
    assert store.list_candidates("u2", db_path=db) == []
    # 남의 후보는 삭제 불가(소유 검증).
    assert store.delete_candidate("u2", 1, db_path=db) is False
