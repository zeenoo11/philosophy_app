"""이중 언어(KO/EN) 컨텍스트 + 사주 용어 사전 — 표시 경계 전용.

설계 원칙(중요):
  - 엔진 내부의 한국어 문자열(십신 '비견', 강약 '신강' 등)은 **정체성 키**다.
    로직·저장·테스트는 전부 한국어 키로 동작하고, 이 모듈은 **표시 직전**에만
    영어로 바꾼다. 내부 값을 영어로 바꾸는 순간 로직이 깨진다 — 절대 금지.
  - 언어는 contextvar 로 요청(핸들러) 단위 격리 — 기본 "ko" 이므로 기존
    테스트·KO 경로는 이 모듈이 없던 때와 완전히 동일하게 동작한다.
  - Chainlit 의 cl.make_async 는 워커 스레드에서 도는데 contextvar 전파를
    보장하지 않으므로, 서비스 계층은 with_lang(fn, lang) 으로 감싸 넘긴다.

사용:
  from engine import i18n
  from engine.i18n import t, term
  t("안녕", "Hello")          # 현재 언어에 맞는 쪽
  term("비견")                # ko→'비견', en→'Friend' (사전 없으면 원문)
  i18n.ganji_en("병오")       # 'Byeong-o' (간지 로마자)
"""
from __future__ import annotations

from contextvars import ContextVar

_LANG: ContextVar[str] = ContextVar("saju_lang", default="ko")

KO, EN = "ko", "en"


def set_lang(lang: str | None) -> None:
    """언어 설정 — 'en' 외의 모든 값(None 포함)은 'ko'."""
    _LANG.set(EN if lang == EN else KO)


def get_lang() -> str:
    return _LANG.get()


def is_en() -> bool:
    return _LANG.get() == EN


def t(ko: str, en: str) -> str:
    """현재 언어의 문자열. 표시 시점에 호출할 것(모듈 상수로 굽지 말 것)."""
    return en if is_en() else ko


def with_lang(fn, lang: str):
    """cl.make_async 등 스레드 경계 너머로 언어를 갖고 들어가는 래퍼.

    contextvar 는 스레드 전파가 보장되지 않으므로, 워커에서 실행될 함수를
    이걸로 감싸면 함수 시작 시점에 해당 스레드의 언어를 맞춘다.
    """
    def _wrapped(*args, **kwargs):
        set_lang(lang)
        return fn(*args, **kwargs)
    return _wrapped


# ─────────────────────────────────────────────────────────────────────────
# 용어 사전 — 한국어 정체성 키 → 영어 표기 (영어권 BaZi 표준 용어 계열)
# ─────────────────────────────────────────────────────────────────────────
TERM_EN: dict[str, str] = {
    # 십신(十神)
    "비견": "Friend", "겁재": "Rob Wealth", "식신": "Eating God", "상관": "Hurting Officer",
    "편재": "Indirect Wealth", "정재": "Direct Wealth", "편관": "Seven Killings",
    "정관": "Direct Officer", "편인": "Indirect Resource", "정인": "Direct Resource",
    "일원": "Day Master",
    # 십신 가족(육친 묶음)
    "비겁": "Companions", "식상": "Output", "재성": "Wealth", "관성": "Authority",
    "인성": "Resource",
    # 강약 — 그라운딩 검사에 쓰이므로 세 라벨 모두 '... Day Master' 로 구분성 확보
    "신강": "Strong Day Master", "신약": "Weak Day Master", "중화": "Balanced Day Master",
    # 오행
    "목": "Wood", "화": "Fire", "토": "Earth", "금": "Metal", "수": "Water",
    # 십이운성
    "장생": "Birth", "목욕": "Bath", "관대": "Coming-of-Age", "건록": "Thriving",
    "제왕": "Peak", "쇠": "Decline", "병": "Sickness", "사": "Death", "묘": "Tomb",
    "절": "Severed", "태": "Conception", "양": "Nurture",
    # 십이신살
    "겁살": "Robbery Star", "재살": "Disaster Star", "천살": "Heaven Star",
    "지살": "Earth Star", "년살": "Year Star", "월살": "Month Star",
    "망신": "Disgrace Star", "장성": "General Star", "반안": "Saddle Star",
    "역마": "Travel Horse", "육해": "Six Harms", "화개": "Canopy Star",
    # 주요 신살 (luck.py 는 단축형 '문창'·'천을' 로도 내보낸다 — 둘 다 수록)
    "천을귀인": "Heavenly Noble", "천을": "Heavenly Noble",
    "문창귀인": "Scholar Star", "문창": "Scholar Star", "양인": "Goat Blade",
    "도화": "Peach Blossom", "공망": "Void", "괴강": "Kuigang", "백호": "White Tiger",
    "현침": "Needle Star", "귀문": "Ghost Gate", "천덕귀인": "Heaven Virtue Noble",
    "월덕귀인": "Month Virtue Noble", "금여": "Golden Carriage",
    # 관계(합충형파해)
    "합": "combine", "충": "clash", "형": "punishment", "파": "break", "해": "harm",
    "삼합": "three-harmony", "방합": "directional combine", "육합": "six-harmony",
    "원진": "grudge",
    # 길흉
    "길": "auspicious", "흉": "inauspicious", "평": "neutral",
    "대길": "very auspicious", "대흉": "very inauspicious",
    # 지지 띠 동물
    "쥐": "Rat", "소": "Ox", "호랑이": "Tiger", "토끼": "Rabbit", "용": "Dragon",
    "뱀": "Snake", "말": "Horse", "미양": "Goat", "원숭이": "Monkey", "닭": "Rooster",
    "개": "Dog", "돼지": "Pig",
    # 용신 취용 정책
    "억부": "Eokbu (strength-balancing)", "조후": "Johu (climate)",
    "병약": "Byeongyak (remedy)", "전왕": "Jeonwang (dominant)",
    "통관": "Tongwan (mediating)",
    # 지장간 역할
    "여기": "lingering qi", "중기": "middle qi", "정기": "principal qi",
    # 달력·기타
    "양력": "solar", "음력": "lunar", "윤달": "leap month",
    "남": "Male", "여": "Female",
    "년": "Year", "월": "Month", "일": "Day", "시": "Hour",
    "년주": "Year Pillar", "월주": "Month Pillar", "일주": "Day Pillar", "시주": "Hour Pillar",
    "천간": "Heavenly Stem", "지지": "Earthly Branch", "십신": "Ten Gods",
    "순행": "forward", "역행": "reverse",
}
# '양(Goat 띠)'은 십이운성 '양(Nurture)'과 키가 겹쳐 '미양' 별칭으로 수록 —
# 띠 표시는 zodiac_en() 을 쓰면 안전하다.

_ZODIAC_EN = ("Rat", "Ox", "Tiger", "Rabbit", "Dragon", "Snake",
              "Horse", "Goat", "Monkey", "Rooster", "Dog", "Pig")
_ZODIAC_KO = ("쥐", "소", "호랑이", "토끼", "용", "뱀", "말", "양", "원숭이", "닭", "개", "돼지")


def zodiac_en(animal_ko: str) -> str:
    """띠 동물 한국어 → 영어 ('양' 충돌 없이)."""
    try:
        return _ZODIAC_EN[_ZODIAC_KO.index(animal_ko)]
    except ValueError:
        return animal_ko


def term(ko: str) -> str:
    """용어 표시 — en 이면 사전 번역(없으면 원문), ko 면 원문 그대로."""
    if not is_en():
        return ko
    return TERM_EN.get(ko, ko)


# ─────────────────────────────────────────────────────────────────────────
# 간지 로마자 (Revised Romanization 기반, 지지 '신'은 Shin 으로 천간 Sin 과 구분)
# ─────────────────────────────────────────────────────────────────────────
_STEM_RR = {"갑": "Gap", "을": "Eul", "병": "Byeong", "정": "Jeong", "무": "Mu",
            "기": "Gi", "경": "Gyeong", "신": "Sin", "임": "Im", "계": "Gye"}
_BRANCH_RR = {"자": "ja", "축": "chuk", "인": "in", "묘": "myo", "진": "jin",
              "사": "sa", "오": "o", "미": "mi", "신": "shin", "유": "yu",
              "술": "sul", "해": "hae"}


def stem_en(stem_ko: str) -> str:
    """천간 한 글자 로마자 — '갑' → 'Gap'."""
    return _STEM_RR.get(stem_ko, stem_ko)


def branch_en(branch_ko: str) -> str:
    """지지 한 글자 로마자(대문자 시작) — '오' → 'O'."""
    rr = _BRANCH_RR.get(branch_ko, branch_ko)
    return rr[:1].upper() + rr[1:]


def ganji_en(ganji_ko: str) -> str:
    """두 글자 간지 로마자 — '병오' → 'Byeong-o'. 형식이 다르면 원문."""
    if len(ganji_ko) != 2:
        return ganji_ko
    s, b = ganji_ko[0], ganji_ko[1]
    if s not in _STEM_RR or b not in _BRANCH_RR:
        return ganji_ko
    return f"{_STEM_RR[s]}-{_BRANCH_RR[b]}"


# ─────────────────────────────────────────────────────────────────────────
# 유파(프리셋) 영어 표기 — presets/*.yaml 의 display_name/description 대응
# ─────────────────────────────────────────────────────────────────────────
PRESET_EN: dict[str, tuple[str, str]] = {
    # preset_id: (display_name_en, description_en)
    "jeongtong_eokbu": (
        "Classic Japyeong (Eokbu-centered)",
        "The most widely used Korean approach — judge Strong/Weak first, then pick the balancing (Eokbu) useful god."),
    "johu_centered": (
        "Johu (Climate-centered)",
        "Reads the chart by seasonal temperature — warming or cooling comes before strength balancing."),
    "jeonwang_tonggwan": (
        "Jeonwang · Tongwan (Dominant / Mediating)",
        "When one element dominates, follow it (Jeonwang); when two clash, mediate (Tongwan)."),
    "byeongyak_sinbong": (
        "Byeongyak (Remedy school)",
        "Finds the chart's 'illness' (excess/blockage) and treats the curing element as the useful god."),
    "sammyeong_gobeop": (
        "Sanming Classics (Traditional)",
        "Follows old classics — rich use of symbolic stars (Sinsal) and traditional elements."),
    "sinpa_dongsaeng": (
        "Modern (Sinpa)",
        "A modern reorganization — emphasizes flow and balance of qi."),
    "mangpa": (
        "Mangpa (Blind school)",
        "Mangpa lineage — direct reading of palace positions and Ten-God dynamics."),
}

# 간편 3종 메뉴 영어 라벨/설명 (reports.SIMPLE_PRESETS 대응)
SIMPLE_PRESET_EN: dict[str, tuple[str, str]] = {
    "jeongtong_eokbu": ("🌿 Standard (default)",
                        "The most common Korean method. Pick this if unsure."),
    "sinpa_dongsaeng": ("✨ Modern",
                        "A recently reorganized method — emphasizes flow and balance of energy."),
    "sammyeong_gobeop": ("📜 Traditional",
                         "Follows old classics, with rich traditional elements like symbolic stars."),
}


def preset_display_name(preset_id: str, ko_name: str) -> str:
    """유파 정식 이름 — en 이면 영어 병기 이름, 없으면 ko."""
    if is_en() and preset_id in PRESET_EN:
        return PRESET_EN[preset_id][0]
    return ko_name


def preset_description(preset_id: str, ko_desc: str) -> str:
    if is_en() and preset_id in PRESET_EN:
        return PRESET_EN[preset_id][1]
    return ko_desc
