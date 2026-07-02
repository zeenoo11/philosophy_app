"""L1 결정론 — 시기별 운세(세운/월운/일진/주간) 간지 산출.

순수 결정론: 입력(차트 + 연/월/일) → 출력(해당 시기의 간지·십신·신살).
'좋다/나쁘다'의 서술 해석은 이 레이어에 없고, day_luck 의 score 만 규칙 기반
점수(아래 명시)로 산출한다. 외부 정답을 박제하지 않으며 규칙·일치만 검증한다.

간지 규약 (constants 와 동일):
  세운(歲運) — 연 간지: gz = (year - 4) % 60
  월운(月運) — 절기월 간지: 寅월(2)~丑월(1) 12개월, 천간은 오호둔(五虎遁)
  일진(日辰) — 일 간지: day_gz60(y, m, d)
"""
from __future__ import annotations

from datetime import date, timedelta

from engine import constants as C
from engine.pillars import day_gz60
from engine.provenance import Trace

# ─────────────────────────────────────────────────────────────────────────
# 절기월(寅월=2) → 양력월 근사 라벨
#   입춘(寅월)을 양력 2월로 보는 통상 근사. 子월/丑월은 동지·소한 구간으로
#   양력으로는 연말~연초(12월/1월)에 걸쳐 '근사' 라벨만 부여한다.
# ─────────────────────────────────────────────────────────────────────────
_SOLAR_MONTH_APPROX = {
    2: "2월",          # 寅
    3: "3월",          # 卯
    4: "4월",          # 辰
    5: "5월",          # 巳
    6: "6월",          # 午
    7: "7월",          # 未
    8: "8월",          # 申
    9: "9월",          # 酉
    10: "10월",        # 戌
    11: "11월",        # 亥
    0: "12월",         # 子
    1: "1월(익년)",    # 丑
}


def _from_date(d) -> date:
    """tuple[int,int,int] | date → date."""
    if isinstance(d, date):
        return d
    return date(d[0], d[1], d[2])


# ─────────────────────────────────────────────────────────────────────────
# 세운 (歲運)
# ─────────────────────────────────────────────────────────────────────────
def saeun(chart, year: int) -> dict:
    """해당 연도의 세운(연 간지) + 일간 기준 십신·오행.

    gz = (year - 4) % 60. 지지 십신은 지지 정기(正氣) 천간 기준.
    """
    dm = chart.day_master
    gz = (year - 4) % 60
    stem = gz % 10
    branch = gz % 12
    jg = C.jeonggi(branch)   # 지지 정기(본기) 천간

    trace = Trace(
        rule_id="luck.saeun",
        preset_id="",
        layer="L1",
        inputs={"year": year, "gz60": gz, "ganji": C.gz_name(gz),
                "day_master": dm},
        classical_source="자평 세운/월운/일진",
    )
    return {
        "year": year,
        "ganji": C.gz_name(gz),
        "gz60": gz,
        "천간십신": C.sipsin(dm, stem),
        "지지십신": C.sipsin(dm, jg),
        "오행": C.OHAENG_HANGUL[C.CHEONGAN_OHAENG[stem]],
        "trace": trace,
    }


# ─────────────────────────────────────────────────────────────────────────
# 월운 (月運)
# ─────────────────────────────────────────────────────────────────────────
def month_luck(chart, year: int) -> list[dict]:
    """그 해 12개월(寅월~丑월 절기월)의 월간지 + 십신.

    연간 = (year - 4) % 10. 寅월 천간 = 오호둔 = (2*연간 + 2) % 10, 이후 +1.
    월지 = 寅(2)부터 +1 (12개). 지지 십신은 월지 정기 천간 기준.
    """
    dm = chart.day_master
    year_stem = (year - 4) % 10
    inmonth_stem = (2 * year_stem + 2) % 10   # 오호둔: 寅월 천간

    out: list[dict] = []
    for k in range(12):
        branch = (2 + k) % 12               # 寅(2)부터
        stem = (inmonth_stem + k) % 10       # 寅월 천간부터 순행 +1
        gz = C.gz_from(stem, branch)
        jg = C.jeonggi(branch)
        out.append({
            "월지": C.JIJI_HANGUL[branch],
            "ganji": C.gz_name(gz),
            "gz60": gz,
            "천간십신": C.sipsin(dm, stem),
            "지지십신": C.sipsin(dm, jg),
            "양력월_근사": _SOLAR_MONTH_APPROX[branch],
        })
    return out


# ─────────────────────────────────────────────────────────────────────────
# 일진 (日辰)
# ─────────────────────────────────────────────────────────────────────────
def day_luck(chart, date: tuple[int, int, int]) -> dict:
    """일진(일 간지) + 신살 + 규칙 기반 길흉 점수.

    신살(일간/년지 기준):
      천을귀인 — 일진 지지 ∈ CHEONEUL_GWIIN[일간]
      양인     — 일진 지지 == YANGIN[일간]
      문창     — 일진 지지 == MUNCHANG[일간]
      도화/역마/화개 — 년지 기준 십이신살이 각각 년살/역마/화개일 때

    score(0~100, 최종 25~95 clamp 정수) 산출 근거:
      base = 55.
      천간십신(일간↔일진천간):
        정관/정재/정인/식신 → +15  (희신류)
        편관/겁재/상관       → -12  (기신류)
      천을귀인 또는 문창 존재 → +12
      양인 존재               → -10
      일진지지 ↔ 일지(chart.day.branch):
        육합(JIJI_YUKHAP)     → +8
        육충(JIJI_CHUNG)      → -10
    """
    dm = chart.day_master
    y, m, d = date[0], date[1], date[2]
    gz = day_gz60(y, m, d)
    stem = gz % 10
    branch = gz % 12

    cheongan_sipsin = C.sipsin(dm, stem)
    jg = C.jeonggi(branch)
    jiji_sipsin = C.sipsin(dm, jg)

    # ── 신살 수집 ──
    sinsal: list[str] = []
    has_cheoneul = branch in C.CHEONEUL_GWIIN[dm]
    if has_cheoneul:
        sinsal.append("천을귀인")
    has_yangin = branch == C.YANGIN.get(dm)
    if has_yangin:
        sinsal.append("양인")
    has_munchang = branch == C.MUNCHANG[dm]
    if has_munchang:
        sinsal.append("문창")
    # 년지 기준 십이신살 → 도화(년살)/역마/화개 매핑
    s12 = C.sibi_sinsal_at(chart.year.branch, branch)
    if s12 == "년살":
        sinsal.append("도화")
    elif s12 == "역마":
        sinsal.append("역마")
    elif s12 == "화개":
        sinsal.append("화개")

    # ── 점수 산출 (위 docstring 규칙 그대로) ──
    score = 55
    if cheongan_sipsin in ("정관", "정재", "정인", "식신"):
        score += 15
    elif cheongan_sipsin in ("편관", "겁재", "상관"):
        score -= 12
    if has_cheoneul or has_munchang:
        score += 12
    if has_yangin:
        score -= 10
    pair = frozenset((branch, chart.day.branch))
    if pair in C.JIJI_YUKHAP:
        score += 8
    elif pair in C.JIJI_CHUNG:
        score -= 10
    score = max(25, min(95, score))   # clamp 25~95, 정수

    gilhyung = "좋음" if score >= 70 else ("보통" if score >= 45 else "주의")

    return {
        "date": f"{y:04d}-{m:02d}-{d:02d}",
        "ganji": C.gz_name(gz),
        "gz60": gz,
        "천간십신": cheongan_sipsin,
        "지지십신": jiji_sipsin,
        "신살": sinsal,
        "score": score,
        "길흉": gilhyung,
    }


# ─────────────────────────────────────────────────────────────────────────
# 주간 운세 (7일)
# ─────────────────────────────────────────────────────────────────────────
def week_luck(chart, start_date: tuple[int, int, int]) -> list[dict]:
    """start_date 부터 7일 연속 일진(day_luck)."""
    start = _from_date(start_date)
    out: list[dict] = []
    for k in range(7):
        d = start + timedelta(days=k)
        out.append(day_luck(chart, (d.year, d.month, d.day)))
    return out
