import gradio as gr
from src.llm import get_chat_response, analyze_philosophical_tendency

def create_gradio_app():
    with gr.Blocks(title="Philosophy App Test") as demo:
        gr.Markdown("# 🦉 Philosophy App (Gradio Test)")
        gr.Markdown("Test the underlying LLM logic and tools without the full Streamlit UI.")
        
        with gr.Row():
            with gr.Column(scale=2):
                chatbot = gr.Chatbot(label="Conversation", height=500)
                msg = gr.Textbox(label="Your Input", placeholder="Type your thoughts here...")
                clear = gr.Button("Clear Chat")
            
            with gr.Column(scale=1):
                analyze_btn = gr.Button("🔮 Analyze Tendency", variant="primary")
                analysis_output = gr.JSON(label="Analysis Result")
                cost_display = gr.Markdown("Total Cost: $0.0000")

        # State to keep track of the full message history in the format LLM expects
        # List[Dict[str, str]]
        chat_state = gr.State([])
        cost_state = gr.State(0.0)

        def user_input(user_message, history, state):
            if not user_message:
                return "", history, state
            
            # Update state with user message
            state.append({"role": "user", "content": user_message})
            
            # Update UI history
            history = history + [[user_message, None]]
            return "", history, state

        def bot_response(history, state, current_cost):
            # Call the LLM (Note: get_chat_response modifies state in-place if tool calls occur)
            response_text, cost = get_chat_response(state)
            
            # Update total cost
            new_cost = current_cost + cost
            cost_text = f"Total Cost: ${new_cost:.4f}"
            
            # Append assistant response to state
            state.append({"role": "assistant", "content": response_text})
            
            # Update UI history
            history[-1][1] = response_text
            
            return history, state, new_cost, cost_text

        def analyze(state, current_cost):
            # Filter for user messages only
            user_messages = [m for m in state if m["role"] == "user"]
            
            if not user_messages:
                return {"error": "No user messages to analyze"}, current_cost, f"Total Cost: ${current_cost:.4f}"
                
            analysis, cost = analyze_philosophical_tendency(user_messages)
            
            new_cost = current_cost + cost
            cost_text = f"Total Cost: ${new_cost:.4f}"
            
            if analysis:
                return analysis, new_cost, cost_text
            else:
                return {"error": "Analysis failed"}, new_cost, cost_text

        def clear_chat():
            return [], [], 0.0, "Total Cost: $0.0000"

        # Event wiring
        msg.submit(user_input, [msg, chatbot, chat_state], [msg, chatbot, chat_state], queue=False).then(
            bot_response, [chatbot, chat_state, cost_state], [chatbot, chat_state, cost_state, cost_display]
        )
        
        analyze_btn.click(analyze, [chat_state, cost_state], [analysis_output, cost_state, cost_display])
        
        clear.click(clear_chat, None, [chatbot, chat_state, cost_state, cost_display], queue=False)

    return demo

if __name__ == "__main__":
    app = create_gradio_app()
    app.launch(server_name="0.0.0.0", server_port=7860)
