import uuid

from probe.ingest import ingest
from probe.data_classes import Provenance


def test_ingest_markdown_extracts_title_from_h1(sample_md_text, sample_md_path):
    result = ingest(
        content=sample_md_text,
        provenance=Provenance(raw_path=str(sample_md_path)),
        source_type="markdown",
    )
    assert result.document.source_type == "markdown"
    assert result.document.title == "Palantir Bull Case"


def test_ingest_markdown_chunks_tagged_by_section(sample_md_text, sample_md_path):
    result = ingest(
        content=sample_md_text,
        provenance=Provenance(raw_path=str(sample_md_path)),
        source_type="markdown",
    )
    sections = [c.section for c in result.chunks if c.section is not None]
    assert "Core Claim" in sections
    assert "Evidence" in sections
    assert "Open Questions" in sections


def test_ingest_markdown_chunks_have_provenance(sample_md_text, sample_md_path):
    result = ingest(
        content=sample_md_text,
        provenance=Provenance(raw_path=str(sample_md_path)),
        source_type="markdown",
    )
    assert len(result.chunks) >= 1
    for chunk in result.chunks:
        assert chunk.content.strip() != ""
        assert chunk.document_id == result.document.id


def test_ingest_tweet_is_atomic(tweet_url):
    text = "AI labs are leaking talent. The infra is the moat now."
    result = ingest(
        content=text,
        provenance=Provenance(
            source_url=tweet_url,
            author="deedydas",
        ),
        source_type="tweet",
    )
    assert len(result.chunks) == 1
    assert result.chunks[0].content == text
    assert result.document.author == "deedydas"
    assert result.document.source_url == tweet_url
    assert result.document.source_type == "tweet"


def test_ingest_web_payload_preserves_provided_metadata():
    parsed_body = (
        "# The AI Investment Thesis\n\n"
        "## Overview\nArtificial intelligence represents the most significant "
        "technological shift since the internet.\n\n"
        "## Key Evidence\nCloud hyperscalers are reporting accelerating capital "
        "expenditure on GPU clusters.\n\n"
        "## Risks\nRegulatory intervention remains the primary tail risk.\n"
    )
    result = ingest(
        content=parsed_body,
        provenance=Provenance(
            source_url="https://example.substack.com/p/ai-thesis",
            title="The AI Investment Thesis",
            author="Jane Doe",
        ),
        source_type="web",
    )
    assert result.document.source_type == "web"
    assert result.document.title == "The AI Investment Thesis"
    assert result.document.author == "Jane Doe"
    assert any("AI Investment Thesis" in c.content for c in result.chunks), (
        f"Expected 'AI Investment Thesis' in chunk content; got: {[c.content[:80] for c in result.chunks]}"
    )
    for chunk in result.chunks:
        assert chunk.document_id == result.document.id


def test_ingest_pdf_payload_carries_page_hint(tmp_path):
    fake_pdf = tmp_path / "bert.pdf"
    fake_pdf.touch()
    parsed = (
        "# BERT: Pre-training of Deep Bidirectional Transformers\n\n"
        "BERT is a method of pre-training language representations.\n"
    )
    result = ingest(
        content=parsed,
        provenance=Provenance(
            source_url="https://arxiv.org/abs/1810.04805",
            raw_path=str(fake_pdf),
            title="BERT: Pre-training of Deep Bidirectional Transformers",
            metadata={"page_number": 1},
        ),
        source_type="pdf",
    )
    assert result.document.source_type == "pdf"
    assert any("BERT" in c.content for c in result.chunks), (
        f"Expected 'BERT' in chunk content; got: {[c.content[:80] for c in result.chunks]}"
    )
    assert any(c.metadata.get("page_number") == 1 for c in result.chunks), (
        f"Expected page_number=1 on a chunk; got metadata: {[c.metadata for c in result.chunks]}"
    )


def test_long_content_splits_into_multiple_chunks():
    body = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 100
    result = ingest(
        content=body,
        provenance=Provenance(source_url="https://example.com/long"),
        source_type="web",
    )
    assert len(result.chunks) > 1


def test_short_content_stays_single_chunk():
    result = ingest(
        content="A very short note.",
        provenance=Provenance(source_url="https://example.com/short"),
        source_type="web",
    )
    assert len(result.chunks) == 1


def test_chunk_indices_are_sequential():
    body = "Lorem ipsum dolor sit amet, consectetur adipiscing elit. " * 100
    result = ingest(
        content=body,
        provenance=Provenance(source_url="https://example.com/seq"),
        source_type="web",
    )
    assert [c.chunk_index for c in result.chunks] == list(range(len(result.chunks)))


def test_all_chunks_link_back_to_document():
    result = ingest(
        content="hello world",
        provenance=Provenance(source_url="https://example.com"),
        source_type="web",
    )
    uuid.UUID(result.document.id)  # raises ValueError if not a valid UUID
    assert all(c.document_id == result.document.id for c in result.chunks)


def test_ingest_lifts_published_from_metadata():
    result = ingest(
        content="BERT abstract body",
        provenance=Provenance(
            source_url="https://arxiv.org/abs/1810.04805",
            metadata={"published": "2018-10-11"},
        ),
        source_type="arxiv_paper",
    )
    assert result.document.published_at == "2018-10-11"


def test_ingest_prefers_published_at_over_published():
    result = ingest(
        content="some body",
        provenance=Provenance(
            source_url="https://example.com",
            metadata={"published_at": "2024-01-15", "published": "2024-01-01"},
        ),
        source_type="web",
    )
    assert result.document.published_at == "2024-01-15"


def test_ingest_published_at_is_none_when_metadata_omits_it():
    result = ingest(
        content="some body",
        provenance=Provenance(source_url="https://example.com"),
        source_type="web",
    )
    assert result.document.published_at is None
