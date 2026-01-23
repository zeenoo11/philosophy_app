import numpy as np
import csv
import streamlit as st
from typing import List, Dict, Any
from src.config import PHILO_CSV_PATH

@st.cache_data
def load_philosophy_data(csv_path: str = PHILO_CSV_PATH) -> List[Dict[str, Any]]:
    """
    CSV 파일에서 사상 데이터를 한 번만 읽어와 캐싱합니다.
    """
    data = []
    try:
        with open(csv_path, mode='r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                data.append({
                    'philosophy': row['philosophy'],
                    'scores': [
                        float(row['agency']),
                        float(row['logic']),
                        float(row['focus']),
                        float(row['outlook'])
                    ],
                    'summary': row['summary']
                })
    except FileNotFoundError:
        print(f"Error: {csv_path} not found.")
    return data

def calculate_similarity(user_scores: List[float], philosophy_scores: List[float]) -> float:
    """
    사용자의 점수와 사상의 점수 사이의 유클리드 거리를 계산합니다.
    """
    u = np.array(user_scores)
    p = np.array(philosophy_scores)
    return float(np.linalg.norm(u - p))

def find_matching_philosophies(user_scores: List[float], csv_path: str = PHILO_CSV_PATH) -> List[Dict[str, Any]]:
    """
    캐싱된 데이터를 사용하여 사용자와의 일치도를 계산하여 정렬합니다.
    """
    data = load_philosophy_data(csv_path)
    results = []
    
    for item in data:
        dist = calculate_similarity(user_scores, item['scores'])
        # 일치도 계산: 1 / (1 + 거리) * 100
        match_rate = (1 / (1 + dist)) * 100
        
        results.append({
            'philosophy': item['philosophy'],
            'distance': dist,
            'match_rate': match_rate,
            'summary': item['summary']
        })
    
    # 일치도가 높은 순(백분율 내림차순)으로 정렬
    results.sort(key=lambda x: x['match_rate'], reverse=True)
    return results
