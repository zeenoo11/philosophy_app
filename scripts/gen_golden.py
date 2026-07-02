"""골든 코퍼스 재생성기 — `uv run python scripts/gen_golden.py` (리포 루트에서).

엔진(민간시 모드) 출력을 생성하되 생성 시점에 sxtwl 과 4기둥 전부 일치를 강제
검증하고(불일치 시 실패) fixtures/golden/cases.json 으로 동결한다. 절기·자시 경계를
피한 '안전한' 시각만 골든에 둔다(경계는 tests/deterministic/test_edge.py 소관).
"""
import json
from pathlib import Path

from engine import constants as C
from engine.pillars import BirthInput, DeterministicConfig, compute_chart
from tests.oracle import sxtwl_pillars

CFG = DeterministicConfig(true_solar_time=False, jasi_rule="yajasi_split")

CASES = [
    ("std_1955",  1955, 7, 20, 16, 0,  "여름 한낮, 未월 중간"),
    ("std_1968",  1968, 11, 25, 6, 0,  "亥월, 새벽"),
    ("std_1984",  1984, 2, 10, 10, 30, "입춘 직후 寅월"),
    ("std_1990",  1990, 6, 15, 14, 30, "午월 오후"),
    ("std_2000",  2000, 1, 15, 8, 0,   "丑월, 2000년대"),
    ("std_2010",  2010, 3, 15, 11, 0,  "卯월 오전"),
    ("std_2024",  2024, 9, 22, 9, 0,   "酉월, 최근"),
    ("hist_1936", 1936, 4, 18, 13, 0,  "역사 tz(일제 +9), 辰월"),
    ("hist_1958", 1958, 8, 12, 15, 0,  "서머타임 적용기, 申월"),
    ("noon_1972", 1972, 12, 10, 12, 0, "子월 정오"),
    ("eve_2001",  2001, 5, 8, 19, 30,  "巳월 저녁"),
    ("morn_1947", 1947, 10, 3, 7, 30,  "戌월 아침(해방 직후)"),
]


def main():
    out = []
    for (cid, y, m, d, hh, mm, note) in CASES:
        ch = compute_chart(BirthInput(y, m, d, hh, mm), CFG)
        mine = (ch.year.gz60, ch.month.gz60, ch.day.gz60, ch.hour.gz60)
        theirs = sxtwl_pillars(y, m, d, hh)
        if mine != theirs:
            raise SystemExit(
                f"[FAIL] {cid} 엔진≠sxtwl: {[C.gz_name(g) for g in mine]} vs "
                f"{[C.gz_name(g) for g in theirs]}")
        out.append({
            "id": cid,
            "input": {"year": y, "month": m, "day": d, "hour": hh, "minute": mm},
            "config": {"true_solar_time": False, "jasi_rule": "yajasi_split"},
            "expected": {
                "year": {"gz60": ch.year.gz60, "name": ch.year.name},
                "month": {"gz60": ch.month.gz60, "name": ch.month.name},
                "day": {"gz60": ch.day.gz60, "name": ch.day.name},
                "hour": {"gz60": ch.hour.gz60, "name": ch.hour.name},
                "eight_chars": ch.eight_chars(),
            },
            "cross_checked": "sxtwl",
            "note": note,
        })

    path = Path("fixtures/golden/cases.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"생성 완료: {len(out)} 케이스 → {path} (전부 sxtwl 일치)")


if __name__ == "__main__":
    main()
