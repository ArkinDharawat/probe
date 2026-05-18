from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from probe.llm import structured_call
from probe.search import hybrid_search


ANALYZE_PROMPT_VERSION = "analyze-v1"

ANALYZE_SCHEMA = {
    "type": "object",
    "properties": {
        "connections": {"type": "array", "items": {"type": "string"}},
        "new_information": {"type": "array", "items": {"type": "string"}},
        "contradictions": {"type": "array", "items": {"type": "string"}},
        "open_questions": {"type": "array", "items": {"type": "string"}},
    },
    "required": ["connections", "new_information", "contradictions", "open_questions"],
}

_QUERY_FIELDS = {
    "paper": "claimed_contribution",
    "financial": "core_claim",
    "general": "main_topic",
}

_NO_CONTEXT_MARKER = "(no other documents in the personal knowledge base)"

_ANALYZE_PROMPT_PATH = Path(__file__).resolve().parents[2] / "prompts" / "analyze.md"


def analyze(conn: sqlite3.Connection, doc_id: str) -> dict:
    row = conn.execute(
        "SELECT extraction_type, output FROM extractions "
        "WHERE document_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
        (doc_id,),
    ).fetchone()
    if row is None:
        raise RuntimeError(
            f"No extraction found for document {doc_id}; call extract() first"
        )

    extraction_type, output_json = row[0], row[1]
    output_dict = json.loads(output_json)

    field = _QUERY_FIELDS.get(extraction_type, "main_topic")
    query = output_dict.get(field)
    if not query:
        raise RuntimeError(
            f"Extraction for document {doc_id} is missing query field '{field}'"
        )

    raw_results = hybrid_search(conn, query, 10)
    surviving = [r for r in raw_results if r.document_id != doc_id][:5]

    if not surviving:
        context = _NO_CONTEXT_MARKER
    else:
        blocks = []
        for idx, r in enumerate(surviving, start=1):
            doc_row = conn.execute(
                "SELECT title, source_url FROM documents WHERE id = ?",
                (r.document_id,),
            ).fetchone()
            title = (doc_row[0] if doc_row and doc_row[0] else "(untitled)")
            url = (doc_row[1] if doc_row and doc_row[1] else "(no url)")
            blocks.append(
                f"[{idx}] title={title} url={url} chunk_id={r.chunk_id}\n{r.content}"
            )
        context = "\n\n".join(blocks)

    user_prompt = (
        "EXTRACTION OUTPUT (just-ingested document):\n"
        f"{json.dumps(output_dict, indent=2)}\n\n"
        "RELATED DOCUMENTS FROM EXISTING KNOWLEDGE:\n"
        f"{context}"
    )

    system_text = _ANALYZE_PROMPT_PATH.read_text()

    llm_result = structured_call(
        prompt=user_prompt,
        output_schema=ANALYZE_SCHEMA,
        system=system_text,
    )

    analysis_id = str(uuid.uuid4())
    created_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    rag_context_ids = [r.chunk_id for r in surviving]

    conn.execute(
        "INSERT INTO analyses (id, document_id, connections, new_information, "
        "contradictions, open_questions, rag_context_ids, prompt_version, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            analysis_id,
            doc_id,
            json.dumps(llm_result["connections"]),
            json.dumps(llm_result["new_information"]),
            json.dumps(llm_result["contradictions"]),
            json.dumps(llm_result["open_questions"]),
            json.dumps(rag_context_ids),
            ANALYZE_PROMPT_VERSION,
            created_at,
        ),
    )
    conn.commit()

    return {
        "id": analysis_id,
        "document_id": doc_id,
        "connections": llm_result["connections"],
        "new_information": llm_result["new_information"],
        "contradictions": llm_result["contradictions"],
        "open_questions": llm_result["open_questions"],
        "rag_context_ids": rag_context_ids,
        "prompt_version": ANALYZE_PROMPT_VERSION,
        "created_at": created_at,
    }
