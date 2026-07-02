"""P4 — 출처 완전성(orphan 금지, SPEC §3.2(d)) + 해석 멱등성.

trace 없는 해석 문장 0건을 CI 게이트로. 모든 by_preset 블록의 모든 claim 은
rule_id·layer·preset_id 를 갖춰야 한다.
"""
from __future__ import annotations

import pytest

from engine.interpret import interpret

pytestmark = pytest.mark.interpretation


def test_no_orphan_claims(sample_births):
    for birth in sample_births:
        r = interpret(birth)
        for pid, block in r["by_preset"].items():
            assert block["claims"], f"{pid}: 해석 문장이 없음"
            for c in block["claims"]:
                tr = c["trace"]
                assert c["claim"], "빈 claim"
                assert tr["rule_id"], f"{pid}: rule_id 누락 (orphan)"
                assert tr["layer"] in {"L2", "L3", "L4"}
                assert tr["preset_id"] == pid
                assert tr["classical_source"], f"{pid}: 고전 근거 누락"


def test_interpret_is_idempotent(sample_births):
    for birth in sample_births[:6]:
        assert interpret(birth) == interpret(birth)


def test_agreement_fields_present(sample_births):
    for birth in sample_births[:6]:
        r = interpret(birth)
        assert set(r["agreement"]) == {"deterministic", "yongsin"}
        assert r["agreement"]["deterministic"] in {"full", "diverged"}
        assert r["agreement"]["yongsin"] in {"full", "diverged", "n/a"}
