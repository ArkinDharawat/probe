from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Optional

from probe.markdown_split import split_markdown
from probe.data_classes import Chunk, Document, IngestResult, Provenance
from probe.embeddings import embed_batch, to_blob

_MAX_CHARS = 1600
_KNOWN_SOURCE_TYPES = {"markdown", "tweet", "web", "pdf"}


def _validate_provenance(provenance: Provenance, source_type: str) -> None:
    if source_type not in _KNOWN_SOURCE_TYPES:
        raise ValueError(
            f"Unknown source_type={source_type!r}; "
            f"must be one of {sorted(_KNOWN_SOURCE_TYPES)}"
        )

    if provenance.source_url is None and provenance.raw_path is None:
        raise ValueError("Provenance must include source_url or raw_path")

    if source_type == "tweet":
        if provenance.source_url is None:
            raise ValueError("tweet ingestion requires source_url")
        if provenance.author is None:
            raise ValueError("tweet ingestion requires author")

    if source_type == "web":
        if provenance.source_url is None:
            raise ValueError("web ingestion requires source_url")


def _extract_markdown_intro(content: str) -> str:
    """Return text between the H1 (or start of content) and the first H2.
    split_markdown intentionally only emits H2-keyed sections, so anything
    preceding the first ## would be silently dropped without this helper."""
    intro_lines: list[str] = []
    for line in content.splitlines():
        if line.startswith("## "):
            break
        if line.startswith("# ") and not line.startswith("## "):
            continue
        intro_lines.append(line)
    return "\n".join(intro_lines).strip()


def _accessed_at(provenance: Provenance) -> str:
    if provenance.accessed_at is not None:
        return provenance.accessed_at
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


def _generic_chunks(content: str) -> list[str]:
    if len(content) <= _MAX_CHARS:
        return [content]

    paragraphs = content.split("\n\n")
    chunks: list[str] = []
    current: list[str] = []
    current_len = 0

    for para in paragraphs:
        if len(para) > _MAX_CHARS:
            if current:
                chunks.append("\n\n".join(current))
                current = []
                current_len = 0
            lines = para.split("\n")
            line_buf: list[str] = []
            line_len = 0
            for line in lines:
                if len(line) > _MAX_CHARS:
                    if line_buf:
                        chunks.append("\n".join(line_buf))
                        line_buf = []
                        line_len = 0
                    words = line.split(" ")
                    word_buf: list[str] = []
                    word_len = 0
                    for word in words:
                        if word_len + len(word) + (1 if word_buf else 0) > _MAX_CHARS:
                            if word_buf:
                                chunks.append(" ".join(word_buf))
                            word_buf = [word]
                            word_len = len(word)
                        else:
                            word_buf.append(word)
                            word_len += len(word) + (1 if len(word_buf) > 1 else 0)
                    if word_buf:
                        chunks.append(" ".join(word_buf))
                else:
                    sep = 1 if line_buf else 0
                    if line_len + len(line) + sep > _MAX_CHARS:
                        if line_buf:
                            chunks.append("\n".join(line_buf))
                        line_buf = [line]
                        line_len = len(line)
                    else:
                        line_buf.append(line)
                        line_len += len(line) + sep
            if line_buf:
                chunks.append("\n".join(line_buf))
        else:
            sep = 2 if current else 0
            if current_len + len(para) + sep > _MAX_CHARS:
                if current:
                    chunks.append("\n\n".join(current))
                current = [para]
                current_len = len(para)
            else:
                current.append(para)
                current_len += len(para) + sep

    if current:
        chunks.append("\n\n".join(current))

    return [c for c in chunks if c.strip()]


def ingest(content: str, provenance: Provenance, source_type: str) -> IngestResult:
    _validate_provenance(provenance, source_type)

    accessed_at = _accessed_at(provenance)
    doc_id = str(uuid.uuid4())

    title: Optional[str] = provenance.title
    raw_sections: list[tuple[Optional[str], str]] = []

    if source_type == "tweet":
        raw_sections = [(None, content)]

    elif source_type == "markdown":
        h1_title, sections = split_markdown(content)
        if h1_title is not None:
            title = h1_title
        intro = _extract_markdown_intro(content)
        if intro:
            raw_sections.append((None, intro))
        if sections:
            raw_sections.extend((s.header, s.body) for s in sections)
        elif not intro:
            raw_sections = [(None, content)]

    else:
        for text in _generic_chunks(content):
            raw_sections.append((None, text))

    document = Document(
        id=doc_id,
        source_type=source_type,
        source_url=provenance.source_url,
        title=title,
        author=provenance.author,
        published_at=None,
        accessed_at=accessed_at,
        description=None,
        raw_path=provenance.raw_path,
        metadata=provenance.metadata or {},
    )

    chunk_metadata = (provenance.metadata or {}) if source_type == "pdf" else {}

    filtered = [(section, text.strip()) for section, text in raw_sections if text.strip()]

    if not filtered:
        raise ValueError(
            f"Ingestion produced zero chunks for source_type={source_type!r}; "
            "content may be empty or whitespace-only"
        )

    texts = [text for _, text in filtered]
    matrix = embed_batch(texts)

    chunks = [
        Chunk(
            id=str(uuid.uuid4()),
            document_id=doc_id,
            content=text,
            section=section,
            chunk_index=idx,
            metadata=dict(chunk_metadata),
            embedding=to_blob(matrix[idx]),
        )
        for idx, (section, text) in enumerate(filtered)
    ]

    return IngestResult(document=document, chunks=chunks)
