import streamlit as st

def apply_custom_styles():
    st.markdown("""
        <style>
        :root {
            --bg-user: #F0F2F6;
            --bg-assistant: #FFFFFF;
            --border-assistant: #E0E0E0;
            --text-main: #1E1E1E;
            --text-secondary: #aaa;
        }

        @media (prefers-color-scheme: dark) {
            :root {
                --bg-user: #2D2D2D;
                --bg-assistant: #1E1E1E;
                --border-assistant: #444444;
                --text-main: #E0E0E0;
                --text-secondary: #888;
            }
        }

        .main-title {
            font-size: 1.8rem !important;
            font-weight: 800;
            margin-bottom: 0.5rem;
            color: var(--text-main);
        }
        .stButton button {
            width: 100%;
            border-radius: 10px;
            transition: all 0.3s ease;
        }
        .stButton button:hover {
            transform: translateY(-2px);
            box-shadow: 0 4px 12px rgba(0,0,0,0.1);
        }
        
        /* 채팅 메시지 스타일 최적화 (Streamlit 기본 컨테이너 대응) */
        [data-testid="stChatMessage"] {
            background-color: transparent !important;
        }
        
        .chat-message-user {
            background-color: var(--bg-user);
            border-radius: 15px;
            padding: 10px;
            color: var(--text-main);
        }
        .chat-message-assistant {
            background-color: var(--bg-assistant);
            border-radius: 15px;
            padding: 10px;
            border: 1px solid var(--border-assistant);
            color: var(--text-main);
        }
        
        [data-testid="stHeader"] {
            visibility: hidden;
            height: 0px;
        }
        
        footer {visibility: hidden;}
        .stChatInputContainer {
            padding-bottom: 0.2rem;
        }
        
        .block-container {
            padding-top: 2rem;
            padding-bottom: 4rem;
            overflow-x: hidden;
        }

        @media (max-width: 640px) {
            .main-title {
                font-size: 1.25rem !important;
            }
            .stButton button {
                font-size: 0.85rem !important;
                padding: 0 5px !important;
                min-height: 2.5rem;
            }
            [data-testid="stHorizontalBlock"] {
                gap: 10px !important;
            }
        }

        .cost-display {
            text-align: right !important;
            width: 100%;
            color: var(--text-secondary);
            font-size: 0.8rem;
            margin-top: 5px;
        }
        </style>
        """, unsafe_allow_html=True)
