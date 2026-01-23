import streamlit as st
from src.llm import analyze_philosophical_tendency, get_chat_response, analyze_turn
from src.analysis_ui import display_analysis_results
from src.styles import apply_custom_styles
from src.config import PAGE_TITLE, PAGE_ICON, LAYOUT
from src.tools import load_questions # Questions loader
from src.icons import USER_ICON, BOT_ICON

# 페이지 설정 (반드시 최상단에 위치)
st.set_page_config(page_title=PAGE_TITLE, page_icon=PAGE_ICON, layout=LAYOUT)

# 커스텀 스타일 적용
apply_custom_styles()




# 질문 리스트 로드 (Session State에 캐싱 권장)
if "question_map" not in st.session_state:
    questions = load_questions() # List[dict]
    st.session_state.question_map = {q['id']: q for q in questions}

# 세션 상태 초기화
if "accumulated_scores" not in st.session_state:
    # 7가지 축에 대한 점수 리스트 초기화
    st.session_state.accumulated_scores = {
        "agency": [],
        "logic": [],
        "focus": [],
        "outlook": [],
        "time": [],
        "meta": [],
        "social": []
    }

if "current_axis" not in st.session_state:
    st.session_state.current_axis = None

if "messages" not in st.session_state:
    st.session_state.messages = []
    # 첫 질문을 랜덤으로 선택하여 assistant 메시지로 추가
    try:
        from src.tools import get_random_question
        first_question = get_random_question()
        if first_question:
            greeting = f"""안녕하세요! 당신의 철학적 가치관을 함께 탐색해볼까요?

**{first_question['question']}**"""
            st.session_state.messages.append({"role": "assistant", "content": greeting})
            # 첫 질문의 축 설정
            st.session_state.current_axis = first_question.get('axis')
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
            
            # 1. 기존 방식대로 전체 분석(Reasoning 생성용) 수행
            analysis, cost = analyze_philosophical_tendency(user_messages)
            st.session_state.total_cost += cost
            
            if analysis:
                # 2. 점수 부분은 누적 평균값으로 덮어쓰기 (Override)
                avg_scores = []
                # 순서: Agency, Logic, Focus, Outlook, Time, Meta, Social
                target_axes = ["agency", "logic", "focus", "outlook", "time", "meta", "social"]
                
                for axis in target_axes:
                    scores_list = st.session_state.accumulated_scores.get(axis, [])
                    if scores_list:
                        avg_val = sum(scores_list) / len(scores_list)
                    else:
                        avg_val = 5 # 기본값 (0-10 스케일)
                    avg_scores.append(avg_val)
                
                analysis['scores'] = avg_scores
                
                # 디버깅용: 계산된 점수 로그 출력 (Optional)
                print(f"Calculated Average Scores: {avg_scores} from {st.session_state.accumulated_scores}")

                display_analysis_results(analysis, st.session_state.total_cost)
            else:
                st.error("분석 중 오류가 발생했습니다. 다시 시도해 주세요.")
    else:
        st.warning("먼저 대화를 시작해주세요.")

# 상단 레이아웃 (세로형으로 단순화)
st.markdown(f'<p class="main-title" style="margin-bottom: 0;">{PAGE_ICON} {PAGE_TITLE}</p>', unsafe_allow_html=True)
st.caption("나를 찾아 떠나는 철학 대화")

# 탐색 시작 가능 여부 확인 (사용자 메시지가 1개 이상 있어야 함)
has_user_messages = any(m["role"] == "user" for m in st.session_state.messages)

# 버튼 및 비용 표시
col_btn, col_info = st.columns([1, 1], vertical_alignment="center")

with col_btn:
    if st.button("탐색 시작", use_container_width=True, disabled=not has_user_messages):
        show_analysis_dialog()

with col_info:
    st.markdown(f"<div class='cost-display'>💸 ${st.session_state.total_cost:.4f}</div>", unsafe_allow_html=True)

st.divider()

# 소개 문구
st.caption("당신의 생각, 고민, 가치관을 자유롭게 들려주세요. 대화가 어느 정도 진행되면 상단의 '탐색 시작' 버튼을 눌러보세요.")

# ... (imports)

# ... (previous code)

def scroll_to_bottom():
    """JavaScript를 사용하여 페이지 최하단으로 스크롤합니다."""
    js = """
    <script>
        function forceScroll() {
            const body = window.parent.document.querySelector(".main");
            if (body) {
                body.scrollTop = body.scrollHeight;
            }
            window.scrollTo({ top: document.body.scrollHeight, behavior: 'smooth' });
        }
        // 반복 호출로 로딩 지연 대응
        setTimeout(forceScroll, 100);
        setTimeout(forceScroll, 500);
        setTimeout(forceScroll, 1000);
    </script>
    """
    st.components.v1.html(js, height=0)

# ...

# 채팅 메시지 표시 (Fragment)
@st.fragment
def display_chat_messages():
    for message in st.session_state.messages:
        role = message["role"]
        avatar = USER_ICON if role == "user" else BOT_ICON
        with st.chat_message(role, avatar=avatar):
            st.markdown(message["content"])

display_chat_messages()

# 채팅 입력창
if prompt := st.chat_input("당신의 생각을 들려주세요..."):
    # 1. 사용자 메시지 저장
    st.session_state.messages.append({"role": "user", "content": prompt})
    
    # 2. 즉시 UI 반영
    with st.chat_message("user", avatar=USER_ICON):
        st.markdown(prompt)

    # 3. AI 분석 및 응답 생성
    with st.chat_message("assistant", avatar=BOT_ICON):
        with st.spinner("사색 중..."):
            
            # (A) 사용자 답변 실시간 점수 분석
            current_axis = st.session_state.current_axis
            if current_axis:
                turn_score, turn_cost = analyze_turn(prompt, current_axis)
                st.session_state.total_cost += turn_cost
                if turn_score is not None:
                    st.session_state.accumulated_scores[current_axis].append(turn_score)
                    print(f"Turn Analyzed: Axis={current_axis}, Score={turn_score}")

            # (B) 다음 대화 생성
            response_data, chat_cost = get_chat_response(st.session_state.messages)
            st.session_state.total_cost += chat_cost
            
            reply_text = response_data.get("reply", "...")
            next_qid = response_data.get("next_question_id")
            
            # (C) 다음 질문 붙이기 & 축 업데이트
            if next_qid:
                next_q = st.session_state.question_map.get(next_qid)
                if next_q:
                    # Context 제거, Question만 표시
                    reply_text += f"\n\n**{next_q['question']}**"
                    st.session_state.current_axis = next_q.get('axis')
                else:
                    st.session_state.current_axis = None
            else:
                st.session_state.current_axis = None
            
            # (D) 응답 표시 및 저장
            st.markdown(reply_text)
            st.session_state.messages.append({"role": "assistant", "content": reply_text})
            
    # 전체 리런
    st.rerun()

# 페이지 하단으로 자동 스크롤
scroll_to_bottom()
