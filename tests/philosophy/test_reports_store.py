"""탐색 히스토리(reports_store) + 통합 리포트 재료(fusion) — 임시 DB, LLM 미호출."""
import pytest

import fusion
import reports_store
from engine import store as saju_store
from engine.pillars import BirthInput
from philosophy import store as philo_store

pytestmark = pytest.mark.philosophy

TOPS = [{"id": "P::singer", "label": "Singer, Irving", "score": 1.4, "n_support": 4}]


@pytest.fixture()
def db(tmp_path):
    p = str(tmp_path / "t.db")
    saju_store.init_db(p)
    philo_store.init_db(p)
    reports_store.init_db(p)
    return p


def test_saju_report_history_newest_first(db):
    reports_store.save_saju_report("wj", kind="saeun", title="신년운세",
                                   body="갑", preset_id="jeongtong_eokbu", db_path=db)
    reports_store.save_saju_report("wj", kind="wealth", title="재물운",
                                   body="을", db_path=db)
    rows = reports_store.list_saju_reports("wj", db_path=db)
    assert [r["title"] for r in rows] == ["재물운", "신년운세"], "최신순"
    assert rows[1]["preset_id"] == "jeongtong_eokbu"
    assert reports_store.list_saju_reports("other", db_path=db) == [], "사용자 격리"


def test_philo_report_roundtrip_with_tops(db):
    reports_store.save_philo_report("wj", query="사랑이란", body="진단문",
                                    top_philosophers=TOPS, db_path=db)
    rows = reports_store.list_philo_reports("wj", db_path=db)
    assert rows[0]["query"] == "사랑이란"
    assert rows[0]["top_philosophers"] == TOPS, "JSON 왕복"


def test_fusion_report_and_counts(db):
    reports_store.save_fusion_report("wj", title="통합", body="본문", db_path=db)
    assert reports_store.list_fusion_reports("wj", db_path=db)[0]["title"] == "통합"
    reports_store.save_saju_report("wj", kind="k", title="t", body="b", db_path=db)
    assert reports_store.counts("wj", db_path=db) == {"saju": 1, "philo": 0, "fusion": 1}


# ── fusion 재료 수집 (DB 경로 주입이 없어 monkeypatch 로 스토어를 겨냥) ──────
@pytest.fixture()
def fusion_user(db, monkeypatch):
    """사주 프로필 + 철학 진단이 모두 있는 사용자 — fusion 재료 완비 상태."""
    saju_store.create_user("wj", "pw", db_path=db)
    saju_store.save_profile("wj", BirthInput(1998, 11, 11, 22, 0), gender="남", db_path=db)
    philo_store.save_diagnosis("wj", query="사랑은 풍요와 결핍을 준다",
                               top_philosophers=TOPS, db_path=db)
    monkeypatch.setattr(saju_store, "DEFAULT_DB", db)
    monkeypatch.setattr("philosophy.store.DEFAULT_DB", db)
    return "wj"


def test_missing_parts_then_complete(db, monkeypatch):
    monkeypatch.setattr(saju_store, "DEFAULT_DB", db)
    monkeypatch.setattr("philosophy.store.DEFAULT_DB", db)
    missing = fusion.missing_parts("ghost")
    assert len(missing) == 2, "사주·철학 둘 다 없음"


def test_gather_facts_and_prompt(fusion_user):
    facts = fusion.gather_facts(fusion_user)
    assert facts is not None
    assert fusion.missing_parts(fusion_user) == []
    s = facts["saju"]
    assert s["eight_chars"] == "무인 계해 임술 신해", "결정론 재계산 일치"
    assert s["strength"] == "신강" and s["yongsin"].get("element")
    prompt = fusion.build_fusion_prompt(facts)
    for token in ("무인 계해 임술 신해", "신강", "Singer, Irving",
                  "두 렌즈가 겹치는 곳", "하나로 읽기"):
        assert token in prompt, f"프롬프트에 '{token}' 누락"
    footer = fusion.fusion_footer(facts)
    assert "1998-11-11 22:00" in footer and "Singer" in footer
