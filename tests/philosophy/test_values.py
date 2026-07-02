"""Schwartz 가치 프로파일 — 결정론 집계·8각 변환 (LLM 미호출)."""
import pytest

from philosophy import values as schwartz
from philosophy.graph import get_graph
from philosophy.schema import RetrievalBundle, RetrievedNode

pytestmark = pytest.mark.philosophy


def test_value_index_covers_plan3_edges():
    idx = get_graph().value_index
    n_edges = sum(len(v) for v in idx.values())
    assert n_edges == 597, "Plan 3 가치층 엣지 전수"
    assert len(idx) == 390, "가치 시그니처 보유 claim 수"
    key, sign, w = next(iter(idx.values()))[0]
    assert key in schwartz.SCHWARTZ_ORDER and sign in (1, -1) and 0 < w <= 1


def _bundle_with(claim_id: str, score: float) -> RetrievalBundle:
    return RetrievalBundle(query="t", neighbors=[
        RetrievedNode(id=claim_id, type="claim", label="c", score=score)])


def test_score_values_weighted_and_signed():
    g = get_graph()
    idx = g.value_index
    # promotes 만 있는 claim / demotes 포함 claim 을 실데이터에서 하나씩 고른다
    promo = next(cid for cid, sigs in idx.items() if all(s == 1 for _k, s, _w in sigs))
    key, _sign, w = idx[promo][0]
    raw = schwartz.score_values([_bundle_with(promo, 0.8)], graph=g)
    assert raw[key] == pytest.approx(0.8 * w, abs=1e-6), "유사도×weight 가중"
    demo = next((cid for cid, sigs in idx.items() if any(s == -1 for _k, s, _w in sigs)), None)
    assert demo is not None
    dkey, dsign, dw = next((k, s, w_) for k, s, w_ in idx[demo] if s == -1)
    raw2 = schwartz.score_values([_bundle_with(demo, 1.0)], graph=g)
    assert raw2[dkey] <= 0 or raw2[dkey] < dw, "demotes 는 음의 기여"


def test_score_values_no_signal_for_valueless_claim():
    g = get_graph()
    valueless = next(nid for nid, n in g.nodes.items()
                     if n["type"] == "claim" and nid not in g.value_index)
    raw = schwartz.score_values([_bundle_with(valueless, 0.9)], graph=g)
    assert not schwartz.has_signal(raw), "가치 표명 없는 claim 은 빈 프로파일(abstain)"
    assert schwartz.to_octagon(raw) is None
    assert schwartz.format_values_section(raw) == ""


def test_to_octagon_shape_and_scale():
    raw = {k: 0.0 for k in schwartz.SCHWARTZ_ORDER}
    raw.update({"benevolence": 2.0, "universalism": 1.0, "power": -0.5,
                "stimulation": 0.6, "hedonism": 0.2})
    octa = schwartz.to_octagon(raw)
    assert octa is not None and len(octa) == 8
    d = dict(octa)
    assert d["자애"] == 10.0, "최대 축 = 10"
    assert d["보편"] == 5.0
    assert d["권력"] == 0.0, "demotes 우세 축은 0 바닥"
    assert d["자극·쾌락"] == pytest.approx((0.6 + 0.2) / 2 / 2.0 * 10, abs=0.01), "병합 축은 평균"
    labels = [l for l, _v in octa]
    assert labels == ["자기주도", "자극·쾌락", "성취", "권력", "안전",
                      "전통·동조", "자애", "보편"], "circumplex 순서 고정"


def test_top_and_demoted_values():
    raw = {k: 0.0 for k in schwartz.SCHWARTZ_ORDER}
    raw.update({"benevolence": 2.0, "self_direction": 1.2, "power": -0.7})
    tops = schwartz.top_values(raw)
    assert tops[0][0] == "자애" and tops[0][1] == "자기 초월"
    assert schwartz.demoted_values(raw)[0] == ("권력", -0.7)
    section = schwartz.format_values_section(raw)
    assert "자애(자기 초월) +2.0" in section and "권력 -0.7" in section
