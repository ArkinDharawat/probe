from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

import pytest

from probe import analysis as analysis_mod
from probe.analysis import (
    ANALYZE_PROMPT_VERSION,
    ANALYZE_SCHEMA,
    _ANALYZE_PROMPT_PATH,
    _NO_CONTEXT_MARKER,
    analyze,
)
from probe.data_classes import SearchResult


def seed_doc(conn, doc_id, source_type="arxiv_paper", title="Doc", source_url="http://x"):
    conn.execute(
        "INSERT INTO documents (id, source_type, source_url, title, author, "
        "published_at, accessed_at, description, raw_path, metadata) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            doc_id,
            source_type,
            source_url,
            title,
            None,
            None,
            datetime.now(timezone.utc).isoformat(),
            None,
            None,
            json.dumps({}),
        ),
    )
    conn.commit()


def seed_extraction(conn, doc_id, extraction_type="paper", output=None, created_at=None):
    if output is None:
        output = {
            "claimed_contribution": "We propose BERT.",
            "method_summary": "Bidirectional transformer.",
        }
    if created_at is None:
        created_at = datetime.now(timezone.utc).isoformat()
    extraction_id = str(uuid.uuid4())
    conn.execute(
        "INSERT INTO extractions (id, document_id, extraction_type, output, "
        "prompt_version, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (
            extraction_id,
            doc_id,
            extraction_type,
            json.dumps(output),
            "v1",
            created_at,
        ),
    )
    conn.commit()
    return extraction_id


def _valid_llm_result():
    return {
        "connections": ["a connects to b"],
        "new_information": ["new fact"],
        "contradictions": [],
        "open_questions": ["what next?"],
    }


def _patch_search(monkeypatch, results, capture=None):
    def fake(conn, query, limit):
        if capture is not None:
            capture["query"] = query
            capture["limit"] = limit
        return results

    monkeypatch.setattr(analysis_mod, "hybrid_search", fake)


def _patch_llm(monkeypatch, result=None, capture=None):
    if result is None:
        result = _valid_llm_result()

    def fake(*args, **kwargs):
        if capture is not None:
            capture["args"] = args
            capture["kwargs"] = kwargs
        return result

    monkeypatch.setattr(analysis_mod, "structured_call", fake)


def test_raises_when_no_extraction(db, monkeypatch):
    doc_id = "doc-1"
    seed_doc(db, doc_id)
    _patch_search(monkeypatch, [])
    _patch_llm(monkeypatch)

    with pytest.raises(RuntimeError, match="extract"):
        analyze(db, doc_id)


def test_uses_claimed_contribution_for_paper(db, monkeypatch):
    doc_id = "doc-1"
    seed_doc(db, doc_id)
    seed_extraction(
        db,
        doc_id,
        extraction_type="paper",
        output={"claimed_contribution": "Bidirectional pretraining wins"},
    )
    captured = {}
    _patch_search(monkeypatch, [], capture=captured)
    _patch_llm(monkeypatch)

    analyze(db, doc_id)

    assert captured["query"] == "Bidirectional pretraining wins"


def test_uses_core_claim_for_financial(db, monkeypatch):
    doc_id = "doc-1"
    seed_doc(db, doc_id)
    seed_extraction(
        db,
        doc_id,
        extraction_type="financial",
        output={"core_claim": "Margins will expand."},
    )
    captured = {}
    _patch_search(monkeypatch, [], capture=captured)
    _patch_llm(monkeypatch)

    analyze(db, doc_id)

    assert captured["query"] == "Margins will expand."


def test_uses_main_topic_for_general(db, monkeypatch):
    doc_id = "doc-1"
    seed_doc(db, doc_id)
    seed_extraction(
        db,
        doc_id,
        extraction_type="general",
        output={"main_topic": "Rust async runtimes"},
    )
    captured = {}
    _patch_search(monkeypatch, [], capture=captured)
    _patch_llm(monkeypatch)

    analyze(db, doc_id)

    assert captured["query"] == "Rust async runtimes"


def test_filters_out_self_doc_chunks(db, monkeypatch):
    doc_id = "doc-1"
    other_id = "doc-2"
    seed_doc(db, doc_id)
    seed_doc(db, other_id, title="Other", source_url="http://other")
    seed_extraction(db, doc_id)

    self_results = [
        SearchResult(chunk_id=f"self-{i}", document_id=doc_id, content="x", score=0.9)
        for i in range(3)
    ]
    other_results = [
        SearchResult(chunk_id=f"other-{i}", document_id=other_id, content="y", score=0.8)
        for i in range(3)
    ]
    _patch_search(monkeypatch, self_results + other_results)
    _patch_llm(monkeypatch)

    analyze(db, doc_id)

    row = db.execute(
        "SELECT rag_context_ids FROM analyses WHERE document_id = ?", (doc_id,)
    ).fetchone()
    stored = json.loads(row[0])
    assert stored == ["other-0", "other-1", "other-2"]


def test_caps_context_at_top_5(db, monkeypatch):
    doc_id = "doc-1"
    other_id = "doc-2"
    seed_doc(db, doc_id)
    seed_doc(db, other_id, title="Other", source_url="http://other")
    seed_extraction(db, doc_id)

    results = [
        SearchResult(chunk_id=f"c-{i}", document_id=other_id, content="z", score=0.5)
        for i in range(10)
    ]
    _patch_search(monkeypatch, results)
    _patch_llm(monkeypatch)

    analyze(db, doc_id)

    row = db.execute(
        "SELECT rag_context_ids FROM analyses WHERE document_id = ?", (doc_id,)
    ).fetchone()
    stored = json.loads(row[0])
    assert stored == [f"c-{i}" for i in range(5)]


def test_no_context_marker_when_empty(db, monkeypatch):
    doc_id = "doc-1"
    seed_doc(db, doc_id)
    seed_extraction(db, doc_id)

    captured = {}
    _patch_search(monkeypatch, [])
    _patch_llm(monkeypatch, capture=captured)

    analyze(db, doc_id)

    assert _NO_CONTEXT_MARKER in captured["kwargs"]["prompt"]
    row = db.execute(
        "SELECT rag_context_ids FROM analyses WHERE document_id = ?", (doc_id,)
    ).fetchone()
    assert json.loads(row[0]) == []


def test_calls_structured_call_with_analyze_schema(db, monkeypatch):
    doc_id = "doc-1"
    seed_doc(db, doc_id)
    seed_extraction(db, doc_id)

    captured = {}
    _patch_search(monkeypatch, [])
    _patch_llm(monkeypatch, capture=captured)

    analyze(db, doc_id)

    assert captured["kwargs"]["output_schema"] is ANALYZE_SCHEMA


def test_calls_structured_call_with_system_from_file(db, monkeypatch):
    doc_id = "doc-1"
    seed_doc(db, doc_id)
    seed_extraction(db, doc_id)

    captured = {}
    _patch_search(monkeypatch, [])
    _patch_llm(monkeypatch, capture=captured)

    analyze(db, doc_id)

    assert captured["kwargs"]["system"] == _ANALYZE_PROMPT_PATH.read_text()


def test_context_includes_title_and_url(db, monkeypatch):
    doc_id = "doc-1"
    other_id = "doc-2"
    seed_doc(db, doc_id)
    seed_doc(db, other_id, title="Other", source_url="http://other")
    seed_extraction(db, doc_id)

    results = [
        SearchResult(chunk_id="c-1", document_id=other_id, content="body", score=0.5)
    ]
    captured = {}
    _patch_search(monkeypatch, results)
    _patch_llm(monkeypatch, capture=captured)

    analyze(db, doc_id)

    prompt = captured["kwargs"]["prompt"]
    assert "Other" in prompt
    assert "http://other" in prompt


def test_persists_analysis_row(db, monkeypatch):
    doc_id = "doc-1"
    seed_doc(db, doc_id)
    seed_extraction(db, doc_id)

    _patch_search(monkeypatch, [])
    _patch_llm(monkeypatch)

    before = db.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]
    analyze(db, doc_id)
    after = db.execute("SELECT COUNT(*) FROM analyses").fetchone()[0]
    assert after == before + 1

    row = db.execute(
        "SELECT connections, new_information, contradictions, open_questions, prompt_version "
        "FROM analyses WHERE document_id = ?",
        (doc_id,),
    ).fetchone()
    for i in range(4):
        json.loads(row[i])
    assert row[4] == ANALYZE_PROMPT_VERSION


def test_multiple_analyses_append(db, monkeypatch):
    doc_id = "doc-1"
    seed_doc(db, doc_id)
    seed_extraction(db, doc_id)

    _patch_search(monkeypatch, [])
    _patch_llm(monkeypatch)

    assert db.execute("SELECT COUNT(*) FROM analyses").fetchone()[0] == 0
    analyze(db, doc_id)
    assert db.execute("SELECT COUNT(*) FROM analyses").fetchone()[0] == 1
    analyze(db, doc_id)
    assert db.execute("SELECT COUNT(*) FROM analyses").fetchone()[0] == 2


def test_return_value_shape(db, monkeypatch):
    doc_id = "doc-1"
    seed_doc(db, doc_id)
    seed_extraction(db, doc_id)

    _patch_search(monkeypatch, [])
    _patch_llm(monkeypatch)

    result = analyze(db, doc_id)

    expected_keys = {
        "id",
        "document_id",
        "connections",
        "new_information",
        "contradictions",
        "open_questions",
        "rag_context_ids",
        "prompt_version",
        "created_at",
    }
    assert expected_keys <= set(result.keys())


def test_picks_latest_extraction(db, monkeypatch):
    doc_id = "doc-1"
    seed_doc(db, doc_id)
    earlier = "2025-01-01T00:00:00+00:00"
    later = "2025-06-01T00:00:00+00:00"
    seed_extraction(
        db,
        doc_id,
        extraction_type="paper",
        output={"claimed_contribution": "EARLIER"},
        created_at=earlier,
    )
    seed_extraction(
        db,
        doc_id,
        extraction_type="general",
        output={"main_topic": "LATER"},
        created_at=later,
    )

    captured = {}
    _patch_search(monkeypatch, [], capture=captured)
    _patch_llm(monkeypatch)

    analyze(db, doc_id)

    assert captured["query"] == "LATER"
