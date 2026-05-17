from dataclasses import dataclass, field
from typing import Optional


@dataclass
class Provenance:
    source_url: Optional[str] = None
    title: Optional[str] = None
    author: Optional[str] = None
    raw_path: Optional[str] = None
    accessed_at: Optional[str] = None
    metadata: dict = field(default_factory=dict)


@dataclass
class Document:
    id: str
    source_type: str
    source_url: Optional[str]
    title: Optional[str]
    author: Optional[str]
    published_at: Optional[str]
    accessed_at: str
    description: Optional[str]
    raw_path: Optional[str]
    metadata: dict


@dataclass
class Chunk:
    id: str
    document_id: str
    content: str
    section: Optional[str]
    chunk_index: int
    metadata: dict
    embedding: Optional[bytes] = None


@dataclass
class IngestResult:
    document: Document
    chunks: list[Chunk]


@dataclass
class SearchResult:
    chunk_id: str
    document_id: str
    content: str
    score: float
