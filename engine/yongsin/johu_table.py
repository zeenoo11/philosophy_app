"""조후(調候) 월지 한난조습(寒暖燥濕) 분류표 — L3 johu 정책 데이터.

궁통보감(欄江網) 계열의 계절 한난 골격을 결정론 룩업으로 고정한다. 본격
일간×월령 정밀표는 후속 과제이며, 여기서는 '월지가 어떤 기후이고 어떤 오행으로
조후하는가'만 12지지 전체에 대해 못박는다(분기 시연 + 충실도 검증 가능).

각 항목: branch(0..11) → (climate, yong_el, rule_id, label)
  • climate  — 한난 분류 키 ("한"/"난"/None). trace inputs 의 한난 값.
  • yong_el  — 조후 용신 오행 인덱스(火=1, 水=4). None 이면 조후 미결정.
  • rule_id  — 출처추적 rule_id (계절 분기별로 구분).
  • label    — claim/trace 에 쓰는 계절 한글 라벨.

오행 인덱스 규약(constants.py): 목0 화1 토2 금3 수4.
지지 인덱스 규약: 子0 丑1 寅2 卯3 辰4 巳5 午6 未7 申8 酉9 戌10 亥11.
"""
from __future__ import annotations

_HWA, _SU = 1, 4  # 火, 水

# 조후 미결정(환절기/온화) 공통 항목 — climate=None, yong_el=None.
_NONE = (None, None, "johu.transitional.none", "환절기")

# 월지 → (climate, yong_el, rule_id, label)
#   겨울 亥子丑(寒)  → 火 난방        ("johu.cold.warm")
#   여름 巳午未(暖燥) → 水 조후        ("johu.hot.cool")
#   戌(늦가을 건조·한기 시작)         → 火, 겨울에 준함 ("johu.late_autumn.warm")
#   辰(늦봄 습) 및 봄 寅卯·가을 申酉   → 미결정(None), 정책 체인 다음으로
JOHU_TABLE: dict[int, tuple[str | None, int | None, str, str]] = {
    11: ("한", _HWA, "johu.cold.warm", "겨울"),         # 亥
    0:  ("한", _HWA, "johu.cold.warm", "겨울"),         # 子
    1:  ("한", _HWA, "johu.cold.warm", "겨울"),         # 丑
    5:  ("난", _SU, "johu.hot.cool", "여름"),           # 巳
    6:  ("난", _SU, "johu.hot.cool", "여름"),           # 午
    7:  ("난", _SU, "johu.hot.cool", "여름"),           # 未
    10: ("한", _HWA, "johu.late_autumn.warm", "늦가을"),  # 戌 — 건조·한기 시작
    2:  _NONE,   # 寅 (이른 봄, 온화)
    3:  _NONE,   # 卯 (봄, 온화)
    4:  _NONE,   # 辰 (늦봄 습 — 조후 미결정)
    8:  _NONE,   # 申 (이른 가을, 온화)
    9:  _NONE,   # 酉 (가을, 온화)
}
