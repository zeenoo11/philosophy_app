"""가치관 입력 → 핵심 명제 분해 + 영어 정규화 + 엔티티 추출 (Graph-Project C_RAG 이식).

긴 복합 생각은 단일 임베딩으로 뭉개진다("풍요롭게 한다"+"결핍을 준다"가 평균됨).
핵심 명제 2~4개로 쪼개 각각 retrieve 후 종합한다. 같은 LLM 호출에서 사용자가
직접 언급한 철학자·개념(entities)도 뽑아 그래프 노드에 링킹한다(경로 추론 앵커).

- 정석: LLM 분해(플랫폼 공용 engine.narrator — OpenRouter/claude 자동) —
  명제 분리 + **영어 정규화**(그래프·임베딩이 영어 SEP 기반이라 영어화가 핵심) + 엔티티.
- 폴백: 규칙 기반(접속사·문장부호 분리). 번역·엔티티 추출은 못 하므로 이 경로는
  영어 입력 가정이며 entities 는 빈 목록(현행 폴백 규약과 동일 — 조용히 비운다).
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class Decomposition:
    """LLM 분해 산출물 — 핵심 명제 + 사용자가 직접 언급한 엔티티(철학자·개념)."""

    claims: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)  # 영어/로마자 이름 — 그래프 링킹용

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
checkable propositions, and extract any philosophers or named concepts they mention, for matching \
against an ENGLISH philosophy knowledge graph (SEP-based).

Rules:
- Output ONLY a JSON object with two keys: "claims" and "entities" — no prose, no markdown fences.
- "claims": an array of 1 to N strings (N given by the user). Each element is ONE atomic claim, a \
single English sentence, present tense, self-contained. Translate to English if the input is in \
another language. Keep contrasts as SEPARATE elements (e.g. "love enriches the world" and "love \
creates lack in each other" become two items). Drop filler/opinion frames ("I think that ...").
- "entities": an array of strings naming any philosopher or well-known philosophical concept the \
person EXPLICITLY mentions (e.g. "Nietzsche", "Kant", "utilitarianism"). Use the standard English \
/ romanized name. Empty array if none are named — do NOT guess or infer unmentioned thinkers.
"""


def decompose(text: str, *, use_llm: bool = True, max_claims: int = 4) -> list[str]:
    """핵심 명제만 반환(하위 호환). 엔티티까지 필요하면 decompose_full 을 쓴다."""
    return decompose_full(text, use_llm=use_llm, max_claims=max_claims).claims


def decompose_full(text: str, *, use_llm: bool = True, max_claims: int = 4) -> Decomposition:
    """명제 + 엔티티. LLM 실패 시 규칙 폴백(명제만, 엔티티는 빈 목록)."""
    text = (text or "").strip()
    if not text:
        return Decomposition()
    if use_llm:
        try:
            return _decompose_llm(text, max_claims)
        except Exception:
            # LLM 실패(키없음/네트워크/파싱오류) 시 규칙 폴백 — 사유는 남긴다.
            logger.warning("LLM 명제 분해 실패 → 규칙 기반 폴백", exc_info=True)
    return Decomposition(claims=_decompose_rule(text, max_claims))


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


def _decompose_llm(text: str, max_claims: int) -> Decomposition:
    """narrator(call_llm_json)로 '핵심 명제 N개 + 영어 정규화 + 엔티티'. 실패 시 예외 → 규칙 폴백.

    출력은 {"claims": [...], "entities": [...]} 객체를 기대하되, 예전처럼 순수 배열이
    오면 명제 목록으로 관용 처리(엔티티는 빈 목록)한다.
    """
    from engine import narrator

    prompt = f"{_LLM_SPLIT_SYSTEM}\nN = {max_claims}\n\nStatement:\n{text}"
    data, _wall = narrator.call_llm_json(prompt, timeout=60)
    parsed = json.loads(_strip_fences(data.get("result") or ""))
    if isinstance(parsed, list):          # 구버전 관용 — 배열이면 명제 목록으로 간주
        raw_claims, raw_entities = parsed, []
    elif isinstance(parsed, dict):
        raw_claims = parsed.get("claims") or []
        raw_entities = parsed.get("entities") or []
        if not isinstance(raw_claims, list) or not isinstance(raw_entities, list):
            raise ValueError("LLM 분해 claims/entities 가 배열이 아님")
    else:
        raise ValueError("LLM 분해 출력이 JSON 객체/배열이 아님")
    claims = [str(c).strip() for c in raw_claims if str(c).strip()]
    if not claims:
        raise ValueError("LLM 분해 결과 비어있음")
    # 엔티티는 dedup(대소문자 무시, 순서 유지) — 링킹 앵커 후보
    entities, seen = [], set()
    for e in raw_entities:
        s = str(e).strip()
        if s and s.lower() not in seen:
            seen.add(s.lower())
            entities.append(s)
    return Decomposition(claims=claims[:max_claims], entities=entities)
