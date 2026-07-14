"""개인 보고서 페이지(/me) — 한 계정의 모든 탐색을 한 장에.

서버 렌더 HTML(哲命 팔레트, web/index.html 과 동일 무드). 마크다운 본문은
서버에서 escape 해 숨겨두고, 클라이언트에서 marked + DOMPurify(CDN)로
렌더한다(LLM 생성 텍스트 — sanitize 필수).

구성: 프로필(命 팔자 미니 격자 + 哲 top 철학자 + 🎯 Schwartz 8각 레이더) →
🔗 통합 리포트 → 🔮 사주 기록 → 🧭 철학 기록. 데이터는 reports_store /
engine.store / philosophy.store 에서 읽고, 레이더 SVG 는 서버가 결정론으로 그린다.
"""
from __future__ import annotations

import html
import math

import reports_store
from engine import i18n
from engine import store as saju_store
from engine.i18n import ganji_en, is_en, t, term
from engine.pillars import compute_chart
from engine.presets import load_preset
from engine.reports import DEFAULT_PRESET
from philosophy import store as philo_store
from philosophy import values as schwartz

# Schwartz 라벨(philosophy.values 의 한국어 정체성 키) → 영어 — 표시 경계 전용
_SCHWARTZ_EN = {
    "자기주도": "Self-Direction", "자극·쾌락": "Stimulation·Hedonism", "성취": "Achievement",
    "권력": "Power", "안전": "Security", "전통·동조": "Tradition·Conformity",
    "자애": "Benevolence", "보편": "Universalism",
    "자극": "Stimulation", "쾌락": "Hedonism", "전통": "Tradition", "동조": "Conformity",
    "변화 개방": "Openness to Change", "자기 고양": "Self-Enhancement",
    "보존": "Conservation", "자기 초월": "Self-Transcendence",
}


def _sv(label: str) -> str:
    """Schwartz 가치/사분면 라벨 표시 — en 이면 영어(사전 밖이면 원문)."""
    return _SCHWARTZ_EN.get(label, label) if is_en() else label


def _md_block(body: str) -> str:
    """마크다운 원문을 escape 해 숨김 div 로 — JS 가 textContent 로 읽어 렌더."""
    return (f'<div class="md-src" hidden>{html.escape(body)}</div>'
            f'<div class="md-out">{t("렌더 중…", "Rendering…")}</div>')


def _entry(title: str, when: str, body: str, *, open_: bool = False) -> str:
    return (f'<details class="entry"{" open" if open_ else ""}>'
            f'<summary><b>{html.escape(title)}</b>'
            f'<time data-utc="{html.escape(when)}">{html.escape(when)}</time></summary>'
            f'{_md_block(body)}</details>')


def _saju_card(username: str) -> str:
    prof = saju_store.get_profile(username)
    tag = t("사주 프로필", "Saju Profile")
    if not prof:
        empty = t("아직 없어요 — 채팅의 🔮 프로필에서 생년월일시를 입력하면 저장됩니다.",
                  "Nothing here yet — enter your birth date and time in the chat's "
                  "🔮 profile and it will be saved.")
        return (f'<div class="card"><span class="tag"><b class="v">命</b> {tag}</span>'
                f'<p class="empty">{empty}</p></div>')
    b = prof["birth"]
    cfg = load_preset(DEFAULT_PRESET).deterministic
    chart = compute_chart(b, cfg)
    chars = chart.eight_chars().split()  # ['무인','계해','임술','신해']
    if is_en():
        chars = [ganji_en(c) for c in chars]  # 'Mu-in' 등 로마자 표시
    labels = ["년", "월", "일", "시"]
    cells = "".join(
        f'<div class="pillar{" day" if i == 2 else ""}">'
        f'<span class="pl">{term(labels[i])}</span><span class="ph">{c}</span></div>'
        for i, c in enumerate(chars))
    gender = term(prof.get("gender")) if prof.get("gender") else t("성별 미지정",
                                                                   "gender unspecified")
    school = t("기준 유파: 표준(정통 억부)", "reference school: Standard (Classic Eokbu)")
    return (f'<div class="card"><span class="tag"><b class="v">命</b> {tag}</span>'
            f'<div class="myeongsik">{cells}</div>'
            f'<p class="meta">{b.year}-{b.month:02d}-{b.day:02d} {b.hour:02d}:{b.minute:02d}'
            f' · {gender} · {school}</p></div>')


def _philo_card(username: str) -> str:
    diag = philo_store.get_diagnosis(username)
    tag = t("철학 진단", "Philosophy Diagnosis")
    if not diag or not diag.get("top_philosophers"):
        empty = t("아직 없어요 — 채팅의 🧭 프로필에서 가치관을 한 문장 들려주면 저장됩니다.",
                  "Nothing here yet — share one sentence about your values in the chat's "
                  "🧭 profile and it will be saved.")
        return (f'<div class="card"><span class="tag"><b class="a">哲</b> {tag}</span>'
                f'<p class="empty">{empty}</p></div>')
    tops = diag["top_philosophers"][:3]

    def _score_line(tp: dict) -> str:
        return t(f"점수 {tp.get('score')} · 유사주장 {tp.get('n_support')}건",
                 f"score {tp.get('score')} · {tp.get('n_support')} similar claims")

    rows = "".join(f'<li><b>{html.escape(str(tp.get("label")))}</b>'
                   f'<span>{_score_line(tp)}</span></li>'
                   for tp in tops)
    q = html.escape((diag.get("query") or "")[:70])
    return (f'<div class="card"><span class="tag"><b class="a">哲</b> {tag}</span>'
            f'<p class="quote">“{q}”</p><ol class="phil-list">{rows}</ol></div>')


def _octagon_svg(axes: list[tuple[str, float]]) -> str:
    """Schwartz 8각 레이더 SVG — 서버 결정론 렌더 (axes: [(라벨, 0~10)] 8개).

    축 순서는 circumplex — 대각이 이론적 대립(자기주도↔안전, 성취↔자애 등)과 마주본다.
    """
    cx, cy, radius = 130.0, 118.0, 82.0

    def pt(i: int, r: float) -> tuple[float, float]:
        a = math.radians(-90 + i * 45)
        return (round(cx + r * math.cos(a), 1), round(cy + r * math.sin(a), 1))

    def ring(r: float) -> str:
        return " ".join(f"{x},{y}" for x, y in (pt(i, r) for i in range(8)))

    shape = " ".join(f"{x},{y}" for x, y in
                     (pt(i, radius * v / 10.0) for i, (_l, v) in enumerate(axes)))
    spokes = "".join(
        f'<line class="sp" x1="{cx}" y1="{cy}" x2="{x}" y2="{y}"/>'
        for x, y in (pt(i, radius) for i in range(8)))
    dots = "".join(f'<circle class="dt" cx="{x}" cy="{y}" r="2.6"/>'
                   for x, y in (pt(i, radius * v / 10.0)
                                for i, (_l, v) in enumerate(axes)))
    labels = []
    for i, (label, v) in enumerate(axes):
        x, y = pt(i, radius + 17)
        anchor = "middle" if i in (0, 4) else ("start" if 1 <= i <= 3 else "end")
        dy = 4 if i in (3, 4, 5) else 0
        labels.append(f'<text class="lb" x="{x}" y="{y + dy}" text-anchor="{anchor}">'
                      f'{html.escape(_sv(label))} <tspan class="vv">{v:g}</tspan></text>')
    aria = t("Schwartz 가치 8각 프로파일", "Schwartz values octagon profile")
    return (f'<svg class="octa" viewBox="0 0 260 240" role="img" '
            f'aria-label="{aria}">'
            f'<polygon class="gr" points="{ring(radius)}"/>'
            f'<polygon class="gr" points="{ring(radius / 2)}"/>{spokes}'
            f'<polygon class="sh" points="{shape}"/>{dots}{"".join(labels)}</svg>')


def _values_card(username: str) -> str:
    diag = philo_store.get_diagnosis(username)
    raw = (diag or {}).get("value_scores") or {}
    octa = schwartz.to_octagon(raw)
    tag = t("가치 프로파일 (Schwartz 기본가치)", "Values Profile (Schwartz basic values)")
    if not octa:
        empty = t("아직 없어요 — 🧭 철학 탐구에서 가치관을 진단하면 회수된 주장의 "
                  "가치층(promotes/demotes)으로 8각 프로파일이 그려집니다.",
                  "Nothing here yet — run a values diagnosis in 🧭 Philosophy and the "
                  "octagon profile is drawn from the value layer (promotes/demotes) of "
                  "the retrieved claims.")
        return (f'<div class="card"><span class="tag"><b class="a">🎯</b> {tag}</span>'
                f'<p class="empty">{empty}</p></div>')
    tops = schwartz.top_values(raw)
    top_line = " · ".join(f"{_sv(n)} <span>({_sv(q)})</span>" for n, q, _s in tops)
    lead = t("지향", "Leaning")
    meta = t("회수된 유사 주장의 가치층(promotes/demotes × 유사도) 결정론 "
             "집계 — 최댓값을 10으로 하는 상대 스케일. 축 배열은 Schwartz 원형 구조로, "
             "마주보는 축은 이론상 긴장 관계(자기주도↔안전, 성취↔자애)예요.",
             "A deterministic tally of the retrieved claims' value layer "
             "(promotes/demotes × similarity), scaled so the maximum is 10. Axes follow "
             "the Schwartz circumplex — opposite axes are in theoretical tension "
             "(Self-Direction↔Security, Achievement↔Benevolence).")
    return (f'<div class="card card-wide"><span class="tag"><b class="a">🎯</b> {tag}</span>'
            f'<div class="octa-wrap">{_octagon_svg(octa)}'
            f'<div class="octa-side"><p class="octa-top">{lead}: {top_line}</p>'
            f'<p class="meta">{meta}</p></div>'
            f'</div></div>')


def _section(icon: str, title: str, entries: list[str], empty_hint: str) -> str:
    body = "".join(entries) if entries else f'<p class="empty">{empty_hint}</p>'
    return (f'<section class="records"><h2>{icon} {html.escape(title)}'
            f'<span class="cnt">{len(entries)}</span></h2>{body}</section>')


def render_me_page(username: str, lang: str = "ko") -> str:
    i18n.set_lang(lang)  # 요청 단위 언어 — FastAPI 라우트(main.py)가 ?lang= 을 넘긴다
    u = html.escape(username)
    c = reports_store.counts(username)
    fusions = reports_store.list_fusion_reports(username, limit=5)
    sajus = reports_store.list_saju_reports(username, limit=20)
    philos = reports_store.list_philo_reports(username, limit=20)

    fusion_entries = [
        _entry(f["title"], f["created_at"], f["body"], open_=(i == 0))
        for i, f in enumerate(fusions)]
    saju_entries = [_entry(s["title"], s["created_at"], s["body"]) for s in sajus]
    philo_entries = [
        _entry(f"“{(p['query'] or '')[:46]}…\"" if len(p["query"] or "") > 46
               else f"“{p['query']}”", p["created_at"], p["body"])
        for p in philos]

    page_title = t(f"哲命 — {u} 님의 기록", f"哲命 — {u}'s Records")
    back_chat = t("← 채팅으로", "← Back to chat")
    lang_link = ('<a class="go" href="?lang=ko">한국어</a>' if is_en()
                 else '<a class="go" href="?lang=en">EN</a>')
    h1 = t(f"{u} 님의 탐구 기록", f"{u}'s Exploration Records")
    sub = t("두 렌즈로 나를 읽어온 흔적 — 모든 결과는 자동으로 저장되고, 언제든 여기서 다시 볼 수 있어요.",
            "Traces of reading yourself through two lenses — every result is saved "
            "automatically and can be revisited here anytime.")
    badge_saju = t(f"🔮 사주 리포트 {c['saju']}건", f"🔮 Saju reports: {c['saju']}")
    badge_philo = t(f"🧭 철학 진단 {c['philo']}건", f"🧭 Philosophy diagnoses: {c['philo']}")
    badge_fusion = t(f"🔗 통합 리포트 {c['fusion']}건", f"🔗 Combined reports: {c['fusion']}")
    sec_fusion = t("통합 리포트 — 사주 × 철학", "Combined Reports — Saju × Philosophy")
    sec_fusion_empty = t("아직 없어요 — 채팅에서 사주와 철학을 모두 탐색한 뒤 "
                         "'🔗 사주×철학 통합 리포트' 버튼을 눌러보세요.",
                         "Nothing here yet — explore both Saju and Philosophy in chat, "
                         "then press the '🔗 Saju × Philosophy combined report' button.")
    sec_saju = t("사주 탐색 기록", "Saju Explorations")
    sec_saju_empty = t("아직 없어요 — 🔮 프로필에서 신년운세·궁합 등 카테고리를 골라보세요.",
                       "Nothing here yet — pick a category (New Year, compatibility, …) "
                       "in the 🔮 profile.")
    sec_philo = t("철학 탐색 기록", "Philosophy Explorations")
    sec_philo_empty = t("아직 없어요 — 🧭 프로필에서 가치관을 한 문장 들려주세요.",
                        "Nothing here yet — share one sentence about your values in the "
                        "🧭 profile.")
    footer = t("哲命 — 재미와 자기 성찰을 위한 기록입니다. 중요한 결정은 언제나 당신의 몫.",
               "哲命 — records for fun and self-reflection. The big decisions are "
               "always yours.")
    locale = "en-US" if is_en() else "ko-KR"
    html_lang = "en" if is_en() else "ko"

    return f"""<!DOCTYPE html>
<html lang="{html_lang}">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{page_title}</title>
<meta name="robots" content="noindex">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Gowun+Batang:wght@400;700&family=IBM+Plex+Mono:wght@400;500&family=Noto+Sans+KR:wght@400;500;700&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/marked@12/marked.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/dompurify@3/dist/purify.min.js"></script>
<style>
  :root{{--ink:#141824;--ink-deep:#0e111a;--ink-soft:#1d2333;--paper:#e9e4d6;
    --vermilion:#c2453f;--aegean:#6b8fb3;--mist:#8b93a7;--line:#2a3145;
    --disp:"Gowun Batang",serif;--body:"Noto Sans KR",sans-serif;--mono:"IBM Plex Mono",monospace}}
  *{{margin:0;padding:0;box-sizing:border-box}}
  body{{background:var(--ink);color:var(--paper);font-family:var(--body);line-height:1.75}}
  a{{color:inherit;text-decoration:none}}
  .wrap{{max-width:820px;margin:0 auto;padding:0 22px 80px}}
  nav{{position:sticky;top:0;z-index:10;background:color-mix(in srgb,var(--ink) 90%,transparent);
      backdrop-filter:blur(10px);border-bottom:1px solid var(--line)}}
  .nav-in{{max-width:820px;margin:0 auto;padding:0 22px;height:56px;display:flex;
          align-items:center;justify-content:space-between}}
  .brand{{font-family:var(--disp);font-size:1.15rem;letter-spacing:.35em}}
  .brand em{{font-style:normal;color:var(--vermilion)}}
  .nav-in a.go{{font-size:.85rem;color:var(--mist)}} .nav-in a.go:hover{{color:var(--paper)}}
  header.me{{padding:52px 0 8px}}
  header.me h1{{font-family:var(--disp);font-size:clamp(1.6rem,4vw,2.3rem);line-height:1.35}}
  header.me .sub{{color:var(--mist);font-size:.9rem;margin-top:10px}}
  .badges{{display:flex;gap:10px;margin-top:16px;flex-wrap:wrap}}
  .badge{{border:1px solid var(--line);border-radius:999px;padding:5px 14px;font-size:.8rem;color:var(--mist)}}
  .cards{{display:grid;grid-template-columns:1fr 1fr;gap:16px;margin-top:30px}}
  @media(max-width:640px){{.cards{{grid-template-columns:1fr}}}}
  .card{{background:var(--ink-soft);border:1px solid var(--line);border-radius:10px;padding:22px}}
  .tag{{font-family:var(--mono);font-size:.72rem;letter-spacing:.24em;color:var(--mist);
       text-transform:uppercase;display:block;margin-bottom:14px}}
  .tag .v{{color:var(--vermilion)}} .tag .a{{color:var(--aegean)}}
  .myeongsik{{display:grid;grid-template-columns:repeat(4,1fr);gap:6px;max-width:260px}}
  .pillar{{background:var(--ink-deep);border:1px solid var(--line);border-radius:6px;
          padding:8px 4px;text-align:center}}
  .pillar .pl{{font-size:.66rem;color:var(--mist);display:block}}
  .pillar .ph{{font-family:var(--disp);font-size:1.1rem}}
  .pillar.day{{border-color:color-mix(in srgb,var(--vermilion) 60%,var(--line))}}
  .pillar.day .ph{{color:var(--vermilion)}}
  .card .meta{{color:var(--mist);font-size:.8rem;margin-top:12px}}
  .card .quote{{font-family:var(--disp);font-size:.95rem;line-height:1.6}}
  .phil-list{{margin:12px 0 0 18px;display:grid;gap:6px;font-size:.88rem}}
  .phil-list span{{color:var(--mist);font-size:.78rem;margin-left:8px}}
  .empty{{color:var(--mist);font-size:.88rem}}
  .card-wide{{grid-column:1 / -1}}
  .octa-wrap{{display:flex;gap:24px;align-items:center;flex-wrap:wrap}}
  .octa{{width:280px;max-width:100%;flex:0 0 auto}}
  .octa .gr{{fill:none;stroke:var(--line);stroke-width:1}}
  .octa .sp{{stroke:var(--line);stroke-width:1}}
  .octa .sh{{fill:color-mix(in srgb,var(--aegean) 30%,transparent);stroke:var(--aegean);
            stroke-width:2;stroke-linejoin:round}}
  .octa .dt{{fill:var(--aegean)}}
  .octa .lb{{fill:var(--paper);font-family:var(--body);font-size:11.5px}}
  .octa .vv{{fill:var(--mist);font-family:var(--mono);font-size:9.5px}}
  .octa-side{{flex:1;min-width:220px}}
  .octa-top{{font-size:.92rem}} .octa-top span{{color:var(--mist);font-size:.8rem}}
  .records{{margin-top:52px}}
  .records h2{{font-family:var(--disp);font-size:1.3rem;border-bottom:1px solid var(--line);
              padding-bottom:10px;display:flex;align-items:baseline;gap:10px}}
  .records .cnt{{font-family:var(--mono);font-size:.8rem;color:var(--mist)}}
  .entry{{border:1px solid var(--line);border-radius:8px;margin-top:14px;background:var(--ink-soft)}}
  .entry summary{{cursor:pointer;padding:14px 18px;display:flex;justify-content:space-between;
                 gap:12px;align-items:baseline;list-style:none}}
  .entry summary::-webkit-details-marker{{display:none}}
  .entry summary b{{font-weight:500;font-size:.95rem}}
  .entry time{{color:var(--mist);font-size:.75rem;font-family:var(--mono);white-space:nowrap}}
  .entry[open] summary{{border-bottom:1px solid var(--line)}}
  .md-out{{padding:6px 22px 20px;font-size:.92rem}}
  .md-out h1,.md-out h2,.md-out h3{{font-family:var(--disp);margin:18px 0 8px;line-height:1.4}}
  .md-out h1{{font-size:1.25rem}} .md-out h2{{font-size:1.1rem}}
  .md-out p{{margin:8px 0}} .md-out li{{margin-left:20px}}
  .md-out blockquote{{border-left:2px solid var(--vermilion);padding-left:12px;color:var(--mist);margin:10px 0}}
  .md-out table{{border-collapse:collapse;margin:10px 0;font-size:.85rem}}
  .md-out th,.md-out td{{border:1px solid var(--line);padding:5px 10px}}
  .md-out code{{font-family:var(--mono);background:var(--ink-deep);padding:1px 5px;border-radius:3px;font-size:.85em}}
  .md-out hr{{border:0;border-top:1px solid var(--line);margin:14px 0}}
  footer{{margin-top:70px;color:var(--mist);font-size:.78rem;border-top:1px solid var(--line);padding-top:22px}}
</style>
</head>
<body>
<nav><div class="nav-in">
  <a class="brand" href="/">哲<em>命</em></a>
  <span style="display:flex;gap:16px">{lang_link}<a class="go" href="/app">{back_chat}</a></span>
</div></nav>
<div class="wrap">
<header class="me">
  <h1>{h1}</h1>
  <p class="sub">{sub}</p>
  <div class="badges">
    <span class="badge">{badge_saju}</span>
    <span class="badge">{badge_philo}</span>
    <span class="badge">{badge_fusion}</span>
  </div>
</header>

<div class="cards">
{_saju_card(username)}
{_philo_card(username)}
{_values_card(username)}
</div>

{_section("🔗", sec_fusion, fusion_entries, sec_fusion_empty)}
{_section("🔮", sec_saju, saju_entries, sec_saju_empty)}
{_section("🧭", sec_philo, philo_entries, sec_philo_empty)}

<footer>{footer}</footer>
</div>
<script>
  // 마크다운 렌더 — 서버가 escape 해 둔 원문을 textContent 로 읽어 sanitize 후 삽입
  document.querySelectorAll(".md-src").forEach(src => {{
    const out = src.nextElementSibling;
    out.innerHTML = DOMPurify.sanitize(marked.parse(src.textContent));
  }});
  // UTC → 로컬 시각
  document.querySelectorAll("time[data-utc]").forEach(t => {{
    const d = new Date(t.dataset.utc);
    if (!isNaN(d)) t.textContent = d.toLocaleString("{locale}", {{dateStyle: "medium", timeStyle: "short"}});
  }});
</script>
</body>
</html>"""
