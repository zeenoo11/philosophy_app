"""카테고리 운세 리포트 데모.

uv run python scripts/demo_fortune.py saeun tojeong aejeong
"""
import sys
import time

from engine.pillars import BirthInput
from engine.reports import run_report

birth = BirthInput(1998, 11, 11, 22, 0)  # 남 (사용자 예시)
kinds = sys.argv[1:] or ["saeun"]

for kind in kinds:
    t = time.perf_counter()
    kw = {"year": 2026, "gender": "남"}
    if kind == "gunghap":
        kw = {"partner": BirthInput(1996, 5, 20, 9, 30)}
    rep = run_report(kind, birth, **kw)
    wall = time.perf_counter() - t
    m = rep.meta
    print("=" * 72)
    print(f"# {rep.title}   [{m.get('models')} · {m.get('duration_ms')}ms · "
          f"${m.get('cost_usd')} · wall {wall:.1f}s · grounded={rep.grounded}]")
    if rep.violations:
        print("  위반:", rep.violations)
    print("=" * 72)
    print(rep.text)
    print()
