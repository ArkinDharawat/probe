import json
import sqlite3
import uuid

import pytest

from probe.data_classes import Chunk, Document, IngestResult


def _make_document(
    doc_id: str | None = None,
    source_type: str = "web",
    source_url: str | None = "https://example.com/post",
    title: str | None = "Example Post",
    author: str | None = "Jane Doe",
    published_at: str | None = "2026-01-01",
    accessed_at: str = "2026-05-17T00:00:00Z",
    description: str | None = None,
    raw_path: str | None = None,
    metadata: dict | None = None,
) -> Document:
    return Document(
        id=doc_id or str(uuid.uuid4()),
        source_type=source_type,
        source_url=source_url,
        title=title,
        author=author,
        published_at=published_at,
        accessed_at=accessed_at,
        description=description,
        raw_path=raw_path,
        metadata=metadata if metadata is not None else {},
    )


def _make_chunk(
    document_id: str,
    chunk_id: str | None = None,
    content: str = "hello world",
    section: str | None = None,
    chunk_index: int = 0,
    metadata: dict | None = None,
    embedding: bytes | None = None,
) -> Chunk:
    return Chunk(
        id=chunk_id or str(uuid.uuid4()),
        document_id=document_id,
        content=content,
        section=section,
        chunk_index=chunk_index,
        metadata=metadata if metadata is not None else {},
        embedding=embedding,
    )


def _make_result(
    document: Document | None = None,
    chunks: list[Chunk] | None = None,
) -> IngestResult:
    doc = document or _make_document()
    if chunks is None:
        chunks = [_make_chunk(document_id=doc.id)]
    return IngestResult(document=doc, chunks=chunks)


def test_connect_creates_all_tables():
    from probe.db import connect

    conn = connect(":memory:")
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type IN ('table','view')"
        ).fetchall()
        names = {row[0] for row in rows}
        for expected in ("documents", "chunks", "extractions", "analyses", "theses", "chunks_fts"):
            assert expected in names, f"missing table: {expected} (got {names})"
    finally:
        conn.close()


def test_create_schema_is_idempotent():
    from probe.db import connect, create_schema

    conn = connect(":memory:")
    try:
        create_schema(conn)
        create_schema(conn)
    finally:
        conn.close()


def test_sqlite_vec_is_loaded():
    from probe.db import connect

    conn = connect(":memory:")
    try:
        version = conn.execute("SELECT vec_version()").fetchone()[0]
        assert version is not None
        assert isinstance(version, str)
        assert version != ""
    finally:
        conn.close()


def test_persist_writes_document_row(db):
    from probe.db import persist

    doc = _make_document(
        source_type="web",
        source_url="https://example.com/post",
        title="Example Post",
        author="Jane Doe",
    )
    persist(db, _make_result(document=doc, chunks=[_make_chunk(document_id=doc.id)]))

    row = db.execute(
        "SELECT id, source_type, source_url, title, author FROM documents WHERE id = ?",
        (doc.id,),
    ).fetchone()
    assert row is not None
    assert row[0] == doc.id
    assert row[1] == "web"
    assert row[2] == "https://example.com/post"
    assert row[3] == "Example Post"
    assert row[4] == "Jane Doe"


def test_persist_writes_chunks_linked_to_document(db):
    from probe.db import persist

    doc = _make_document()
    chunks = [
        _make_chunk(document_id=doc.id, content="first", chunk_index=0),
        _make_chunk(document_id=doc.id, content="second", chunk_index=1),
    ]
    persist(db, IngestResult(document=doc, chunks=chunks))

    rows = db.execute(
        "SELECT id, document_id, content, chunk_index FROM chunks WHERE document_id = ? ORDER BY chunk_index",
        (doc.id,),
    ).fetchall()
    assert len(rows) == 2
    assert rows[0][1] == doc.id
    assert rows[1][1] == doc.id
    assert rows[0][2] == "first"
    assert rows[1][2] == "second"


def test_persist_round_trips_metadata_json(db):
    from probe.db import persist

    doc = _make_document(metadata={"page_number": 3, "tag": "x"})
    chunk = _make_chunk(document_id=doc.id, metadata={"page_number": 3, "tag": "x"})
    persist(db, IngestResult(document=doc, chunks=[chunk]))

    doc_meta = db.execute(
        "SELECT metadata FROM documents WHERE id = ?", (doc.id,)
    ).fetchone()[0]
    chunk_meta = db.execute(
        "SELECT metadata FROM chunks WHERE id = ?", (chunk.id,)
    ).fetchone()[0]

    assert json.loads(doc_meta) == {"page_number": 3, "tag": "x"}
    assert json.loads(chunk_meta) == {"page_number": 3, "tag": "x"}


def test_persist_round_trips_embedding_blob(db):
    from probe.db import persist

    doc = _make_document()
    chunk = _make_chunk(document_id=doc.id, embedding=b"\x00\x01\x02\x03")
    persist(db, IngestResult(document=doc, chunks=[chunk]))

    stored = db.execute(
        "SELECT embedding FROM chunks WHERE id = ?", (chunk.id,)
    ).fetchone()[0]
    assert bytes(stored) == b"\x00\x01\x02\x03"


def test_chunks_fts_is_queryable_after_persist(db):
    from probe.db import persist

    doc = _make_document()
    chunk = _make_chunk(
        document_id=doc.id,
        content="Palantir bull case strong moat",
    )
    persist(db, IngestResult(document=doc, chunks=[chunk]))

    rows = db.execute(
        "SELECT content FROM chunks_fts WHERE chunks_fts MATCH 'palantir'"
    ).fetchall()
    assert len(rows) >= 1
    assert any("Palantir" in row[0] for row in rows)


def test_foreign_key_rejects_orphan_chunk(db):
    with pytest.raises(sqlite3.IntegrityError):
        db.execute(
            "INSERT INTO chunks (id, document_id, content, section, chunk_index, metadata, embedding) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), "no-such-doc", "orphan", None, 0, "{}", None),
        )
        db.commit()


def test_persist_with_zero_chunks_writes_only_document(db):
    from probe.db import persist

    doc = _make_document()
    persist(db, IngestResult(document=doc, chunks=[]))

    doc_row = db.execute(
        "SELECT id FROM documents WHERE id = ?", (doc.id,)
    ).fetchone()
    assert doc_row is not None
    assert doc_row[0] == doc.id

    chunk_count = db.execute(
        "SELECT COUNT(*) FROM chunks WHERE document_id = ?", (doc.id,)
    ).fetchone()[0]
    assert chunk_count == 0
