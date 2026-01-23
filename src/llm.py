import json
from typing import List, Dict, Optional, Any, Tuple
from openai import OpenAI
from src.config import (
    OPENAI_API_KEY, 
    MODEL_NAME, 
    SYSTEM_PROMPT_PATH,
    PRICE_PER_1M_INPUT_TOKENS, 
    PRICE_PER_1M_OUTPUT_TOKENS
)
from src.tools import get_philosophical_questions

# OpenAI 클라이언트 초기화
client = OpenAI(api_key=OPENAI_API_KEY)

def calculate_cost(usage) -> float:
    """토큰 사용량을 기반으로 비용(USD)을 계산합니다."""
    if not usage:
        return 0.0
    
    input_cost = (usage.prompt_tokens / 1_000_000) * PRICE_PER_1M_INPUT_TOKENS
    output_cost = (usage.completion_tokens / 1_000_000) * PRICE_PER_1M_OUTPUT_TOKENS
    return input_cost + output_cost

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

        반드시 다음 JSON 형식으로 출력하세요:
        {
            "reasoning": "점수 산정 근거 요약 (3문장 이내, 내담자에게 말하듯 부드러운 어조)",
            "scores": [Agency, Logic, Focus, Outlook, Time, Meta, Social]
        }
        """

def analyze_philosophical_tendency(messages: List[Dict[str, str]]) -> Tuple[Optional[Dict[str, Any]], float]:
    """
    LLM을 통해 사용자의 대화 내역 전체를 분석하여 4개 축 점수를 추출합니다.
    Returns: (분석결과, 비용)
    """
    system_prompt = load_system_prompt()
    
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[
                {"role": "system", "content": system_prompt}
            ] + messages,
            response_format={"type": "json_object"}
        )
        
        cost = calculate_cost(response.usage)
        content = response.choices[0].message.content
        
        if content:
            return json.loads(content), cost
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

    prompt = f"""
    당신은 심리/철학 분석가입니다.
    사용자의 답변이 '{current_axis}' 축에서 어떤 성향을 보이는지 5단계로 평가하세요.

    [평가 기준: {current_axis}]
    1점 (-2): 투철하게 반대됨 / 매우 낮음 (Score: 0.1)
    2점 (-1): 다소 반대됨 / 낮음 (Score: 0.3)
    3점 (0): 중립 / 모호함 / 판단 불가 (Score: 0.5)
    4점 (+1): 다소 해당됨 / 높음 (Score: 0.7)
    5점 (+2): 강력하게 해당됨 / 매우 높음 (Score: 0.9)

    [답변]: "{user_message}"

    반드시 다음 JSON 형식으로만 응답하세요:
    {{
        "score_level": 3,
        "score_value": 0.5,
        "reason": "짧은 이유"
    }}
    """

    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "system", "content": prompt}],
            response_format={"type": "json_object"}
        )
        cost = calculate_cost(response.usage)
        content = json.loads(response.choices[0].message.content)
        return content.get('score_value', 0.5), cost
    except Exception as e:
        print(f"Turn Analysis Error: {e}")
        return None, 0.0

def get_chat_response(messages: List[Dict[str, str]]) -> Tuple[Dict[str, Any], float]:
    """
    사용자의 대화 흐름을 이어가며 철학적 답변을 유도하는 응답을 생성합니다.
    Returns: (JSON응답, 비용)
    
    JSON 응답 구조:
    {
        "reply": "사용자에게 할 말",
        "next_question_id": 12 (질문 리스트의 ID, 없으면 null)
    }
    """
    # 질문 리스트를 미리 로드
    questions_json = get_philosophical_questions()
    
    chat_system_prompt = f"""당신은 사용자의 철학적 가치관을 탐색하는 따뜻한 대화 파트너입니다.

[상태]
현재 대화는 JSON 포맷으로 통신합니다.

[핵심 목표]
아래 질문 리스트를 활용하여 사용자의 철학적 성향을 파악합니다.
이전 대화 맥락을 고려하여, 가장 자연스럽게 이어질 수 있는 다음 질문을 선택하세요.

[응답 포맷]
반드시 JSON 형식으로 응답해야 합니다:
{{
    "reply": "공감 멘트 + 자연스러운 질문 유도 멘트 (질문 본문은 제외하고 연결만)",
    "next_question_id": 5  // 다음에 던질 질문의 ID (질문 리스트 참조)
}}
* 주의: `reply`에는 질문 자체를 통째로 쓰지 말고, 자연스럽게 화제를 돌리는 멘트 정도만 작성하세요. 
  실제 질문 내용은 앱이 `next_question_id`를 보고 자동으로 붙여줄 것입니다.
  만약 더 이상 물을 질문이 없거나 대화를 종료해야 한다면 `next_question_id`는 null로 하세요.

[질문 리스트]
{questions_json}
"""

    total_cost = 0.0
    
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "system", "content": chat_system_prompt}] + messages,
            response_format={"type": "json_object"}
        )
        
        total_cost += calculate_cost(response.usage)
        content_str = response.choices[0].message.content
        
        try:
            return json.loads(content_str), total_cost
        except json.JSONDecodeError:
            # Fallback for plain text response
            return {"reply": content_str, "next_question_id": None}, total_cost

    except Exception as e:
        print(f"Chat Error: {e}")
        return {"reply": "이야기를 좀 더 들려주시겠어요?", "next_question_id": None}, 0.0

