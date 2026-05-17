import numpy as np


EXPECTED_DIM = 384  # all-MiniLM-L6-v2


def test_embed_returns_float32_vector_of_expected_dim():
    from probe.embeddings import embed

    vec = embed("hello world")
    assert isinstance(vec, np.ndarray)
    assert vec.dtype == np.float32
    assert vec.shape == (EXPECTED_DIM,)


def test_embed_is_deterministic():
    from probe.embeddings import embed

    a = embed("the quick brown fox")
    b = embed("the quick brown fox")
    assert np.array_equal(a, b)


def test_embed_empty_string_returns_valid_vector():
    from probe.embeddings import embed

    vec = embed("")
    assert vec.shape == (EXPECTED_DIM,)
    assert vec.dtype == np.float32
    assert np.isfinite(vec).all()


def test_embed_batch_returns_matrix_in_order():
    from probe.embeddings import embed, embed_batch

    texts = ["alpha", "beta", "gamma"]
    matrix = embed_batch(texts)

    assert isinstance(matrix, np.ndarray)
    assert matrix.dtype == np.float32
    assert matrix.shape == (3, EXPECTED_DIM)

    for i, text in enumerate(texts):
        assert np.array_equal(matrix[i], embed(text)), f"row {i} disagrees with single embed({text!r})"


def test_embed_batch_empty_list_returns_empty_matrix():
    from probe.embeddings import embed_batch

    matrix = embed_batch([])
    assert isinstance(matrix, np.ndarray)
    assert matrix.dtype == np.float32
    assert matrix.shape == (0, EXPECTED_DIM)


def test_to_blob_round_trips_through_from_blob():
    from probe.embeddings import embed, from_blob, to_blob

    original = embed("round trip me")
    blob = to_blob(original)
    restored = from_blob(blob)

    assert isinstance(blob, bytes)
    assert isinstance(restored, np.ndarray)
    assert restored.dtype == np.float32
    assert restored.shape == original.shape
    assert np.array_equal(original, restored)


def test_to_blob_emits_float32_bytes():
    from probe.embeddings import to_blob

    vec = np.arange(EXPECTED_DIM, dtype=np.float32)
    blob = to_blob(vec)
    assert isinstance(blob, bytes)
    assert len(blob) == EXPECTED_DIM * 4  # float32 = 4 bytes per element


def test_to_blob_rejects_non_float32():
    import pytest

    from probe.embeddings import to_blob

    vec_f64 = np.zeros(EXPECTED_DIM, dtype=np.float64)
    with pytest.raises((ValueError, TypeError)):
        to_blob(vec_f64)


def test_semantically_similar_texts_have_higher_cosine_than_unrelated():
    from probe.embeddings import embed

    def cosine(a: np.ndarray, b: np.ndarray) -> float:
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))

    cat = embed("a small domestic cat sat on the mat")
    kitten = embed("a tiny kitten sleeping on a rug")
    finance = embed("quarterly earnings exceeded analyst expectations")

    assert cosine(cat, kitten) > cosine(cat, finance)
