"""PhiloRAG — 가치관 진단 파이프라인 (Graph-Project C_RAG GraphRAG 이식).

흐름: decompose → retrieve_many → rank_philosophers → build_diagnosis → (LLM 진단문)
LLM 백엔드는 플랫폼 공용 engine.narrator(OpenRouter 스트리밍/claude) 를 쓴다.

diagnose() 는 단계별 (이름, ms, 요약) 기록을 함께 반환한다 — Chainlit Step 표시용.
"""
from __future__ import annotations

import re
import time
from dataclasses import dataclass, field

from philosophy.decompose import decompose
from philosophy.diagnose import build_diagnosis, format_diagnosis
from philosophy.retriever import LiteRetriever
from philosophy.schema import Diagnosis, RagAnswer

DIAGNOSIS_SYSTEM_PROMPT = """당신은 사용자의 가치관·생각을 철학 지형에 위치시키는 어시스턴트다.
아래 '회수 결과'는 사용자 입력을 철학 지식그래프(SEP 기반)에서 회수한 것이다.
이를 근거로, 아래 순서의 섹션(이 제목 그대로)으로 진단문을 작성하라:

## 유사한 주장
사용자의 생각과 가장 닿는 주장(claim)·개념 몇 가지를, 그 내용이 사용자 생각의 어느 지점과
공명하는지 자연스러운 문장으로 풀어 설명한다.

## 가까운 철학자
유사 주장의 실제 저자를 중심으로 가까운 철학자 1~3명을 짚고, 각자의 입장이 사용자 생각과
어떻게 연결되는지 설명한다.

## 당신과 유사한 사상
위 내용을 종합해 사용자의 가치관을 한 문단으로 해석한다 — 어떤 철학적 입장에 서 있고,
무엇을 중시하며, 어떤 긴장(tension)을 품고 있는지. 대비되는 입장(opposes)이 있으면
그 긴장도 언급한다.

작성 규칙:
- 반드시 한국어로 작성한다 (철학자 이름·개념은 한국어 관례 표기, 필요시 원어 병기).
- 본문에는 노드 코드(예: love::C_xxx)나 [대괄호 코드]를 절대 쓰지 말 것. 철학자·개념은 이름으로만 지칭한다.
- 회수 결과에 없는 철학자·주장은 지어내지 말 것. 근거가 약하면 약하다고 밝힐 것.
- 참고자료·인용 목록은 시스템이 본문 아래에 따로 덧붙이므로 직접 작성하지 말 것.
- 어조는 사용자의 생각을 존중하며 안내하듯이.
"""

_CITE_RE = re.compile(r"\[([^\]\s]+::[^\]\s]+)\]")  # [love::P_velleman] 형태


@dataclass
class StepRecord:
    name: str
    ms: float
    summary: str


@dataclass
class DiagnosisRun:
    diagnosis: Diagnosis
    steps: list[StepRecord] = field(default_factory=list)


class PhiloRAG:
    def __init__(self, retriever: LiteRetriever | None = None, *,
                 use_llm_split: bool = True):
        self.retriever = retriever or LiteRetriever()
        self.use_llm_split = use_llm_split

    def diagnose(self, query: str, *, split: bool = True, top_k: int = 10) -> DiagnosisRun:
        steps: list[StepRecord] = []

        def _timed(name: str, fn, summarize):
            t0 = time.perf_counter()
            out = fn()
            steps.append(StepRecord(name, (time.perf_counter() - t0) * 1000, summarize(out)))
            return out

        claims = _timed(
            "decompose",
            lambda: decompose(query, use_llm=self.use_llm_split) if split else [query],
            lambda c: "  |  ".join(c) or "(분해 없음)")
        bundles = _timed(
            "retrieve",
            lambda: self.retriever.retrieve_many(claims),
            lambda bs: f"회수 노드 {sum(len(b.neighbors) + len(b.expanded_nodes) for b in bs)}개"
                       f" / 명제 {len(bs)}건")
        top_phil = _timed(
            "rank_philosophers",
            lambda: self.retriever.rank_philosophers(bundles, top_k=top_k),
            lambda ps: ", ".join(f"{p.label}({p.score})" for p in ps[:5]) or "(없음)")
        diag = _timed(
            "build_diagnosis",
            lambda: build_diagnosis(query, claims, bundles, top_phil),
            lambda d: f"유사주장 {len(d.similar_claims)}건 · 대비 {len(d.contrasting_claims)}건")
        return DiagnosisRun(diagnosis=diag, steps=steps)

    # -- LLM 진단문 ----------------------------------------------------------
    def build_prompt(self, diag: Diagnosis) -> str:
        """narrator(단일 프롬프트 계약)용 — system+회수 리포트 결합."""
        return f"{DIAGNOSIS_SYSTEM_PROMPT}\n\n[회수 결과]\n{format_diagnosis(diag)}"

    def answer(self, query: str, *, split: bool = True, top_k: int = 10) -> RagAnswer:
        """비스트리밍 진단문 생성(스트리밍은 서비스 층에서 narrator.stream_openrouter)."""
        from engine import narrator

        run = self.diagnose(query, split=split, top_k=top_k)
        data, wall = narrator.call_llm_json(self.build_prompt(run.diagnosis), timeout=180)
        text = (data.get("result") or "").strip()
        meta = narrator.llm_meta(data, wall)
        d = run.diagnosis
        cited = set(_CITE_RE.findall(text))
        pool = [*d.similar_claims, *d.contrasting_claims, *d.school_concepts]
        return RagAnswer(query=query, answer=text,
                         citations=[n for n in pool if n.id in cited],
                         diagnosis=d, meta=meta)
