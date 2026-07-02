"""철학 그래프 노드 임베딩 사전계산 → philosophy/data/embeddings.npz.

실행:  uv run python scripts/build_philo_embeddings.py
대상:  unified_graph.json 의 claim/concept 노드 (~2,000개)
모델:  fastembed all-MiniLM-L6-v2 (PHILO_EMBED_MODEL 로 변경 가능 — 바꾸면 재실행 필수)

Docker 빌드에서 이 스크립트를 1회 실행해 모델 캐시와 npz 를 이미지에 베이크한다.
"""
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # 프로젝트 루트

from philosophy.embed import build_node_embeddings  # noqa: E402


def main() -> None:
    for stream in (sys.stdout, sys.stderr):  # Windows cp949 콘솔
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    t0 = time.perf_counter()
    info = build_node_embeddings()
    print(f"OK — {info['n']} nodes × {info['dim']}d ({info['model']}) "
          f"→ {info['path']}  [{time.perf_counter() - t0:.1f}s]")


if __name__ == "__main__":
    main()
