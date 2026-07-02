"""L4 자연어 종합 (narrator) — `claude -p`(실 LLM) 서술 + 그라운딩 가드 + 트레이싱.

입력은 L1~L3 의 구조화 결과(verdict + trace)뿐이다. trace 에 없는 사실은 언급
금지(SPEC §3.3). 강약·용신은 '확정값'으로 프롬프트에 박아 결론을 못 바꾸게 하고,
생성문이 확정 결론과 모순되는지 사후 검사한다.

`--output-format json` 으로 호출해 모델·토큰·비용·지연 메타데이터를 받고 MLflow
span 에 기록한다(→ 'LLM 실제 호출' 감사 + LLMOps 트레이싱). 검증 목표(SPEC §3.3):
그라운딩(환각 차단) + 결정성. 정확성 점수는 매기지 않는다.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import dataclass, field

from engine import constants as C
from engine.tracing import llm_span

_STRENGTHS = ("신강", "신약", "중화")

# .env 로드(있으면) — OPENROUTER_API_KEY 등. chainlit 도 자동 로드하나 스크립트/exec 대비.
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:  # noqa: BLE001
    pass

# LLM 백엔드: openrouter(HTTP API) | claude(claude -p subprocess).
#   OPENROUTER_API_KEY 있으면 기본 openrouter(키 한도 설정 가능 → 공개 배포에 안전·저렴),
#   없으면 claude. SAJU_LLM_BACKEND 로 강제 가능.
LLM_BACKEND = (os.environ.get("SAJU_LLM_BACKEND")
               or ("openrouter" if os.environ.get("OPENROUTER_API_KEY") else "claude"))
_DEFAULT_MODEL_BY_BACKEND = {"claude": "sonnet", "openrouter": "deepseek/deepseek-v4-flash"}
# 모델: SAJU_LLM_MODEL 우선, 없으면 백엔드별 기본. (claude 에서 ""=--model 미지정)
DEFAULT_MODEL = (os.environ.get("SAJU_LLM_MODEL")
                 if os.environ.get("SAJU_LLM_MODEL") is not None
                 else _DEFAULT_MODEL_BY_BACKEND.get(LLM_BACKEND, "sonnet"))


@dataclass(frozen=True)
class Narration:
    text: str
    grounded: bool
    violations: tuple[str, ...]
    prompt: str
    meta: dict = field(default_factory=dict)   # model/tokens/cost/latency (LLM 증거)


# ── 프롬프트 구성 (확정 결론 + trace 근거만 주입) ───────────────────────────
def _facts_block(block: dict) -> str:
    det = block["deterministic"]
    lines = [
        f"- 유파: {block['display_name']} ({block['lineage']})",
        f"- 일간(日元): {det['day_master']}({det['day_master_element']})",
        f"- 8글자: {det['eight_chars']}",
        f"- 오행분포: {det['element_distribution']}",
        f"- 천간 십신: {det['stem_sipsin']}",
        f"- 강약(확정): {block['strength']}",
    ]
    if block["engine"] == "yongsin" and block.get("yongsin"):
        y = block["yongsin"]
        lines.append(f"- 용신(확정): {y['element']}({y['family']}) · 정책 {block.get('policy')}")
    elif block["engine"] == "structure":
        s = block["structure"]
        lines.append(f"- (맹파) 주공: {s['jugong']['가족']} · 체용: {s['cheyong']} · 상: {s['sang']}")
    if det.get("relations"):
        lines.append("- 합충형파해: " + "; ".join(det["relations"]))
    lines.append("- 확정 근거:")
    for c in block["claims"]:
        lines.append(f"    · {c['claim']}")
    return "\n".join(lines)


def build_prompt(block: dict) -> str:
    strength = block["strength"]
    if block["engine"] == "yongsin" and block.get("yongsin"):
        verdict_line = f"강약은 '{strength}', 용신은 '{block['yongsin']['element']}'로 확정되어 있습니다."
        must = f"반드시 강약('{strength}')과 용신('{block['yongsin']['element']}')을 명시적으로 언급하세요."
    else:
        verdict_line = f"강약은 '{strength}'이며, 맹파 구조(주공/체용/상)로 봅니다."
        must = f"반드시 강약('{strength}')과 주공/상을 언급하세요. 용신 개념은 쓰지 마세요."
    return (
        "당신은 신중한 사주 명리 해석가입니다. 아래 '확정 분석 데이터'는 결정론 "
        "계산 엔진과 해당 유파 규칙으로 이미 산출된 값입니다.\n"
        "이 데이터에 적힌 사실만 근거로 한국어 해석을 작성하세요.\n\n"
        "[엄수 규칙]\n"
        f"- {verdict_line} 이 확정값을 절대 바꾸지 마세요.\n"
        "- 데이터에 없는 글자·신살·숫자·오행을 새로 지어내지 마세요.\n"
        f"- {must}\n"
        "- 4~6문장, 200~350자. 군더더기 없이.\n\n"
        f"[확정 분석 데이터]\n{_facts_block(block)}\n\n"
        "[해석]"
    )


# ── 그라운딩 검사 (확정 결론과 모순 탐지) ───────────────────────────────────
def check_grounding(text: str, block: dict) -> list[str]:
    v = []
    strength = block["strength"]
    if strength not in text:
        v.append(f"확정 강약 '{strength}' 미언급")
    for other in _STRENGTHS:
        if other != strength and other in text and strength not in text:
            v.append(f"확정과 다른 강약 '{other}' 주장")
    if block["engine"] == "yongsin" and block.get("yongsin"):
        yong = block["yongsin"]["element"]
        if yong not in text:
            v.append(f"확정 용신 '{yong}' 미언급")
        for el in C.OHAENG_HANGUL:
            if el != yong and f"용신은 {el}" in text:
                v.append(f"확정과 다른 용신 '{el}' 주장")
    elif block["engine"] == "structure":
        if "용신" in text:
            v.append("맹파인데 용신 개념 사용")
    return v


# ── claude -p (JSON) 호출 + 메타데이터 ──────────────────────────────────────
def _claude():
    claude = shutil.which("claude")
    if not claude:
        raise RuntimeError("claude CLI 를 찾을 수 없습니다 (PATH 확인)")
    return claude


def call_claude_json(prompt: str, *, model: str | None = None,
                     timeout: int = 180) -> tuple[dict, float]:
    """claude -p --output-format json 호출 → (응답 dict, 벽시계 초)."""
    cmd = [_claude(), "-p", prompt, "--output-format", "json"]
    if model:
        cmd += ["--model", model]
    t0 = time.perf_counter()
    proc = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8",
                          stdin=subprocess.DEVNULL, timeout=timeout)
    wall = time.perf_counter() - t0
    if proc.returncode != 0:
        raise RuntimeError(f"claude -p 실패 (rc={proc.returncode}): {proc.stderr[:300]}")
    data = json.loads(proc.stdout)
    if data.get("is_error"):
        raise RuntimeError(f"claude -p 오류: {str(data.get('result'))[:300]}")
    return data, wall


def llm_meta(data: dict, wall: float) -> dict:
    """LLM 호출 증거 메타데이터 (모델/토큰/비용/지연)."""
    usage = data.get("usage", {}) or {}
    return {
        "models": list((data.get("modelUsage") or {}).keys()),
        "input_tokens": usage.get("input_tokens"),
        "output_tokens": usage.get("output_tokens"),
        "cost_usd": data.get("total_cost_usd"),
        "duration_ms": data.get("duration_ms"),
        "ttft_ms": data.get("ttft_ms"),
        "wall_s": round(wall, 2),
        "session_id": data.get("session_id"),
        "num_turns": data.get("num_turns"),
    }


_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


def call_openrouter_json(prompt: str, *, model: str, timeout: int = 180) -> tuple[dict, float]:
    """OpenRouter chat completions 호출 → claude_json 과 동일 형태의 (data, wall)."""
    import httpx  # chainlit 의존성으로 항상 존재
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY 가 없습니다 (.env 확인)")
    t0 = time.perf_counter()
    resp = httpx.post(
        _OPENROUTER_URL,
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                 "X-Title": "saju-app"},
        json={"model": model, "messages": [{"role": "user", "content": prompt}],
              "max_tokens": 6000, "temperature": 0.6, "usage": {"include": True}},
        timeout=timeout,
    )
    wall = time.perf_counter() - t0
    if resp.status_code != 200:
        raise RuntimeError(f"OpenRouter 실패 (HTTP {resp.status_code}): {resp.text[:300]}")
    j = resp.json()
    if j.get("error"):
        raise RuntimeError(f"OpenRouter 오류: {str(j['error'])[:300]}")
    text = (j["choices"][0]["message"]["content"] or "").strip()
    usage = j.get("usage") or {}
    used = j.get("model", model)
    data = {
        "result": text, "is_error": False,
        "usage": {"input_tokens": usage.get("prompt_tokens"),
                  "output_tokens": usage.get("completion_tokens")},
        "total_cost_usd": usage.get("cost"),
        "duration_ms": int(wall * 1000), "ttft_ms": None,
        "session_id": j.get("id"), "num_turns": 1,
        "modelUsage": {used: {}},
    }
    return data, wall


def call_llm_json(prompt: str, *, model: str | None = None,
                  timeout: int = 180) -> tuple[dict, float]:
    """백엔드(openrouter/claude)에 따라 LLM 호출. 반환은 동일 (data, wall)."""
    mdl = model if model is not None else DEFAULT_MODEL
    if LLM_BACKEND == "openrouter":
        return call_openrouter_json(prompt, model=mdl, timeout=timeout)
    return call_claude_json(prompt, model=mdl, timeout=timeout)


def supports_streaming() -> bool:
    """현재 백엔드가 토큰 스트리밍을 지원하는가 (openrouter 만)."""
    return LLM_BACKEND == "openrouter"


async def stream_openrouter(prompt: str, *, on_token, model: str | None = None,
                            timeout: int = 240, meta_out: dict | None = None) -> str:
    """OpenRouter SSE 스트리밍 — 토큰마다 `await on_token(delta)` 호출, 전체 본문 반환.

    콜백 방식(제너레이터 아님): httpx `async with` 컨텍스트를 **소비 코루틴과 같은
    태스크 안에서** 열고 닫는다. (제너레이터로 yield 를 가로지르면 Chainlit 태스크
    모델에서 GC 정리가 다른 태스크에서 일어나 anyio cancel-scope 오류가 난다.)
    끝나면 meta_out 에 llm_meta 동형 메타를 채운다.
    """
    import httpx
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise RuntimeError("OPENROUTER_API_KEY 가 없습니다 (.env 확인)")
    mdl = model if model is not None else DEFAULT_MODEL
    body = {"model": mdl, "messages": [{"role": "user", "content": prompt}],
            "max_tokens": 6000, "temperature": 0.6, "stream": True,
            "stream_options": {"include_usage": True}}
    t0 = time.perf_counter()
    used_model, usage, parts = mdl, {}, []
    async with httpx.AsyncClient(timeout=timeout) as client:
        async with client.stream(
            "POST", _OPENROUTER_URL,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                     "X-Title": "saju-app"},
            json=body,
        ) as resp:
            if resp.status_code != 200:
                raw = (await resp.aread()).decode("utf-8", "replace")[:300]
                raise RuntimeError(f"OpenRouter 스트리밍 실패 (HTTP {resp.status_code}): {raw}")
            async for line in resp.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                chunk = line[5:].strip()
                if chunk == "[DONE]":
                    # break 하지 않고 자연 EOF 까지 소비 — 조기 break 는 httpx 내부 바이트
                    # 스트림을 미소진 상태로 남겨 GC 시 anyio cancel-scope 오류를 낸다.
                    continue
                try:
                    j = json.loads(chunk)
                except json.JSONDecodeError:
                    continue
                if j.get("model"):
                    used_model = j["model"]
                if j.get("usage"):
                    usage = j["usage"]
                ch = (j.get("choices") or [{}])[0]
                delta = (ch.get("delta") or {}).get("content")
                if delta:
                    parts.append(delta)
                    await on_token(delta)
    if meta_out is not None:
        wall = time.perf_counter() - t0
        meta_out.update({
            "models": [used_model],
            "input_tokens": usage.get("prompt_tokens"),
            "output_tokens": usage.get("completion_tokens"),
            "cost_usd": usage.get("cost"),
            "duration_ms": int(wall * 1000), "ttft_ms": None,
            "wall_s": round(wall, 1), "session_id": None, "num_turns": 1,
        })
    return "".join(parts)


def narrate(block: dict, *, model: str | None = DEFAULT_MODEL, timeout: int = 180,
            trace: bool = True) -> Narration:
    """LLM(백엔드 자동) 로 1회 서술 생성 + 그라운딩 검사 + 트레이싱."""
    prompt = build_prompt(block)
    with llm_span("narrate", {"preset": block.get("display_name"), "prompt": prompt},
                  enabled=trace) as span:
        data, wall = call_llm_json(prompt, model=model, timeout=timeout)
        text = (data.get("result") or "").strip()
        violations = check_grounding(text, block)
        meta = llm_meta(data, wall)
        span.set_outputs({"text": text})
        span.set_attributes({**meta, "grounded": not violations,
                             "violations": list(violations)})
    return Narration(text=text, grounded=not violations,
                     violations=tuple(violations), prompt=prompt, meta=meta)


# ── 서비스용: 주제별·일반인용 통합 리포트 (1회 LLM 호출) ─────────────────────
# 일반 사용자 피드백 반영: 한자 제거, '많다≠좋다' 설명, 올해 흐름, 유파 안내+메인기준,
# 실천 팁·직업 예시, 비유→행동 번역.
_REPORT_SECTIONS = ("🔮 한 줄 요약", "🧭 성향", "💰 재물운", "🏆 직업·명예",
                    "💕 애정·궁합", "🩺 건강", "⏳ 올해 흐름", "📅 인생의 큰 흐름(대운)",
                    "⚖️ 유파별로 보면", "✅ 실천 팁 3가지")


def _report_facts(result: dict) -> str:
    prim = result["by_preset"][result["primary_preset"]]
    d = result.get("deterministic") or prim["deterministic"]
    lines = [
        f"- 8글자: {d['eight_chars']} (일간 {d['day_master']}={d['day_master_element']})",
        f"- 오행분포(목화토금수): {d['element_distribution']}",
        f"- 강약(대표 유파 {prim['display_name']}): {prim['strength']}",
    ]
    if prim.get("yongsin"):
        y = prim["yongsin"]
        lines.append(f"- 용신(대표, 나에게 가장 이로운 기운): {y['element']}({y['family']})")
    lines.append("- 주제별 근거(엔진 산출):")
    for topic, blk in result.get("topics", {}).items():
        lines.append(f"    [{topic}] 요지={blk['hint']} / 사실={blk['facts']}")
    if result.get("current"):
        cu = result["current"]
        sw = cu["sewoon"]
        line = (f"- 올해({cu['now_year']}, 세는나이 {cu['age']}세): 세운(올해 간지) "
                f"{sw['name']} — 천간 십신 {sw['천간십신']}, 지지 십신 {sw['지지십신']}")
        if cu.get("current_daeun"):
            cd = cu["current_daeun"]
            line += f" / 현재 대운 {cd['age']}세 {cd['name']}(십신 {cd['천간십신']})"
        lines.append(line)
    if result.get("daeun"):
        dn = result["daeun"]
        run = ", ".join(f"{p['age']}세 {p['name']}" for p in dn["pillars"][:7])
        arrow = "순행" if dn["forward"] else "역행"
        lines.append(f"- 대운 타임라인({dn['gender']}, {arrow}, {dn['start_age']}세부터): {run}")
    else:
        lines.append("- 대운: (성별 미입력 — 시기 흐름 산출 불가)")
    lines.append(f"- 유파별 결론 (이 앱 메인 기준 = {prim['display_name']}):")
    for pid, b in result["by_preset"].items():
        tag = " ★메인" if pid == result["primary_preset"] else ""
        if b["engine"] == "yongsin" and b.get("yongsin"):
            lines.append(f"    {b['display_name']}{tag}: {b['strength']}, 용신 {b['yongsin']['element']}({b['yongsin']['family']})")
        elif b["engine"] == "structure":
            s = b["structure"]
            lines.append(f"    {b['display_name']}{tag}: (맹파) 주공 {s['jugong']['가족']}, 상 {s['sang']}")
    return "\n".join(lines)


def build_report_prompt(result: dict) -> str:
    secs = "\n".join(f"## {s}" for s in _REPORT_SECTIONS)
    prim = result["by_preset"][result["primary_preset"]]
    return (
        "당신은 사주를 처음 접하는 평범한 사용자에게 친절하고 쉽게 설명하는 상담가입니다.\n"
        "아래 '확정 분석 데이터'(결정론 엔진 + 유파 규칙으로 이미 산출됨)만 근거로 "
        "한국어 리포트를 작성하세요. 목표는 '사주를 1도 모르는 사람도 술술 읽히는 글'입니다.\n\n"
        "[쉬운 글쓰기 규칙 — 중요]\n"
        "- 한자(漢字)를 절대 본문에 쓰지 마세요. 용어는 쉬운 한글 뜻만 괄호로 풀어주세요. "
        "예: 재성(내가 다루는 돈·재물), 비겁(나와 같은 편·동료 기운), 인성(배움·도움·문서), "
        "식상(표현·재능·끼), 관성(직책·책임·규율), 용신(나에게 가장 이로운 기운).\n"
        "- 어떤 기운이 '많다'고 무조건 좋은 게 아닙니다. 용신이 아니면 많아도 부담/과제가 될 수 "
        "있음을 자연스럽게 짚어주세요(예: 관성이 많지만 용신이 아니라 책임이 버거울 수 있음).\n"
        "- 비유는 반드시 현실 행동으로 풀어주세요. 예: '재고가 있다' → '한번 모으기 시작하면 "
        "잘 새지 않고 쌓이는 편'.\n"
        "- 용어 풀이는 '처음 나올 때 한 번만' 괄호로 풀고, 이후에는 쉬운 말(예: '동료 "
        "기운')만 쓰세요. 같은 용어(특히 용신)를 매 섹션 반복해서 풀지 마세요.\n"
        "- 단정적 운명론·미신 금지. '~한 경향', '~에 유리' 처럼 부드럽게. 데이터에 없는 사실 "
        f"지어내기 금지. 강약('{prim['strength']}')·용신 등 확정값은 그대로 유지.\n\n"
        "[섹션별 지침]\n"
        "- '⏳ 올해 흐름': 올해 세운과 현재 대운의 십신 의미로 '올해 무엇에 신경 쓰고 무엇이 "
        "유리한지' 구체적으로 1~2가지. (세운 데이터 없으면 생략 안내)\n"
        "- '📅 인생의 큰 흐름(대운)': '대운은 10년마다 바뀌는 인생의 큰 날씨'라고 한 줄로 풀고 "
        "타임라인 제시. 단 '올해 흐름'과 내용이 겹치지 않게 — 지금이 10년 흐름의 어디쯤인지, "
        "그리고 '다음 대운부터 결이 어떻게 달라지는지'(분위기 변화)에 초점. 올해 처방을 반복하지 말 것.\n"
        "- '🏆 직업·명예': 어울리는 '직업 분야 예시'를 데이터(관성/인성/식상 경향) 근거로 1~2개.\n"
        "- '⚖️ 유파별로 보면': 첫 줄에 '사주는 보는 학파(관점)가 여럿이라 강조점이 조금씩 다를 뿐, "
        "어느 하나가 틀린 게 아니니 참고용으로 보세요'라고 안내. 그 다음 이 앱의 메인 기준이 "
        f"'{prim['display_name']}'임을 밝히고, 각 관점을 '관점 이름(쉬운 설명): 한 줄 결론'으로. "
        "여기서도 비겁·인성 등은 쉬운 뜻 병기.\n"
        "- '✅ 실천 팁 3가지': 당장 써먹을 구체 조언 3개(돈·일·관계·건강 중). 점술식 단정 말고 실용.\n\n"
        f"[섹션 형식 — 이 제목들을 그대로, 각 2~4문장(팁은 불릿 3개)]\n{secs}\n\n"
        f"[확정 분석 데이터]\n{_report_facts(result)}\n\n"
        "[리포트]"
    )


def check_report_grounding(text: str, result: dict) -> list[str]:
    v = []
    prim = result["by_preset"][result["primary_preset"]]
    if prim["strength"] not in text:
        v.append(f"강약 '{prim['strength']}' 미반영")
    if prim.get("yongsin") and prim["yongsin"]["element"] not in text:
        v.append(f"용신 '{prim['yongsin']['element']}' 미반영")
    for sec in ("성향", "재물", "직업", "애정", "건강", "올해", "팁"):
        if sec not in text:
            v.append(f"섹션 누락:{sec}")
    # 한자 노출 점검(쉬운 글 규칙) — 대표 한자 몇 개만 샘플 검사
    for han in ("財星", "官星", "印星", "食傷", "比劫", "用神", "身弱", "身強"):
        if han in text:
            v.append(f"한자 노출:{han}")
            break
    return v


def narrate_report(result: dict, *, model: str | None = DEFAULT_MODEL, timeout: int = 240,
                   trace: bool = True) -> Narration:
    """주제별·일반인용 통합 리포트를 claude -p 1회로 생성(+그라운딩+트레이싱)."""
    prompt = build_report_prompt(result)
    inp = {"primary": result["primary_preset"],
           "eight_chars": (result.get("deterministic") or {}).get("eight_chars"),
           "prompt": prompt}
    with llm_span("narrate_report", inp, enabled=trace) as span:
        data, wall = call_llm_json(prompt, model=model, timeout=timeout)
        text = (data.get("result") or "").strip()
        violations = check_report_grounding(text, result)
        meta = llm_meta(data, wall)
        span.set_outputs({"report": text})
        span.set_attributes({**meta, "grounded": not violations,
                             "violations": list(violations)})
    return Narration(text=text, grounded=not violations,
                     violations=tuple(violations), prompt=prompt, meta=meta)
