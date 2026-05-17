import pytest

from probe.ingest import ingest
from probe.data_classes import Provenance


def test_substack_with_source_url_accepted():
    result = ingest(
        content="A short substack post body.",
        provenance=Provenance(source_url="https://foo.substack.com/p/post"),
        source_type="substack",
    )
    assert len(result.chunks) >= 1
    assert all(c.content.strip() for c in result.chunks)


def test_medium_with_source_url_accepted():
    result = ingest(
        content="A short medium post body.",
        provenance=Provenance(source_url="https://medium.com/@foo/post"),
        source_type="medium",
    )
    assert len(result.chunks) >= 1
    assert all(c.content.strip() for c in result.chunks)


def test_substack_without_source_url_rejected():
    with pytest.raises(ValueError, match="substack"):
        ingest(
            content="body",
            provenance=Provenance(source_url=None, raw_path="/tmp/foo"),
            source_type="substack",
        )


def test_medium_without_source_url_rejected():
    with pytest.raises(ValueError, match="medium"):
        ingest(
            content="body",
            provenance=Provenance(source_url=None, raw_path="/tmp/foo"),
            source_type="medium",
        )


def test_blog_source_type_round_trips_as_is():
    result = ingest(
        content="A blog post body.",
        provenance=Provenance(
            source_url="https://example.com/blog/post",
            author="Jane Doe",
        ),
        source_type="blog",
    )
    assert result.document.source_type == "blog"


def test_empty_source_type_rejected():
    with pytest.raises(ValueError, match="source_type"):
        ingest(
            content="body",
            provenance=Provenance(source_url="https://example.com"),
            source_type="",
        )


def test_whitespace_source_type_rejected():
    with pytest.raises(ValueError, match="source_type"):
        ingest(
            content="body",
            provenance=Provenance(source_url="https://example.com"),
            source_type="   ",
        )


def test_substack_with_both_source_url_and_raw_path_accepted(tmp_path):
    raw = tmp_path / "post.html"
    raw.write_text("<p>hi</p>")
    result = ingest(
        content="A substack post body.",
        provenance=Provenance(
            source_url="https://foo.substack.com/p/post",
            raw_path=str(raw),
        ),
        source_type="substack",
    )
    assert result.document.source_url == "https://foo.substack.com/p/post"
    assert result.document.raw_path == str(raw)
    assert len(result.chunks) >= 1


def test_long_medium_content_splits_into_multiple_chunks():
    body = "lorem " * 500
    result = ingest(
        content=body,
        provenance=Provenance(source_url="https://medium.com/@foo/long"),
        source_type="medium",
    )
    assert len(result.chunks) > 1


def test_arbitrary_new_label_accepted_with_source_url():
    result = ingest(
        content="A newsletter body.",
        provenance=Provenance(source_url="https://example.com/newsletter/1"),
        source_type="newsletter",
    )
    assert result.document.source_type == "newsletter"
    assert len(result.chunks) >= 1
