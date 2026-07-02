"""불일치 우선(disagreement-first) 해석 API (SPEC §2.3).

단일 결론이 아니라 {deterministic, by_preset, agreement} 를 반환한다.
  • deterministic — 프리셋 무관 공통(8글자·십신·합충 등). 토글이 갈리면 None.
  • by_preset    — 유파별 강약/용신(또는 구조) + 모든 문장의 trace.
  • agreement    — 어디서 합의/분기했는지(deterministic, yongsin).

모든 해석 문장은 trace 를 동반한다(orphan 금지, SPEC §0.3).
"""
from __future__ import annotations

from dataclasses import replace
from datetime import datetime

from engine import constants as C, relations, scorer, sinsal
from engine.daeun import compute_daeun
from engine.interp_types import element_presence
from engine.pillars import BirthInput, compute_chart
from engine.presets import list_presets, load_preset
from engine.provenance import Claim, Trace
from engine.topics import topic_facts
from engine.yongsin import resolve


def _trace_dict(t: Trace) -> dict:
    return {"rule_id": t.rule_id, "preset_id": t.preset_id, "layer": t.layer,
            "inputs": t.inputs, "classical_source": t.classical_source}


def _claims_dicts(claims) -> list[dict]:
    return [{"claim": c.claim, "trace": _trace_dict(c.trace)} for c in claims]


def deterministic_dict(chart) -> dict:
    """결정론 레이어 직렬화 (프리셋 무관 공통 후보)."""
    return {
        "eight_chars": chart.eight_chars(),
        "pillars": {
            p.position: {"name": p.name, "hanja": p.hanja,
                         "stem": C.CHEONGAN_HANGUL[p.stem],
                         "branch": C.JIJI_HANGUL[p.branch], "gz60": p.gz60}
            for p in chart.pillars
        },
        "day_master": C.CHEONGAN_HANGUL[chart.day_master],
        "day_master_element": C.OHAENG_HANGUL[C.CHEONGAN_OHAENG[chart.day_master]],
        "stem_sipsin": chart.stem_sipsin(),
        "unseong": chart.unseong(),
        "jijanggan": chart.branch_jijanggan_sipsin(),
        "relations": relations.analyze(chart),
        "sinsal": sinsal.analyze(chart),
        "element_distribution": dict(zip(C.OHAENG_HANGUL, element_presence(chart))),
    }


def _current_luck(daeun: dict, birth_year: int, day_stem: int, now_year: int) -> dict:
    """올해(현재) 운 — 진행 중인 대운 + 세운(올해 간지) + 십신(의미)."""
    age = now_year - birth_year + 1  # 한국 세는나이 근사
    cur = None
    for p in daeun["pillars"]:
        if p["age"] <= age:
            cur = p
        else:
            break
    sewoon_gz = (now_year - 4) % 60
    sw_stem, sw_branch = sewoon_gz % 10, sewoon_gz % 12
    out = {
        "now_year": now_year, "age": age,
        "sewoon": {"name": C.gz_name(sewoon_gz), "gz60": sewoon_gz,
                   "천간십신": C.sipsin(day_stem, sw_stem),
                   "지지십신": C.sipsin(day_stem, C.jeonggi(sw_branch))},
    }
    if cur is not None:
        out["current_daeun"] = {**cur, "천간십신": C.sipsin(day_stem, cur["gz60"] % 10)}
    return out


def interpret(birth: BirthInput, preset_ids: list[str] | None = None,
              config_override: dict | None = None,
              gender: str | None = None, now_year: int | None = None) -> dict:
    """유파별 해석을 disagreement-first 로 산출.

    config_override: 결정론 토글 일괄 오버라이드(예: {"true_solar_time": False,
    "longitude_deg": 135.0}). UI 실험용 — 미지정 시 각 프리셋의 YAML 설정 사용.
    gender: "남"|"여" 지정 시 대운(大運) 블록을 추가(L1 결정론, 성별 의존).
    """
    preset_ids = preset_ids or list_presets()
    charts, by_preset = {}, {}
    # 주제별 facts 는 대표 유파(정통 억부) 1개 기준으로 산출
    primary_pid = "jeongtong_eokbu" if "jeongtong_eokbu" in preset_ids else preset_ids[0]
    primary: dict = {}

    for pid in preset_ids:
        preset = load_preset(pid)
        cfg = replace(preset.deterministic, **config_override) if config_override else preset.deterministic
        chart = compute_chart(birth, cfg)
        charts[pid] = chart
        scored = scorer.score_strength(
            chart, preset.interpretation.get("sinkang_weights"), pid)
        l3 = resolve(chart, scored, preset)
        if pid == primary_pid:
            primary = {"chart": chart, "scored": scored,
                       "yongsin": l3["result"] if l3["kind"] == "yongsin" else None}
        claims = list(scored.claims)

        block: dict = {"display_name": preset.display_name, "lineage": preset.lineage,
                       "strength": scored.strength, "engine": l3["kind"],
                       "strength_detail": {
                           "ratio": round(scored.ratio, 3),
                           "bands": scored.trace.inputs.get("bands", []),
                           "deukryeong": scored.deukryeong}}
        if l3["kind"] == "yongsin":
            r = l3["result"]
            # 용신 취용 트레이스(채택 정책 + 미성립해 건너뛴 상위 순위) — 감사 ②⑤
            block["yongsin_chain"] = {"configured": l3.get("configured", []),
                                      "adopted": l3["policy"],
                                      "skipped": l3.get("skipped", [])}
            if r is not None:
                claims += list(r.claims)
                block["policy"] = l3["policy"]
                block["yongsin"] = {"element": r.element_name,
                                    "element_idx": r.element, "family": r.family}
            else:
                block["policy"] = None
                block["yongsin"] = None
        else:  # structure
            r = l3["result"]
            claims += list(r.claims)
            block["structure"] = {"binju": r.binju, "jugong": r.jugong,
                                  "cheyong": r.cheyong, "sang": r.sang}

        block["deterministic"] = deterministic_dict(chart)
        block["claims"] = _claims_dicts(claims)
        by_preset[pid] = block

    # 합의/분기 판정
    eights = {pid: charts[pid].eight_chars() for pid in preset_ids}
    det_agree = "full" if len(set(eights.values())) == 1 else "diverged"
    yong_idx = [by_preset[p]["yongsin"]["element_idx"]
                for p in preset_ids
                if by_preset[p].get("engine") == "yongsin" and by_preset[p].get("yongsin")]
    yong_agree = ("n/a" if len(yong_idx) < 2
                  else "full" if len(set(yong_idx)) == 1 else "diverged")

    common = deterministic_dict(charts[preset_ids[0]]) if det_agree == "full" else None

    daeun = None
    if gender in ("남", "여"):
        dr = compute_daeun(charts[preset_ids[0]], gender)
        daeun = {
            "forward": dr.forward, "start_age": dr.start_age, "gender": gender,
            "pillars": [{"age": a, "gz60": g, "name": n} for (a, g, n) in dr.pillars],
            "trace": _trace_dict(dr.trace),
        }

    topics = topic_facts(primary["chart"], primary["scored"],
                         primary["yongsin"], daeun, gender)

    current = None
    if daeun is not None:
        ny = now_year if now_year is not None else datetime.now().year
        current = _current_luck(daeun, birth.year, primary["chart"].day_master, ny)

    return {
        "input": {"year": birth.year, "month": birth.month, "day": birth.day,
                  "hour": birth.hour, "minute": birth.minute, "gender": gender},
        "deterministic": common,
        "daeun": daeun,
        "current": current,
        "topics": topics,
        "primary_preset": primary_pid,
        "by_preset": by_preset,
        "agreement": {"deterministic": det_agree, "yongsin": yong_agree},
    }
