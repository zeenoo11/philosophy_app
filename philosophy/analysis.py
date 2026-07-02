"""7축 철학 성향 분석 — 플랫폼 공용 LLM 백엔드(engine.narrator) 사용.

legacy/src/llm.py (LangChain + OpenAI 구조화 출력) 를 사주와 동일한
OpenRouter/claude 백엔드로 포팅했다. SDK 의 structured output 대신
'JSON 만 출력' 지시 + 관대한 파싱(_json_from)으로 처리한다 — 파싱 실패 시
None 을 반환하고 호출부가 폴백 문구로 진행한다(크래시 금지).

점수 스케일은 전 구간 0~10 으로 통일한다. legacy 는 턴 점수(0.1~0.9)와
전체 점수(0~10)가 섞여 누적 평균이 왜곡되는 문제가 있었다.
"""
from __future__ import annotations

import json
import random
import re
from pathlib import Path

from engine import narrator

from philosophy.matching import AXES, AXIS_LABELS  # noqa: F401 — 재노출(서비스 편의)

DATA_DIR = Path(__file__).parent / "data"
QUESTION_LIST_PATH = DATA_DIR / "question_list.json"
SYSTEM_PROMPT_PATH = DATA_DIR / "system_prompt.md"


# ── 질문 리스트 ───────────────────────────────────────────────────────────
def load_questions() -> list[dict]:
    """question_list.json → [{'id','topic','question','context','axis'}]."""
    try:
        with open(QUESTION_LIST_PATH, encoding="utf-8") as f:
            return json.load(f).get("questions", [])
    except (OSError, json.JSONDecodeError):
        return []


def get_random_question(exclude_ids: set[int] | None = None) -> dict | None:
    """아직 묻지 않은 질문 중 랜덤 1개(모두 소진이면 None)."""
    pool = [q for q in load_questions() if not exclude_ids or q["id"] not in exclude_ids]
    return random.choice(pool) if pool else None


def question_by_id(qid: int) -> dict | None:
    return next((q for q in load_questions() if q["id"] == qid), None)


# ── LLM 헬퍼 ─────────────────────────────────────────────────────────────
def _json_from(text: str) -> dict | None:
    """LLM 응답에서 JSON 오브젝트를 관대하게 추출(코드펜스·앞뒤 산문 허용)."""
    if not text:
        return None
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    candidate = m.group(1) if m else None
    if candidate is None:
        i, j = text.find("{"), text.rfind("}")
        if i == -1 or j <= i:
            return None
        candidate = text[i:j + 1]
    try:
        obj = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    return obj if isinstance(obj, dict) else None


def _ask_json(prompt: str, *, timeout: int = 120) -> tuple[dict | None, dict]:
    """LLM 1회 호출 → (파싱된 JSON | None, 메타). 백엔드는 narrator 가 자동 선택."""
    data, wall = narrator.call_llm_json(prompt, timeout=timeout)
    meta = narrator.llm_meta(data, wall)
    return _json_from(data.get("result") or ""), meta


def _history_block(messages: list[dict], *, limit: int = 20) -> str:
    """대화 이력을 프롬프트용 텍스트로(최근 limit 턴)."""
    lines = []
    for m in messages[-limit:]:
        who = "사용자" if m["role"] == "user" else "진행자"
        lines.append(f"{who}: {m['content']}")
    return "\n".join(lines)


# ── ① 대화 유도(다음 질문 선택) ──────────────────────────────────────────
def chat_turn(messages: list[dict], *, asked_ids: set[int] | None = None
              ) -> tuple[str, dict | None, dict]:
    """공감 응답 + 다음 질문 선택 → (reply, next_question|None, meta).

    reply 에는 질문 본문을 넣지 않는다 — 호출부가 next_question 을 보고
    붙인다(legacy 와 동일한 계약, 질문 중복 노출 방지).
    """
    remaining = [q for q in load_questions()
                 if not asked_ids or q["id"] not in asked_ids]
    if not remaining:  # 모든 질문 소진 — LLM 없이 종료 안내
        return ("이제 충분히 이야기를 나눈 것 같아요. 분석을 시작해볼까요?", None, {})
    qjson = json.dumps(remaining, ensure_ascii=False)
    prompt = f"""당신은 사용자의 철학적 가치관을 탐색하는 따뜻한 대화 파트너입니다.

[대화 이력]
{_history_block(messages)}

[남은 질문 리스트]
{qjson}

[지시]
1. 사용자의 마지막 답변에 짧게 공감하고(1~2문장), 자연스럽게 화제를 전환하는 멘트를 쓰세요.
2. 이전 대화 맥락과 가장 자연스럽게 이어질 다음 질문을 리스트에서 하나 고르세요.
3. reply 에는 질문 본문을 통째로 쓰지 마세요 — 앱이 next_question_id 를 보고 붙입니다.

아래 JSON 형식으로만 답하세요(다른 텍스트 금지):
{{"reply": "공감+전환 멘트", "next_question_id": 질문ID정수 또는 null}}"""
    parsed, meta = _ask_json(prompt)
    if not parsed or not isinstance(parsed.get("reply"), str):
        return ("그렇군요, 조금 더 들려주시겠어요?", None, meta)
    nq = None
    if parsed.get("next_question_id") is not None:
        try:
            nq = question_by_id(int(parsed["next_question_id"]))
        except (TypeError, ValueError):
            nq = None
    if nq is None and remaining:  # LLM 이 못 고르면 랜덤 폴백 — 대화가 멈추지 않게
        nq = random.choice(remaining)
    return (parsed["reply"].strip(), nq, meta)


# ── ② 턴 점수화(현재 축 0~10) ────────────────────────────────────────────
def analyze_turn(user_text: str, axis: str) -> tuple[float | None, dict]:
    """답변 1건을 해당 축 0~10 점수로 → (score|None, meta)."""
    if axis not in AXIS_LABELS:
        return None, {}
    left, right, label = AXIS_LABELS[axis]
    prompt = f"""당신은 철학적 성향 분석가입니다. 사용자의 답변이 아래 축에서
어느 쪽으로 기우는지 0~10 정수로 평가하세요.

[축] {label}
- 0 = {left} 쪽으로 극단
- 5 = 중립/모호/판단 불가
- 10 = {right} 쪽으로 극단

[사용자 답변]
{user_text}

아래 JSON 형식으로만 답하세요:
{{"score": 0~10 정수, "reason": "한 문장 근거"}}"""
    parsed, meta = _ask_json(prompt, timeout=60)
    if not parsed:
        return None, meta
    try:
        score = float(parsed["score"])
    except (KeyError, TypeError, ValueError):
        return None, meta
    return (min(10.0, max(0.0, score)), meta)


# ── ③ 전체 분석(리포트) ──────────────────────────────────────────────────
def _system_prompt() -> str:
    try:
        return SYSTEM_PROMPT_PATH.read_text(encoding="utf-8")
    except OSError:
        return "사용자의 대화를 분석하여 7가지 축의 점수(0~10)를 산출하세요."


def analyze_full(messages: list[dict]) -> tuple[dict | None, dict]:
    """전체 대화 → ({'scores': {axis: float}, 'reasoning': str} | None, meta).

    reasoning(서술)은 LLM 이 쓰고, 최종 표시 점수는 서비스가 누적 턴 점수
    평균으로 덮어쓸 수 있다(신뢰도: 턴별 축 지정 평가 > 일괄 평가).
    """
    user_only = [m for m in messages if m["role"] == "user"]
    if not user_only:
        return None, {}
    axes_csv = ", ".join(AXES)
    prompt = f"""{_system_prompt()}

[사용자 대화 내역]
{_history_block(messages, limit=40)}

[지시]
위 축 정의에 따라 7개 축을 각각 0~10 으로 평가하고, 점수 산정 근거를
내담자에게 말하듯 부드러운 어조로 3문장 이내로 요약하세요.

아래 JSON 형식으로만 답하세요(축 키: {axes_csv}):
{{"reasoning": "요약", "scores": {{"agency": 0~10, "logic": 0~10, "focus": 0~10,
"outlook": 0~10, "time": 0~10, "meta": 0~10, "social": 0~10}}}}"""
    parsed, meta = _ask_json(prompt, timeout=180)
    if not parsed or not isinstance(parsed.get("scores"), dict):
        return None, meta
    scores: dict[str, float] = {}
    for a in AXES:
        try:
            scores[a] = min(10.0, max(0.0, float(parsed["scores"][a])))
        except (KeyError, TypeError, ValueError):
            scores[a] = 5.0  # 누락 축은 중립
    return ({"scores": scores, "reasoning": str(parsed.get("reasoning", "")).strip()}, meta)
