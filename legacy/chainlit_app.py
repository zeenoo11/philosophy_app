import chainlit as cl
from src.llm import get_chat_response, analyze_philosophical_tendency
from src.distance import find_matching_philosophies
import json

@cl.set_starters
async def set_starters():
    return [
        cl.Starter(
            label="분석 시작",
            message="분석 시작",
            icon="/public/analysis_icon.svg",
        )
    ]

@cl.on_chat_start
async def start():
    # Initialize session state
    cl.user_session.set("messages", [])
    cl.user_session.set("cost", 0.0)

    # 질문 리스트에서 랜덤 질문 선택
    from src.tools import get_random_question
    first_question = get_random_question()
    
    if first_question:
        greeting = f"""🦉 **Philosophy App**

안녕하세요! 당신의 철학적 가치관을 함께 탐색해볼까요?

**{first_question['question']}**

*{first_question['context']}*"""
    else:
        greeting = "🦉 **Philosophy App**\n\n안녕하세요! 당신의 철학적 가치관을 탐색해 보세요. 대화를 나누다가 언제든 '분석 시작'을 입력하거나 아래 버튼을 눌러 분석할 수 있습니다."

    await cl.Message(content=greeting).send()

@cl.on_message
async def main(message: cl.Message):
    # Get current state
    messages = cl.user_session.get("messages")
    total_cost = cl.user_session.get("cost")

    # Handle Analysis Request
    if message.content.strip() == "분석 시작":
        await run_analysis()
        return

    # Normal Chat Flow
    # Add user message to history
    messages.append({"role": "user", "content": message.content})

    # Call LLM
    response_text, cost = get_chat_response(messages)
    
    # Update cost
    total_cost += cost
    cl.user_session.set("cost", total_cost)
    
    # Add assistant message to history
    messages.append({"role": "assistant", "content": response_text})
    
    # Update session
    cl.user_session.set("messages", messages)

    # Send response
    await cl.Message(
        content=f"{response_text}\n\n*💰 ${total_cost:.4f}*"
    ).send()

async def run_analysis():
    messages = cl.user_session.get("messages")
    user_messages = [m for m in messages if m["role"] == "user"]
    
    if not user_messages:
        await cl.Message(content="❌ 분석할 대화 내용이 충분하지 않습니다.").send()
        return

    loading_msg = cl.Message(content="🧐 분석 중입니다... 잠시만 기다려주세요.")
    await loading_msg.send()
    
    # Run analysis
    analysis, cost = analyze_philosophical_tendency(user_messages)
    
    # Update cost
    current_cost = cl.user_session.get("cost")
    total_cost = current_cost + cost
    cl.user_session.set("cost", total_cost)

    if analysis:
        # --- Logic from analysis_ui.py ported to Markdown ---
        scores = analysis['scores']
        reasoning = analysis['reasoning']
        
        # 1. Matching
        results = find_matching_philosophies(scores)
        top_match = results[0]
        top_3 = results[:3]
        bottom_match = results[-1]
        
        md_content = f"""# 🎉 당신은 **[{top_match['philosophy']}]** 입니다!

> **AI의 분석**: {reasoning}

---

## 🔗 나와 닮은, 그리고 먼 철학

### 🤝 나의 소울메이트
"""
        for i, match in enumerate(top_3):
            md_content += f"**{i+1}위. {match['philosophy']}** ({match['match_rate']:.0f}%)\n> {match['summary']}\n\n"
            
        md_content += f"""### ⚡️ 나와 정반대
**{bottom_match['philosophy']}** ({bottom_match['match_rate']:.0f}%)
> {bottom_match['summary']}
> *이 철학을 가진 사람과는 대화가 아주 흥미로울 거예요!*

---

## 📊 나의 철학적 좌표
"""
        axes_labels = [
            ("수동", "능동", "Agency (주체성)"),
            ("감성", "이성", "Logic (판단 근거)"),
            ("공동체", "개인", "Focus (관심 반경)"),
            ("비관", "낙관", "Outlook (삶의 태도)")
        ]
        
        for i, (left, right, label) in enumerate(axes_labels):
            score = scores[i]
            # Simple visualization using text
            bar_len = 20
            pos = int(score * bar_len)
            bar = "─" * pos + "●" + "─" * (bar_len - pos)
            
            md_content += f"**{label}**: {score:.2f}\n"
            md_content += f"`{left} |{bar}| {right}`\n\n"
            
        md_content += f"\n---\n💰 **Total Cost: ${total_cost:.4f}**"
        
        await loading_msg.remove()
        await cl.Message(content=md_content).send()
    else:
        await loading_msg.remove()
        await cl.Message(content="❌ 분석 중 오류가 발생했습니다.").send()
