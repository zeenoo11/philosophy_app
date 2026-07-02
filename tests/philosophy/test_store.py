"""철학 진단 저장 + 사용자 유사도(철학자 분포 코사인) — 임시 DB."""
import pytest

from philosophy.store import (get_diagnosis, init_db, list_diagnoses,
                              philosopher_similarity, rank_similar_users,
                              save_diagnosis)

pytestmark = pytest.mark.philosophy

TOPS_A = [{"id": "P::singer", "label": "Singer, Irving", "score": 1.4, "n_support": 4},
          {"id": "P::nagel", "label": "Nagel, Thomas", "score": 1.1, "n_support": 3}]
TOPS_B = [{"id": "P::singer", "label": "Singer, Irving", "score": 1.2, "n_support": 3},
          {"id": "P::velleman", "label": "Velleman, J. David", "score": 0.8, "n_support": 2}]
TOPS_C = [{"id": "P::rawls", "label": "Rawls, John", "score": 2.0, "n_support": 5}]


@pytest.fixture()
def db(tmp_path):
    p = str(tmp_path / "t.db")
    init_db(p)
    return p


def test_save_get_roundtrip_and_upsert(db):
    save_diagnosis("wj", query="사랑이란", top_philosophers=TOPS_A,
                   summary="사랑 진단", db_path=db)
    got = get_diagnosis("wj", db_path=db)
    assert got["top_philosophers"] == TOPS_A and got["summary"] == "사랑 진단"
    save_diagnosis("wj", query="정의란", top_philosophers=TOPS_C, db_path=db)
    got = get_diagnosis("wj", db_path=db)
    assert got["query"] == "정의란" and got["top_philosophers"] == TOPS_C
    assert len(list_diagnoses(db_path=db)) == 1


def test_get_missing_returns_none(db):
    assert get_diagnosis("nobody", db_path=db) is None


def test_similarity_shared_vs_disjoint():
    assert philosopher_similarity(TOPS_A, TOPS_A) == pytest.approx(100.0)
    assert philosopher_similarity(TOPS_A, TOPS_C) == 0.0, "공통 철학자 없으면 0"
    partial = philosopher_similarity(TOPS_A, TOPS_B)
    assert 0 < partial < 100


def test_rank_similar_users_orders_and_lists_shared(db):
    save_diagnosis("me", query="q", top_philosophers=TOPS_A, db_path=db)
    save_diagnosis("friend", query="q", top_philosophers=TOPS_B, db_path=db)
    save_diagnosis("stranger", query="q", top_philosophers=TOPS_C, db_path=db)
    others = list_diagnoses(exclude="me", db_path=db)
    rows = rank_similar_users(TOPS_A, others)
    assert [r["username"] for r in rows] == ["friend", "stranger"]
    assert "Singer, Irving" in rows[0]["shared"]
    assert rows[1]["match_rate"] == 0.0
