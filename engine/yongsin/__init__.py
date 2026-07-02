"""L3 용신 선정기 (yongsin-policy) — 정책 분기. 정답 없음.

억부/조후/병약 정책을 함수로, 우선순위는 프리셋(yongsin_policy). 첫 번째로
용신을 산출하는 정책이 채택된다. 맹파(engine: structure)는 이 레이어를 우회해
용신 대신 주공/상 구조를 산출한다.

검증 목표(SPEC §3.2): 정확성(X) → 유파 충실도(내적 무모순) + 결정성.
  L3 에는 `assert 용신 == "水"` 같은 정확성 테스트를 절대 쓰지 않는다.
"""
from __future__ import annotations

from engine.yongsin import byeongyak, eokbu, jeonwang, johu, structure, tongwan

_POLICIES = {"eokbu": eokbu, "johu": johu, "byeongyak": byeongyak,
             "tongwan": tongwan, "jeonwang": jeonwang}


def resolve(chart, scored, preset) -> dict:
    """프리셋 엔진/정책에 따라 L3 결과를 산출.

    반환: {"kind": "yongsin"|"structure", "policy": str|None, "result": obj|None,
           "configured": [정책...], "skipped": [상위순위 미성립 정책...]}.
    `skipped` 는 채택 전에 시도했으나 미성립(None)한 상위 우선순위 정책들 —
    "1순위 조후가 미성립해 억부로 폴백" 같은 취용 과정을 사용자에게 투명화하기
    위한 트레이스다(감사 결함 ②⑤ 대응).
    """
    if preset.engine == "structure":
        return {"kind": "structure", "policy": None, "configured": [], "skipped": [],
                "result": structure.analyze_structure(chart, preset)}

    configured = list(preset.interpretation.get("yongsin_policy") or [])
    skipped: list[str] = []
    for name in configured:
        mod = _POLICIES.get(name)
        if mod is None:
            continue
        res = mod.select(chart, scored, preset)
        if res is not None:
            return {"kind": "yongsin", "policy": name, "result": res,
                    "configured": configured, "skipped": skipped}
        skipped.append(name)   # 미성립 — 다음 우선순위로 폴백

    return {"kind": "yongsin", "policy": None, "result": None,
            "configured": configured, "skipped": skipped}
