import pytest


# ---------- handle_ingest ----------

def test_handle_ingest_markdown_returns_doc_id_chunk_count_and_title(db, sample_md_text, sample_md_path):
    from probe.mcp_server import handle_ingest

    result = handle_ingest(
        db,
        content=sample_md_text,
        provenance={"raw_path": str(sample_md_path)},
        source_type="markdown",
    )

    assert isinstance(result, dict)
    assert isinstance(result["document_id"], str) and result["document_id"]
    assert result["chunk_count"] >= 1
    assert result["title"] == "Palantir Bull Case"


def test_handle_ingest_tweet_returns_single_chunk(db, tweet_url):
    from probe.mcp_server import handle_ingest

    result = handle_ingest(
        db,
        content="AI labs are leaking talent. The infra is the moat now.",
        provenance={"source_url": tweet_url, "author": "deedydas"},
        source_type="tweet",
    )

    assert result["chunk_count"] == 1


def test_handle_ingest_web_long_content_returns_multiple_chunks(db):
    from probe.mcp_server import handle_ingest

    paragraph = (
        "Artificial intelligence is reshaping the economics of software. "
        "Capital expenditure on GPU clusters keeps accelerating, and the "
        "hyperscalers continue to underwrite the buildout despite mounting "
        "questions about near-term return on invested capital. "
    )
    # 30 paragraphs * ~260 chars each ~= 7800 chars, well beyond the 1600-char chunk ceiling.
    long_content = "\n\n".join(f"{paragraph} Paragraph number {i}." for i in range(30))

    result = handle_ingest(
        db,
        content=long_content,
        provenance={"source_url": "https://example.com/long-post"},
        source_type="web",
    )

    assert result["chunk_count"] > 1


def test_handle_ingest_unknown_source_type_substack(db):
    from probe.mcp_server import handle_ingest

    result = handle_ingest(
        db,
        content="A short substack post body about markets.",
        provenance={"source_url": "https://example.substack.com/p/post"},
        source_type="substack",
    )

    assert isinstance(result["document_id"], str) and result["document_id"]
    assert result["chunk_count"] >= 1


def test_handle_ingest_missing_source_url_and_raw_path_raises(db):
    from probe.mcp_server import handle_ingest

    with pytest.raises(ValueError):
        handle_ingest(
            db,
            content="Some body",
            provenance={"title": "Orphaned"},
            source_type="web",
        )


def test_handle_ingest_tweet_missing_author_raises(db, tweet_url):
    from probe.mcp_server import handle_ingest

    with pytest.raises(ValueError):
        handle_ingest(
            db,
            content="A tweet body",
            provenance={"source_url": tweet_url},
            source_type="tweet",
        )


def test_handle_ingest_document_id_is_queryable(db, sample_md_text, sample_md_path):
    from probe.mcp_server import handle_ingest

    result = handle_ingest(
        db,
        content=sample_md_text,
        provenance={"raw_path": str(sample_md_path)},
        source_type="markdown",
    )

    row = db.execute(
        "SELECT id, source_type, title FROM documents WHERE id = ?",
        (result["document_id"],),
    ).fetchone()
    assert row is not None
    assert row[0] == result["document_id"]
    assert row[1] == "markdown"
    assert row[2] == "Palantir Bull Case"


def test_handle_ingest_chunk_count_matches_db_row_count(db, sample_md_text, sample_md_path):
    from probe.mcp_server import handle_ingest

    result = handle_ingest(
        db,
        content=sample_md_text,
        provenance={"raw_path": str(sample_md_path)},
        source_type="markdown",
    )

    (count,) = db.execute(
        "SELECT COUNT(*) FROM chunks WHERE document_id = ?",
        (result["document_id"],),
    ).fetchone()
    assert count == result["chunk_count"]


# ---------- handle_search ----------

def test_handle_search_empty_db_returns_empty_list(db):
    from probe.mcp_server import handle_search

    assert handle_search(db, "anything", limit=5) == []


def test_handle_search_returns_dicts_with_expected_keys(db):
    from probe.mcp_server import handle_ingest, handle_search

    handle_ingest(
        db,
        content=(
            "# Palantir Bull Case\n\n"
            "## Core Claim\nPalantir has a strong moat in government data analytics.\n\n"
            "## Evidence\nQuarterly earnings exceeded analyst expectations.\n"
        ),
        provenance={"source_url": "https://example.com/palantir"},
        source_type="markdown",
    )

    results = handle_search(db, "palantir", limit=5)

    assert len(results) >= 1
    for r in results:
        assert isinstance(r, dict)
        assert set(r.keys()) == {"chunk_id", "document_id", "content", "score"}
        assert isinstance(r["chunk_id"], str)
        assert isinstance(r["document_id"], str)
        assert isinstance(r["content"], str)
        assert isinstance(r["score"], float)


def test_handle_search_respects_limit(db):
    from probe.mcp_server import handle_ingest, handle_search

    body = "\n\n".join(
        f"## Section {i}\nPalantir analysis paragraph number {i} with relevant context."
        for i in range(8)
    )
    handle_ingest(
        db,
        content=f"# Palantir Notes\n\n{body}\n",
        provenance={"source_url": "https://example.com/palantir-notes"},
        source_type="markdown",
    )

    results = handle_search(db, "palantir", limit=2)
    assert len(results) <= 2


def test_handle_search_results_sorted_descending_by_score(db):
    from probe.mcp_server import handle_ingest, handle_search

    handle_ingest(
        db,
        content=(
            "# Palantir Bull Case\n\n"
            "## Core Claim\nPalantir has a strong moat in government data analytics.\n\n"
            "## Earnings\nQuarterly earnings exceeded analyst expectations.\n\n"
            "## Unrelated\nA kitten sleeping on a soft rug.\n"
        ),
        provenance={"source_url": "https://example.com/palantir"},
        source_type="markdown",
    )

    results = handle_search(db, "palantir moat government", limit=5)
    assert len(results) >= 2
    scores = [r["score"] for r in results]
    assert scores == sorted(scores, reverse=True)


# ---------- handle_get_document ----------

def test_handle_get_document_returns_none_for_missing_id(db):
    from probe.mcp_server import handle_get_document

    assert handle_get_document(db, "does-not-exist") is None


def test_handle_get_document_returns_document_fields(db, sample_md_text, sample_md_path):
    from probe.mcp_server import handle_get_document, handle_ingest

    result = handle_ingest(
        db,
        content=sample_md_text,
        provenance={"raw_path": str(sample_md_path)},
        source_type="markdown",
    )
    doc_id = result["document_id"]

    detail = handle_get_document(db, doc_id)

    assert detail is not None
    doc = detail["document"]
    assert doc["id"] == doc_id
    assert doc["source_type"] == "markdown"
    assert doc["title"] == "Palantir Bull Case"


def test_handle_get_document_chunks_match_ingest_count(db, sample_md_text, sample_md_path):
    from probe.mcp_server import handle_get_document, handle_ingest

    result = handle_ingest(
        db,
        content=sample_md_text,
        provenance={"raw_path": str(sample_md_path)},
        source_type="markdown",
    )
    doc_id = result["document_id"]

    detail = handle_get_document(db, doc_id)

    assert len(detail["chunks"]) == result["chunk_count"]


def test_handle_get_document_chunks_ordered_by_index(db):
    from probe.mcp_server import handle_get_document, handle_ingest

    body = "\n\n".join(f"## Section {i}\nContent for section {i}." for i in range(5))
    result = handle_ingest(
        db,
        content=f"# My Notes\n\n{body}\n",
        provenance={"source_url": "https://example.com/notes"},
        source_type="markdown",
    )

    detail = handle_get_document(db, result["document_id"])
    indices = [c["chunk_index"] for c in detail["chunks"]]
    assert indices == sorted(indices)


def test_handle_get_document_chunk_has_expected_keys(db):
    from probe.mcp_server import handle_get_document, handle_ingest

    result = handle_ingest(
        db,
        content="# Title\n\n## Section\nSome content here.",
        provenance={"source_url": "https://example.com/doc"},
        source_type="markdown",
    )

    detail = handle_get_document(db, result["document_id"])
    chunk = detail["chunks"][0]
    assert set(chunk.keys()) == {"id", "section", "chunk_index", "content", "metadata"}


def test_handle_get_document_empty_extractions_and_analyses(db):
    from probe.mcp_server import handle_get_document, handle_ingest

    result = handle_ingest(
        db,
        content="A short web post.",
        provenance={"source_url": "https://example.com/post"},
        source_type="web",
    )

    detail = handle_get_document(db, result["document_id"])
    assert detail["extractions"] == []
    assert detail["analyses"] == []


# ---------- handle_extract ----------

def _stub_general_output():
    return {
        "main_topic": "palantir moat",
        "key_points": ["government data analytics"],
        "entities_mentioned": ["Palantir"],
        "author_stance": "bullish",
    }


def _stub_paper_output():
    return {
        "claimed_contribution": "x",
        "method": "y",
        "key_findings": [],
        "baselines": [],
        "limitations": [],
        "builds_on": [],
    }


def test_handle_extract_persists_extraction(db, sample_md_text, sample_md_path, monkeypatch):
    from probe.mcp_server import handle_extract, handle_ingest

    stub = _stub_general_output()
    monkeypatch.setattr("probe.extraction.general.run", lambda content: stub)

    ingested = handle_ingest(
        db,
        content=sample_md_text,
        provenance={"raw_path": str(sample_md_path)},
        source_type="markdown",
    )

    result = handle_extract(db, ingested["document_id"])

    assert result["extraction_type"] == "general"
    assert result["output"] == stub


def test_handle_extract_override_extraction_type(db, sample_md_text, sample_md_path, monkeypatch):
    from probe.mcp_server import handle_extract, handle_ingest

    general_stub = _stub_general_output()
    paper_stub = _stub_paper_output()

    paper_calls = {"n": 0}

    def fake_paper_run(content):
        paper_calls["n"] += 1
        return paper_stub

    monkeypatch.setattr("probe.extraction.general.run", lambda content: general_stub)
    monkeypatch.setattr("probe.extraction.paper.run", fake_paper_run)

    ingested = handle_ingest(
        db,
        content=sample_md_text,
        provenance={"raw_path": str(sample_md_path)},
        source_type="markdown",
    )

    result = handle_extract(db, ingested["document_id"], extraction_type="general")

    assert result["extraction_type"] == "general"
    assert result["output"] == general_stub
    assert paper_calls["n"] == 0


# ---------- handle_analyze ----------

def _stub_structured_call(result):
    def _fn(**kwargs):
        return result
    return _fn


def _valid_analyze_llm_result():
    return {
        "connections": ["a connects to b"],
        "new_information": ["new fact"],
        "contradictions": [],
        "open_questions": ["what next?"],
    }


def test_handle_analyze_persists_analysis(db, sample_md_text, sample_md_path, monkeypatch):
    from probe.mcp_server import handle_analyze, handle_extract, handle_ingest

    monkeypatch.setattr("probe.extraction.general.run", lambda content: _stub_general_output())
    monkeypatch.setattr(
        "probe.analysis.structured_call", _stub_structured_call(_valid_analyze_llm_result())
    )
    monkeypatch.setattr("probe.analysis.hybrid_search", lambda conn, q, n: [])

    ingested = handle_ingest(
        db,
        content=sample_md_text,
        provenance={"raw_path": str(sample_md_path)},
        source_type="markdown",
    )
    doc_id = ingested["document_id"]
    handle_extract(db, doc_id)

    result = handle_analyze(db, doc_id)

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


def test_handle_analyze_raises_without_prior_extract(db, sample_md_text, sample_md_path):
    from probe.mcp_server import handle_analyze, handle_ingest

    ingested = handle_ingest(
        db,
        content=sample_md_text,
        provenance={"raw_path": str(sample_md_path)},
        source_type="markdown",
    )

    with pytest.raises(RuntimeError):
        handle_analyze(db, ingested["document_id"])


# ---------- handle_list_theses ----------

def test_handle_list_theses_returns_only_active_by_default(db):
    from probe.mcp_server import handle_list_theses
    from probe.thesis import create_thesis, update_thesis

    create_thesis(db, name="t1", core_claim="claim 1")
    create_thesis(db, name="t2", core_claim="claim 2")
    archived_id = create_thesis(db, name="t3", core_claim="claim 3")
    update_thesis(db, archived_id, status="archived")

    active = handle_list_theses(db)
    archived = handle_list_theses(db, "archived")

    assert len(active) == 2
    assert len(archived) == 1


def test_handle_list_theses_empty(db):
    from probe.mcp_server import handle_list_theses

    assert handle_list_theses(db) == []


# ---------- handle_evaluate_thesis ----------

def _valid_evaluate_llm_result():
    return {
        "verdict": "supported",
        "reasoning": "because reasons",
        "supporting": [],
        "contradicting": [],
    }


def test_handle_evaluate_thesis_id_path(db, monkeypatch):
    from probe.mcp_server import handle_evaluate_thesis
    from probe.thesis import create_thesis

    monkeypatch.setattr("probe.thesis.hybrid_search", lambda conn, q, n: [])
    monkeypatch.setattr(
        "probe.thesis.structured_call", _stub_structured_call(_valid_evaluate_llm_result())
    )

    thesis_id = create_thesis(db, name="t1", core_claim="margins will expand")

    result = handle_evaluate_thesis(db, thesis_id)

    assert result["thesis_id"] == thesis_id
    assert result["claim"] == "margins will expand"


def test_handle_evaluate_thesis_claim_path(db, monkeypatch):
    from probe.mcp_server import handle_evaluate_thesis

    monkeypatch.setattr("probe.thesis.hybrid_search", lambda conn, q, n: [])
    monkeypatch.setattr(
        "probe.thesis.structured_call", _stub_structured_call(_valid_evaluate_llm_result())
    )

    result = handle_evaluate_thesis(db, "ad-hoc claim text")

    assert result["thesis_id"] is None
    assert result["claim"] == "ad-hoc claim text"
