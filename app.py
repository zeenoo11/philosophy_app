import streamlit as st
from src.llm import analyze_philosophical_tendency, get_chat_response
from src.analysis_ui import display_analysis_results
from src.styles import apply_custom_styles
from src.config import PAGE_TITLE, PAGE_ICON, LAYOUT

# 페이지 설정 (반드시 최상단에 위치)
st.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON, layout=LAYOUT)

# 커스텀 스타일 적용
apply_custom_styles()

# 세션 상태 초기화
if "messages" not in st.session_state:
    st.session_state.messages = []
    # 첫 질문을 랜덤으로 선택하여 assistant 메시지로 추가
    try:
        from src.tools import get_random_question
        first_question = get_random_question()
        if first_question:
            greeting = f"""안녕하세요! 당신의 철학적 가치관을 함께 탐색해볼까요?

**{first_question['question']}**

*{first_question['context']}*"""
            st.session_state.messages.append({"role": "assistant", "content": greeting})
    except ImportError as e:
        st.error(f"필요한 모듈을 불러오지 못했습니다: {e}")


if "total_cost" not in st.session_state:
    st.session_state.total_cost = 0.0

# 분석 결과 팝업 함수
@st.dialog("🧐 나의 철학 분석 리포트", width="large")
def show_analysis_dialog():
    if len(st.session_state.messages) > 0:
        with st.spinner("당신의 철학적 영혼을 탐색하는 중..."):
            user_messages = [m for m in st.session_state.messages if m["role"] == "user"]
            analysis, cost = analyze_philosophical_tendency(user_messages)
            st.session_state.total_cost += cost
            if analysis:
                display_analysis_results(analysis, st.session_state.total_cost)
            else:
                st.error("분석 중 오류가 발생했습니다. 다시 시도해 주세요.")
    else:
        st.warning("먼저 대화를 시작해주세요.")

# 상단 레이아웃 (세로형으로 단순화)
st.markdown(f'<p class="main-title" style="margin-bottom: 0;">{PAGE_ICON} {PAGE_TITLE}</p>', unsafe_allow_html=True)
st.caption("나를 찾아 떠나는 철학 대화")

# 버튼 및 비용 표시
col_btn, col_info = st.columns([1, 1], vertical_alignment="center")
with col_btn:
    if st.button("탐색 시작", use_container_width=True):
        show_analysis_dialog()

with col_info:
    st.markdown(f"<div class='cost-display'>💸 ${st.session_state.total_cost:.4f}</div>", unsafe_allow_html=True)

st.divider()

# 소개 문구
st.caption("당신의 생각, 고민, 가치관을 자유롭게 들려주세요. 대화가 어느 정도 진행되면 상단의 '탐색 시작' 버튼을 눌러보세요.")

# 채팅 메시지 표시 (Fragment) - 메시지 렌더링만 독립적으로 수행
@st.fragment
def display_chat_messages():
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

display_chat_messages()

# 채팅 입력창 (Fragment 외부, 최하단 고정 보장)
if prompt := st.chat_input("당신의 생각을 들려주세요..."):
    # 사용자 메시지 저장
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # 즉시 UI 반영 (UX 향상)
    with st.chat_message("user"):
        st.markdown(prompt)

    # AI 응답 생성 및 표시
    with st.chat_message("assistant"):
        with st.spinner("사색 중..."):
            # 여기서 전체 메시지를 보냄
            response, cost = get_chat_response(st.session_state.messages)
            st.session_state.total_cost += cost
            st.markdown(response)
            st.session_state.messages.append({"role": "assistant", "content": response})
            
    # 전체 리런 (비용 업데이트 및 메시지 리스트 동기화)
    # 입력창이 Fragment 밖에 있으므로, 입력 시 스크립트가 리런되어 헤더 비용이 업데이트됨.
    st.rerun()
