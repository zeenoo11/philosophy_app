"""사주 운세 서비스 — 플랫폼 '🔮 사주 운세' 프로필 핸들러.

단독 앱이던 sajoo_app/app.py 를 Chat Profiles 구조로 이식한 모듈.
@cl.on_* 전역 데코레이터는 라우터(app.py)가 갖고, 이 모듈은 start /
on_message / on_settings 함수와 사주 전용 액션 콜백들을 제공한다.

흐름:
  1) 생년월일시 입력 → 사주 차트 + '전체 운세 한눈에'(즉시, 결정론)
  2) 해석 방식(간편 3종: 표준·현대·전통)을 먼저 고른다 — 일반인이 어려워하지 않게
     쉬운 말로. 전문가용 7종 유파는 '🔧 전문가용 더보기'로 접근.
  3) "무엇이 궁금하세요?" 카테고리 메뉴(버튼) → 상세 리포트(LLM, 선택 방식 기준 + 그라운딩)
     (신년운세/토정비결/애정·궁합/재물/평생/오늘·주간/건강)
     OpenRouter 백엔드면 토큰 스트리밍으로 섹션이 실시간으로 한 줄씩 차오른다.

해석 방식(유파)은 버튼 또는 '방식'/'유파' 입력으로 언제든 바꾼다(근거: docs/schools.md).
강약·용신 기준이 방식마다 갈리며, 선택은 세션에 저장되어 이후 리포트에 적용된다.
미선택 시 기본값은 '표준'(DEFAULT_PRESET=정통 억부)이라 곧바로 운세를 골라도 동작한다.
"""
from __future__ import annotations

import re
from datetime import datetime

import chainlit as cl
from chainlit.input_widget import Select, Switch

import mdutil
import reports_store
from engine import narrator, store
from engine.interpret import interpret
from engine.lunar import lunar_to_solar
from engine.matching import best_in_year_range, rank_candidates
from engine.pillars import BirthInput
from engine.reports import (CATALOG, DEFAULT_PRESET, _dehanja, deterministic_diff,
                            finalize_report, is_truncated, preset_menu, run_report,
                            simple_preset_menu)

# DB 초기화(init_db)와 인증 콜백은 라우터(app.py)가 담당한다.

_DATE_RE = re.compile(
    r"(\d{4})[-/.]\s*(\d{1,2})[-/.]\s*(\d{1,2})"
    r"(?:[\sT]+(\d{1,2})[:시]\s*(\d{1,2})?)?"
)
_YMD8_RE = re.compile(r"(?<!\d)(\d{4})(\d{2})(\d{2})(?:[ T]?(\d{2})(\d{2})?)?(?!\d)")
_TOPIC_EMOJI = {"성향": "🧭", "재물": "💰", "직업·명예": "🏆",
                "애정·궁합": "💕", "건강": "🩺", "대운": "⏳"}
# 타이핑으로도 카테고리 접근
_KEYWORDS = {
    "신년": "saeun", "올해": "saeun", "종합": "saeun", "토정": "tojeong",
    "애정": "aejeong", "사랑": "aejeong", "반쪽": "aejeong", "연애": "aejeong",
    "궁합": "gunghap", "재물": "wealth", "돈": "wealth", "부자": "wealth",
    "평생": "pyeongsaeng", "대운": "daeun", "오늘": "today", "주간": "week",
    "이번주": "week", "건강": "health",
}
# 성별이 꼭 필요한 카테고리(순행/역행 등) — 미입력 시 먼저 성별을 받는다.
_GENDER_REQUIRED = {"daeun"}

WELCOME = (
    "## 🔮 사주 운세\n"
    "**생년월일시와 성별**을 알려주세요 — 예: `1998-11-11 22:00 남`\n"
    "- 별다른 말이 없으면 **양력**으로 봐요. 음력이면 `음력` 을 붙여주세요 — 예: `음력 1998-09-23 22:00 남` (윤달이면 `윤`)\n"
    "- 성별은 대운·세운·평생운에 필요해요(생일만 입력하면 여쭤볼게요).\n"
    "- 🧭 **해석 방식**(표준·현대·전통)은 사주를 입력하면 바로 골라드릴게요 — 쉬운 말로 안내해요."
)


def _is_lunar(text: str) -> bool:
    """음/양 판별 — 기본 양력. '음력'/'음'(양 없을 때) 이면 음력."""
    if re.search(r"양력|陽", text):
        return False
    return bool(re.search(r"음력|陰|lunar", text, re.I)) or ("음" in text)


def _parse_input(text: str) -> tuple[BirthInput | None, dict]:
    """생년월일시 + 양/음력 파싱 → (BirthInput[양력], info).

    YYYY-MM-DD HH:MM / YYYYMMDD(HHMM) 지원. 음력이면 양력으로 변환(윤달 '윤').
    명시 없으면 양력. 유효하지 않으면 (None, {}).
    """
    m = _DATE_RE.search(text) or _YMD8_RE.search(text)
    if not m:
        return None, {}
    y, mo, d = int(m[1]), int(m[2]), int(m[3])
    hh = int(m[4]) if m[4] else 12
    mm = int(m[5]) if m[5] else 0
    lunar = _is_lunar(text)
    leap = "윤" in text
    info: dict = {"calendar": "음력" if lunar else "양력"}
    if lunar:
        if not (1 <= mo <= 12 and 1 <= d <= 30):
            return None, {}
        info["lunar"] = (y, mo, d, leap)
        try:
            y, mo, d = lunar_to_solar(y, mo, d, leap)
        except Exception:  # noqa: BLE001 — 존재하지 않는 음력일/윤달
            return None, {}
    try:  # 1998-13-45, 25:99 등 비정상 입력 방어 (크래시 방지)
        datetime(y, mo, d, hh, mm)
    except ValueError:
        return None, {}
    info["solar"] = (y, mo, d)
    return BirthInput(y, mo, d, hh, mm), info


def _parse_birth(text: str) -> BirthInput | None:
    return _parse_input(text)[0]


def _parse_gender(text: str) -> str | None:
    if re.search(r"(남자|남성|男|\bmale\b|\bm\b)", text, re.I):
        return "남"
    if re.search(r"(여자|여성|女|\bfemale\b|\bf\b)", text, re.I):
        return "여"
    has_m, has_f = ("남" in text), ("여" in text)
    if has_m and not has_f:
        return "남"
    if has_f and not has_m:
        return "여"
    return None


def _md_chart(result: dict) -> str:
    d = result.get("deterministic") or next(iter(result["by_preset"].values()))["deterministic"]
    cols = ["년", "월", "일", "시"]
    p, sip = d["pillars"], d["stem_sipsin"]
    rows = [
        "| | 년주 | 월주 | 일주 | 시주 |", "|---|---|---|---|---|",
        "| 천간 | " + " | ".join(f"{p[c]['stem']}({p[c]['hanja'][0]})" for c in cols) + " |",
        "| 지지 | " + " | ".join(f"{p[c]['branch']}({p[c]['hanja'][1]})" for c in cols) + " |",
        "| 십신 | " + " | ".join(sip[c] for c in cols) + " |",
    ]
    out = [f"## 📜 내 사주 ({d['eight_chars']})",
           f"일간 **{d['day_master']}({d['day_master_element']})** · 오행 {d['element_distribution']}",
           "", "\n".join(rows)]
    if result.get("daeun"):
        dn = result["daeun"]
        run = " · ".join(f"{x['age']}세 {x['name']}" for x in dn["pillars"][:6])
        out.append(f"\n**대운**({dn['gender']}): {run}")
    if result.get("current"):
        cu = result["current"]
        out.append(f"**올해({cu['now_year']})**: {cu['sewoon']['name']} — "
                   f"{cu['sewoon']['천간십신']}의 해")
    return "\n".join(out)


def _md_intro(result: dict) -> str:
    out = ["## 📊 전체 운세 한눈에"]
    for topic, blk in result.get("topics", {}).items():
        out.append(f"- {_TOPIC_EMOJI.get(topic, '•')} **{topic}** — {blk['hint']}")
    out.append("\n먼저 **어떤 방식으로 풀어드릴지** 골라주세요 👇 "
               "*(잘 모르겠으면 '🌿 표준' — 운세는 그다음에 고르면 돼요)*")
    return "\n".join(out)


def _fmt_birth(b: BirthInput) -> str:
    return f"{b.year}-{b.month:02d}-{b.day:02d} {b.hour:02d}:{b.minute:02d}"


def _extract_label(text: str) -> str | None:
    """후보 입력에서 날짜·시간·성별·음양 토큰을 뺀 나머지를 이름으로."""
    t = re.sub(r"\d{4}[-/.]\s*\d{1,2}[-/.]\s*\d{1,2}", " ", text)
    t = re.sub(r"\d{1,2}[:시]\s*\d{0,2}", " ", t)
    t = re.sub(r"(?<!\d)\d{8}(?!\d)", " ", t)
    t = re.sub(r"(음력|양력|윤|남자|여자|남성|여성|남|여)", " ", t)
    return t.strip() or None


def _md_rank(rows: list[dict]) -> str:
    lines = ["## 💘 궁합 순위", "",
             "| 순위 | 상대 | 점수 | 등급 | 일간 | 일지 | 띠 | 오행 |",
             "|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        lines.append(f"| {i} | {r['label']} | {r['총점']} | {r['등급']} | "
                     f"{r['일간관계']} | {r['일지관계']} | {r['띠관계']} | {r['오행보완']} |")
    lines.append("\n> 📎 일간·일지·띠·오행보완 가중평균(결정론). 근거: docs/SPEC.md")
    return "\n".join(lines)


def _md_best(res: dict, y0: int, y1: int) -> str:
    lines = [f"## 💘 {y0}~{y1}년 중 나와 Best 궁합",
             f"이 기간 **{res['scanned']:,}일**을 모두 따져봤어요(결정론 완전탐색). "
             f"최고 **{res['best_score']}점 · {res['best_grade']}**.", "",
             "| 순위 | 추정 생일 | 점수 | 등급 | 일간 | 일지 | 띠 |",
             "|---|---|---|---|---|---|---|"]
    for i, r in enumerate(res["top"], 1):
        lines.append(f"| {i} | {r['label']} | {r['총점']} | {r['등급']} | "
                     f"{r['일간관계']} | {r['일지관계']} | {r['띠관계']} |")
    tti = ", ".join(f"{k} {v}일" for k, v in res["tti_dist"])
    ilju = ", ".join(f"{k} {v}일" for k, v in res["ilju_dist"])
    lines += ["", f"**최고점과 잘 맞는 띠**: {tti}", f"**잘 맞는 일주(日柱)**: {ilju}",
              "", "> 📎 생시는 정오 기준이에요. 실제 인물의 생시를 알면 더 정밀해져요. "
              "'추정 생일'은 동점 중 가장 이른 날입니다."]
    return "\n".join(lines)


def _menu_actions() -> list[cl.Action]:
    acts = [cl.Action(name="category", payload={"kind": k}, label=label, tooltip=desc)
            for (k, label, desc) in CATALOG]
    acts.append(cl.Action(name="match", payload={}, label="💘 인연 찾기",
                          tooltip="후보들과 궁합 순위 / 연도 범위로 Best 사주 역산"))
    acts.append(cl.Action(name="show_presets", payload={},
                          label="🧭 해석 방식 바꾸기",
                          tooltip="표준·현대·전통 중 선택 (전문가용 7종도 가능)"))
    if _username():  # 플랫폼 기능 — 철학 진단과 묶은 통합 리포트(콜백은 app.py)
        acts.append(cl.Action(name="fusion_report", payload={},
                              label="🔗 사주×철학 통합 리포트",
                              tooltip="두 렌즈(사주·철학 진단)를 한 장의 보고서로"))
    return acts


def _save_report(kind: str, rep) -> None:
    """로그인 사용자의 리포트를 히스토리에 저장 — /me 개인 보고서에서 재확인."""
    user = _username()
    if user:
        reports_store.save_saju_report(user, kind=kind, title=rep.title,
                                       body=rep.text, preset_id=_preset())


# ── 해석 방식(프리셋) 선택 ───────────────────────────────────────────────
# 일반인에겐 '표준·현대·전통' 간편 3종(simple_preset_menu)을 기본으로 보여주고,
# 전문가용 7종 전부(preset_menu)는 '더보기'로 숨긴다. 둘 다 같은 preset 콜백을 쓴다.
def _preset() -> str:
    """세션의 선택 해석 방식(미지정 시 표준=정통 억부)."""
    return cl.user_session.get("preset") or DEFAULT_PRESET


def _preset_name(pid: str) -> str:
    """전문가용 정식 이름(display_name)."""
    return next((name for p, name, _ in preset_menu() if p == pid), pid)


def _simple_label(pid: str) -> str | None:
    """간편 3종에 해당하면 쉬운 라벨, 아니면 None."""
    return next((lbl for p, lbl, _ in simple_preset_menu() if p == pid), None)


def _preset_label(pid: str) -> str:
    """일반인용 표시 이름 — 간편 3종이면 쉬운 라벨, 그 외엔 정식 이름으로 폴백."""
    return _simple_label(pid) or _preset_name(pid)


def _simple_preset_actions() -> list[cl.Action]:
    """간편 해석 방식 버튼(표준·현대·전통) + 전문가용 더보기 — 현재 선택에 ✅."""
    cur = _preset()
    acts = [cl.Action(name="preset", payload={"pid": pid},
                      label=("✅ " if pid == cur else "") + label, tooltip=desc)
            for (pid, label, desc) in simple_preset_menu()]
    acts.append(cl.Action(name="show_presets_full", payload={},
                          label="🔧 전문가용 7종 전부 보기",
                          tooltip="억부·조후·전왕·병약·삼명통회·신파·맹파"))
    return acts


def _preset_actions() -> list[cl.Action]:
    """전문가용 유파 7종 버튼 — 현재 선택에 ✅ 표시 + 간단히 보기로 돌아가기."""
    cur = _preset()
    acts = [cl.Action(name="preset", payload={"pid": pid},
                      label=("✅ " if pid == cur else "") + name, tooltip=desc)
            for (pid, name, desc) in preset_menu()]
    acts.append(cl.Action(name="show_presets", payload={},
                          label="← 간단히 보기 (표준·현대·전통)"))
    return acts


def _menu_tail() -> str:
    """메뉴 메시지에 붙는 현재 해석 방식 안내 한 줄."""
    return (f"\n\n> 🧭 지금 해석 방식: **{_preset_label(_preset())}** — "
            "'방식'이라고 입력하거나 버튼으로 변경")


def _clean_md(text: str) -> str:
    """Chainlit 마크다운 렌더 오류 방지 — 플랫폼 공용 규약(mdutil)에 위임."""
    return mdutil.clean_md(text)


async def _send(content: str, actions: list | None = None):
    """마크다운 정리 후 전송."""
    kw = {"actions": actions} if actions else {}
    await cl.Message(content=_clean_md(content), **kw).send()


def _gender() -> str | None:
    g = cl.user_session.get("gender")
    if g in ("남", "여"):
        return g
    s = cl.user_session.get("settings") or {}
    g = s.get("gender")
    return g if g in ("남", "여") else None


def _username() -> str | None:
    """로그인된 사용자 id(익명이면 None) — 인증 비활성/세션 컨텍스트 밖이면 None."""
    try:
        u = cl.user_session.get("user")
    except Exception:  # noqa: BLE001 — Chainlit 컨텍스트 밖(테스트 등)
        return None
    return getattr(u, "identifier", None) if u else None


def _list_candidates() -> list[dict]:
    """후보 목록 — 로그인 시 영속(store), 익명 시 세션."""
    user = _username()
    if user:
        return store.list_candidates(user)
    return cl.user_session.get("cands") or []


def _add_candidate(birth: BirthInput, label: str | None, gender: str | None = None) -> None:
    user = _username()
    if user:
        store.add_candidate(user, birth, label=label, gender=gender)
        return
    cands = cl.user_session.get("cands") or []
    cands.append({"id": len(cands) + 1, "label": label, "birth": birth, "gender": gender})
    cl.user_session.set("cands", cands)


def _clear_candidates() -> None:
    user = _username()
    if user:
        store.clear_candidates(user)
    else:
        cl.user_session.set("cands", [])


def _chart_md_for(birth: BirthInput, preset_id: str):
    """선택 유파 1개 기준의 차트 result + 마크다운(음/양력·야자시 안내 포함).

    리포트(_verdict_line)와 **동일한 단일-프리셋 경로**로 원국을 계산한다 — 앞면
    차트와 리포트가 다른 config 를 쓰던 이원화(감사 ⑥)를 제거. 진태양시 등 보정은
    프리셋 YAML 설정을 그대로 따른다(하드코딩 override 폐기).
    """
    result = interpret(birth, [preset_id], gender=_gender())
    chart = _md_chart(result)
    info = cl.user_session.get("birth_info") or {}
    if info.get("calendar") == "음력" and info.get("lunar") and info.get("solar"):
        ly, lm, ld, leap = info["lunar"]
        sy, sm, sd = info["solar"]
        chart = (f"> 🌙 입력: 음력 {ly}-{lm:02d}-{ld:02d}{' 윤달' if leap else ''} "
                 f"→ 양력 {sy}-{sm:02d}-{sd:02d} 로 변환했어요.\n\n") + chart
    if birth.hour in (23, 0):  # 子시/야자시 경계 — 진태양시 보정 안내
        chart += ("\n\n> ⏰ 밤 11시~새벽 1시 출생은 **진태양시 보정**(약 −30분)으로 시주가 "
                  "달라질 수 있어요. 표준시 기준으로 계산했습니다.")
    return result, chart


async def _show_for_birth(birth: BirthInput):
    cl.user_session.set("birth", birth)
    user = _username()
    if user:  # 로그인 사용자는 본인 사주를 저장(다음 방문 시 자동 로드)
        store.save_profile(user, birth, gender=_gender())
    result, chart = _chart_md_for(birth, _preset())
    await _send(chart)
    # 사주 입력 직후 '해석 방식'을 먼저 받는다(간편 3종). 고른 뒤 카테고리 메뉴로 이어진다.
    await _send(_md_intro(result), actions=_simple_preset_actions())


def _meta_line(meta: dict, grounded: bool) -> str:
    return (f"{meta.get('models')} · {meta.get('duration_ms')}ms · "
            f"${meta.get('cost_usd')} · 그라운딩={grounded}")


async def _run_and_send(kind: str, birth: BirthInput, **kw):
    label = next((lbl for k, lbl, _ in CATALOG if k == kind), kind)
    # OpenRouter 백엔드면 토큰 스트리밍 — 섹션이 실시간으로 한 줄씩 나타난다(step별 표시).
    if narrator.supports_streaming():
        await _stream_and_send(kind, label, birth, **kw)
        return
    # 폴백(claude -p 등 비스트리밍): 한 번에 생성
    async with cl.Step(name=f"✍️ {label} 풀이 작성 중…", type="llm") as step:
        try:
            rep = await cl.make_async(run_report)(kind, birth, gender=_gender(),
                                                  preset_id=_preset(), **kw)
        except Exception as e:  # noqa: BLE001
            step.output = f"실패: {e}"
            await _send(f"⚠️ '{label}' 생성 실패: {e}")
            return
        step.output = _meta_line(rep.meta, rep.grounded)
    tail = "" if rep.grounded else f"\n\n> ⚠️ 검토필요: {', '.join(rep.violations)}"
    await _send(f"# {rep.title}\n\n{rep.text}{tail}")
    _save_report(kind, rep)
    await _send("🔎 다른 운세도 볼까요?" + _menu_tail(), actions=_menu_actions())


async def _stream_and_send(kind: str, label: str, birth: BirthInput, **kw):
    """리포트를 토큰 스트리밍해 섹션이 실시간으로 나타나게 한다(OpenRouter 백엔드).

    ① 결정론 사주 분석(프롬프트·근거 준비, LLM 미호출)
    ② 본문을 스트리밍(섹션 제목이 한 줄씩 차오름)
    ③ 끝나면 그라운딩 검사 + '근거' 푸터를 붙여 최종본으로 갱신
    """
    # ① 사주 분석(결정론) — 수십 ms, LLM 호출 없음
    async with cl.Step(name=f"🧮 {label}: 사주 분석 중…", type="tool") as pstep:
        try:
            prep = await cl.make_async(run_report)(kind, birth, gender=_gender(),
                                                   preset_id=_preset(), prepare_only=True, **kw)
        except Exception as e:  # noqa: BLE001
            pstep.output = f"실패: {e}"
            await _send(f"⚠️ '{label}' 생성 실패: {e}")
            return
        secs = [s.split(" ", 1)[-1] for s in (prep.get("sections") or [])]
        pstep.output = "분석 완료 → 작성할 항목: " + (" · ".join(secs) if secs else "해석")
    # ② 본문 스트리밍 (섹션이 실시간으로 채워진다)
    msg = cl.Message(content="")
    await msg.send()
    await msg.stream_token(f"# {prep['title']}\n\n_✍️ 풀이를 쓰는 중…_\n\n")
    meta: dict = {}

    async def _on_token(tok: str):
        # 취소선 방지(~→∼) + 천간·지지·오행 한자 누출 즉시 한글화(라이브 뷰도 깨끗)
        await msg.stream_token(_dehanja(tok.replace("~", "∼")))

    try:
        body = await narrator.stream_openrouter(
            prep["prompt"], on_token=_on_token, model=narrator.DEFAULT_MODEL, meta_out=meta)
    except Exception as e:  # noqa: BLE001
        await msg.remove()
        await _send(f"⚠️ '{label}' 생성 실패: {e}")
        return
    # ③ 스트림이 도중에 끊겼으면(조기 종료) 비스트리밍 전체 생성으로 교체(내부 재시도 포함)
    if is_truncated(body):
        await msg.stream_token("\n\n_(생성이 잠깐 끊겨 다시 정리하는 중…)_")
        try:
            rep = await cl.make_async(run_report)(kind, birth, gender=_gender(),
                                                  preset_id=_preset(), **kw)
            meta = rep.meta
        except Exception as e:  # noqa: BLE001
            await msg.remove()
            await _send(f"⚠️ '{label}' 생성 실패: {e}")
            return
    else:
        # 그라운딩 검사 + 근거 푸터(결정론값, LLM 비관여)
        rep = finalize_report(prep, body, meta)
    tail = "" if rep.grounded else f"\n\n> ⚠️ 검토필요: {', '.join(rep.violations)}"
    msg.content = _clean_md(f"# {rep.title}\n\n{rep.text}") + tail
    await msg.update()
    _save_report(kind, rep)
    async with cl.Step(name="ℹ️ 생성 정보 (모델·시간·비용)", type="llm") as mstep:
        mstep.output = _meta_line(meta, rep.grounded)
    await _send("🔎 다른 운세도 볼까요?" + _menu_tail(), actions=_menu_actions())


async def start():
    await cl.ChatSettings([
        Select(id="gender", label="성별 (대운·세운·평생운)", values=["미지정", "남", "여"], initial_index=0),
        Switch(id="true_solar", label="진태양시 보정", initial=True),
    ]).send()
    cl.user_session.set("settings", {"gender": "미지정", "true_solar": True})
    user = _username()
    if user:  # 로그인 + 저장된 프로필 → 자동 로드 후 차트 표시
        prof = store.get_profile(user)
        if prof:
            if prof["gender"]:
                cl.user_session.set("gender", prof["gender"])
            await _send(f"👋 다시 오셨어요, **{user}**님! 저장해둔 사주를 불러왔어요. "
                        "*(모든 리포트는 자동 저장 — [📖 내 기록 (/me)](/me) 에서 다시 볼 수 있어요)*")
            await _show_for_birth(prof["birth"])
            return
        await _send(f"👋 **{user}**님 환영해요! 생년월일시를 알려주시면 저장해둘게요.\n\n" + WELCOME)
        return
    await _send(WELCOME)


async def on_settings(settings):
    cl.user_session.set("settings", settings)


async def _ask_gender():
    await _send("성별을 선택해주세요 (대운·세운·평생운 산출에 필요해요) 👇",
                actions=[cl.Action(name="gender", payload={"g": "남"}, label="🙋‍♂️ 남성"),
                         cl.Action(name="gender", payload={"g": "여"}, label="🙋‍♀️ 여성")])


@cl.action_callback("gender")
async def on_gender(action: cl.Action):
    cl.user_session.set("gender", action.payload["g"])
    birth = cl.user_session.get("pending_birth")
    if birth:
        cl.user_session.set("pending_birth", None)
        await _show_for_birth(birth)
        return
    # 성별 필요 카테고리(예: 대운)를 기다리고 있었으면 이제 실행
    pend = cl.user_session.get("pending_category")
    me = cl.user_session.get("birth")
    if pend and me:
        cl.user_session.set("pending_category", None)
        await _run_and_send(pend, me)


@cl.action_callback("category")
async def on_category(action: cl.Action):
    kind = action.payload["kind"]
    birth = cl.user_session.get("birth")
    if not birth:
        await _send("먼저 생년월일시를 입력해주세요. 예: `1998-11-11 22:00`")
        return
    if kind == "gunghap":
        cl.user_session.set("pending", "gunghap")
        await _send("💞 **상대방**의 생년월일시를 입력해주세요. 예: `1996-05-20 09:30`")
        return
    if kind in _GENDER_REQUIRED and not _gender():
        cl.user_session.set("pending_category", kind)
        await _ask_gender()
        return
    await _run_and_send(kind, birth)


async def _show_simple_preset_picker():
    """일반인용 — 표준·현대·전통 3종 + 전문가용 더보기. 쉬운 말."""
    await _send(
        f"🧭 어떤 방식으로 풀어드릴까요? *(잘 모르겠으면 '🌿 표준')*\n"
        "방식에 따라 풀이의 강조점이 달라지고, 일부(현대식·전통식)는 **사주 원판(원국) "
        "계산법**까지 조금 달라져요(바꾸면 알려드릴게요). 언제든 다시 바꿀 수 있어요 👇",
        actions=_simple_preset_actions())


async def _show_full_preset_picker():
    """전문가용 — 유파 7종 전부 + 간단히 보기로 돌아가기."""
    await _send(
        f"🔧 **전문가용 — 해석 유파 7종**\n"
        f"현재: **{_preset_label(_preset())}**. 운세 풀이의 **강약·용신 기준**이 바뀌어요 👇\n"
        "*(궁합은 유파와 무관해요. 근거: docs/schools.md)*",
        actions=_preset_actions())


@cl.action_callback("show_presets")
async def on_show_presets(action: cl.Action):
    await _show_simple_preset_picker()


@cl.action_callback("show_presets_full")
async def on_show_presets_full(action: cl.Action):
    await _show_full_preset_picker()


@cl.action_callback("preset")
async def on_preset(action: cl.Action):
    pid = action.payload["pid"]
    prev = _preset()
    cl.user_session.set("preset", pid)
    msg = f"🧭 해석 방식을 **{_preset_label(pid)}** (으)로 정했어요."
    birth = cl.user_session.get("birth")
    if not birth:
        await _send(msg + " 생년월일시를 입력하면 이 방식으로 풀이를 시작할게요.")
        return
    # 결정론 토글이 바뀌는 유파면 '원국이 달라진다'를 숨기지 않고 경고+재렌더(감사 ③).
    vs_std = deterministic_diff(pid)                 # 표준 대비 차이
    chart_changed = bool(deterministic_diff(pid, base=prev))  # 직전 대비 실제 변화
    if vs_std:
        msg += ("\n\n⚠️ 이 방식은 **사주 원판(원국) 계산법**이 표준과 달라요 — "
                f"**{', '.join(vs_std)}**이(가) 달라서, 차트의 일부 값이 표준과 다르게 "
                "나올 수 있어요. *(강조점 차이가 아니라 계산 입력이 바뀌는 거예요.)*")
    await _send(msg)
    if chart_changed:
        _, chart = _chart_md_for(birth, pid)
        await _send("🔄 바뀐 계산법으로 다시 뽑은 원국이에요:")
        await _send(chart)
    await _send("이제 어떤 운세가 궁금하세요? 아래에서 골라주세요 👇 (또는 '토정비결', '궁합'처럼 입력)"
                + _menu_tail(), actions=_menu_actions())


# ── 인연 찾기(궁합 매칭) ──────────────────────────────────────────────────
@cl.action_callback("match")
async def on_match(action: cl.Action):
    if not cl.user_session.get("birth"):
        await _send("먼저 내 생년월일시를 입력해주세요. 예: `1998-11-11 22:00 남`")
        return
    n = len(_list_candidates())
    await _send(
        "💘 **인연 찾기** — 어떻게 찾을까요?\n"
        f"- 👥 **후보 비교**: 마음에 둔 사람들의 생일로 궁합 순위 (지금 {n}명 저장됨)\n"
        "- 📅 **연도로 Best**: 특정 기간 중 나와 가장 잘 맞는 사주를 역산",
        actions=[cl.Action(name="match_mode", payload={"m": "cand"}, label="👥 후보 비교"),
                 cl.Action(name="match_mode", payload={"m": "range"}, label="📅 연도로 Best 찾기")])


@cl.action_callback("match_mode")
async def on_match_mode(action: cl.Action):
    if action.payload["m"] == "range":
        cl.user_session.set("pending", "match_range")
        await _send("📅 찾을 **연도 범위**를 입력해주세요. 예: `1990 1995` 또는 `1990~1995`\n"
                    "*(그 기간의 모든 날짜를 따져 나와 가장 잘 맞는 사주를 찾아드려요. 최대 15년)*")
        return
    cands = _list_candidates()
    listing = "\n".join(f"- {c['label'] or _fmt_birth(c['birth'])}" for c in cands) or "_아직 없어요_"
    acts: list[cl.Action] = []
    if cands:
        acts.append(cl.Action(name="match_run", payload={}, label="📊 순위 보기"))
    acts.append(cl.Action(name="match_add", payload={}, label="➕ 후보 추가"))
    if cands:
        acts.append(cl.Action(name="match_clear", payload={}, label="🗑 후보 비우기"))
    await _send(f"👥 **후보 {len(cands)}명**\n{listing}\n\n후보를 추가하거나 순위를 볼 수 있어요 👇",
                actions=acts)


@cl.action_callback("match_add")
async def on_match_add(action: cl.Action):
    cl.user_session.set("pending", "add_candidate")
    await _send("➕ 후보의 생년월일시를 입력해주세요. 예: `1996-05-20 09:30` "
                "(이름을 붙여도 돼요: `철수 1996-05-20 09:30`)")


@cl.action_callback("match_run")
async def on_match_run(action: cl.Action):
    me = cl.user_session.get("birth")
    cands = _list_candidates()
    if not me or not cands:
        await _send("내 사주와 후보가 모두 필요해요. 후보를 먼저 추가해주세요.")
        return
    items = [(c["label"] or _fmt_birth(c["birth"]), c["birth"]) for c in cands]
    rows = rank_candidates(me, items)
    await _send(_md_rank(rows), actions=_menu_actions())


@cl.action_callback("match_clear")
async def on_match_clear(action: cl.Action):
    _clear_candidates()
    await _send("🗑 후보를 모두 비웠어요.", actions=_menu_actions())


async def on_message(message: cl.Message):
    text = message.content.strip()
    birth, info = _parse_input(text)

    # 궁합 상대 입력 대기 중 (상대도 음/양력 지원)
    if cl.user_session.get("pending") == "gunghap" and birth:
        cl.user_session.set("pending", None)
        me = cl.user_session.get("birth")
        await _run_and_send("gunghap", me, partner=birth)
        return

    # 인연 찾기 — 후보 추가 대기
    if cl.user_session.get("pending") == "add_candidate" and birth:
        cl.user_session.set("pending", None)
        _add_candidate(birth, _extract_label(text), _parse_gender(text))
        n = len(_list_candidates())
        await _send(f"➕ 후보를 추가했어요 (총 {n}명).",
                    actions=[cl.Action(name="match_add", payload={}, label="➕ 더 추가"),
                             cl.Action(name="match_run", payload={}, label="📊 순위 보기")])
        return

    # 인연 찾기 — 연도 범위 대기 (예: '1990 1995')
    if cl.user_session.get("pending") == "match_range":
        years = [int(y) for y in re.findall(r"(?:19|20)\d{2}", text)]
        if not years:
            await _send("연도를 인식하지 못했어요. 예: `1990 1995`")
            return
        cl.user_session.set("pending", None)
        y0, y1 = min(years), max(years)
        if y1 - y0 > 15:
            cl.user_session.set("pending", "match_range")
            await _send("범위가 너무 넓어요(최대 15년). 좁혀서 다시 입력해주세요. 예: `1990 2000`")
            return
        me = cl.user_session.get("birth")
        async with cl.Step(name=f"{y0}~{y1}년 사주 전수 탐색 중… 🔎", type="tool") as step:
            res = await cl.make_async(best_in_year_range)(me, y0, y1)
            step.output = f"{res['scanned']}일 스캔 · 최고 {res['best_score']}점({res['best_grade']})"
        await _send(_md_best(res, y0, y1), actions=_menu_actions())
        return

    # 새 생년월일시 → (성별 확인 후) 차트 + 메뉴
    if birth:
        cl.user_session.set("birth_info", info)
        g = _parse_gender(text)
        if g:
            cl.user_session.set("gender", g)
        if not _gender():
            cl.user_session.set("pending_birth", birth)
            await _ask_gender()
            return
        await _show_for_birth(birth)
        return

    # 해석 방식(유파) 선택 열기
    if re.search(r"유파|학파|해석\s*방식|풀이\s*방식|해석\s*기준", text):
        await _show_simple_preset_picker()
        return

    # 카테고리 키워드 타이핑
    for kw, kind in _KEYWORDS.items():
        if kw in text:
            me = cl.user_session.get("birth")
            if not me:
                await _send("먼저 생년월일시를 입력해주세요. 예: `1998-11-11 22:00`")
                return
            if kind == "gunghap":
                cl.user_session.set("pending", "gunghap")
                await _send("💞 상대방 생년월일시를 입력해주세요.")
                return
            if kind in _GENDER_REQUIRED and not _gender():
                cl.user_session.set("pending_category", kind)
                await _ask_gender()
                return
            await _run_and_send(kind, me)
            return

    if re.search(r"\d{4}", text):  # 날짜 시도로 보이나 인식 실패
        await _send("📅 날짜를 인식하지 못했어요. 예: `1998-11-11 22:00 남` "
                    "(또는 `19981111`). 연-월-일 순서와 숫자를 확인해 주세요.")
        return
    await _send("생년월일시를 입력하거나(예: `1998-11-11 22:00 남`), "
                "메뉴 버튼 또는 '토정비결'·'궁합'처럼 입력해주세요.")
