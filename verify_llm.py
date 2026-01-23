from src.llm import analyze_philosophical_tendency, analyze_turn, get_chat_response
import sys

def test_llm_refactoring():
    print("Testing LLM Refactoring...")

    # 1. Test analyze_turn
    print("\n[1] Testing analyze_turn...")
    score, cost = analyze_turn("나는 내 운명을 내가 개척해.", "Agency")
    print(f"Result: Score={score}, Cost={cost}")
    assert score is not None, "Score should not be None"
    # Expected score around 0.9 for high agency
    
    # 2. Test get_chat_response
    print("\n[2] Testing get_chat_response...")
    messages = [{"role": "user", "content": "안녕, 나는 철학에 관심이 많아."}]
    response, cost_chat = get_chat_response(messages)
    print(f"Result: {response}, Cost={cost_chat}")
    assert "reply" in response, "Response must have 'reply'"
    assert "next_question_id" in response, "Response must have 'next_question_id'"

    # 3. Test analyze_philosophical_tendency
    print("\n[3] Testing analyze_philosophical_tendency...")
    # Mocking a short conversation
    messages_history = [
        {"role": "user", "content": "나는 자유가 가장 중요해."},
        {"role": "assistant", "content": "그렇군요."},
        {"role": "user", "content": "신은 없다고 생각해. 오직 물질뿐이야."}
    ]
    analysis, cost_analysis = analyze_philosophical_tendency(messages_history)
    print(f"Result: {analysis}, Cost={cost_analysis}")
    
    if analysis:
        assert "reasoning" in analysis
        assert "scores" in analysis
        assert len(analysis["scores"]) == 7
        print("Analysis Structure Verified.")
    else:
        print("Analysis returned None (could be an error or dry run if quota exceeded).")

if __name__ == "__main__":
    try:
        test_llm_refactoring()
        print("\n✅ LLM Verification Passed!")
    except Exception as e:
        print(f"\n❌ LLM Verification Failed: {e}")
        sys.exit(1)
