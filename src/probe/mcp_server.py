from __future__ import annotations

import json
import sqlite3
from typing import Any

from mcp.server.fastmcp import FastMCP

from probe.config import load
from probe.data_classes import Provenance
from probe.db import connect, persist
from probe.ingest import ingest
from probe.search import hybrid_search

_PROVENANCE_FIELDS = {"source_url", "title", "author", "raw_path", "accessed_at", "metadata"}


def _provenance_from_dict(data: dict[str, Any]) -> Provenance:
    fields = {k: v for k, v in data.items() if k in _PROVENANCE_FIELDS}
    return Provenance(**fields)


def handle_ingest(
    conn: sqlite3.Connection,
    content: str,
    provenance: dict[str, Any],
    source_type: str,
) -> dict[str, Any]:
    prov = _provenance_from_dict(provenance)
    result = ingest(content, prov, source_type)
    persist(conn, result)
    return {
        "document_id": result.document.id,
        "chunk_count": len(result.chunks),
        "title": result.document.title or None,
    }


# Convention: row access throughout this module uses positional indexing (r[0],
# r[1], ...) to match search.py and ingest.py. SELECT column order MUST match
# the unpacking order below. Do not switch to sqlite3.Row in isolation.
def handle_get_document(conn: sqlite3.Connection, doc_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT id, source_type, source_url, title, author, published_at, "
        "accessed_at, description, raw_path, metadata FROM documents WHERE id = ?",
        (doc_id,),
    ).fetchone()
    if row is None:
        return None

    doc = {
        "id": row[0],
        "source_type": row[1],
        "source_url": row[2],
        "title": row[3],
        "author": row[4],
        "published_at": row[5],
        "accessed_at": row[6],
        "description": row[7],
        "raw_path": row[8],
        "metadata": json.loads(row[9]) if row[9] else {},
    }

    chunks = [
        {
            "id": r[0],
            "section": r[1],
            "chunk_index": r[2],
            "content": r[3],
            "metadata": json.loads(r[4]) if r[4] else {},
        }
        for r in conn.execute(
            "SELECT id, section, chunk_index, content, metadata FROM chunks "
            "WHERE document_id = ? ORDER BY chunk_index",
            (doc_id,),
        ).fetchall()
    ]

    extractions = [
        {
            "id": r[0],
            "extraction_type": r[1],
            "output": json.loads(r[2]),
            "prompt_version": r[3],
            "created_at": r[4],
        }
        for r in conn.execute(
            "SELECT id, extraction_type, output, prompt_version, created_at "
            "FROM extractions WHERE document_id = ? ORDER BY created_at, id",
            (doc_id,),
        ).fetchall()
    ]

    analyses = [
        {
            "id": r[0],
            "connections": json.loads(r[1]),
            "new_information": json.loads(r[2]) if r[2] else [],
            "contradictions": json.loads(r[3]) if r[3] else [],
            "open_questions": json.loads(r[4]) if r[4] else [],
            "rag_context_ids": json.loads(r[5]) if r[5] else [],
            "prompt_version": r[6],
            "created_at": r[7],
        }
        for r in conn.execute(
            "SELECT id, connections, new_information, contradictions, open_questions, "
            "rag_context_ids, prompt_version, created_at "
            "FROM analyses WHERE document_id = ? ORDER BY created_at, id",
            (doc_id,),
        ).fetchall()
    ]

    return {"document": doc, "chunks": chunks, "extractions": extractions, "analyses": analyses}


def handle_search(conn: sqlite3.Connection, query: str, limit: int = 5) -> list[dict[str, Any]]:
    results = hybrid_search(conn, query, limit)
    return [
        {
            "chunk_id": r.chunk_id,
            "document_id": r.document_id,
            "content": r.content,
            "score": r.score,
        }
        for r in results
    ]


def run() -> None:
    config = load()
    # Single connection: stdio MCP is serial, so reuse avoids per-call open/close overhead.
    conn = connect(config.db_path)

    server = FastMCP(name="probe")

    @server.tool(
        name="ingest",
        description=(
            "Store a research source. Requires source_url or raw_path in provenance; "
            "tweet source_type also requires author."
        ),
    )
    def ingest_tool(content: str, provenance: dict, source_type: str) -> dict:
        return handle_ingest(conn, content, provenance, source_type)

    @server.tool(
        name="search_personal_knowledge",
        description="Hybrid vector + FTS search over ingested chunks.",
    )
    def search_tool(query: str, limit: int = 5) -> list[dict]:
        return handle_search(conn, query, limit)

    @server.tool(
        name="get_document",
        description=(
            "Retrieve a full document by ID, including all chunks, extractions, and analyses. "
            "Returns null if the document does not exist."
        ),
    )
    def get_document_tool(doc_id: str) -> dict | None:
        # None is serialized as JSON null by mcp>=1.0,<2 (pinned in pyproject.toml); do not relax that pin without revisiting the not-found contract.
        return handle_get_document(conn, doc_id)

    server.run(transport="stdio")
