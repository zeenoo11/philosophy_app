"""마크다운 정리 — 플랫폼 공용 (Chainlit/GFM 렌더 오류 방지).

LLM 생성 텍스트에서 자주 깨지는 두 가지를 고친다:
- 단일 물결표(~)는 GFM 취소선으로 해석되어 '다음 ~까지 줄이 그어짐' → 틸드형(∼) 치환.
- 굵게(**) 정규화: 안쪽 공백 제거(** x ** → **x**), 홀수 개면 dangling 제거,
  닫는 ** 뒤에 한글 조사가 바로 붙어 강조가 안 닫히는 케이스(**용신(토)**이라는)는
  ** 뒤에 zero-width 문자 없이도 렌더되도록 별표 자체를 걷어낸다(짝이 안 맞을 때만).

사주(saju_service)·철학(philo_service)·통합(app.py fusion)이 모두 이 함수를 쓴다 —
답변 형태를 한 규약으로 유지하기 위한 단일 진실원.
"""
from __future__ import annotations

import re

_BOLD_INNER = re.compile(r"\*\*[ \t]*([^*\n]+?)[ \t]*\*\*")


def clean_md(text: str) -> str:
    if not text:
        return text
    text = text.replace("~", "∼")
    text = _BOLD_INNER.sub(r"**\1**", text)
    if text.count("**") % 2 == 1:  # 짝 안 맞는 dangling ** 제거
        i = text.rfind("**")
        text = text[:i] + text[i + 2:]
    return text
