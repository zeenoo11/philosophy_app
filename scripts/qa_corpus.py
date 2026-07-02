"""QA 코퍼스 생성 — 여러 사람×카테고리 리포트를 파일로 저장(QA 에이전트가 읽고 평가).

- 일관성(consistency): 동일인·동일 카테고리를 여러 번 생성 → 결론이 안 뒤집히는지.
- 합리성/근거/길이: 사람별 리포트가 사주 확정값에 근거하고 충분히 긴지.

사용: PYTHONUTF8=1 PYTHONPATH=. uv run python scripts/qa_corpus.py
출력: qa_out/<사람>__<카테고리>__run<N>.md (본문+근거푸터+메타 헤더)
"""
from __future__ import annotations

import pathlib
import time

from engine.pillars import BirthInput
from engine.reports import run_report

OUT = pathlib.Path("qa_out")
OUT.mkdir(exist_ok=True)

# (라벨, 생일, 성별)
PEOPLE = [
    ("personA_1998남", BirthInput(1998, 11, 11, 22, 0), "남"),
    ("personB_1990여", BirthInput(1990, 4, 15, 10, 0), "여"),
    ("personC_1985남", BirthInput(1985, 7, 3, 14, 30), "남"),
    ("personD_2001여", BirthInput(2001, 1, 20, 8, 0), "여"),
]

# (사람 index, 카테고리, 반복횟수)  — 반복>1 은 일관성 검증용
JOBS = [
    (0, "saeun", 2), (0, "daeun", 2), (0, "wealth", 1),
    (1, "saeun", 2), (1, "aejeong", 1),
    (2, "pyeongsaeng", 1),
    (3, "wealth", 1),
]


def main() -> None:
    total = sum(n for _, _, n in JOBS)
    done = 0
    for pidx, kind, runs in JOBS:
        label, birth, gender = PEOPLE[pidx]
        for r in range(1, runs + 1):
            t0 = time.perf_counter()
            rep = run_report(kind, birth, gender=gender)
            dt = time.perf_counter() - t0
            body = rep.text.split("📎 이 풀이의 근거")[0].rstrip().rstrip("-").rstrip()
            fp = OUT / f"{label}__{kind}__run{r}.md"
            header = (f"<!-- 사람={label} 생일={birth.year}-{birth.month:02d}-{birth.day:02d} "
                      f"{birth.hour:02d}:{birth.minute:02d} 성별={gender} | 카테고리={kind} run={r} "
                      f"| 본문{len(body)}자 out_tokens={rep.meta.get('output_tokens')} "
                      f"grounded={rep.grounded} {dt:.1f}s -->\n\n")
            fp.write_text(header + rep.text, encoding="utf-8")
            done += 1
            print(f"[{done}/{total}] {fp.name}: {len(body)}자 "
                  f"out={rep.meta.get('output_tokens')} grounded={rep.grounded} {dt:.1f}s")
    print(f"\n완료 → {OUT}/ ({done}개 파일)")


if __name__ == "__main__":
    main()
