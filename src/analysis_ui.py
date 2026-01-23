import streamlit as st
from typing import Dict, Any
from src.distance import find_matching_philosophies
import os
from src.config import BASE_DIR

def load_axis_guide():
    """docs/index.md 파일을 읽어옵니다."""
    try:
        path = os.path.join(BASE_DIR, "docs", "index.md")
        with open(path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception:
        return "가이드 파일을 찾을 수 없습니다."

def display_analysis_results(analysis: Dict[str, Any], total_cost: float = 0.0):
    """
    분석 결과를 시각화하여 Streamlit에 표시합니다.
    """
    if not analysis:
        return

    scores = analysis['scores']
    reasoning = analysis['reasoning']
    
    # 사상 매칭 결과 계산
    results = find_matching_philosophies(scores)
    
    # Top 1 사상
    top_match = results[0]
    # Top 3 (가까운 순위)
    top_3 = results[:3]
    # Bottom 1 (가장 먼 순위)
    bottom_match = results[-1]

    # 1. 헤드라인: "당신은 OOO 입니다"
    st.markdown(f"### 🎉 당신은 **[{top_match['philosophy']}]** 입니다!")
    st.info(f"**AI의 분석**: {reasoning}")
    
    st.divider()

    # 2. 사상 매칭 결과 (가까운, 먼)
    st.subheader("🔗 나와 닮은, 그리고 먼 철학")
    
    col_close, col_far = st.columns(2)
    
    with col_close:
        st.markdown("#### 🤝 나의 소울메이트")
        for i, match in enumerate(top_3):
            st.markdown(f"**{i+1}위. {match['philosophy']}** ({match['match_rate']:.0f}%)")
            st.caption(match['summary'])

    with col_far:
        st.markdown("#### ⚡️ 나와 정반대")
        st.markdown(f"**{bottom_match['philosophy']}** ({bottom_match['match_rate']:.0f}%)")
        st.caption(bottom_match['summary'])
        st.caption("이 철학을 가진 사람과는 대화가 아주 흥미로울 거예요!")

    st.divider()

    # 3. 철학적 좌표 (가치관 스케일)
    st.subheader("📊 나의 철학적 좌표")
    
    with st.expander("ℹ️ 각 지표가 무엇을 의미하나요?"):
        # 글자 크기를 줄이기 위해 HTML/CSS 활용
        guide_content = load_axis_guide()
        st.markdown(f"""
        <div style="font-size: 0.85rem; line-height: 1.4; color: #444;">
        {guide_content}
        </div>
        """, unsafe_allow_html=True)

    axes_labels = [
        ("수동", "능동", "Agency (주체성)"),
        ("감성", "이성", "Logic (판단 근거)"),
        ("공동체", "개인", "Focus (관심 반경)"),
        ("비관", "낙관", "Outlook (삶의 태도)")
    ]

    for i, (left, right, label) in enumerate(axes_labels):
        score = scores[i]
        st.markdown(f"**{label}**")
        
        # 슬라이더 (사용자 수정 불가)
        st.slider(
            label=label,
            min_value=0.0,
            max_value=1.0,
            value=float(score),
            step=0.01,
            disabled=True,
            label_visibility="collapsed",
            key=f"scale_{i}"
        )
        col_l, col_r = st.columns(2)
        col_l.caption(f"← {left}")
        col_r.markdown(f"<p style='text-align: right; color: gray; font-size: 0.8rem;'>{right} →</p>", unsafe_allow_html=True)

    st.divider()
    # 비용 표시
    st.markdown(f"<div style='text-align: right; font-size: 0.9rem; color: gray;'>💰 Total Cost: ${total_cost:.4f}</div>", unsafe_allow_html=True)

