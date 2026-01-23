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

# 대립 쌍 설명 데이터 (matching_sheet.md 섹션 5.1 기반)
BINARY_OPPOSITIONS = [
    {
        "title": "결과주의 vs 의무론",
        "pair": ("공리주의", "칸트주의"),
        "description": "선의의 거짓말이나 소수의 희생을 통한 다수의 구원을 긍정하면 **공리주의**, "
                      "결과와 상관없이 원칙 준수를 강조하면 **칸트주의**에 가깝습니다."
    },
    {
        "title": "노력 vs 흐름",
        "pair": ("스토아", "도가"),
        "description": "두 사상 모두 '수용'을 말하지만, **스토아**는 이성적 노력과 훈련을 통해, "
                      "**도가**는 힘을 빼고 직관적으로 맡김으로써 평정에 도달합니다."
    },
    {
        "title": "개인 vs 집단",
        "pair": ("객관주의", "유교"),
        "description": "**객관주의**는 개인의 성취와 합리적 이기심을 최우선하며, "
                      "**유교**는 가족과 사회 내에서의 역할 완수와 관계의 조화를 중시합니다."
    },
    {
        "title": "의미의 발견 vs 창조",
        "pair": ("전통/종교", "실존주의"),
        "description": "전통적 사상은 의미가 외부(신, 도, 자연)에 존재한다고 보지만, "
                      "**실존주의**는 의미가 부재하며 인간이 스스로 만들어야 한다고 봅니다."
    }
]

def display_analysis_results(analysis: Dict[str, Any], total_cost: float = 0.0):
    """
    분석 결과를 시각화하여 Streamlit에 표시합니다.
    7축 점수(0-10)와 대립 쌍 설명을 포함합니다.
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

    # 3. 대립 쌍 설명 (새로 추가)
    st.subheader("⚖️ 철학적 대립 쌍")
    st.caption("철학 사상들은 종종 서로 대비되는 가치관을 보여줍니다.")
    
    for opp in BINARY_OPPOSITIONS:
        with st.expander(f"🔀 {opp['title']}"):
            st.markdown(opp['description'])
    
    st.divider()

    # 4. 철학적 좌표 (가치관 스케일) - 7축
    st.subheader("📊 나의 철학적 좌표")
    
    with st.expander("ℹ️ 각 지표가 무엇을 의미하나요?"):
        # 글자 크기를 줄이기 위해 HTML/CSS 활용
        guide_content = load_axis_guide()
        st.markdown(f"""
        <div style="font-size: 0.85rem; line-height: 1.4; color: #444;">
        {guide_content}
        </div>
        """, unsafe_allow_html=True)

    # 7축 레이블 정의
    axes_labels = [
        ("결정론", "자유의지", "Agency (행위 주체성)"),
        ("감성/직관", "이성/합리", "Logic (인식론)"),
        ("이기주의", "이타주의", "Focus (지향점)"),
        ("비관", "낙관", "Outlook (세계관)"),
        ("과거/전통", "미래/진보", "Time (시간 지향성)"),
        ("유물론", "영성/초월", "Meta (형이상학)"),
        ("반항", "순응", "Social (사회적 동조성)")
    ]

    for i, (left, right, label) in enumerate(axes_labels):
        score = scores[i] if i < len(scores) else 5
        st.markdown(f"**{label}**")
        
        # 슬라이더 (사용자 수정 불가) - 0-10 스케일
        st.slider(
            label=label,
            min_value=0,
            max_value=10,
            value=int(round(score)),
            step=1,
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
