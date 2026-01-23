import json
from typing import List, Dict, Optional, Any, Tuple
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.messages import SystemMessage
from pydantic import BaseModel, Field
from langchain_community.callbacks import get_openai_callback
from src.config import (
    OPENAI_API_KEY, 
    MODEL_NAME, 
    SYSTEM_PROMPT_PATH
)
from src.tools import get_philosophical_questions

# LangChain Chat Model 초기화
llm = ChatOpenAI(api_key=OPENAI_API_KEY, model=MODEL_NAME, temperature=0.7)

# --- Pydantic Models for Structured Output ---

class PhilosophicalAnalysis(BaseModel):
    reasoning: str = Field(description="점수 산정 근거 요약 (3문장 이내, 내담자에게 말하듯 부드러운 어조)")
    scores: List[int] = Field(
        description="7가지 축의 점수 리스트 [Agency, Logic, Focus, Outlook, Time, Meta, Social]. 각 점수는 0~10 사이 정수.",
        min_items=7,
        max_items=7
    )

class TurnAnalysis(BaseModel):
    score_level: int = Field(description="1(-2) ~ 5(+2) 사이의 척도 레벨")
    score_value: float = Field(description="변환된 점수 값 (0.1, 0.3, 0.5, 0.7, 0.9 중 하나)")
    reason: str = Field(description="판단 이유")

class ChatResponse(BaseModel):
    reply: str = Field(description="사용자에게 건넬 공감 및 유도 멘트 (질문 본문은 제외)")
    next_question_id: Optional[int] = Field(description="다음에 던질 질문의 ID. 더 이상 물을 게 없으면 null.")


def load_system_prompt(file_path: str = SYSTEM_PROMPT_PATH) -> str:
    """정교한 분석 프롬프트를 로드합니다."""
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        # Fallback prompt if file is missing
        return """
        # Role: 철학적 가치관 분석가
        
        사용자의 대화를 분석하여 다음 7가지 축의 점수(0~10)를 산출하세요.
        
        1. Agency (주체성): 결정론(0) <-> 자유의지(10)
        2. Logic (인식론): 감정/직관(0) <-> 이성/합리(10)
        3. Focus (지향점): 이기주의(0) <-> 이타주의(10)
        4. Outlook (세계관): 비관(0) <-> 낙관(10)
        5. Time (시간 지향): 과거/전통(0) <-> 미래/진보(10)
        6. Meta (형이상학): 유물론(0) <-> 영성/초월(10)
        7. Social (사회 동조): 반항(0) <-> 순응(10)
        """

def analyze_philosophical_tendency(messages: List[Dict[str, str]]) -> Tuple[Optional[Dict[str, Any]], float]:
    """
    LLM을 통해 사용자의 대화 내역 전체를 분석하여 7개 축 점수를 추출합니다.
    Returns: (분석결과, 비용)
    """
    system_prompt_text = load_system_prompt()
    
    # 프롬프트 템플릿 구성
    # SystemMessage 객체를 직접 사용하여 텍스트 내의 중괄호가 템플릿 변수로 인식되지 않도록 함
    prompt = ChatPromptTemplate.from_messages([
        SystemMessage(content=system_prompt_text),
        MessagesPlaceholder(variable_name="messages")
    ])

    # Structured Output Chain 생성
    chain = prompt | llm.with_structured_output(PhilosophicalAnalysis)

    try:
        with get_openai_callback() as cb:
            result: PhilosophicalAnalysis = chain.invoke({"messages": messages})
            cost = cb.total_cost
            
            if result:
                return result.dict(), cost
            return None, cost
    except Exception as e:
        print(f"AI 분석 중 오류가 발생했습니다: {e}")
        return None, 0.0

def analyze_turn(user_message: str, current_axis: str) -> Tuple[Optional[float], float]:
    """
    사용자의 한 턴 답변을 분석하여 5단계 척도 점수로 변환합니다.
    Returns: (점수(0.1~0.9), 비용)
    """
    if not current_axis:
        return None, 0.0

    system_text = f"""
    당신은 심리/철학 분석가입니다.
    사용자의 답변이 '{current_axis}' 축에서 어떤 성향을 보이는지 5단계로 평가하세요.

    [평가 기준: {current_axis}]
    1점 (-2): 투철하게 반대됨 / 매우 낮음 (Score: 0.1)
    2점 (-1): 다소 반대됨 / 낮음 (Score: 0.3)
    3점 (0): 중립 / 모호함 / 판단 불가 (Score: 0.5)
    4점 (+1): 다소 해당됨 / 높음 (Score: 0.7)
    5점 (+2): 강력하게 해당됨 / 매우 높음 (Score: 0.9)
    """

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_text),
        ("human", "{user_message}")
    ])

    chain = prompt | llm.with_structured_output(TurnAnalysis)

    try:
        with get_openai_callback() as cb:
            result: TurnAnalysis = chain.invoke({"user_message": user_message})
            cost = cb.total_cost
            return result.score_value, cost
    except Exception as e:
        print(f"Turn Analysis Error: {e}")
        return None, 0.0

def get_chat_response(messages: List[Dict[str, str]]) -> Tuple[Dict[str, Any], float]:
    """
    사용자의 대화 흐름을 이어가며 철학적 답변을 유도하는 응답을 생성합니다.
    Returns: (JSON응답, 비용)
    """
    questions_json = get_philosophical_questions()
    
    system_text = """당신은 사용자의 철학적 가치관을 탐색하는 따뜻한 대화 파트너입니다.

[상태]
현재 대화는 JSON 포맷으로 통신합니다.

[핵심 목표]
아래 질문 리스트를 활용하여 사용자의 철학적 성향을 파악합니다.
이전 대화 맥락을 고려하여, 가장 자연스럽게 이어질 수 있는 다음 질문을 선택하세요.

[응답 가이드]
- `reply`: 공감 멘트 + 자연스러운 질문 유도 멘트 (질문 본문은 제외하고 연결만)
- `next_question_id`: 다음에 던질 질문의 ID (질문 리스트 참조). 더 이상 물을 질문이 없으면 null.
- 주의: `reply`에는 질문 자체를 통째로 쓰지 말고, 자연스럽게 화제를 돌리는 멘트 정도만 작성하세요. 
  실제 질문 내용은 앱이 `next_question_id`를 보고 자동으로 붙여줄 것입니다.

[질문 리스트]
{questions_json}
"""

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_text),
        MessagesPlaceholder(variable_name="history")
    ])

    chain = prompt | llm.with_structured_output(ChatResponse)

    try:
        with get_openai_callback() as cb:
            result: ChatResponse = chain.invoke({
                "questions_json": questions_json,
                "history": messages
            })
            cost = cb.total_cost
            return result.dict(), cost

    except Exception as e:
        print(f"Chat Error: {e}")
        return {"reply": "이야기를 좀 더 들려주시겠어요?", "next_question_id": None}, 0.0

