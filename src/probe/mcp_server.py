from __future__ import annotations

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

    server.run(transport="stdio")
