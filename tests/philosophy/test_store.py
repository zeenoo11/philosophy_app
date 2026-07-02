"""철학 프로필 저장 — sqlite 왕복·갱신·목록 (임시 DB)."""
import pytest

from philosophy.store import (get_philo_profile, init_db, list_philo_profiles,
                              save_philo_profile)

pytestmark = pytest.mark.philosophy

SCORES = [8.0, 9.0, 5.0, 6.0, 5.0, 4.0, 7.0]


@pytest.fixture()
def db(tmp_path):
    p = str(tmp_path / "test.db")
    init_db(p)
    return p


def test_save_and_get_roundtrip(db):
    save_philo_profile("wj", SCORES, top_philosophy="스토아주의",
                       reasoning="이성적 통제 성향", db_path=db)
    got = get_philo_profile("wj", db_path=db)
    assert got is not None
    assert got["scores"] == SCORES
    assert got["top_philosophy"] == "스토아주의"
    assert got["reasoning"] == "이성적 통제 성향"
    assert got["updated_at"]


def test_get_missing_returns_none(db):
    assert get_philo_profile("nobody", db_path=db) is None


def test_upsert_overwrites(db):
    save_philo_profile("wj", SCORES, top_philosophy="스토아주의", db_path=db)
    new_scores = [1.0] * 7
    save_philo_profile("wj", new_scores, top_philosophy="허무주의", db_path=db)
    got = get_philo_profile("wj", db_path=db)
    assert got["scores"] == new_scores
    assert got["top_philosophy"] == "허무주의"
    assert len(list_philo_profiles(db_path=db)) == 1


def test_list_excludes_self(db):
    save_philo_profile("me", SCORES, db_path=db)
    save_philo_profile("you", [5.0] * 7, top_philosophy="실용주의", db_path=db)
    rows = list_philo_profiles(exclude="me", db_path=db)
    assert [r["username"] for r in rows] == ["you"]
    assert rows[0]["scores"] == [5.0] * 7
