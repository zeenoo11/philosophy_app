"""L1 결정론 코어 (pillars-core) — 사주 8글자 + 파생 구조.

순수 결정론: 입력(생년월일시 + tz + 경도 + 이산 토글) → 출력(8글자, 지장간,
십신, 합충형파해, 십이운성, 신살). 해석(용신 등)은 이 레이어에 없다.

경계 처리 설계 (docs/SPEC.md §2.x 정합):
  • 년주·월주 = 절대 UTC 순간을 천문 절기(태양황경)와 직접 비교 → tz/진태양시
    토글과 무관(절기는 절대 순간). 입춘(λ=315°)에서 년이, 12절(節)에서 월이 바뀜.
  • 일주·시주 = '태양 벽시계'(진태양시 토글 적용) 기준. 야자시 규칙으로 일 경계 결정.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from engine import astro, constants as C, timeutil


# ─────────────────────────────────────────────────────────────────────────
# 설정 / 입력
# ─────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class DeterministicConfig:
    """프리셋의 deterministic 토글 — 출력 '글자'를 바꾸는 이산 선택."""
    sipiunseong_theory: str = "eumyang_sunyeok"      # 십이운성 이론
    woryulbunya_theory: str = "japyeongjinjeon"      # 지장간 월률분야
    jasi_rule: str = "yajasi_split"                  # 야자시 분리 | jasi_unified
    true_solar_time: bool = True                     # 진태양시(경도+균시차) 보정
    longitude_deg: float = 127.0                     # 출생지 경도(동경 양수)
    tz_name: str = "Asia/Seoul"


@dataclass(frozen=True)
class BirthInput:
    """민간 벽시계 기준 출생 정보."""
    year: int
    month: int
    day: int
    hour: int = 0
    minute: int = 0
    second: int = 0
    fold: int = 0  # DST 모호시각 해소 (기본 0)

    def naive(self) -> datetime:
        return datetime(self.year, self.month, self.day,
                        self.hour, self.minute, self.second)


# ─────────────────────────────────────────────────────────────────────────
# 기둥 / 차트
# ─────────────────────────────────────────────────────────────────────────
@dataclass(frozen=True)
class Pillar:
    position: str          # 년/월/일/시
    stem: int              # 천간 0..9
    branch: int            # 지지 0..11

    @property
    def gz60(self) -> int:
        return C.gz_from(self.stem, self.branch)

    @property
    def name(self) -> str:
        return C.CHEONGAN_HANGUL[self.stem] + C.JIJI_HANGUL[self.branch]

    @property
    def hanja(self) -> str:
        return C.CHEONGAN_HANJA[self.stem] + C.JIJI_HANJA[self.branch]

    def jijanggan(self, theory: str) -> list[tuple[int, str]]:
        return C.jijanggan(self.branch, theory)


@dataclass(frozen=True)
class Chart:
    year: Pillar
    month: Pillar
    day: Pillar
    hour: Pillar
    config: DeterministicConfig
    meta: dict = field(default_factory=dict)

    @property
    def day_master(self) -> int:
        """일간(日干) — 십신/용신의 기준."""
        return self.day.stem

    @property
    def pillars(self) -> tuple[Pillar, Pillar, Pillar, Pillar]:
        return (self.year, self.month, self.day, self.hour)

    # 결정론 파생 — '정답 있음' 영역만. 해석은 미포함.
    def sipsin_of(self, stem: int) -> str:
        return C.sipsin(self.day_master, stem)

    def stem_sipsin(self) -> dict[str, str]:
        """각 기둥 천간의 십신 (일간은 '일원')."""
        out = {}
        for p in self.pillars:
            out[p.position] = "일원" if p.position == "일" else C.sipsin(self.day_master, p.stem)
        return out

    def branch_jijanggan_sipsin(self) -> dict[str, list[tuple[str, str, str]]]:
        """각 지지 지장간의 (천간한글, 역할, 십신)."""
        theory = self.config.woryulbunya_theory
        out = {}
        for p in self.pillars:
            items = []
            for stem, role in C.jijanggan(p.branch, theory):
                items.append((C.CHEONGAN_HANGUL[stem], role, C.sipsin(self.day_master, stem)))
            out[p.position] = items
        return out

    def unseong(self) -> dict[str, str]:
        """일간 기준 각 지지의 십이운성."""
        theory = self.config.sipiunseong_theory
        return {p.position: C.sipiunseong(self.day_master, p.branch, theory)
                for p in self.pillars}

    def eight_chars(self) -> str:
        return " ".join(p.name for p in self.pillars)


# ─────────────────────────────────────────────────────────────────────────
# 율리우스일 / 일주
# ─────────────────────────────────────────────────────────────────────────
def julian_day_number(year: int, month: int, day: int) -> int:
    """그레고리력 (proleptic) 율리우스일수 (정오 기준 정수)."""
    a = (14 - month) // 12
    y = year + 4800 - a
    m = month + 12 * a - 3
    return (day + (153 * m + 2) // 5 + 365 * y + y // 4
            - y // 100 + y // 400 - 32045)


def day_gz60(year: int, month: int, day: int) -> int:
    """해당 (양력) 날짜의 일주 60갑자 인덱스.

    앵커: 2000-01-01 = 戊午(60-index 54). JDN(2000-01-01)=2451545,
    2451545 % 60 = 5 → 보정상수 49.  gz = (JDN + 49) % 60.
    (sxtwl 과 독립인 순수 캘린더 산술; 교차검증으로 전 구간 일치 확인)
    """
    return (julian_day_number(year, month, day) + 49) % 60


# ─────────────────────────────────────────────────────────────────────────
# 기둥 계산
# ─────────────────────────────────────────────────────────────────────────
def _year_pillar(t_utc: datetime) -> tuple[int, int, int, datetime]:
    """절대 UTC → (천간, 지지, 사주연도, 입춘시각). 입춘(λ=315°) 경계."""
    ipchun = astro.solar_term_time(t_utc.year, 3)   # 그 해 입춘
    saju_year = t_utc.year if t_utc >= ipchun else t_utc.year - 1
    stem = (saju_year - 4) % 10
    branch = (saju_year - 4) % 12
    return stem, branch, saju_year, ipchun


def _month_pillar(t_utc: datetime, year_stem: int) -> tuple[int, int, int]:
    """절대 UTC → (천간, 지지, 월지오프셋). 태양황경 band + 오호둔(五虎遁)."""
    lam = astro.solar_longitude_deg(t_utc)
    offset = int(((lam - 315.0) % 360.0) // 30.0)   # 0=寅 … 11=丑
    branch = (2 + offset) % 12
    # 오호둔: 寅월 천간 = (2*년간 + 2) % 10, 이후 월지 순서대로 +1
    stem = (2 * year_stem + 2 + offset) % 10
    return stem, branch, offset


def _hour_branch(solar_wall: datetime) -> int:
    """태양 벽시계 → 시지 (子=23:00–01:00)."""
    return ((solar_wall.hour + 1) // 2) % 12


def _effective_date(solar_wall: datetime, jasi_rule: str) -> datetime:
    """야자시 규칙에 따른 일주 산정용 '유효 날짜'."""
    if jasi_rule == "jasi_unified":
        # 일 경계 23:00 — 23시대(야자시)는 다음날 일주로 통합
        if solar_wall.hour >= 23:
            return (solar_wall + timedelta(days=1))
        return solar_wall
    # yajasi_split — 일 경계 00:00 (23–24시 야자시는 당일 일주 유지)
    return solar_wall


def _day_hour_pillars(t_utc: datetime, cfg: DeterministicConfig
                      ) -> tuple[int, int, int, int, datetime]:
    """(일간, 일지, 시간, 시지, 태양벽시계). 일·시는 태양 벽시계 기준."""
    solar_wall = timeutil.solar_wall_clock(
        t_utc, cfg.longitude_deg, cfg.true_solar_time, cfg.tz_name)
    hour_branch = _hour_branch(solar_wall)
    eff = _effective_date(solar_wall, cfg.jasi_rule)
    d_gz = day_gz60(eff.year, eff.month, eff.day)
    day_stem, day_branch = d_gz % 10, d_gz % 12
    # 오자둔(五子遁): 子시 천간 = (2*일간) % 10, 이후 시지 순서대로 +1
    hour_stem = (2 * day_stem + hour_branch) % 10
    return day_stem, day_branch, hour_stem, hour_branch, solar_wall


def compute_chart(birth: BirthInput, config: DeterministicConfig | None = None) -> Chart:
    """생년월일시 → 사주 8글자 차트 (L1 결정론)."""
    cfg = config or DeterministicConfig()
    t_utc = timeutil.civil_to_utc(birth.naive(), cfg.tz_name, birth.fold)

    y_stem, y_branch, saju_year, ipchun = _year_pillar(t_utc)
    m_stem, m_branch, m_off = _month_pillar(t_utc, y_stem)
    d_stem, d_branch, h_stem, h_branch, solar_wall = _day_hour_pillars(t_utc, cfg)

    meta = {
        "t_utc": t_utc,
        "solar_wall": solar_wall,
        "saju_year": saju_year,
        "ipchun_utc": ipchun,
        "solar_longitude": astro.solar_longitude_deg(t_utc),
        "month_offset": m_off,
        "utc_offset_hours": timeutil.utc_offset_hours(birth.naive(), cfg.tz_name, birth.fold),
    }
    return Chart(
        year=Pillar("년", y_stem, y_branch),
        month=Pillar("월", m_stem, m_branch),
        day=Pillar("일", d_stem, d_branch),
        hour=Pillar("시", h_stem, h_branch),
        config=cfg,
        meta=meta,
    )
