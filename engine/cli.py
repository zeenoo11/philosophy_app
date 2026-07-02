"""사주 차트 뷰어 (L1 결정론 출력 확인용).

사용:
  uv run python -m engine.cli 1990-06-15 14:30
  uv run python -m engine.cli 1990-06-15 14:30 --preset mangpa
  uv run python -m engine.cli 2000-01-01 23:30 --no-true-solar --jasi jasi_unified
"""
from __future__ import annotations

import argparse
from datetime import datetime

from engine import constants as C, relations, sinsal
from engine.daeun import compute_daeun
from engine.pillars import BirthInput, DeterministicConfig, compute_chart
from engine.presets import load_preset


def _grid(chart) -> str:
    cols = chart.pillars  # 년 월 일 시
    head = "        " + "".join(f"{p.position:^8}" for p in cols)
    hanja = "  천간  " + "".join(f"{p.hanja[0]:^8}" for p in cols)
    hang = "        " + "".join(f"{C.CHEONGAN_HANGUL[p.stem]:^7}" for p in cols)
    hanja2 = "  지지  " + "".join(f"{p.hanja[1]:^8}" for p in cols)
    hang2 = "        " + "".join(f"{C.JIJI_HANGUL[p.branch]:^7}" for p in cols)
    return "\n".join([head, hanja, hang, hanja2, hang2])


def render(chart, preset_id: str, gender: str | None = None) -> str:
    p = load_preset(preset_id)
    dm = C.CHEONGAN_HANGUL[chart.day_master]
    out = []
    out.append(f"┌─ 사주 차트 · {p.display_name} ({preset_id})")
    out.append(f"│  근거: {p.lineage}")
    out.append("└" + "─" * 50)
    out.append(f"\n8글자: {chart.eight_chars()}   (일간 日元: {dm}{C.OHAENG_HANGUL[C.CHEONGAN_OHAENG[chart.day_master]]})")
    out.append("")
    out.append(_grid(chart))

    out.append("\n[천간 십신]")
    out.append("  " + "  ".join(f"{k}:{v}" for k, v in chart.stem_sipsin().items()))

    out.append("\n[십이운성]  (" + chart.config.sipiunseong_theory + ")")
    out.append("  " + "  ".join(f"{k}:{v}" for k, v in chart.unseong().items()))

    out.append("\n[지장간 / 십신]  (" + chart.config.woryulbunya_theory + ")")
    for pos, items in chart.branch_jijanggan_sipsin().items():
        s = ", ".join(f"{g}({r[0]}·{ss})" for g, r, ss in items)
        out.append(f"  {pos}: {s}")

    rel = relations.analyze(chart)
    out.append("\n[합충형파해]")
    if rel:
        for k, vs in rel.items():
            tags = "; ".join("".join(v["글자"]) + (f"→{v['화기']}" if "화기" in v else "") for v in vs)
            out.append(f"  {k}: {tags}")
    else:
        out.append("  (없음)")

    ss = sinsal.analyze(chart)
    out.append("\n[신살]")
    for key in ("천을귀인", "양인", "문창귀인"):
        if ss.get(key):
            out.append(f"  {key}: {', '.join(ss[key])}")
    out.append(f"  공망: {', '.join(ss['공망_지지'])}" +
               (f" (위치: {', '.join(ss['공망_위치'])})" if ss.get("공망_위치") else ""))
    out.append(f"  십이신살(년지): " +
               ", ".join(f"{k}={v}" for k, v in ss["십이신살_년지기준"].items()))

    if gender in ("남", "여"):
        dr = compute_daeun(chart, gender)
        arrow = "順行" if dr.forward else "逆行"
        out.append(f"\n[대운]  ({gender}, {arrow}, 대운수 {dr.start_age})")
        out.append("  " + "  ".join(f"{age}세 {C.gz_name(g)}" for age, g, _ in dr.pillars))

    m = chart.meta
    out.append("\n[메타]")
    out.append(f"  UTC: {m['t_utc']:%Y-%m-%d %H:%M:%S}  |  tz오프셋: {m['utc_offset_hours']:+.1f}h")
    out.append(f"  태양벽시계: {m['solar_wall']:%Y-%m-%d %H:%M:%S}  |  태양황경: {m['solar_longitude']:.2f}°")
    out.append(f"  사주연도: {m['saju_year']}  |  입춘(UTC): {m['ipchun_utc']:%Y-%m-%d %H:%M:%S}")
    return "\n".join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description="사주 차트 뷰어 (L1 결정론)")
    ap.add_argument("date", help="생년월일 YYYY-MM-DD")
    ap.add_argument("time", nargs="?", default="12:00", help="시각 HH:MM (기본 12:00)")
    ap.add_argument("--preset", default="jeongtong_eokbu", help="유파 프리셋 id")
    ap.add_argument("--lon", type=float, default=None, help="경도(동경) 오버라이드")
    ap.add_argument("--no-true-solar", action="store_true", help="진태양시 보정 끔")
    ap.add_argument("--jasi", default=None, help="yajasi_split | jasi_unified")
    ap.add_argument("--gender", default=None, choices=["남", "여"], help="대운 산출용 성별")
    args = ap.parse_args(argv)

    d = datetime.strptime(args.date, "%Y-%m-%d")
    hh, mm = (int(x) for x in args.time.split(":"))
    cfg = load_preset(args.preset).deterministic
    over = {}
    if args.lon is not None:
        over["longitude_deg"] = args.lon
    if args.no_true_solar:
        over["true_solar_time"] = False
    if args.jasi:
        over["jasi_rule"] = args.jasi
    if over:
        cfg = DeterministicConfig(**{**cfg.__dict__, **over})

    chart = compute_chart(BirthInput(d.year, d.month, d.day, hh, mm), cfg)
    print(render(chart, args.preset, args.gender))


if __name__ == "__main__":
    main()
