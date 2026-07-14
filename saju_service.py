"""사주 운세 서비스 — 플랫폼 '🔮 사주 · Saju' 프로필 핸들러.

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

언어(KO/EN): 세션 "lang" 을 라우터·설정·🌐 버튼이 정하고, 모든 표시는 engine.i18n
경계에서 갈린다(내부 값·로직은 한국어 정체성 키 그대로).
"""
from __future__ import annotations

import re
from datetime import datetime

import chainlit as cl
from chainlit.input_widget import Select, Switch

import mdutil
import reports_store
from engine import i18n, narrator, store
from engine.i18n import branch_en, ganji_en, is_en, stem_en, t, term
from engine.interpret import interpret
from engine.lunar import lunar_to_solar
from engine.matching import best_in_year_range, rank_candidates
from engine.pillars import BirthInput
from engine.reports import (DEFAULT_PRESET, _dehanja, catalog, deterministic_diff,
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
# 토픽 키(한국어 정체성) → 영어 표시 이름
_TOPIC_EN = {"성향": "Character", "재물": "Wealth", "직업·명예": "Career & Honor",
             "애정·궁합": "Love & Match", "건강": "Health", "대운": "Decade Cycles"}
# 타이핑으로도 카테고리 접근 — 한국어 키는 원문 그대로, 영어 키는 소문자 비교.
# ("lifetime" 을 "life" 보다 먼저 — dict 순회 순서 보존)
_KEYWORDS = {
    "신년": "saeun", "올해": "saeun", "종합": "saeun", "토정": "tojeong",
    "애정": "aejeong", "사랑": "aejeong", "반쪽": "aejeong", "연애": "aejeong",
    "궁합": "gunghap", "재물": "wealth", "돈": "wealth", "부자": "wealth",
    "평생": "pyeongsaeng", "대운": "daeun", "오늘": "today", "주간": "week",
    "이번주": "week", "건강": "health",
    "new year": "saeun", "year ahead": "saeun", "tojeong": "tojeong",
    "love": "aejeong", "soulmate": "aejeong", "compat": "gunghap", "match": "gunghap",
    "wealth": "wealth", "money": "wealth", "lifetime": "pyeongsaeng",
    "decade": "daeun", "today": "today", "week": "week", "health": "health",
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

WELCOME_EN = (
    "## 🔮 Saju Fortune\n"
    "Tell me your **birth date, time, and gender** — e.g. `1998-11-11 22:00 male`\n"
    "- Dates are read as **solar** unless you say otherwise. For lunar, add `lunar` — "
    "e.g. `lunar 1998-09-23 22:00 male` (add `leap` for a leap month)\n"
    "- Gender is needed for decade/year/lifetime luck (I'll ask if you leave it out).\n"
    "- 🧭 The **interpretation style** (Standard · Modern · Traditional) comes right "
    "after you enter your birth info — explained in plain words."
)


def _lang() -> str:
    return cl.user_session.get("lang") or "ko"


def _sync_lang() -> None:
    """액션 콜백 등 독립 진입점에서 세션 언어를 contextvar 로 동기화."""
    i18n.set_lang(_lang())


def _welcome() -> str:
    return WELCOME_EN if is_en() else WELCOME


def _lang_action() -> cl.Action:
    """웰컴에 붙는 🌐 전환 버튼 — 콜백(set_lang)은 라우터(app.py)가 등록."""
    if is_en():
        return cl.Action(name="set_lang", payload={"lang": "ko"}, label="🌐 한국어")
    return cl.Action(name="set_lang", payload={"lang": "en"}, label="🌐 English")


def _is_lunar(text: str) -> bool:
    """음/양 판별 — 기본 양력. '음력'/'음'(양 없을 때)/'lunar' 이면 음력."""
    if re.search(r"양력|陽|\bsolar\b", text, re.I):
        return False
    return bool(re.search(r"음력|陰|lunar", text, re.I)) or ("음" in text)


def _parse_input(text: str) -> tuple[BirthInput | None, dict]:
    """생년월일시 + 양/음력 파싱 → (BirthInput[양력], info).

    YYYY-MM-DD HH:MM / YYYYMMDD(HHMM) 지원. 음력이면 양력으로 변환(윤달 '윤'/'leap').
    명시 없으면 양력. 유효하지 않으면 (None, {}).
    """
    m = _DATE_RE.search(text) or _YMD8_RE.search(text)
    if not m:
        return None, {}
    y, mo, d = int(m[1]), int(m[2]), int(m[3])
    hh = int(m[4]) if m[4] else 12
    mm = int(m[5]) if m[5] else 0
    lunar = _is_lunar(text)
    leap = ("윤" in text) or bool(re.search(r"\bleap\b", text, re.I))
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
    if is_en():
        rows = [
            "| | Year | Month | Day | Hour |", "|---|---|---|---|---|",
            "| Stem | " + " | ".join(
                f"{stem_en(p[c]['stem'])}({p[c]['hanja'][0]})" for c in cols) + " |",
            "| Branch | " + " | ".join(
                f"{branch_en(p[c]['branch'])}({p[c]['hanja'][1]})" for c in cols) + " |",
            "| Ten Gods | " + " | ".join(term(sip[c]) for c in cols) + " |",
        ]
        out = [f"## 📜 My Chart ({_eight_disp(d['eight_chars'])})",
               f"Day Master **{stem_en(d['day_master'])} "
               f"({term(d['day_master_element'])})** · elements "
               f"{_dist_disp(d['element_distribution'])}",
               "", "\n".join(rows)]
        if result.get("daeun"):
            dn = result["daeun"]
            run = " · ".join(f"age {x['age']} {ganji_en(x['name'])}"
                             for x in dn["pillars"][:6])
            out.append(f"\n**Decade cycles** ({term(dn['gender'])}): {run}")
        if result.get("current"):
            cu = result["current"]
            out.append(f"**This year ({cu['now_year']})**: {ganji_en(cu['sewoon']['name'])} — "
                       f"a year of {term(cu['sewoon']['천간십신'])}")
        return "\n".join(out)
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


def _eight_disp(eight_chars: str) -> str:
    """8글자 표시 — en 이면 각 간지 로마자."""
    if not is_en():
        return eight_chars
    return " ".join(ganji_en(x) for x in eight_chars.split())


def _dist_disp(dist) -> str:
    """오행 분포 표시 — en 이면 'Wood 1 · …'."""
    if not is_en():
        return f"{dist}"
    if isinstance(dist, dict):
        return " · ".join(f"{term(k)} {v}" for k, v in dist.items())
    return f"{dist}"


def _md_intro(result: dict) -> str:
    out = [t("## 📊 전체 운세 한눈에", "## 📊 Fortune at a Glance")]
    for topic, blk in result.get("topics", {}).items():
        name = _TOPIC_EN.get(topic, topic) if is_en() else topic
        out.append(f"- {_TOPIC_EMOJI.get(topic, '•')} **{name}** — {blk['hint']}")
    out.append(t("\n먼저 **어떤 방식으로 풀어드릴지** 골라주세요 👇 "
                 "*(잘 모르겠으면 '🌿 표준' — 운세는 그다음에 고르면 돼요)*",
                 "\nFirst, pick **how you'd like it interpreted** 👇 "
                 "*(if unsure, '🌿 Standard' — you pick the fortune right after)*"))
    return "\n".join(out)


def _fmt_birth(b: BirthInput) -> str:
    return f"{b.year}-{b.month:02d}-{b.day:02d} {b.hour:02d}:{b.minute:02d}"


def _extract_label(text: str) -> str | None:
    """후보 입력에서 날짜·시간·성별·음양 토큰을 뺀 나머지를 이름으로."""
    tx = re.sub(r"\d{4}[-/.]\s*\d{1,2}[-/.]\s*\d{1,2}", " ", text)
    tx = re.sub(r"\d{1,2}[:시]\s*\d{0,2}", " ", tx)
    tx = re.sub(r"(?<!\d)\d{8}(?!\d)", " ", tx)
    tx = re.sub(r"(음력|양력|윤|남자|여자|남성|여성|남|여)", " ", tx)
    tx = re.sub(r"\b(lunar|solar|leap|male|female|m|f)\b", " ", tx, flags=re.I)
    return tx.strip() or None


def _md_rank(rows: list[dict]) -> str:
    lines = [t("## 💘 궁합 순위", "## 💘 Compatibility Ranking"), "",
             t("| 순위 | 상대 | 점수 | 등급 | 일간 | 일지 | 띠 | 오행 |",
               "| Rank | Partner | Score | Grade | Day Stem | Day Branch | Zodiac | Elements |"),
             "|---|---|---|---|---|---|---|---|"]
    for i, r in enumerate(rows, 1):
        lines.append(f"| {i} | {r['label']} | {r['총점']} | {r['등급']} | "
                     f"{r['일간관계']} | {r['일지관계']} | {r['띠관계']} | {r['오행보완']} |")
    lines.append(t("\n> 📎 일간·일지·띠·오행보완 가중평균(결정론). 근거: docs/SPEC.md",
                   "\n> 📎 Weighted average of day stem/branch, zodiac, and element "
                   "complement (deterministic). Basis: docs/SPEC.md"))
    return "\n".join(lines)


def _md_best(res: dict, y0: int, y1: int) -> str:
    lines = [t(f"## 💘 {y0}~{y1}년 중 나와 Best 궁합",
               f"## 💘 Best Match for Me, {y0}-{y1}"),
             t(f"이 기간 **{res['scanned']:,}일**을 모두 따져봤어요(결정론 완전탐색). "
               f"최고 **{res['best_score']}점 · {res['best_grade']}**.",
               f"I checked **all {res['scanned']:,} days** in this range (deterministic "
               f"exhaustive search). Best: **{res['best_score']} pts · "
               f"{res['best_grade']}**."), "",
             t("| 순위 | 추정 생일 | 점수 | 등급 | 일간 | 일지 | 띠 |",
               "| Rank | Estimated Birthday | Score | Grade | Day Stem | Day Branch | Zodiac |"),
             "|---|---|---|---|---|---|---|"]
    for i, r in enumerate(res["top"], 1):
        lines.append(f"| {i} | {r['label']} | {r['총점']} | {r['등급']} | "
                     f"{r['일간관계']} | {r['일지관계']} | {r['띠관계']} |")
    _day = t("일", " days")
    tti = ", ".join(f"{k} {v}{_day}" for k, v in res["tti_dist"])
    ilju = ", ".join(f"{k} {v}{_day}" for k, v in res["ilju_dist"])
    lines += ["", t(f"**최고점과 잘 맞는 띠**: {tti}", f"**Zodiac signs among the best**: {tti}"),
              t(f"**잘 맞는 일주(日柱)**: {ilju}", f"**Best-matching day pillars**: {ilju}"),
              "", t("> 📎 생시는 정오 기준이에요. 실제 인물의 생시를 알면 더 정밀해져요. "
                    "'추정 생일'은 동점 중 가장 이른 날입니다.",
                    "> 📎 Birth time is assumed noon. Knowing the real birth time makes it "
                    "more precise. 'Estimated birthday' is the earliest among ties.")]
    return "\n".join(lines)


def _viewing() -> str | None:
    """지금 남의 사주를 보는 중이면 그 라벨(이름 또는 생일) — 아니면 None."""
    try:
        return cl.user_session.get("viewing_label")
    except Exception:  # noqa: BLE001 — Chainlit 컨텍스트 밖(테스트 등)
        return None


def _menu_actions() -> list[cl.Action]:
    acts: list[cl.Action] = []
    if _viewing():
        acts.append(cl.Action(name="back_to_me", payload={},
                              label=t("↩️ 내 사주로 돌아가기", "↩️ Back to My Chart"),
                              tooltip=t("보던 사주를 닫고 내 사주 기준으로 돌아가요",
                                        "Close this chart and return to your own")))
    acts += [cl.Action(name="category", payload={"kind": k}, label=label, tooltip=desc)
             for (k, label, desc) in catalog()]
    acts.append(cl.Action(name="view_other", payload={},
                          label=t("👀 다른 사주 보기", "👀 View Another Chart"),
                          tooltip=t("가족·친구 등 다른 사람의 사주를 내 사주는 그대로 둔 채 봐요",
                                    "Look up someone else's chart — yours stays saved")))
    acts.append(cl.Action(name="match", payload={},
                          label=t("💘 인연 찾기", "💘 Find a Match"),
                          tooltip=t("후보들과 궁합 순위 / 연도 범위로 Best 사주 역산",
                                    "Rank candidates / reverse-search the best chart "
                                    "across birth years")))
    acts.append(cl.Action(name="show_presets", payload={},
                          label=t("🧭 해석 방식 바꾸기", "🧭 Change Interpretation Style"),
                          tooltip=t("표준·현대·전통 중 선택 (전문가용 7종도 가능)",
                                    "Standard · Modern · Traditional (7 expert schools "
                                    "available too)")))
    if _username():  # 플랫폼 기능 — 철학 진단과 묶은 통합 리포트(콜백은 app.py)
        acts.append(cl.Action(name="fusion_report", payload={},
                              label=t("🔗 사주×철학 통합 리포트",
                                      "🔗 Saju × Philosophy Combined Report"),
                              tooltip=t("두 렌즈(사주·철학 진단)를 한 장의 보고서로",
                                        "Both lenses (Saju + philosophy diagnosis) in "
                                        "one report")))
    return acts


def _save_report(kind: str, rep) -> None:
    """로그인 사용자의 리포트를 히스토리에 저장 — /me 개인 보고서에서 재확인.

    남의 사주를 보는 중이면 제목에 [라벨] 을 붙여 누구의 리포트인지 남긴다.
    """
    user = _username()
    if user:
        title = f"[{_viewing()}] {rep.title}" if _viewing() else rep.title
        reports_store.save_saju_report(user, kind=kind, title=title,
                                       body=rep.text, preset_id=_preset())


# ── 해석 방식(프리셋) 선택 ───────────────────────────────────────────────
# 일반인에겐 '표준·현대·전통' 간편 3종(simple_preset_menu)을 기본으로 보여주고,
# 전문가용 7종 전부(preset_menu)는 '더보기'로 숨긴다. 둘 다 같은 preset 콜백을 쓴다.
def _preset() -> str:
    """세션의 선택 해석 방식(미지정 시 표준=정통 억부)."""
    return cl.user_session.get("preset") or DEFAULT_PRESET


def _preset_name(pid: str) -> str:
    """전문가용 정식 이름(display_name) — preset_menu 가 언어 인지."""
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
                          label=t("🔧 전문가용 7종 전부 보기", "🔧 All 7 Expert Schools"),
                          tooltip=t("억부·조후·전왕·병약·삼명통회·신파·맹파",
                                    "Eokbu · Johu · Jeonwang · Byeongyak · Sanming · "
                                    "Sinpa · Mangpa")))
    return acts


def _preset_actions() -> list[cl.Action]:
    """전문가용 유파 7종 버튼 — 현재 선택에 ✅ 표시 + 간단히 보기로 돌아가기."""
    cur = _preset()
    acts = [cl.Action(name="preset", payload={"pid": pid},
                      label=("✅ " if pid == cur else "") + name, tooltip=desc)
            for (pid, name, desc) in preset_menu()]
    acts.append(cl.Action(name="show_presets", payload={},
                          label=t("← 간단히 보기 (표준·현대·전통)",
                                  "← Simple View (Standard · Modern · Traditional)")))
    return acts


def _menu_tail() -> str:
    """메뉴 메시지에 붙는 현재 해석 방식(+남의 사주 열람 중이면 그 안내) 한 줄."""
    tail = t(f"\n\n> 🧭 지금 해석 방식: **{_preset_label(_preset())}** — "
             "'방식'이라고 입력하거나 버튼으로 변경",
             f"\n\n> 🧭 Current interpretation style: **{_preset_label(_preset())}** — "
             "type 'style' or use the button to change")
    if _viewing():
        tail += t(f"\n> 👀 지금 보는 사주: **{_viewing()}** (내 사주 아님)",
                  f"\n> 👀 Now viewing: **{_viewing()}** (not your own)")
    return tail


def _clean_md(text: str) -> str:
    """Chainlit 마크다운 렌더 오류 방지 — 플랫폼 공용 규약(mdutil)에 위임."""
    return mdutil.clean_md(text)


async def _send(content: str, actions: list | None = None):
    """마크다운 정리 후 전송."""
    kw = {"actions": actions} if actions else {}
    await cl.Message(content=_clean_md(content), **kw).send()


_GENDER_NORM = {"Male": "남", "Female": "여", "남": "남", "여": "여"}


def _gender() -> str | None:
    g = cl.user_session.get("gender")
    if g in ("남", "여"):
        return g
    if _viewing():  # 남의 사주 — 내 설정(⚙️) 성별로 폴백하면 안 된다
        return None
    s = cl.user_session.get("settings") or {}
    g = _GENDER_NORM.get(s.get("gender") or "")
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
        chart = t(f"> 🌙 입력: 음력 {ly}-{lm:02d}-{ld:02d}{' 윤달' if leap else ''} "
                  f"→ 양력 {sy}-{sm:02d}-{sd:02d} 로 변환했어요.\n\n",
                  f"> 🌙 Input: lunar {ly}-{lm:02d}-{ld:02d}"
                  f"{' (leap month)' if leap else ''} → converted to solar "
                  f"{sy}-{sm:02d}-{sd:02d}.\n\n") + chart
    if birth.hour in (23, 0):  # 子시/야자시 경계 — 진태양시 보정 안내
        chart += t("\n\n> ⏰ 밤 11시~새벽 1시 출생은 **진태양시 보정**(약 −30분)으로 시주가 "
                   "달라질 수 있어요. 표준시 기준으로 계산했습니다.",
                   "\n\n> ⏰ Births between 11 pm and 1 am can get a different hour pillar "
                   "under **true solar time correction** (about −30 min). Standard time "
                   "was used here.")
    return result, chart


async def _show_for_birth(birth: BirthInput, *, mine: bool = True, label: str | None = None):
    """차트 + '전체 운세 한눈에' 표시.

    mine=True  — 내 사주: 세션·프로필에 저장(로그인 시), 복귀용 백업(my_birth 등) 갱신.
    mine=False — 남의 사주 보기: 내 프로필은 건드리지 않고 활성 사주만 바꾼다.
                 배너로 누구의 사주인지 명시, ↩️ 버튼으로 언제든 복귀.
    """
    cl.user_session.set("birth", birth)
    if mine:
        cl.user_session.set("viewing_label", None)
        cl.user_session.set("my_birth", birth)
        cl.user_session.set("my_gender", cl.user_session.get("gender"))
        user = _username()
        if user:  # 로그인 사용자는 본인 사주를 저장(다음 방문 시 자동 로드)
            store.save_profile(user, birth, gender=_gender())
    else:
        cl.user_session.set("viewing_label", label or _fmt_birth(birth))
    result, chart = _chart_md_for(birth, _preset())
    if not mine:
        chart = t(f"> 👀 지금 보는 사주: **{_viewing()}** — 내 사주가 아니에요. "
                  "아래 메뉴의 리포트도 이 사주 기준으로 나가요. "
                  "(↩️ 버튼으로 내 사주 복귀)\n\n",
                  f"> 👀 Now viewing: **{_viewing()}** — not your own chart. "
                  "Reports from the menu below follow this chart. "
                  "(↩️ button returns to yours)\n\n") + chart
    await _send(chart)
    # 사주 입력 직후 '해석 방식'을 먼저 받는다(간편 3종). 고른 뒤 카테고리 메뉴로 이어진다.
    await _send(_md_intro(result), actions=_simple_preset_actions())


def _meta_line(meta: dict, grounded: bool) -> str:
    return (f"{meta.get('models')} · {meta.get('duration_ms')}ms · "
            f"${meta.get('cost_usd')} · " + t(f"그라운딩={grounded}", f"grounded={grounded}"))


def _category_label(kind: str) -> str:
    return next((lbl for k, lbl, _ in catalog() if k == kind), kind)


async def _run_and_send(kind: str, birth: BirthInput, **kw):
    label = _category_label(kind)
    # OpenRouter 백엔드면 토큰 스트리밍 — 섹션이 실시간으로 한 줄씩 나타난다(step별 표시).
    if narrator.supports_streaming():
        await _stream_and_send(kind, label, birth, **kw)
        return
    # 폴백(claude -p 등 비스트리밍): 한 번에 생성
    async with cl.Step(name=t(f"✍️ {label} 풀이 작성 중…", f"✍️ Writing {label}…"),
                       type="llm") as step:
        try:
            rep = await cl.make_async(i18n.with_lang(run_report, _lang()))(
                kind, birth, gender=_gender(), preset_id=_preset(), **kw)
        except Exception as e:  # noqa: BLE001
            step.output = t(f"실패: {e}", f"failed: {e}")
            await _send(t(f"⚠️ '{label}' 생성 실패: {e}", f"⚠️ '{label}' failed: {e}"))
            return
        step.output = _meta_line(rep.meta, rep.grounded)
    tail = "" if rep.grounded else t(f"\n\n> ⚠️ 검토필요: {', '.join(rep.violations)}",
                                     f"\n\n> ⚠️ Needs review: {', '.join(rep.violations)}")
    await _send(f"# {rep.title}\n\n{rep.text}{tail}")
    _save_report(kind, rep)
    await _send(t("🔎 다른 운세도 볼까요?", "🔎 Want to see another fortune?") + _menu_tail(),
                actions=_menu_actions())


async def _stream_and_send(kind: str, label: str, birth: BirthInput, **kw):
    """리포트를 토큰 스트리밍해 섹션이 실시간으로 나타나게 한다(OpenRouter 백엔드).

    ① 결정론 사주 분석(프롬프트·근거 준비, LLM 미호출)
    ② 본문을 스트리밍(섹션 제목이 한 줄씩 차오름)
    ③ 끝나면 그라운딩 검사 + '근거' 푸터를 붙여 최종본으로 갱신
    """
    # ① 사주 분석(결정론) — 수십 ms, LLM 호출 없음
    async with cl.Step(name=t(f"🧮 {label}: 사주 분석 중…", f"🧮 {label}: analyzing chart…"),
                       type="tool") as pstep:
        try:
            prep = await cl.make_async(i18n.with_lang(run_report, _lang()))(
                kind, birth, gender=_gender(), preset_id=_preset(), prepare_only=True, **kw)
        except Exception as e:  # noqa: BLE001
            pstep.output = t(f"실패: {e}", f"failed: {e}")
            await _send(t(f"⚠️ '{label}' 생성 실패: {e}", f"⚠️ '{label}' failed: {e}"))
            return
        secs = [s.split(" ", 1)[-1] for s in (prep.get("sections") or [])]
        pstep.output = t("분석 완료 → 작성할 항목: ", "analysis done → sections: ") + \
            (" · ".join(secs) if secs else t("해석", "reading"))
    # ② 본문 스트리밍 (섹션이 실시간으로 채워진다)
    msg = cl.Message(content="")
    await msg.send()
    await msg.stream_token(f"# {prep['title']}\n\n" +
                           t("_✍️ 풀이를 쓰는 중…_\n\n", "_✍️ Writing the reading…_\n\n"))
    meta: dict = {}
    lang = _lang()

    async def _on_token(tok: str):
        # 취소선 방지(~→∼) + 한자 누출 즉시 교정(KO만 — EN 은 가드가 잡음)
        i18n.set_lang(lang)
        await msg.stream_token(_dehanja(tok.replace("~", "∼")))

    try:
        body = await narrator.stream_openrouter(
            prep["prompt"], on_token=_on_token, model=narrator.DEFAULT_MODEL, meta_out=meta)
    except Exception as e:  # noqa: BLE001
        await msg.remove()
        await _send(t(f"⚠️ '{label}' 생성 실패: {e}", f"⚠️ '{label}' failed: {e}"))
        return
    # ③ 스트림이 도중에 끊겼으면(조기 종료) 비스트리밍 전체 생성으로 교체(내부 재시도 포함)
    if is_truncated(body):
        await msg.stream_token(t("\n\n_(생성이 잠깐 끊겨 다시 정리하는 중…)_",
                                 "\n\n_(the stream broke off — regenerating…)_"))
        try:
            rep = await cl.make_async(i18n.with_lang(run_report, _lang()))(
                kind, birth, gender=_gender(), preset_id=_preset(), **kw)
            meta = rep.meta
        except Exception as e:  # noqa: BLE001
            await msg.remove()
            await _send(t(f"⚠️ '{label}' 생성 실패: {e}", f"⚠️ '{label}' failed: {e}"))
            return
    else:
        # 그라운딩 검사 + 근거 푸터(결정론값, LLM 비관여)
        rep = finalize_report(prep, body, meta)
    tail = "" if rep.grounded else t(f"\n\n> ⚠️ 검토필요: {', '.join(rep.violations)}",
                                     f"\n\n> ⚠️ Needs review: {', '.join(rep.violations)}")
    msg.content = _clean_md(f"# {rep.title}\n\n{rep.text}") + tail
    await msg.update()
    _save_report(kind, rep)
    async with cl.Step(name=t("ℹ️ 생성 정보 (모델·시간·비용)",
                              "ℹ️ Generation info (model · time · cost)"), type="llm") as mstep:
        mstep.output = _meta_line(meta, rep.grounded)
    await _send(t("🔎 다른 운세도 볼까요?", "🔎 Want to see another fortune?") + _menu_tail(),
                actions=_menu_actions())


async def _send_settings():
    """채팅 설정(⚙️) — 언어·성별·진태양시. 언어가 바뀌면 라벨도 새 언어로 다시 보낸다."""
    cur_gender = (cl.user_session.get("settings") or {}).get("gender")
    gender_values = ["Unspecified", "Male", "Female"] if is_en() else ["미지정", "남", "여"]
    gi = 0
    norm = _GENDER_NORM.get(cur_gender or "")
    if norm == "남":
        gi = 1
    elif norm == "여":
        gi = 2
    await cl.ChatSettings([
        Select(id="lang", label="🌐 Language / 언어", values=["한국어", "English"],
               initial_index=1 if is_en() else 0),
        Select(id="gender",
               label=t("성별 (대운·세운·평생운)", "Gender (decade/year/lifetime luck)"),
               values=gender_values, initial_index=gi),
        Switch(id="true_solar",
               label=t("진태양시 보정", "True solar time correction"), initial=True),
    ]).send()


async def start():
    await _send_settings()
    prev = cl.user_session.get("settings") or {}
    cl.user_session.set("settings", {
        "lang": "English" if is_en() else "한국어",
        "gender": prev.get("gender") or ("Unspecified" if is_en() else "미지정"),
        "true_solar": True})
    user = _username()
    if user:  # 로그인 + 저장된 프로필 → 자동 로드 후 차트 표시
        prof = store.get_profile(user)
        if prof:
            if prof["gender"]:
                cl.user_session.set("gender", prof["gender"])
            # 🌐 버튼을 여기에도 — 저장 프로필 경로가 이 버튼을 빼먹으면 셸(app.html)의
            # 언어 자동 적용(버튼 자동 클릭)이 통째로 건너뛰어진다.
            await _send(t(f"👋 다시 오셨어요, **{user}**님! 저장해둔 사주를 불러왔어요. "
                          "*(모든 리포트는 자동 저장 — [📖 내 기록 (/me)](/me) 에서 다시 볼 수 있어요)*",
                          f"👋 Welcome back, **{user}**! I loaded your saved chart. "
                          "*(Every report is saved — revisit them at "
                          "[📖 My records (/me)](/me?lang=en).)*"),
                        actions=[_lang_action()])
            await _show_for_birth(prof["birth"])
            return
        await _send(t(f"👋 **{user}**님 환영해요! 생년월일시를 알려주시면 저장해둘게요.\n\n",
                      f"👋 Welcome, **{user}**! Tell me your birth date & time and I'll "
                      "save it.\n\n") + _welcome(),
                    actions=[_lang_action()])
        return
    await _send(_welcome(), actions=[_lang_action()])


async def on_settings(settings):
    new_lang = "en" if settings.get("lang") == "English" else "ko"
    changed = new_lang != _lang()
    cl.user_session.set("settings", settings)
    if not changed:
        return
    cl.user_session.set("lang", new_lang)
    i18n.set_lang(new_lang)
    await _send_settings()  # 설정 위젯 라벨도 새 언어로
    await _send(t("🌐 이제 **한국어**로 안내할게요.",
                  "🌐 Switched to **English** — menus and reports will follow."))
    if cl.user_session.get("birth"):
        await _send(t("🔎 어떤 운세가 궁금하세요?", "🔎 Which fortune shall we look at?")
                    + _menu_tail(), actions=_menu_actions())
    else:
        await _send(_welcome(), actions=[_lang_action()])


async def _ask_gender():
    await _send(t("성별을 선택해주세요 (대운·세운·평생운 산출에 필요해요) 👇",
                  "Please pick a gender (needed for decade/year/lifetime luck) 👇"),
                actions=[cl.Action(name="gender", payload={"g": "남"},
                                   label=t("🙋‍♂️ 남성", "🙋‍♂️ Male")),
                         cl.Action(name="gender", payload={"g": "여"},
                                   label=t("🙋‍♀️ 여성", "🙋‍♀️ Female"))])


@cl.action_callback("gender")
async def on_gender(action: cl.Action):
    _sync_lang()
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
    _sync_lang()
    kind = action.payload["kind"]
    birth = cl.user_session.get("birth")
    if not birth:
        await _send(t("먼저 생년월일시를 입력해주세요. 예: `1998-11-11 22:00`",
                      "Please enter your birth date & time first. "
                      "e.g. `1998-11-11 22:00`"))
        return
    if kind == "gunghap":
        cl.user_session.set("pending", "gunghap")
        await _send(t("💞 **상대방**의 생년월일시를 입력해주세요. 예: `1996-05-20 09:30`",
                      "💞 Enter your **partner's** birth date & time. "
                      "e.g. `1996-05-20 09:30`"))
        return
    if kind in _GENDER_REQUIRED and not _gender():
        cl.user_session.set("pending_category", kind)
        await _ask_gender()
        return
    await _run_and_send(kind, birth)


async def _show_simple_preset_picker():
    """일반인용 — 표준·현대·전통 3종 + 전문가용 더보기. 쉬운 말."""
    await _send(
        t("🧭 어떤 방식으로 풀어드릴까요? *(잘 모르겠으면 '🌿 표준')*\n"
          "방식에 따라 풀이의 강조점이 달라지고, 일부(현대식·전통식)는 **사주 원판(원국) "
          "계산법**까지 조금 달라져요(바꾸면 알려드릴게요). 언제든 다시 바꿀 수 있어요 👇",
          "🧭 How shall I interpret it? *(if unsure, '🌿 Standard')*\n"
          "The style changes what the reading emphasizes, and some (Modern · Traditional) "
          "even change **how the base chart is computed** (I'll tell you when that "
          "happens). You can switch anytime 👇"),
        actions=_simple_preset_actions())


async def _show_full_preset_picker():
    """전문가용 — 유파 7종 전부 + 간단히 보기로 돌아가기."""
    await _send(
        t(f"🔧 **전문가용 — 해석 유파 7종**\n"
          f"현재: **{_preset_label(_preset())}**. 운세 풀이의 **강약·용신 기준**이 바뀌어요 👇\n"
          "*(궁합은 유파와 무관해요. 근거: docs/schools.md)*",
          f"🔧 **Expert — all 7 interpretation schools**\n"
          f"Current: **{_preset_label(_preset())}**. The **strength & useful-god "
          f"criteria** change with the school 👇\n"
          "*(Compatibility is school-independent. Basis: docs/schools.md)*"),
        actions=_preset_actions())


@cl.action_callback("show_presets")
async def on_show_presets(action: cl.Action):
    _sync_lang()
    await _show_simple_preset_picker()


@cl.action_callback("show_presets_full")
async def on_show_presets_full(action: cl.Action):
    _sync_lang()
    await _show_full_preset_picker()


@cl.action_callback("preset")
async def on_preset(action: cl.Action):
    _sync_lang()
    pid = action.payload["pid"]
    prev = _preset()
    cl.user_session.set("preset", pid)
    msg = t(f"🧭 해석 방식을 **{_preset_label(pid)}** (으)로 정했어요.",
            f"🧭 Interpretation style set to **{_preset_label(pid)}**.")
    birth = cl.user_session.get("birth")
    if not birth:
        await _send(msg + t(" 생년월일시를 입력하면 이 방식으로 풀이를 시작할게요.",
                            " Enter your birth date & time and I'll read it this way."))
        return
    # 결정론 토글이 바뀌는 유파면 '원국이 달라진다'를 숨기지 않고 경고+재렌더(감사 ③).
    vs_std = deterministic_diff(pid)                 # 표준 대비 차이
    chart_changed = bool(deterministic_diff(pid, base=prev))  # 직전 대비 실제 변화
    if vs_std:
        msg += t("\n\n⚠️ 이 방식은 **사주 원판(원국) 계산법**이 표준과 달라요 — "
                 f"**{', '.join(vs_std)}**이(가) 달라서, 차트의 일부 값이 표준과 다르게 "
                 "나올 수 있어요. *(강조점 차이가 아니라 계산 입력이 바뀌는 거예요.)*",
                 "\n\n⚠️ This style computes the **base chart** differently from "
                 f"Standard — **{', '.join(vs_std)}** differ, so some chart values may "
                 "come out differently. *(Not just emphasis — the calculation inputs "
                 "change.)*")
    await _send(msg)
    if chart_changed:
        _, chart = _chart_md_for(birth, pid)
        await _send(t("🔄 바뀐 계산법으로 다시 뽑은 원국이에요:",
                      "🔄 Here's the chart recomputed with the new method:"))
        await _send(chart)
    await _send(t("이제 어떤 운세가 궁금하세요? 아래에서 골라주세요 👇 (또는 '토정비결', '궁합'처럼 입력)",
                  "Now, which fortune interests you? Pick below 👇 (or type e.g. "
                  "'new year', 'match')")
                + _menu_tail(), actions=_menu_actions())


# ── 다른 사람 사주 보기 ──────────────────────────────────────────────────
async def _ask_other_birth():
    cl.user_session.set("pending", "view_other")
    await _send(t("👀 **다른 사람 사주 보기** — 그 사람의 생년월일시를 입력해주세요. "
                  "예: `엄마 1965-03-02 07:30 여` (이름·성별은 붙이면 좋고, 음력이면 `음력`)\n"
                  "*내 사주는 그대로 저장돼 있어요 — 언제든 ↩️ 버튼으로 돌아옵니다.*",
                  "👀 **View another chart** — enter that person's birth date & time. "
                  "e.g. `Mom 1965-03-02 07:30 female` (name & gender help; add `lunar` "
                  "for lunar dates)\n*Your own chart stays saved — the ↩️ button brings "
                  "it back anytime.*"))


@cl.action_callback("view_other")
async def on_view_other(action: cl.Action):
    _sync_lang()
    await _ask_other_birth()


@cl.action_callback("back_to_me")
async def on_back_to_me(action: cl.Action):
    _sync_lang()
    cl.user_session.set("viewing_label", None)
    my_birth = cl.user_session.get("my_birth")
    cl.user_session.set("gender", cl.user_session.get("my_gender"))
    if not my_birth:
        cl.user_session.set("birth", None)
        await _send(t("↩️ 돌아왔어요. 아직 내 사주가 없네요 — 생년월일시를 입력해주세요. "
                      "예: `1998-11-11 22:00 남`",
                      "↩️ Back. You haven't entered your own chart yet — please type "
                      "your birth date & time. e.g. `1998-11-11 22:00 male`"))
        return
    await _send(t("↩️ 내 사주로 돌아왔어요.", "↩️ Back to your own chart."))
    await _show_for_birth(my_birth)


# ── 인연 찾기(궁합 매칭) ──────────────────────────────────────────────────
@cl.action_callback("match")
async def on_match(action: cl.Action):
    _sync_lang()
    if not cl.user_session.get("birth"):
        await _send(t("먼저 내 생년월일시를 입력해주세요. 예: `1998-11-11 22:00 남`",
                      "Please enter your own birth date & time first. "
                      "e.g. `1998-11-11 22:00 male`"))
        return
    n = len(_list_candidates())
    await _send(
        t("💘 **인연 찾기** — 어떻게 찾을까요?\n"
          f"- 👥 **후보 비교**: 마음에 둔 사람들의 생일로 궁합 순위 (지금 {n}명 저장됨)\n"
          "- 📅 **연도로 Best**: 특정 기간 중 나와 가장 잘 맞는 사주를 역산",
          "💘 **Find a match** — how shall we search?\n"
          f"- 👥 **Compare candidates**: rank people you have in mind by birth date "
          f"({n} saved now)\n"
          "- 📅 **Best by year**: reverse-search the chart that fits you best in a "
          "year range"),
        actions=[cl.Action(name="match_mode", payload={"m": "cand"},
                           label=t("👥 후보 비교", "👥 Compare Candidates")),
                 cl.Action(name="match_mode", payload={"m": "range"},
                           label=t("📅 연도로 Best 찾기", "📅 Best by Year Range"))])


@cl.action_callback("match_mode")
async def on_match_mode(action: cl.Action):
    _sync_lang()
    if action.payload["m"] == "range":
        cl.user_session.set("pending", "match_range")
        await _send(t("📅 찾을 **연도 범위**를 입력해주세요. 예: `1990 1995` 또는 `1990~1995`\n"
                      "*(그 기간의 모든 날짜를 따져 나와 가장 잘 맞는 사주를 찾아드려요. 최대 15년)*",
                      "📅 Enter the **year range** to search. e.g. `1990 1995` or "
                      "`1990~1995`\n*(I'll check every date in that range for the chart "
                      "that fits you best. Up to 15 years.)*"))
        return
    cands = _list_candidates()
    listing = "\n".join(f"- {c['label'] or _fmt_birth(c['birth'])}" for c in cands) or \
        t("_아직 없어요_", "_none yet_")
    acts: list[cl.Action] = []
    if cands:
        acts.append(cl.Action(name="match_run", payload={},
                              label=t("📊 순위 보기", "📊 Show Ranking")))
    acts.append(cl.Action(name="match_add", payload={},
                          label=t("➕ 후보 추가", "➕ Add Candidate")))
    if cands:
        acts.append(cl.Action(name="match_clear", payload={},
                              label=t("🗑 후보 비우기", "🗑 Clear Candidates")))
    await _send(t(f"👥 **후보 {len(cands)}명**\n{listing}\n\n후보를 추가하거나 순위를 볼 수 있어요 👇",
                  f"👥 **{len(cands)} candidate(s)**\n{listing}\n\nAdd candidates or see "
                  "the ranking 👇"),
                actions=acts)


@cl.action_callback("match_add")
async def on_match_add(action: cl.Action):
    _sync_lang()
    cl.user_session.set("pending", "add_candidate")
    await _send(t("➕ 후보의 생년월일시를 입력해주세요. 예: `1996-05-20 09:30` "
                  "(이름을 붙여도 돼요: `철수 1996-05-20 09:30`)",
                  "➕ Enter the candidate's birth date & time. e.g. `1996-05-20 09:30` "
                  "(you can add a name: `Alex 1996-05-20 09:30`)"))


@cl.action_callback("match_run")
async def on_match_run(action: cl.Action):
    _sync_lang()
    me = cl.user_session.get("birth")
    cands = _list_candidates()
    if not me or not cands:
        await _send(t("내 사주와 후보가 모두 필요해요. 후보를 먼저 추가해주세요.",
                      "I need both your chart and at least one candidate. Please add "
                      "a candidate first."))
        return
    items = [(c["label"] or _fmt_birth(c["birth"]), c["birth"]) for c in cands]
    rows = rank_candidates(me, items)
    await _send(_md_rank(rows), actions=_menu_actions())


@cl.action_callback("match_clear")
async def on_match_clear(action: cl.Action):
    _sync_lang()
    _clear_candidates()
    await _send(t("🗑 후보를 모두 비웠어요.", "🗑 Cleared all candidates."),
                actions=_menu_actions())


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
        await _send(t(f"➕ 후보를 추가했어요 (총 {n}명).",
                      f"➕ Candidate added ({n} total)."),
                    actions=[cl.Action(name="match_add", payload={},
                                       label=t("➕ 더 추가", "➕ Add More")),
                             cl.Action(name="match_run", payload={},
                                       label=t("📊 순위 보기", "📊 Show Ranking"))])
        return

    # 다른 사람 사주 보기 — 생일 입력 대기 (내 프로필은 건드리지 않는다)
    if cl.user_session.get("pending") == "view_other" and birth:
        cl.user_session.set("pending", None)
        cl.user_session.set("birth_info", info)
        cl.user_session.set("gender", _parse_gender(text))  # 그 사람 성별(없으면 None)
        await _show_for_birth(birth, mine=False, label=_extract_label(text))
        return

    # 인연 찾기 — 연도 범위 대기 (예: '1990 1995')
    if cl.user_session.get("pending") == "match_range":
        years = [int(y) for y in re.findall(r"(?:19|20)\d{2}", text)]
        if not years:
            await _send(t("연도를 인식하지 못했어요. 예: `1990 1995`",
                          "I couldn't read the years. e.g. `1990 1995`"))
            return
        cl.user_session.set("pending", None)
        y0, y1 = min(years), max(years)
        if y1 - y0 > 15:
            cl.user_session.set("pending", "match_range")
            await _send(t("범위가 너무 넓어요(최대 15년). 좁혀서 다시 입력해주세요. 예: `1990 2000`",
                          "That range is too wide (max 15 years). Please narrow it. "
                          "e.g. `1990 2000`"))
            return
        me = cl.user_session.get("birth")
        async with cl.Step(name=t(f"{y0}~{y1}년 사주 전수 탐색 중… 🔎",
                                  f"Searching every chart {y0}-{y1}… 🔎"),
                           type="tool") as step:
            res = await cl.make_async(i18n.with_lang(best_in_year_range, _lang()))(me, y0, y1)
            step.output = t(f"{res['scanned']}일 스캔 · 최고 {res['best_score']}점({res['best_grade']})",
                            f"{res['scanned']} days scanned · best {res['best_score']} pts "
                            f"({res['best_grade']})")
        await _send(_md_best(res, y0, y1), actions=_menu_actions())
        return

    # 새 생년월일시 → (성별 확인 후) 차트 + 메뉴
    if birth:
        cl.user_session.set("birth_info", info)
        # 남의 사주를 보던 중에 또 생일이 오면 — 내 프로필을 덮지 않고 그 사람 것으로 본다
        if _viewing():
            cl.user_session.set("gender", _parse_gender(text))
            await _show_for_birth(birth, mine=False, label=_extract_label(text))
            return
        g = _parse_gender(text)
        if g:
            cl.user_session.set("gender", g)
        if not _gender():
            cl.user_session.set("pending_birth", birth)
            await _ask_gender()
            return
        await _show_for_birth(birth)
        return

    # 다른 사람 사주 보기 — 타이핑 트리거
    if re.search(r"다른\s*사(주|람)|남의\s*사주|지인\s*사주|someone\s*else|another\s*(person|chart)",
                 text, re.I):
        await _ask_other_birth()
        return

    # 해석 방식(유파) 선택 열기
    if re.search(r"유파|학파|해석\s*방식|풀이\s*방식|해석\s*기준|school|method|style", text, re.I):
        await _show_simple_preset_picker()
        return

    # 카테고리 키워드 타이핑 (한국어 키는 원문, 영어 키는 소문자 비교)
    tl = text.lower()
    for kw, kind in _KEYWORDS.items():
        if kw in (tl if kw.isascii() else text):
            me = cl.user_session.get("birth")
            if not me:
                await _send(t("먼저 생년월일시를 입력해주세요. 예: `1998-11-11 22:00`",
                              "Please enter your birth date & time first. "
                              "e.g. `1998-11-11 22:00`"))
                return
            if kind == "gunghap":
                cl.user_session.set("pending", "gunghap")
                await _send(t("💞 상대방 생년월일시를 입력해주세요.",
                              "💞 Enter your partner's birth date & time."))
                return
            if kind in _GENDER_REQUIRED and not _gender():
                cl.user_session.set("pending_category", kind)
                await _ask_gender()
                return
            await _run_and_send(kind, me)
            return

    if re.search(r"\d{4}", text):  # 날짜 시도로 보이나 인식 실패
        await _send(t("📅 날짜를 인식하지 못했어요. 예: `1998-11-11 22:00 남` "
                      "(또는 `19981111`). 연-월-일 순서와 숫자를 확인해 주세요.",
                      "📅 I couldn't read that date. e.g. `1998-11-11 22:00 male` "
                      "(or `19981111`). Please check the year-month-day order."))
        return
    await _send(t("생년월일시를 입력하거나(예: `1998-11-11 22:00 남`), "
                  "메뉴 버튼 또는 '토정비결'·'궁합'처럼 입력해주세요.",
                  "Enter a birth date & time (e.g. `1998-11-11 22:00 male`), "
                  "use the menu buttons, or type things like 'new year' or 'match'."))
