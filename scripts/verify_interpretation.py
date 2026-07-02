"""해석 검증 (목표 ②) — claude -p 로 유파별 N회 서술 생성 후 정확성·일관성 검토.

각 유파마다 N개의 서술을 생성하고:
  • 정확성(grounding) = 생성문이 그 유파의 '확정 강약·용신' 결론과 모순되지 않는가
  • 일관성(consistency) = N개가 모두 동일 확정 결론에 그라운딩되는가
유파 간에는 확정 결론이 갈릴 수 있음(disagreement-first)을 함께 보고한다.

사용: uv run python scripts/verify_interpretation.py [YYYY-MM-DD] [HH:MM] [--n 5]
"""
from __future__ import annotations

import argparse

from engine.interpret import interpret
from engine.narrator import narrate
from engine.pillars import BirthInput


def review_birth(birth: BirthInput, n: int, model: str | None):
    r = interpret(birth)
    print("=" * 70)
    print(f"입력 {birth.year}-{birth.month:02d}-{birth.day:02d} "
          f"{birth.hour:02d}:{birth.minute:02d}  |  N={n}/유파")
    if r["deterministic"]:
        d = r["deterministic"]
        print(f"8글자(공통): {d['eight_chars']}  일간 {d['day_master']}  "
              f"오행 {d['element_distribution']}")
    print(f"합의: deterministic={r['agreement']['deterministic']}, "
          f"yongsin={r['agreement']['yongsin']}\n")

    summary = {}
    for pid, block in r["by_preset"].items():
        if block["engine"] == "yongsin" and block.get("yongsin"):
            verdict = f"{block['strength']} / 용신 {block['yongsin']['element']}({block['yongsin']['family']})"
        else:
            verdict = f"{block['strength']} / 맹파 주공 {block['structure']['jugong']['가족']}"
        print(f"── [{pid}] 확정결론: {verdict}")

        narrations = []
        for i in range(n):
            try:
                narr = narrate(block, model=model)
            except Exception as e:  # noqa: BLE001
                print(f"   #{i+1} 생성 실패: {e}")
                continue
            narrations.append(narr)
            mark = "✓grounded" if narr.grounded else f"✗{narr.violations}"
            preview = narr.text.replace("\n", " ")
            print(f"   #{i+1} [{mark}] {preview[:90]}{'…' if len(preview) > 90 else ''}")

        grounded = sum(1 for x in narrations if x.grounded)
        got = len(narrations)
        consistency = grounded / got if got else 0.0
        summary[pid] = {"verdict": verdict, "grounded": grounded, "n": got,
                        "consistency": consistency}
        print(f"   → 정확성(그라운딩) {grounded}/{got}, 일관성 {consistency:.0%}\n")

    print("[유파별 종합]")
    for pid, s in summary.items():
        verdict_ok = "정확" if s["grounded"] == s["n"] and s["n"] > 0 else "검토필요"
        print(f"  {pid:<18} {s['verdict']:<30} 일관성 {s['consistency']:.0%}  [{verdict_ok}]")
    return summary


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", default="1990-06-15")
    ap.add_argument("time", nargs="?", default="14:30")
    ap.add_argument("--n", type=int, default=5)
    ap.add_argument("--model", default=None)
    args = ap.parse_args()
    y, m, d = (int(x) for x in args.date.split("-"))
    hh, mm = (int(x) for x in args.time.split(":"))
    review_birth(BirthInput(y, m, d, hh, mm), args.n, args.model)


if __name__ == "__main__":
    main()
