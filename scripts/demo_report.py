"""주제별·일반인용 리포트 데모 — 결정론 요지(즉시) + AI 리포트(claude -p).

uv run python scripts/demo_report.py [YYYY-MM-DD] [HH:MM] [남|여]
"""
import sys

from engine.interpret import interpret
from engine.narrator import narrate_report
from engine.pillars import BirthInput

y, m, d, hh, mm, g = 1990, 6, 15, 14, 30, "남"
if len(sys.argv) >= 3:
    y, m, d = (int(x) for x in sys.argv[1].split("-"))
    hh, mm = (int(x) for x in sys.argv[2].split(":"))
if len(sys.argv) >= 4:
    g = sys.argv[3]

r = interpret(BirthInput(y, m, d, hh, mm), gender=g)
det = r["deterministic"]
print(f"■ 8글자: {det['eight_chars']}  일간 {det['day_master']}  오행 {det['element_distribution']}")
print("\n=== 주제별 요지 (결정론, LLM 없이 즉시) ===")
for topic, blk in r["topics"].items():
    print(f"  [{topic}] {blk['hint']}")

print("\n=== AI 상세 리포트 (claude -p, 일반인용) ===")
narr = narrate_report(r)
m_ = narr.meta
print(f"  [모델 {m_['models']} · {m_['duration_ms']}ms · ${m_['cost_usd']} · grounded={narr.grounded}"
      + (f" · 위반 {narr.violations}" if narr.violations else "") + "]\n")
print(narr.text)
