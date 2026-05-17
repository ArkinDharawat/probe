from __future__ import annotations

import sqlite3

import numpy as np

from probe.data_classes import SearchResult
from probe.embeddings import embed

_RRF_K = 60


def vector_search(conn: sqlite3.Connection, query: np.ndarray, limit: int) -> list[SearchResult]:
    # NOTE: sqlite-vec's vec_distance_cosine raises if the query dim != stored chunk dim.
    # All production chunks are 384d (all-MiniLM-L6-v2); if you hit a dim-mismatch error,
    # something fed a non-384d vector through ingest. Fix the writer, not this query.
    query_bytes = query.astype(np.float32, copy=False).tobytes()
    rows = conn.execute(
        "SELECT id, document_id, content, vec_distance_cosine(embedding, ?) AS dist "
        "FROM chunks WHERE embedding IS NOT NULL "
        "ORDER BY dist ASC LIMIT ?",
        (query_bytes, limit),
    ).fetchall()
    return [
        SearchResult(chunk_id=row[0], document_id=row[1], content=row[2], score=1.0 - row[3])
        for row in rows
    ]


def fts_search(conn: sqlite3.Connection, query: str, limit: int) -> list[SearchResult]:
    rows = conn.execute(
        "SELECT c.id, c.document_id, c.content, bm25(chunks_fts) AS rank "
        "FROM chunks_fts JOIN chunks c ON c.rowid = chunks_fts.rowid "
        "WHERE chunks_fts MATCH ? ORDER BY rank ASC LIMIT ?",
        (query, limit),
    ).fetchall()
    return [
        SearchResult(chunk_id=row[0], document_id=row[1], content=row[2], score=-row[3])
        for row in rows
    ]


def rrf_merge(lists: list[list[SearchResult]], limit: int, k: int = _RRF_K) -> list[SearchResult]:
    fused: dict[str, tuple[SearchResult, float]] = {}
    for ranked_list in lists:
        for rank, result in enumerate(ranked_list, start=1):
            contribution = 1.0 / (k + rank)
            existing = fused.get(result.chunk_id)
            if existing is None:
                fused[result.chunk_id] = (result, contribution)
            else:
                fused[result.chunk_id] = (existing[0], existing[1] + contribution)

    merged = [
        SearchResult(
            chunk_id=result.chunk_id,
            document_id=result.document_id,
            content=result.content,
            score=score,
        )
        for result, score in fused.values()
    ]
    merged.sort(key=lambda r: r.score, reverse=True)
    return merged[:limit]


def hybrid_search(conn: sqlite3.Connection, query: str, limit: int) -> list[SearchResult]:
    query_vec = embed(query)
    vector_results = vector_search(conn, query_vec, limit)
    fts_results = fts_search(conn, query, limit)
    return rrf_merge([vector_results, fts_results], limit)
