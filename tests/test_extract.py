from __future__ import annotations

import json
import uuid

import pytest

from probe.extraction import extract
from probe.extraction import paper as paper_mod


def seed_doc(conn, source_type: str, chunks: list[str] | None = None) -> str:
    doc_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO documents (id, source_type, source_url, title, author, "
        "published_at, accessed_at, description, raw_path, metadata) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            doc_id,
            source_type,
            "https://example.com",
            "Test Doc",
            None,
            None,
            "2026-01-01T00:00:00",
            None,
            None,
            "{}",
        ),
    )
    chunk_contents = chunks if chunks is not None else ["first chunk", "second chunk"]
    for i, content in enumerate(chunk_contents):
        conn.execute(
            "INSERT INTO chunks (id, document_id, content, section, chunk_index, "
            "metadata, embedding) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (str(uuid.uuid4()), doc_id, content, None, i, "{}", None),
        )
    conn.commit()
    return doc_id


def test_routes_arxiv_paper_to_paper(db, monkeypatch):
    calls = []

    def fake_run(content):
        calls.append(content)
        return {"title": "stub paper"}

    monkeypatch.setattr("probe.extraction.paper.run", fake_run)
    doc_id = seed_doc(db, "arxiv_paper")
    result = extract(db, doc_id)
    assert result["extraction_type"] == "paper"
    assert len(calls) == 1


def test_routes_sec_filing_to_financial(db, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "probe.extraction.financial.run",
        lambda content: calls.append(content) or {"company": "ACME"},
    )
    doc_id = seed_doc(db, "sec_filing")
    result = extract(db, doc_id)
    assert result["extraction_type"] == "financial"
    assert len(calls) == 1


def test_routes_substack_to_general(db, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "probe.extraction.general.run",
        lambda content: calls.append(content) or {"summary": "x"},
    )
    doc_id = seed_doc(db, "substack")
    result = extract(db, doc_id)
    assert result["extraction_type"] == "general"
    assert len(calls) == 1


def test_routes_unknown_to_general(db, monkeypatch):
    calls = []
    monkeypatch.setattr(
        "probe.extraction.general.run",
        lambda content: calls.append(content) or {"summary": "x"},
    )
    doc_id = seed_doc(db, "some_new_type")
    result = extract(db, doc_id)
    assert result["extraction_type"] == "general"
    assert len(calls) == 1


def test_explicit_extraction_type_overrides_routing(db, monkeypatch):
    paper_calls = []
    general_calls = []
    monkeypatch.setattr(
        "probe.extraction.paper.run",
        lambda content: paper_calls.append(content) or {"title": "p"},
    )
    monkeypatch.setattr(
        "probe.extraction.general.run",
        lambda content: general_calls.append(content) or {"summary": "g"},
    )
    doc_id = seed_doc(db, "arxiv_paper")
    result = extract(db, doc_id, extraction_type="general")
    assert result["extraction_type"] == "general"
    assert len(general_calls) == 1
    assert len(paper_calls) == 0


def test_explicit_invalid_extraction_type_raises(db):
    doc_id = seed_doc(db, "arxiv_paper")
    with pytest.raises(ValueError):
        extract(db, doc_id, extraction_type="bogus")


def test_missing_doc_raises_keyerror(db):
    with pytest.raises(KeyError):
        extract(db, "missing")


def test_persists_to_extractions_table(db, monkeypatch):
    stub = {"title": "stub", "value": 42}
    monkeypatch.setattr("probe.extraction.paper.run", lambda content: stub)
    doc_id = seed_doc(db, "arxiv_paper")
    extract(db, doc_id)

    count = db.execute(
        "SELECT COUNT(*) FROM extractions WHERE document_id = ?", (doc_id,)
    ).fetchone()[0]
    assert count == 1

    row = db.execute(
        "SELECT output, extraction_type, prompt_version FROM extractions "
        "WHERE document_id = ?",
        (doc_id,),
    ).fetchone()
    assert json.loads(row[0]) == stub
    assert row[1] == "paper"
    assert row[2] == paper_mod.PROMPT_VERSION


def test_rerun_upserts_in_place(db, monkeypatch):
    stubs = [{"v": 1}, {"v": 2}]
    iterator = iter(stubs)
    monkeypatch.setattr("probe.extraction.paper.run", lambda content: next(iterator))
    doc_id = seed_doc(db, "arxiv_paper")

    extract(db, doc_id)
    extract(db, doc_id)

    count = db.execute(
        "SELECT COUNT(*) FROM extractions WHERE document_id = ?", (doc_id,)
    ).fetchone()[0]
    assert count == 1

    output = db.execute(
        "SELECT output FROM extractions WHERE document_id = ?", (doc_id,)
    ).fetchone()[0]
    assert json.loads(output) == {"v": 2}


def test_rerun_preserves_row_id(db, monkeypatch):
    stubs = [{"v": 1}, {"v": 2}]
    iterator = iter(stubs)
    monkeypatch.setattr("probe.extraction.paper.run", lambda content: next(iterator))
    doc_id = seed_doc(db, "arxiv_paper")

    extract(db, doc_id)
    first_id = db.execute(
        "SELECT id FROM extractions WHERE document_id = ?", (doc_id,)
    ).fetchone()[0]

    extract(db, doc_id)
    second_id = db.execute(
        "SELECT id FROM extractions WHERE document_id = ?", (doc_id,)
    ).fetchone()[0]

    assert first_id == second_id


def test_concatenates_chunks_in_order(db, monkeypatch):
    captured: list[str] = []
    monkeypatch.setattr(
        "probe.extraction.paper.run",
        lambda content: captured.append(content) or {"ok": True},
    )
    doc_id = seed_doc(db, "arxiv_paper", chunks=["alpha", "bravo", "charlie"])
    extract(db, doc_id)
    assert captured == ["alpha\n\nbravo\n\ncharlie"]


def test_return_value_shape(db, monkeypatch):
    monkeypatch.setattr("probe.extraction.paper.run", lambda content: {"x": 1})
    doc_id = seed_doc(db, "arxiv_paper")
    result = extract(db, doc_id)
    assert set(result.keys()) == {
        "document_id",
        "extraction_type",
        "prompt_version",
        "created_at",
        "output",
    }
    assert result["document_id"] == doc_id
    assert result["prompt_version"] == paper_mod.PROMPT_VERSION
    assert result["output"] == {"x": 1}
