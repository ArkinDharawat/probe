from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path

from probe.llm import structured_call
from probe.search import hybrid_search

_ALLOWED_UPDATE_FIELDS = {
    "name",
    "status",
    "core_claim",
    "evidence",
    "risks",
    "last_evaluated",
}

_JSON_FIELDS = {"evidence", "risks"}


# Indirected for monkeypatching in tests.
def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _dumps_or_none(value: list[str] | None) -> str | None:
    return None if value is None else json.dumps(value)


def _loads_or_none(value: str | None) -> list[str] | None:
    return None if value is None else json.loads(value)


def create_thesis(
    conn: sqlite3.Connection,
    name: str,
    core_claim: str,
    evidence: list[str] | None = None,
    risks: list[str] | None = None,
) -> str:
    tid = str(uuid.uuid4())
    now = _utc_now_iso()
    conn.execute(
        "INSERT INTO theses (id, name, status, core_claim, evidence, risks, "
        "last_evaluated, created_at, updated_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            tid,
            name,
            "active",
            core_claim,
            _dumps_or_none(evidence),
            _dumps_or_none(risks),
            None,
            now,
            now,
        ),
    )
    conn.commit()
    return tid


def get_thesis(conn: sqlite3.Connection, thesis_id: str) -> dict | None:
    row = conn.execute(
        "SELECT id, name, status, core_claim, evidence, risks, "
        "last_evaluated, created_at, updated_at FROM theses WHERE id = ?",
        (thesis_id,),
    ).fetchone()
    if row is None:
        return None
    return {
        "id": row[0],
        "name": row[1],
        "status": row[2],
        "core_claim": row[3],
        "evidence": _loads_or_none(row[4]),
        "risks": _loads_or_none(row[5]),
        "last_evaluated": row[6],
        "created_at": row[7],
        "updated_at": row[8],
    }


def list_theses(conn: sqlite3.Connection, status: str = "active") -> list[dict]:
    rows = conn.execute(
        "SELECT id, name, status, core_claim, evidence, risks, "
        "last_evaluated, created_at, updated_at FROM theses "
        "WHERE status = ? ORDER BY created_at DESC",
        (status,),
    ).fetchall()
    return [
        {
            "id": r[0],
            "name": r[1],
            "status": r[2],
            "core_claim": r[3],
            "evidence": _loads_or_none(r[4]),
            "risks": _loads_or_none(r[5]),
            "last_evaluated": r[6],
            "created_at": r[7],
            "updated_at": r[8],
        }
        for r in rows
    ]


def update_thesis(conn: sqlite3.Connection, thesis_id: str, **fields) -> None:
    bad = set(fields) - _ALLOWED_UPDATE_FIELDS
    if bad:
        raise ValueError(f"disallowed update fields: {sorted(bad)}")

    exists = conn.execute(
        "SELECT 1 FROM theses WHERE id = ?", (thesis_id,)
    ).fetchone()
    if exists is None:
        raise KeyError(thesis_id)

    assignments = []
    values: list = []
    for key, value in fields.items():
        assignments.append(f"{key} = ?")
        values.append(_dumps_or_none(value) if key in _JSON_FIELDS else value)

    assignments.append("updated_at = ?")
    values.append(_utc_now_iso())
    values.append(thesis_id)

    conn.execute(
        f"UPDATE theses SET {', '.join(assignments)} WHERE id = ?",
        values,
    )
    conn.commit()


EVALUATE_PROMPT_VERSION = "evaluate-v1"
EVALUATE_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["supported", "contradicted", "mixed", "insufficient_evidence"],
        },
        "reasoning": {"type": "string"},
        "supporting": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "chunk_id": {"type": "string"},
                    "document_id": {"type": "string"},
                    "quote": {"type": "string"},
                },
                "required": ["chunk_id", "document_id", "quote"],
            },
        },
        "contradicting": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "chunk_id": {"type": "string"},
                    "document_id": {"type": "string"},
                    "quote": {"type": "string"},
                },
                "required": ["chunk_id", "document_id", "quote"],
            },
        },
    },
    "required": ["verdict", "reasoning", "supporting", "contradicting"],
}

_NO_CHUNKS_MARKER = "(no chunks found in the personal knowledge base)"
_EVALUATE_PROMPT_PATH = (
    Path(__file__).resolve().parents[2] / "prompts" / "evaluate_thesis.md"
)


def _build_context(results) -> str:
    if not results:
        return _NO_CHUNKS_MARKER
    blocks = []
    for idx, r in enumerate(results, start=1):
        blocks.append(
            f"[{idx}] chunk_id={r.chunk_id} document_id={r.document_id}\n{r.content}"
        )
    return "\n\n".join(blocks)


def evaluate_thesis(conn: sqlite3.Connection, claim_or_id: str) -> dict:
    thesis = get_thesis(conn, claim_or_id)
    if thesis is not None:
        claim = thesis["core_claim"]
        thesis_id: str | None = thesis["id"]
    else:
        claim = claim_or_id
        thesis_id = None

    results = hybrid_search(conn, claim, 5)
    context = _build_context(results)

    user_prompt = f"THESIS CLAIM:\n{claim}\n\nRETRIEVED CONTEXT:\n{context}"
    system_prompt = _EVALUATE_PROMPT_PATH.read_text()

    llm_out = structured_call(
        prompt=user_prompt,
        output_schema=EVALUATE_SCHEMA,
        system=system_prompt,
    )

    if thesis_id is not None:
        update_thesis(conn, thesis_id, last_evaluated=_utc_now_iso())

    return {**llm_out, "thesis_id": thesis_id, "claim": claim}
