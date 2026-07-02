"""개인 보고서 페이지(/me) — 한 계정의 모든 탐색을 한 장에.

서버 렌더 HTML(哲命 팔레트, web/index.html 과 동일 무드). 마크다운 본문은
서버에서 escape 해 숨겨두고, 클라이언트에서 marked + DOMPurify(CDN)로
렌더한다(LLM 생성 텍스트 — sanitize 필수).

구성: 프로필(命 팔자 미니 격자 + 哲 top 철학자) → 🔗 통합 리포트 →
🔮 사주 기록 → 🧭 철학 기록. 데이터는 reports_store / engine.store /
philosophy.store 에서 읽는다.
"""
from __future__ import annotations

import html

import reports_store
from engine import store as saju_store
from engine.pillars import compute_chart
from engine.presets import load_preset
from engine.reports import DEFAULT_PRESET
from philosophy import store as philo_store


def _md_block(body: str) -> str:
    """마크다운 원문을 escape 해 숨김 div 로 — JS 가 textContent 로 읽어 렌더."""
    return (f'<div class="md-src" hidden>{html.escape(body)}</div>'
            f'<div class="md-out">렌더 중…</div>')


def _entry(title: str, when: str, body: str, *, open_: bool = False) -> str:
    return (f'<details class="entry"{" open" if open_ else ""}>'
            f'<summary><b>{html.escape(title)}</b>'
            f'<time data-utc="{html.escape(when)}">{html.escape(when)}</time></summary>'
            f'{_md_block(body)}</details>')


def _saju_card(username: str) -> str:
    prof = saju_store.get_profile(username)
    if not prof:
        return ('<div class="card"><span class="tag"><b class="v">命</b> 사주 프로필</span>'
                '<p class="empty">아직 없어요 — 채팅의 🔮 프로필에서 생년월일시를 '
                '입력하면 저장됩니다.</p></div>')
    b = prof["birth"]
    cfg = load_preset(DEFAULT_PRESET).deterministic
    chart = compute_chart(b, cfg)
    chars = chart.eight_chars().split()  # ['무인','계해','임술','신해']
    labels = ["년", "월", "일", "시"]
    cells = "".join(
        f'<div class="pillar{" day" if i == 2 else ""}">'
        f'<span class="pl">{labels[i]}</span><span class="ph">{c}</span></div>'
        for i, c in enumerate(chars))
    return (f'<div class="card"><span class="tag"><b class="v">命</b> 사주 프로필</span>'
            f'<div class="myeongsik">{cells}</div>'
            f'<p class="meta">{b.year}-{b.month:02d}-{b.day:02d} {b.hour:02d}:{b.minute:02d}'
            f' · {prof.get("gender") or "성별 미지정"} · 기준 유파: 표준(정통 억부)</p></div>')


def _philo_card(username: str) -> str:
    diag = philo_store.get_diagnosis(username)
    if not diag or not diag.get("top_philosophers"):
        return ('<div class="card"><span class="tag"><b class="a">哲</b> 철학 진단</span>'
                '<p class="empty">아직 없어요 — 채팅의 🧭 프로필에서 가치관을 한 문장 '
                '들려주면 저장됩니다.</p></div>')
    tops = diag["top_philosophers"][:3]
    rows = "".join(f'<li><b>{html.escape(str(t.get("label")))}</b>'
                   f'<span>점수 {t.get("score")} · 유사주장 {t.get("n_support")}건</span></li>'
                   for t in tops)
    q = html.escape((diag.get("query") or "")[:70])
    return (f'<div class="card"><span class="tag"><b class="a">哲</b> 철학 진단</span>'
            f'<p class="quote">“{q}”</p><ol class="phil-list">{rows}</ol></div>')


def _section(icon: str, title: str, entries: list[str], empty_hint: str) -> str:
    body = "".join(entries) if entries else f'<p class="empty">{empty_hint}</p>'
    return (f'<section class="records"><h2>{icon} {html.escape(title)}'
            f'<span class="cnt">{len(entries)}</span></h2>{body}</section>')


def render_me_page(username: str) -> str:
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

    return f"""<!DOCTYPE html>
<html lang="ko">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>哲命 — {u} 님의 기록</title>
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
  <a class="go" href="/app">← 채팅으로</a>
</div></nav>
<div class="wrap">
<header class="me">
  <h1>{u} 님의 탐구 기록</h1>
  <p class="sub">두 렌즈로 나를 읽어온 흔적 — 모든 결과는 자동으로 저장되고, 언제든 여기서 다시 볼 수 있어요.</p>
  <div class="badges">
    <span class="badge">🔮 사주 리포트 {c['saju']}건</span>
    <span class="badge">🧭 철학 진단 {c['philo']}건</span>
    <span class="badge">🔗 통합 리포트 {c['fusion']}건</span>
  </div>
</header>

<div class="cards">
{_saju_card(username)}
{_philo_card(username)}
</div>

{_section("🔗", "통합 리포트 — 사주 × 철학", fusion_entries,
          "아직 없어요 — 채팅에서 사주와 철학을 모두 탐색한 뒤 '🔗 사주×철학 통합 리포트' 버튼을 눌러보세요.")}
{_section("🔮", "사주 탐색 기록", saju_entries,
          "아직 없어요 — 🔮 프로필에서 신년운세·궁합 등 카테고리를 골라보세요.")}
{_section("🧭", "철학 탐색 기록", philo_entries,
          "아직 없어요 — 🧭 프로필에서 가치관을 한 문장 들려주세요.")}

<footer>哲命 — 재미와 자기 성찰을 위한 기록입니다. 중요한 결정은 언제나 당신의 몫.</footer>
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
    if (!isNaN(d)) t.textContent = d.toLocaleString("ko-KR", {{dateStyle: "medium", timeStyle: "short"}});
  }});
</script>
</body>
</html>"""
