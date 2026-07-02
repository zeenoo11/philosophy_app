"""saju-engine — 다중 유파 사주 해석 엔진.

레이어 분리 (docs/SPEC.md §1):
  L1 pillars  — 결정론 (정답 있음): 천문/룩업/산술
  L2 scorer   — 스코어링 (규칙, 가중치는 프리셋)
  L3 yongsin  — 용신 정책 (정답 없음)
  L4 narrator — 자연어 종합 (LLM, 그라운딩)

이 패키지의 공개 진입점은 L1 결정론 레이어다. 해석 레이어(L2~L4)는
프리셋에 의존하며 별도 모듈로 분리되어 검증 철학이 섞이지 않는다.
"""

from engine.pillars import compute_chart, Chart, Pillar  # noqa: E402,F401

__all__ = ["compute_chart", "Chart", "Pillar"]
