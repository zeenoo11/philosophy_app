import os
import json
import random
from typing import Optional
from src.config import QUESTION_LIST_PATH

def load_questions() -> list[dict]:
    """
    JSON 파일에서 철학적 질문 리스트를 로드합니다.
    
    Returns:
        list[dict]: 질문 리스트 (파싱 실패 시 빈 리스트)
    """
    try:
        with open(QUESTION_LIST_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("questions", [])
    except FileNotFoundError:
        print(f"Error: Question list file not found at {QUESTION_LIST_PATH}")
        return []
    except json.JSONDecodeError as e:
        print(f"Error parsing JSON: {e}")
        return []
    except Exception as e:
        print(f"Error reading question list: {e}")
        return []

def get_random_question() -> Optional[dict]:
    """
    질문 리스트에서 랜덤으로 하나를 선택합니다.
    
    Returns:
        dict: 선택된 질문 (질문이 없으면 None)
    """
    questions = load_questions()
    if questions:
        return random.choice(questions)
    return None

def get_philosophical_questions() -> str:
    """
    LLM 도구용: 철학적 질문 리스트를 JSON 문자열로 반환합니다.
    
    Returns:
        str: JSON 형식의 질문 리스트
    """
    questions = load_questions()
    if questions:
        return json.dumps(questions, ensure_ascii=False, indent=2)
    return "Error: No questions available."

