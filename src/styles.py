import streamlit as st

def apply_custom_styles():
    st.markdown("""
        <style>
        .main-title {
            font-size: 1.8rem !important;
            font-weight: 800;
            margin-bottom: 0.5rem;
            color: #1E1E1E;
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
        .chat-message-user {
            background-color: #F0F2F6;
            border-radius: 15px;
            padding: 10px;
        }
        .chat-message-assistant {
            background-color: #FFFFFF;
            border-radius: 15px;
            padding: 10px;
            border: 1px solid #E0E0E0;
        }
        
        /* Streamlit Header/Toolbar 숨기기 (Deploy 버튼 포함) */
        [data-testid="stHeader"] {
            visibility: hidden;
            height: 0px;
        }
        
        /* 모바일 채팅 입력창 렉 완화 (하단 고정 관련 안정성 확보) */
        /* footer {visibility: hidden;} */
        .stChatInputContainer {
            padding-bottom: 1rem;
        }
        
        /* 전체 컨테이너 여백 및 넘침 방지 */
        .block-container {
            padding-top: 2rem;
            padding-bottom: 5rem;
            overflow-x: hidden;
        }

        /* 모바일 대응: 타이틀 폰트 크기 및 레이아웃 최적화 */
        @media (max-width: 640px) {
            .main-title {
                font-size: 1.25rem !important; /* 모바일에서 약간 축소 */
            }
            .stButton button {
                font-size: 0.85rem !important; /* 버튼 내 텍스트 크기 축소 */
                padding: 0 5px !important;
                min-height: 2.5rem;
            }
            /* 헤더 등 특정 행에서만 가로 유지하도록 유도 */
            [data-testid="stHorizontalBlock"] {
                gap: 10px !important;
            }
        }

        /* 비용 텍스트 우측 정렬 */
        .cost-display {
            text-align: right !important;
            width: 100%;
            color: #aaa;
            font-size: 0.8rem;
            margin-top: 5px;
        }
        </style>
        """, unsafe_allow_html=True)
