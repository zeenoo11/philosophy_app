"""인연 매칭(緣分) — 결정론 궁합 순위·탐색 (engine.compatibility 재사용).

두 가지 결정론 연산:
  • rank_candidates(me, candidates) — 후보 N명을 나와의 궁합 점수로 내림차순.
  • best_in_year_range(me, y0, y1)  — 주어진 연도 구간의 사주 공간을
    완전탐색하여 나와 최고 궁합인 생일을 역산 + 최고점 동치류(띠·일주) 요약.

핵심 불변식 ("계산은 정답 있다"):
  입력(나·후보풀, 또는 나·연도구간·옵션)이 같으면 결과도 같다. 난수·외부
  상태·LLM 미사용. 동점은 (연,월,일,시) 오름차순으로 고정 정렬해 순위까지
  결정론으로 만든다.

성능: 나의 차트를 1회만 계산해 gunghap_charts 로 재사용 → 후보당
compute_chart 1회(≈2.5ms). 일(日) 단위 연도탐색 ≈ 1초/년.
"""
from __future__ import annotations

from collections import Counter
from datetime import date, timedelta

from engine import constants as C
from engine.compatibility import gunghap_charts
from engine.pillars import BirthInput, compute_chart
from engine.provenance import Trace


# ─────────────────────────────────────────────────────────────────────────
# 공통
# ─────────────────────────────────────────────────────────────────────────
def _row(label: str, birth: BirthInput, res: dict) -> dict:
    """매칭 결과 1건의 표준 행(行) — rank/best 공용. birth=상대(후보)."""
    return {
        "label": label,
        "birth": birth,
        "총점": res["총점"],
        "등급": res["등급"],
        "일간관계": res["일간관계"]["label"],
        "일지관계": res["일지관계"]["label"],
        "띠관계": res["띠관계"]["label"],
        "오행보완": res["오행보완"]["label"],
        "eight_chars": res["b"]["eight_chars"],
        "근거": res["근거"],
    }


def _birth_label(b: BirthInput, with_hour: bool) -> str:
    s = f"{b.year}-{b.month:02d}-{b.day:02d}"
    return f"{s} {b.hour:02d}시" if with_hour else s


# ─────────────────────────────────────────────────────────────────────────
# 1:N 후보 순위
# ─────────────────────────────────────────────────────────────────────────
def rank_candidates(
    me: BirthInput,
    candidates,
    *,
    top_k: int | None = None,
) -> list[dict]:
    """후보들을 나와의 궁합 점수 내림차순으로 정렬한다.

    candidates: BirthInput 또는 (label, BirthInput) 2-튜플의 시퀀스.
    동점은 (연,월,일,시,분,입력순) 오름차순으로 tie-break → 순위 결정론.
    """
    me_chart = compute_chart(me)
    rows: list[tuple[int, tuple, dict]] = []
    for i, item in enumerate(candidates):
        if isinstance(item, (tuple, list)) and len(item) == 2:
            label, cb = item
        else:
            label, cb = None, item
        if label is None:
            label = _birth_label(cb, with_hour=True)
        res = gunghap_charts(me_chart, compute_chart(cb))
        tie = (cb.year, cb.month, cb.day, cb.hour, cb.minute, i)
        rows.append((res["총점"], tie, _row(label, cb, res)))
    rows.sort(key=lambda r: (-r[0], r[1]))
    out = [r[2] for r in rows]
    return out[:top_k] if top_k else out


# ─────────────────────────────────────────────────────────────────────────
# 연도 범위 완전탐색 (Best 사주 역산)
# ─────────────────────────────────────────────────────────────────────────
def _iter_days(year_from: int, year_to: int):
    d, end = date(year_from, 1, 1), date(year_to, 12, 31)
    while d <= end:
        yield d
        d += timedelta(days=1)


def best_in_year_range(
    me: BirthInput,
    year_from: int,
    year_to: int,
    *,
    hours: tuple[int, ...] = (12,),
    top_k: int = 10,
    summary_k: int = 5,
) -> dict:
    """연도 구간 [year_from, year_to] 의 사주 공간을 완전탐색해
    나와 최고 궁합인 생일을 역산한다.

    hours: 탐색할 시(時). 기본 (12,)=정오 고정(일 단위). 시주는 오행분포에만
        영향을 주므로 생시 미상이면 정오 1점이 실용적이다. 정밀 탐색은
        hours=tuple(range(24)) 등으로 넓힌다(스캔 비용 비례 증가).
    반환: top(상위 top_k 행) + best_score/best_grade + 최고점 동치류
        (ilju_dist=일주 분포, tti_dist=띠 분포, most_common) + scanned/best_count
        + trace. 같은 입력이면 top 라벨·점수 시퀀스까지 동일(결정론).
    """
    if year_from > year_to:
        year_from, year_to = year_to, year_from
    with_hour = len(hours) > 1
    me_chart = compute_chart(me)

    # (총점, tie-break, 후보생일, 일주명, 띠명, 궁합결과)
    scored: list[tuple[int, tuple, BirthInput, str, str, dict]] = []
    for d in _iter_days(year_from, year_to):
        for h in hours:
            cb = BirthInput(d.year, d.month, d.day, h)
            cc = compute_chart(cb)
            res = gunghap_charts(me_chart, cc)
            tie = (d.year, d.month, d.day, h)
            scored.append(
                (res["총점"], tie, cb, cc.day.name, C.JIJI_HANGUL[cc.year.branch], res)
            )

    scored.sort(key=lambda x: (-x[0], x[1]))
    best_score = scored[0][0]
    best_group = [x for x in scored if x[0] == best_score]
    ilju = Counter(x[3] for x in best_group)
    tti = Counter(x[4] for x in best_group)

    top = [_row(_birth_label(b, with_hour), b, r)
           for (_s, _t, b, _ij, _tt, r) in scored[:top_k]]

    trace = Trace(
        rule_id="matching.best_range",
        preset_id="gunghap",
        layer="L1",
        inputs={
            "from": year_from, "to": year_to,
            "hours": len(hours), "scanned": len(scored),
            "best_score": best_score, "best_count": len(best_group),
        },
        classical_source="자평 궁합 완전탐색(연도구간 사주공간)",
    )
    return {
        "top": top,
        "best_score": best_score,
        "best_grade": scored[0][5]["등급"],
        "scanned": len(scored),
        "best_count": len(best_group),
        "ilju_dist": ilju.most_common(summary_k),
        "tti_dist": tti.most_common(summary_k),
        "trace": trace,
    }
