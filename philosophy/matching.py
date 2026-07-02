"""철학 사상 매칭 + 사용자 간 유사도 — 결정론, 순수 파이썬.

legacy/src/distance.py (numpy + streamlit 캐시) 를 의존성 없이 포팅.
7축 벡터(0~10) 간 유클리드 거리를 선형 일치율로 환산한다:

    similarity = max(0, 1 - dist / D_MAX) * 100     (D_MAX = √(7·10²) ≈ 26.46)

legacy 의 1/(1+d)·100 공식은 거리 3에서 이미 25%로 떨어져 체감이 박했다 —
선형 환산은 '거의 같음 95% / 정반대 0%' 로 직관과 맞는다(근거: 축이 유한 범위).
"""
from __future__ import annotations

import csv
import math
from pathlib import Path

DATA_DIR = Path(__file__).parent / "data"
PHILO_CSV = DATA_DIR / "philo.csv"

#: 7축 순서 — philo.csv 컬럼·store 저장·분석 결과가 모두 이 순서를 따른다.
AXES = ["agency", "logic", "focus", "outlook", "time", "meta", "social"]

#: 축별 (왼쪽 극, 오른쪽 극, 표시 라벨) — 0점=왼쪽, 10점=오른쪽.
AXIS_LABELS = {
    "agency": ("운명·수용", "자유의지·능동", "Agency (주체성)"),
    "logic": ("감성·직관", "이성·논리", "Logic (판단 근거)"),
    "focus": ("나·개인", "모두·이타", "Focus (지향점)"),
    "outlook": ("비관·냉소", "낙관·진보", "Outlook (세계관)"),
    "time": ("과거·전통", "미래·진보", "Time (시간 지향)"),
    "meta": ("유물·물질", "영성·초월", "Meta (형이상학)"),
    "social": ("반항·비순응", "순응·질서", "Social (사회 동조)"),
}

_D_MAX = math.sqrt(len(AXES) * 10.0**2)  # ≈ 26.46
_cache: list[dict] | None = None


def load_philosophy_data(csv_path: Path | str = PHILO_CSV, *, refresh: bool = False) -> list[dict]:
    """philo.csv → [{'philosophy', 'scores': [7], 'summary', ...}] (모듈 캐시)."""
    global _cache
    if _cache is not None and not refresh and Path(csv_path) == PHILO_CSV:
        return _cache
    data: list[dict] = []
    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            data.append({
                "philosophy": row["philosophy"],
                "scores": [float(row[a]) for a in AXES],
                "summary": row["summary"],
                "core_keywords": row.get("core_keywords", ""),
                "positive_keywords": row.get("positive_keywords", ""),
                "negative_keywords": row.get("negative_keywords", ""),
            })
    if Path(csv_path) == PHILO_CSV:
        _cache = data
    return data


def similarity(a: list[float], b: list[float]) -> float:
    """두 7축 벡터의 일치율(0~100). 벡터 길이가 다르면 ValueError."""
    if len(a) != len(b):
        raise ValueError(f"axis length mismatch: {len(a)} != {len(b)}")
    dist = math.dist(a, b)
    return max(0.0, 1.0 - dist / _D_MAX) * 100.0


def find_matching_philosophies(user_scores: list[float],
                               csv_path: Path | str = PHILO_CSV) -> list[dict]:
    """사용자 7축 점수와 모든 사상의 일치율 — 내림차순 정렬."""
    results = []
    for item in load_philosophy_data(csv_path):
        rate = similarity(user_scores, item["scores"])
        results.append({
            "philosophy": item["philosophy"],
            "match_rate": rate,
            "summary": item["summary"],
            "core_keywords": item["core_keywords"],
        })
    results.sort(key=lambda x: x["match_rate"], reverse=True)
    return results


def rank_similar_users(my_scores: list[float],
                       others: list[dict]) -> list[dict]:
    """사용자 간 철학 유사도 랭킹 — '나와 닮은 영혼' (Graph-Project 의 연결 컨셉).

    others: [{'username', 'scores': [7], 'top_philosophy': str|None}, ...]
    반환: match_rate 내림차순 [{'username', 'match_rate', 'top_philosophy'}].
    """
    rows = []
    for o in others:
        rows.append({
            "username": o["username"],
            "match_rate": similarity(my_scores, o["scores"]),
            "top_philosophy": o.get("top_philosophy"),
        })
    rows.sort(key=lambda x: x["match_rate"], reverse=True)
    return rows
