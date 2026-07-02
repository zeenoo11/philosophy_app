"""disagreement-first 해석 API 데모 — `uv run python scripts/demo_interpret.py`."""
import json
import sys

from engine.interpret import interpret
from engine.pillars import BirthInput

cases = [BirthInput(1990, 6, 15, 14, 30), BirthInput(1984, 1, 20, 6, 0),
         BirthInput(2000, 12, 25, 22, 0)]
if len(sys.argv) >= 3:
    y, m, d = (int(x) for x in sys.argv[1].split("-"))
    hh, mm = (int(x) for x in sys.argv[2].split(":"))
    cases = [BirthInput(y, m, d, hh, mm)]

for birth in cases:
    r = interpret(birth)
    print("=" * 64)
    print(f"입력: {birth.year}-{birth.month:02d}-{birth.day:02d} {birth.hour:02d}:{birth.minute:02d}")
    print(f"합의: deterministic={r['agreement']['deterministic']}, yongsin={r['agreement']['yongsin']}")
    if r["deterministic"]:
        print(f"8글자(공통): {r['deterministic']['eight_chars']}  일간 {r['deterministic']['day_master']}")
        print(f"오행분포: {r['deterministic']['element_distribution']}")
    for pid, b in r["by_preset"].items():
        if b["engine"] == "yongsin":
            y = b["yongsin"]
            ystr = f"{y['element']}({y['family']}) via {b['policy']}" if y else "미결정"
            print(f"  [{pid}] {b['strength']} → 용신 {ystr}")
        else:
            print(f"  [{pid}] 구조형 주공={b['structure']['jugong']['가족']} 상={b['structure']['sang']}")
        for c in b["claims"]:
            print(f"       · {c['claim']}  ⟵ {c['trace']['rule_id']}")
