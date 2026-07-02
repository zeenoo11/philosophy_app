"""가치관 입력 → 핵심 명제 분해 + 영어 정규화 (Graph-Project C_RAG 이식).

긴 복합 생각은 단일 임베딩으로 뭉개진다("풍요롭게 한다"+"결핍을 준다"가 평균됨).
핵심 명제 2~4개로 쪼개 각각 retrieve 후 종합한다.

- 정석: LLM 분해(플랫폼 공용 engine.narrator — OpenRouter/claude 자동) —
  명제 분리 + **영어 정규화**(그래프·임베딩이 영어 SEP 기반이라 영어화가 핵심).
- 폴백: 규칙 기반(접속사·문장부호 분리). 번역은 못 하므로 이 경로는 영어 입력 가정.
"""
from __future__ import annotations

import json
import logging
import re

logger = logging.getLogger(__name__)

# 한국어/영어 역접·순접 접속사 — 명제 경계
_CONNECTIVES = (
    r"하지만|그러나|그런데|반면(?:에)?|동시에|그리고|또한|또|but|however|"
    r"whereas|while|yet|and also"
)
_SPLIT_RE = re.compile(rf"\s*(?:[.;\n]|,?\s*(?:{_CONNECTIVES})\b)\s*", re.IGNORECASE)

# "나는 ~라고 생각해" 같은 의견 프레임(분해 신호에 무의미) 제거
_FRAME_PREFIX = re.compile(
    r"^\s*(?:나는|내\s*생각(?:에는|엔|은)?|개인적으로|i\s+(?:think|believe|feel)\s+that?)\s*",
    re.IGNORECASE,
)
_FRAME_SUFFIX = re.compile(
    r"\s*(?:라고\s*생각(?:한다|해|합니다|해요)|이라고\s*생각.*|다고\s*봐.*|같(?:다|아).*)\s*$"
)

_LLM_SPLIT_SYSTEM = """You split a person's value/worldview statement into its core, independently \
checkable propositions, for matching against an ENGLISH philosophy knowledge graph (SEP-based).

Rules:
- Output ONLY a JSON array of strings — no prose, no markdown fences.
- Each element: ONE atomic claim, a single English sentence, present tense, self-contained.
- Translate to English if the input is in another language.
- Keep contrasts as SEPARATE elements (e.g. "love enriches the world" and "love creates lack \
in each other" become two items).
- 1 to N items (N given by the user). Drop filler/opinion frames ("I think that ...").
"""


def decompose(text: str, *, use_llm: bool = True, max_claims: int = 4) -> list[str]:
    text = (text or "").strip()
    if not text:
        return []
    if use_llm:
        try:
            return _decompose_llm(text, max_claims)
        except Exception:
            # LLM 실패(키없음/네트워크/파싱오류) 시 규칙 폴백 — 사유는 남긴다.
            logger.warning("LLM 명제 분해 실패 → 규칙 기반 폴백", exc_info=True)
    return _decompose_rule(text, max_claims)


def _decompose_rule(text: str, max_claims: int) -> list[str]:
    core = _FRAME_SUFFIX.sub("", _FRAME_PREFIX.sub("", text)).strip()
    parts = [p.strip(" ,.。·") for p in _SPLIT_RE.split(core) if p and p.strip()]
    parts = [p for p in parts if len(p) > 3]
    seen: set[str] = set()
    uniq = [p for p in parts if not (p.lower() in seen or seen.add(p.lower()))]
    return uniq[:max_claims] or [core or text]


def _strip_fences(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text


def _decompose_llm(text: str, max_claims: int) -> list[str]:
    """narrator(call_llm_json)로 '핵심 명제 N개 + 영어 정규화'. 실패 시 예외 → 규칙 폴백."""
    from engine import narrator

    prompt = f"{_LLM_SPLIT_SYSTEM}\nN = {max_claims}\n\nStatement:\n{text}"
    data, _wall = narrator.call_llm_json(prompt, timeout=60)
    parsed = json.loads(_strip_fences(data.get("result") or ""))
    if not isinstance(parsed, list):
        raise ValueError("LLM 분해 출력이 JSON 배열이 아님")
    claims = [str(c).strip() for c in parsed if str(c).strip()]
    if not claims:
        raise ValueError("LLM 분해 결과 비어있음")
    return claims[:max_claims]
