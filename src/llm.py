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
        
        사용자의 대화를 분석하여 다음 4가지 축의 점수(0.0~1.0)를 산출하세요.
        
        1. Agency (주체성): 수동(0.0) <-> 능동(1.0)
        2. Logic (판단 근거): 감성(0.0) <-> 이성(1.0)
        3. Focus (관심 반경): 공동체(0.0) <-> 개인(1.0)
        4. Outlook (삶의 태도): 비관/냉소(0.0) <-> 낙관(1.0)

        반드시 다음 JSON 형식으로 출력하세요:
        {
            "reasoning": "점수 산정 근거 요약 (3문장 이내, 내담자에게 말하듯 부드러운 어조)",
            "scores": [0.5, 0.5, 0.5, 0.5]
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

def get_chat_response(messages: List[Dict[str, str]]) -> Tuple[str, float]:
    """
    사용자의 대화 흐름을 이어가며 철학적 답변을 유도하는 응답을 생성합니다.
    Returns: (응답텍스트, 비용)
    """
    # 질문 리스트를 미리 로드
    questions_json = get_philosophical_questions()
    
    chat_system_prompt = f"""당신은 사용자의 철학적 가치관을 탐색하는 따뜻한 대화 파트너입니다.

[핵심 목표]
아래 질문 리스트를 활용하여 사용자의 철학적 성향(주체성, 판단 방식, 관심 범위, 삶의 태도)을 자연스럽게 파악합니다.

[대화 방식]
1. **공감 먼저**: 사용자의 답변에 1문장으로 짧게 공감하거나 이해를 표현합니다.
2. **질문 연결**: 바로 다음 질문으로 넘어갑니다. 아래 리스트에서 아직 물어보지 않은 질문을 선택하세요.
3. **자연스러운 전환**: "그렇군요. 그럼 이런 건 어떠세요?" 같은 짧은 연결어를 사용합니다.
4. **간결함 유지**: 전체 응답은 2-3문장 이내로 짧게 유지합니다.

[금지 사항]
- 사용자가 말한 지엽적인 내용에 대해 꼬리를 무는 질문 금지
- 추상적이거나 철학적인 강의 금지
- 철학자 이름이나 이론 언급 금지
- 긴 설명이나 해석 금지

[질문 리스트]
{questions_json}

[대화 종료 시]
사용자가 "고마워", "여기까지", "정리해줘", "분석 시작" 등 종료 의사를 밝히면:
1. 대화를 정리하며 따뜻하게 마무리합니다.
2. "분석 시작"을 눌러보시라고 안내합니다.

[예시 응답]
사용자: "저는 규칙 안에서 사는 게 편해요"
AI: "안정감이 중요하시군요. 그럼 중요한 결정을 할 때는 어떠세요? 논리적으로 분석하는 편인가요, 아니면 직감을 따르시나요?"
"""

    total_cost = 0.0
    
    try:
        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "system", "content": chat_system_prompt}] + messages,
        )
        
        total_cost += calculate_cost(response.usage)
        return response.choices[0].message.content or "계속 말씀해 주세요.", total_cost

    except Exception as e:
        print(f"Chat Error: {e}")
        return "흥미로운 생각이네요. 조금 더 들려주실 수 있나요?", 0.0

