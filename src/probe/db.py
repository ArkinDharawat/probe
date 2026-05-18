from __future__ import annotations

import json
import os
import sqlite3
from typing import Union

import sqlite_vec

from probe.data_classes import IngestResult


_SCHEMA = """
CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    source_type TEXT NOT NULL,
    source_url TEXT,
    title TEXT,
    author TEXT,
    published_at TEXT,
    accessed_at TEXT NOT NULL,
    description TEXT,
    raw_path TEXT,
    metadata TEXT
);

CREATE TABLE IF NOT EXISTS chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id),
    content TEXT NOT NULL,
    section TEXT,
    chunk_index INTEGER,
    metadata TEXT,
    embedding BLOB
);

CREATE TABLE IF NOT EXISTS extractions (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id),
    extraction_type TEXT NOT NULL,
    output TEXT NOT NULL,
    prompt_version TEXT,
    created_at TEXT,
    UNIQUE(document_id, extraction_type)
);

CREATE TABLE IF NOT EXISTS analyses (
    id TEXT PRIMARY KEY,
    document_id TEXT NOT NULL REFERENCES documents(id),
    connections TEXT NOT NULL,
    new_information TEXT,
    contradictions TEXT,
    open_questions TEXT,
    rag_context_ids TEXT,
    prompt_version TEXT,
    created_at TEXT
);

CREATE TABLE IF NOT EXISTS theses (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    status TEXT DEFAULT 'active',
    core_claim TEXT NOT NULL,
    evidence TEXT,
    risks TEXT,
    last_evaluated TEXT,
    created_at TEXT,
    updated_at TEXT
);

CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(content);

CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN
    INSERT INTO chunks_fts(rowid, content) VALUES (new.rowid, new.content);
END;

CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN
    DELETE FROM chunks_fts WHERE rowid = old.rowid;
END;

CREATE TRIGGER IF NOT EXISTS chunks_au AFTER UPDATE ON chunks BEGIN
    UPDATE chunks_fts SET content = new.content WHERE rowid = old.rowid;
END;
"""


def connect(path: Union[str, "os.PathLike[str]"]) -> sqlite3.Connection:
    conn = sqlite3.connect(path)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    conn.execute("PRAGMA foreign_keys = ON")
    create_schema(conn)
    return conn


def create_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(_SCHEMA)
    conn.commit()


def persist(conn: sqlite3.Connection, result: IngestResult) -> None:
    doc = result.document
    conn.execute(
        "INSERT INTO documents (id, source_type, source_url, title, author, "
        "published_at, accessed_at, description, raw_path, metadata) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            doc.id,
            doc.source_type,
            doc.source_url,
            doc.title,
            doc.author,
            doc.published_at,
            doc.accessed_at,
            doc.description,
            doc.raw_path,
            json.dumps(doc.metadata or {}),
        ),
    )
    for chunk in result.chunks:
        conn.execute(
            "INSERT INTO chunks (id, document_id, content, section, chunk_index, "
            "metadata, embedding) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                chunk.id,
                chunk.document_id,
                chunk.content,
                chunk.section,
                chunk.chunk_index,
                json.dumps(chunk.metadata or {}),
                chunk.embedding,
            ),
        )
    conn.commit()
