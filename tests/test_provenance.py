import pytest

from probe.ingest import ingest
from probe.data_classes import Provenance


def test_rejects_content_with_no_traceable_source():
    with pytest.raises(ValueError):
        ingest(
            content="hello",
            provenance=Provenance(source_url=None, raw_path=None),
            source_type="web",
        )


def test_tweet_requires_author():
    with pytest.raises(ValueError):
        ingest(
            content="hot take here",
            provenance=Provenance(
                source_url="https://x.com/foo/status/1",
                author=None,
            ),
            source_type="tweet",
        )


def test_tweet_requires_source_url():
    with pytest.raises(ValueError):
        ingest(
            content="hot take here",
            provenance=Provenance(
                source_url=None,
                author="foo",
                raw_path="/tmp/foo",
            ),
            source_type="tweet",
        )


def test_markdown_accepts_raw_path_without_url(tmp_path):
    md_file = tmp_path / "note.md"
    md_file.write_text("# Title\n\nbody\n")
    result = ingest(
        content=md_file.read_text(),
        provenance=Provenance(source_url=None, raw_path=str(md_file)),
        source_type="markdown",
    )
    assert result.document.raw_path == str(md_file)
    assert result.document.source_url is None


def test_web_requires_source_url():
    with pytest.raises(ValueError):
        ingest(
            content="<p>some web content</p>",
            provenance=Provenance(source_url=None, title="Foo"),
            source_type="web",
        )


def test_accessed_at_auto_set_when_omitted():
    result = ingest(
        content="hello world",
        provenance=Provenance(source_url="https://example.com"),
        source_type="web",
    )
    assert result.document.accessed_at is not None
    assert isinstance(result.document.accessed_at, str)
    assert "-" in result.document.accessed_at


def test_caller_supplied_accessed_at_preserved():
    fixed = "2025-01-15T12:00:00"
    result = ingest(
        content="hello world",
        provenance=Provenance(
            source_url="https://example.com",
            accessed_at=fixed,
        ),
        source_type="web",
    )
    assert result.document.accessed_at == fixed
