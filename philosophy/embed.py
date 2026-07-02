"""임베딩 — fastembed(ONNX) 로 원본과 같은 all-MiniLM-L6-v2 를 torch 없이 실행.

원본(Graph-Project)은 sentence-transformers(torch)로 노드/쿼리를 임베딩했다.
플랫폼은 GNN 체크포인트 없이 텍스트 신호만 쓰므로, 같은 모델의 ONNX 포트로 대체한다.

노드 임베딩은 사전 계산(scripts/build_philo_embeddings.py → data/embeddings.npz)
하고, 런타임에는 쿼리만 임베딩한다. npz 에 모델명을 기록해 불일치를 감지한다.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import numpy as np

DATA_DIR = Path(__file__).parent / "data"
EMBEDDINGS_NPZ = DATA_DIR / "embeddings.npz"
DEFAULT_MODEL = os.environ.get("PHILO_EMBED_MODEL", "sentence-transformers/all-MiniLM-L6-v2")


@lru_cache(maxsize=1)
def _model():
    """fastembed TextEmbedding — 최초 1회 로드(모델 캐시는 ~/.cache/fastembed 또는
    FASTEMBED_CACHE_PATH). Docker 는 빌드 시 베이크(스크립트 1회 실행)."""
    from fastembed import TextEmbedding

    return TextEmbedding(DEFAULT_MODEL)


def encode(texts: list[str]) -> np.ndarray:
    """텍스트 → 정규화된 임베딩 행렬 (N, dim) float32. cosine = dot."""
    vecs = np.asarray(list(_model().embed(texts)), dtype=np.float32)
    norms = np.linalg.norm(vecs, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return vecs / norms


def build_node_embeddings(out_path: Path | str = EMBEDDINGS_NPZ, *,
                          batch: int = 256) -> dict:
    """그래프의 claim/concept 노드를 임베딩해 npz 로 저장 → 요약 dict."""
    from philosophy.graph import get_graph

    targets = get_graph().embed_targets()
    ids = [t[0] for t in targets]
    texts = [t[1] for t in targets]
    parts = [encode(texts[i:i + batch]) for i in range(0, len(texts), batch)]
    vectors = np.vstack(parts)
    np.savez_compressed(out_path, ids=np.array(ids, dtype=object),
                        vectors=vectors, model=np.array(DEFAULT_MODEL))
    return {"n": len(ids), "dim": int(vectors.shape[1]),
            "model": DEFAULT_MODEL, "path": str(out_path)}


@lru_cache(maxsize=1)
def load_node_embeddings() -> tuple[list[str], np.ndarray]:
    """사전 계산된 노드 임베딩 로드 → (ids, vectors). 모델 불일치 시 에러."""
    if not EMBEDDINGS_NPZ.exists():
        raise FileNotFoundError(
            f"{EMBEDDINGS_NPZ} 가 없습니다 — 먼저 실행: "
            "uv run python scripts/build_philo_embeddings.py")
    z = np.load(EMBEDDINGS_NPZ, allow_pickle=True)
    stored = str(z["model"])
    if stored != DEFAULT_MODEL:
        raise RuntimeError(
            f"임베딩 모델 불일치: npz={stored} / 설정={DEFAULT_MODEL} — "
            "scripts/build_philo_embeddings.py 로 재빌드하세요")
    return list(z["ids"]), np.asarray(z["vectors"], dtype=np.float32)


def top_k_similar(query_vec: np.ndarray, ids: list[str], vectors: np.ndarray,
                  k: int = 10) -> list[tuple[str, float]]:
    """정규화 벡터 기준 cosine top-k → [(node_id, score)]."""
    sims = vectors @ query_vec
    if k >= len(ids):
        order = np.argsort(-sims)
    else:
        part = np.argpartition(-sims, k)[:k]
        order = part[np.argsort(-sims[part])]
    return [(ids[i], float(sims[i])) for i in order[:k]]
