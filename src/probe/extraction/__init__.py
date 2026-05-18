import json
import uuid
from datetime import datetime, timezone
from typing import Any

from probe.extraction import paper, financial, general

_MODULES = {
    "paper": paper,
    "financial": financial,
    "general": general,
}

_ROUTING: dict[str, set[str]] = {
    "paper": {"paper", "arxiv_paper", "arxiv"},
    "financial": {"financial", "sec_filing", "10k", "10q", "earnings_call"},
}


def _route(source_type: str) -> str:
    for extraction_type, source_types in _ROUTING.items():
        if source_type in source_types:
            return extraction_type
    return "general"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def extract(conn, doc_id: str, *, extraction_type: str | None = None) -> dict[str, Any]:
    """Run domain-specific extraction on a document and upsert the result.

    Routing: if `extraction_type` is None, derive from doc.source_type via _ROUTING.
    Upsert key: (document_id, extraction_type). Re-running replaces the prior row's
    output, prompt_version, and created_at in place.

    Returns a dict: {"document_id", "extraction_type", "prompt_version",
    "created_at", "output"} where output is the extraction module's dict.
    """
    row = conn.execute(
        "SELECT source_type FROM documents WHERE id = ?", (doc_id,)
    ).fetchone()
    if row is None:
        raise KeyError(doc_id)
    source_type = row[0]

    resolved_type = extraction_type if extraction_type is not None else _route(source_type)
    if resolved_type not in _MODULES:
        raise ValueError(f"Unknown extraction_type: {resolved_type}")

    chunk_rows = conn.execute(
        "SELECT content FROM chunks WHERE document_id = ? ORDER BY chunk_index",
        (doc_id,),
    ).fetchall()
    joined = "\n\n".join(r[0] for r in chunk_rows)

    module = _MODULES[resolved_type]
    output = module.run(joined)
    prompt_version = module.PROMPT_VERSION
    created_at = _utc_now_iso()

    # `id` in VALUES is only used on insert; ON CONFLICT preserves the existing row id.
    conn.execute(
        """
        INSERT INTO extractions (id, document_id, extraction_type, output, prompt_version, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
        ON CONFLICT(document_id, extraction_type) DO UPDATE SET
            output=excluded.output,
            prompt_version=excluded.prompt_version,
            created_at=excluded.created_at
        """,
        (
            str(uuid.uuid4()),
            doc_id,
            resolved_type,
            json.dumps(output),
            prompt_version,
            created_at,
        ),
    )
    conn.commit()

    return {
        "document_id": doc_id,
        "extraction_type": resolved_type,
        "prompt_version": prompt_version,
        "created_at": created_at,
        "output": output,
    }
