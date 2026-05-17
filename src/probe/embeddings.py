from __future__ import annotations

import numpy as np

_MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"
_DIM = 384

_model = None


def _get_model():
    global _model
    if _model is None:
        from sentence_transformers import SentenceTransformer

        _model = SentenceTransformer(_MODEL_NAME)
    return _model


def embed(text: str) -> np.ndarray:
    vec = _get_model().encode(text, convert_to_numpy=True)
    return vec.astype(np.float32, copy=False)


def embed_batch(texts: list[str]) -> np.ndarray:
    if not texts:
        return np.empty((0, _DIM), dtype=np.float32)
    matrix = _get_model().encode(texts, convert_to_numpy=True)
    return matrix.astype(np.float32, copy=False)


def to_blob(vec: np.ndarray) -> bytes:
    if vec.dtype != np.float32:
        raise ValueError(f"to_blob expected float32, got {vec.dtype}")
    return vec.tobytes()


def from_blob(blob: bytes) -> np.ndarray:
    return np.frombuffer(blob, dtype=np.float32)
