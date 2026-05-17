import uuid

import numpy as np
import pytest

from probe.data_classes import Chunk, Document, IngestResult


# ---------- helpers ----------

def _vec(*components: float, dim: int = 4) -> np.ndarray:
    """Build a deterministic float32 vector for tests. Use .tobytes() for chunk storage."""
    arr = np.zeros(dim, dtype=np.float32)
    for i, v in enumerate(components):
        arr[i] = v
    return arr


def _doc(**overrides) -> Document:
    base = dict(
        id=str(uuid.uuid4()),
        source_type="web",
        source_url="https://example.com/post",
        title="Example",
        author="Tester",
        published_at=None,
        accessed_at="2026-05-17T00:00:00Z",
        description=None,
        raw_path=None,
        metadata={},
    )
    base.update(overrides)
    return Document(**base)


def _chunk(document_id: str, content: str, *, chunk_index: int = 0,
           embedding: bytes | None = None, section: str | None = None) -> Chunk:
    return Chunk(
        id=str(uuid.uuid4()),
        document_id=document_id,
        content=content,
        section=section,
        chunk_index=chunk_index,
        metadata={},
        embedding=embedding,
    )


def _persist(conn, doc: Document, chunks: list[Chunk]) -> None:
    from probe.db import persist

    persist(conn, IngestResult(document=doc, chunks=chunks))


# ---------- vector_search ----------

def test_vector_search_ranks_by_cosine_similarity(db):
    from probe.search import vector_search

    doc = _doc()
    near = _chunk(doc.id, "near chunk", chunk_index=0, embedding=_vec(1.0, 0.0, 0.0, 0.0).tobytes())
    orthogonal = _chunk(doc.id, "orthogonal chunk", chunk_index=1, embedding=_vec(0.0, 1.0, 0.0, 0.0).tobytes())
    opposite = _chunk(doc.id, "opposite chunk", chunk_index=2, embedding=_vec(-1.0, 0.0, 0.0, 0.0).tobytes())
    _persist(db, doc, [near, orthogonal, opposite])

    results = vector_search(db, _vec(1.0, 0.0, 0.0, 0.0), limit=3)

    assert len(results) == 3
    assert results[0].chunk_id == near.id
    assert results[-1].chunk_id == opposite.id


def test_vector_search_respects_limit(db):
    from probe.search import vector_search

    doc = _doc()
    chunks = [
        _chunk(doc.id, f"c{i}", chunk_index=i, embedding=_vec(1.0 - i * 0.1, 0.0, 0.0, 0.0).tobytes())
        for i in range(5)
    ]
    _persist(db, doc, chunks)

    results = vector_search(db, _vec(1.0, 0.0, 0.0, 0.0), limit=2)
    assert len(results) == 2


def test_vector_search_on_empty_db_returns_empty(db):
    from probe.search import vector_search

    results = vector_search(db, _vec(1.0, 0.0, 0.0, 0.0), limit=5)
    assert results == []


def test_vector_search_skips_chunks_without_embedding(db):
    from probe.search import vector_search

    doc = _doc()
    has_emb = _chunk(doc.id, "has embedding", chunk_index=0, embedding=_vec(1.0, 0.0, 0.0, 0.0).tobytes())
    no_emb = _chunk(doc.id, "no embedding", chunk_index=1, embedding=None)
    _persist(db, doc, [has_emb, no_emb])

    results = vector_search(db, _vec(1.0, 0.0, 0.0, 0.0), limit=10)
    returned_ids = {r.chunk_id for r in results}
    assert has_emb.id in returned_ids
    assert no_emb.id not in returned_ids


def test_vector_search_result_carries_doc_and_content(db):
    from probe.search import vector_search

    doc = _doc(title="The Title")
    chunk = _chunk(doc.id, "the body text", chunk_index=0, embedding=_vec(1.0, 0.0, 0.0, 0.0).tobytes())
    _persist(db, doc, [chunk])

    [result] = vector_search(db, _vec(1.0, 0.0, 0.0, 0.0), limit=1)
    assert result.chunk_id == chunk.id
    assert result.document_id == doc.id
    assert result.content == "the body text"


# ---------- fts_search ----------

def test_fts_search_matches_keyword(db):
    from probe.search import fts_search

    doc = _doc()
    chunks = [
        _chunk(doc.id, "Palantir bull case strong moat", chunk_index=0),
        _chunk(doc.id, "unrelated chunk about cats", chunk_index=1),
    ]
    _persist(db, doc, chunks)

    results = fts_search(db, "palantir", limit=5)
    assert len(results) == 1
    assert results[0].chunk_id == chunks[0].id


def test_fts_search_ranks_more_relevant_higher(db):
    from probe.search import fts_search

    doc = _doc()
    chunks = [
        _chunk(doc.id, "Palantir Palantir Palantir analysis", chunk_index=0),
        _chunk(doc.id, "Palantir mentioned briefly here", chunk_index=1),
    ]
    _persist(db, doc, chunks)

    results = fts_search(db, "palantir", limit=5)
    assert len(results) == 2
    assert results[0].chunk_id == chunks[0].id


def test_fts_search_returns_empty_on_no_match(db):
    from probe.search import fts_search

    doc = _doc()
    _persist(db, doc, [_chunk(doc.id, "nothing relevant here")])

    results = fts_search(db, "cryptocurrency", limit=5)
    assert results == []


def test_fts_search_respects_limit(db):
    from probe.search import fts_search

    doc = _doc()
    chunks = [_chunk(doc.id, f"palantir item {i}", chunk_index=i) for i in range(5)]
    _persist(db, doc, chunks)

    results = fts_search(db, "palantir", limit=2)
    assert len(results) == 2


def test_fts_search_on_empty_db_returns_empty(db):
    from probe.search import fts_search

    assert fts_search(db, "anything", limit=5) == []


def test_fts_search_handles_hyphenated_query(db):
    # FTS5 treats '-' as the NOT operator on a bare term; user queries
    # containing hyphenated words ("old-timers") must not be interpreted that way.
    from probe.search import fts_search

    doc = _doc()
    chunks = [
        _chunk(doc.id, "the old-timers voted guilty", chunk_index=0),
        _chunk(doc.id, "unrelated content here", chunk_index=1),
    ]
    _persist(db, doc, chunks)

    results = fts_search(db, "old-timers voted guilty", limit=5)
    assert len(results) >= 1
    assert results[0].chunk_id == chunks[0].id


def test_fts_search_does_not_crash_on_fts5_metacharacters(db):
    # Each query below would raise sqlite3.OperationalError if passed raw to MATCH.
    from probe.search import fts_search

    doc = _doc()
    _persist(db, doc, [_chunk(doc.id, "hello world")])

    for query in ['"unterminated', "foo:bar", "foo*bar", "(parens)", "a AND b"]:
        result = fts_search(db, query, limit=5)
        assert isinstance(result, list)


def test_fts_search_returns_empty_on_blank_query(db):
    # An empty MATCH expression is itself a syntax error in FTS5; blank input is a no-op.
    from probe.search import fts_search

    doc = _doc()
    _persist(db, doc, [_chunk(doc.id, "anything")])

    assert fts_search(db, "", limit=5) == []
    assert fts_search(db, "   ", limit=5) == []


# ---------- rrf_merge ----------

def test_rrf_merge_ranks_overlap_above_unique():
    from probe.data_classes import SearchResult
    from probe.search import rrf_merge

    a = SearchResult(chunk_id="a", document_id="d", content="a", score=0.0)
    b = SearchResult(chunk_id="b", document_id="d", content="b", score=0.0)
    c = SearchResult(chunk_id="c", document_id="d", content="c", score=0.0)

    # 'b' appears in both ranked lists; 'a' and 'c' only in one each.
    vector_results = [a, b]
    fts_results = [c, b]

    merged = rrf_merge([vector_results, fts_results], limit=3)
    assert merged[0].chunk_id == "b"
    assert {r.chunk_id for r in merged} == {"a", "b", "c"}


def test_rrf_merge_assigns_higher_score_to_higher_ranked_items():
    from probe.data_classes import SearchResult
    from probe.search import rrf_merge

    items = [SearchResult(chunk_id=str(i), document_id="d", content=str(i), score=0.0) for i in range(3)]
    merged = rrf_merge([items], limit=3)

    assert merged[0].chunk_id == "0"
    assert merged[0].score > merged[1].score > merged[2].score


def test_rrf_merge_handles_empty_lists():
    from probe.search import rrf_merge

    assert rrf_merge([], limit=5) == []
    assert rrf_merge([[], []], limit=5) == []


def test_rrf_merge_respects_limit():
    from probe.data_classes import SearchResult
    from probe.search import rrf_merge

    items = [SearchResult(chunk_id=str(i), document_id="d", content=str(i), score=0.0) for i in range(10)]
    merged = rrf_merge([items], limit=3)
    assert len(merged) == 3


def test_rrf_merge_deduplicates_across_lists():
    from probe.data_classes import SearchResult
    from probe.search import rrf_merge

    shared = SearchResult(chunk_id="shared", document_id="d", content="x", score=0.0)
    merged = rrf_merge([[shared], [shared]], limit=5)
    assert len(merged) == 1
    assert merged[0].chunk_id == "shared"


# ---------- hybrid_search (integration) ----------

@pytest.fixture
def populated_db(db):
    """A small corpus with real embeddings — exercises the full hybrid path."""
    from probe.embeddings import embed, to_blob

    doc = _doc(title="Palantir bull case")
    chunks = [
        _chunk(doc.id, "Palantir has a strong moat in government data analytics",
               chunk_index=0, embedding=to_blob(embed("Palantir has a strong moat in government data analytics"))),
        _chunk(doc.id, "Quarterly earnings exceeded analyst expectations",
               chunk_index=1, embedding=to_blob(embed("Quarterly earnings exceeded analyst expectations"))),
        _chunk(doc.id, "A kitten sleeping on a soft rug",
               chunk_index=2, embedding=to_blob(embed("A kitten sleeping on a soft rug"))),
    ]
    _persist(db, doc, chunks)
    return db, doc, chunks


def test_hybrid_search_returns_search_results(populated_db):
    from probe.data_classes import SearchResult
    from probe.search import hybrid_search

    conn, _, _ = populated_db
    results = hybrid_search(conn, "palantir moat", limit=3)

    assert len(results) > 0
    for r in results:
        assert isinstance(r, SearchResult)
        assert r.chunk_id
        assert r.document_id
        assert r.content
        assert isinstance(r.score, float)


def test_hybrid_search_top_result_matches_query_intent(populated_db):
    from probe.search import hybrid_search

    conn, _, chunks = populated_db
    palantir_chunk = chunks[0]

    results = hybrid_search(conn, "palantir moat government", limit=3)
    assert results[0].chunk_id == palantir_chunk.id


def test_hybrid_search_respects_limit(populated_db):
    from probe.search import hybrid_search

    conn, _, _ = populated_db
    results = hybrid_search(conn, "anything", limit=2)
    assert len(results) <= 2


def test_hybrid_search_on_empty_db_returns_empty(db):
    from probe.search import hybrid_search

    assert hybrid_search(db, "anything", limit=5) == []
