"""L1 시간 처리 — IANA tz(역사 오프셋/서머타임) + 진태양시 보정.

⚠️ UTC+9 하드코딩 금지 (SPEC §3.1, §7). 한국 표준시는 역사적으로
   UTC+8:30 ↔ UTC+9 를 오갔고(대략 1908/1912/1954/1961 전후) 서머타임
   적용 연도(1948–51, 55–60, 87–88 등)도 있다. 이 모든 것은 IANA
   `Asia/Seoul` tz 데이터에 인코딩돼 있으므로 거기에 위임한다.
   진태양시(경도+균시차) 보정만 그 위에 추가로 얹는다.
"""
from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo

from engine import astro


def civil_to_utc(naive_local: datetime, tz_name: str = "Asia/Seoul",
                 fold: int = 0) -> datetime:
    """민간 벽시계(naive) + tz 이름 → UTC aware datetime.

    역사적 오프셋·서머타임은 zoneinfo(tzdata)가 처리한다. DST 전환의
    모호/비존재 시각은 fold 로 결정(기본 fold=0).
    """
    local = naive_local.replace(tzinfo=ZoneInfo(tz_name), fold=fold)
    return local.astimezone(timezone.utc)


def solar_wall_clock(t_utc: datetime, longitude_deg: float,
                     true_solar_time: bool, tz_name: str = "Asia/Seoul") -> datetime:
    """시주/일경계 판정에 쓰는 '태양 벽시계' (naive).

    true_solar_time=True  → 진태양시(LAST): UT + 경도/15h + 균시차.
                            경도 보정의 기준은 tz 의 실제 오프셋이 아니라
                            UT+경도 이므로 역사적 오프셋과 자동 정합.
    true_solar_time=False → 표준 zone 벽시계를 그대로 태양시로 간주(간이 모드).
    """
    if true_solar_time:
        return astro.true_solar_datetime(t_utc, longitude_deg)
    return t_utc.astimezone(ZoneInfo(tz_name)).replace(tzinfo=None)


def utc_offset_hours(naive_local: datetime, tz_name: str = "Asia/Seoul",
                     fold: int = 0) -> float:
    """해당 민간시각에 적용된 tz 오프셋(시간). 역사 검증용."""
    local = naive_local.replace(tzinfo=ZoneInfo(tz_name), fold=fold)
    off = local.utcoffset()
    return off.total_seconds() / 3600.0 if off else 0.0
