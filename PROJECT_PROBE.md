# Probe — Personal Research CLI

## What This Is

A CLI tool that ingests diverse research sources (papers, SEC filings, Substack posts, tweets, earnings transcripts), extracts structured information, stores everything in a local searchable index, and connects new information to what you already know via RAG. Exposes the knowledge base via MCP so Claude can query it.

**3-day build. Python. Single-user. Local-first.**

---

## Architecture (keep it simple)

```
CLI (typer)
  │
  ├─ probe ingest <url_or_file>     → Ingestion Skill → Chunks + Provenance → SQLite
  ├─ probe ingest --type tweet       → prompts for text + URL
  ├─ probe extract <doc_id>          → Extraction Skill → Structured output → SQLite
  ├─ probe analyze <doc_id>          → RAG context + Anthropic API → Connections → SQLite
  ├─ probe search "query"            → sqlite-vec similarity + FTS5 keyword → Results
  ├─ probe thesis list|show|create   → Thesis CRUD
  ├─ probe serve                     → MCP server (localhost)
  └─ probe stats                     → counts, last import, db size
```

**Key reuse decisions (from research):**
- `sqlite-vec` for vectors, `FTS5` for keyword search, plain `sqlite3` for everything else — one file, zero ops
- Anthropic API (claude-sonnet-4-20250514) for extraction and analysis — you already pay for Pro
- `sentence-transformers` (all-MiniLM-L6-v2) for local embeddings — fast, free, 384d, good enough to start
- `httpx` for fetching URLs, `pymupdf4llm` for PDFs, `beautifulsoup4` for HTML
- `edgartools` for SEC filings if you want EDGAR support (add in Day 3)

---

## Data Model

```sql
-- Every ingested source
documents (
    id TEXT PRIMARY KEY,          -- uuid
    source_type TEXT NOT NULL,    -- 'arxiv', 'substack', 'tweet', 'filing', 'pdf', 'markdown'
    source_url TEXT,              -- original URL (nullable for pasted text)
    title TEXT,
    author TEXT,
    published_at TEXT,            -- ISO date if known
    accessed_at TEXT NOT NULL,    -- when you ingested it
    description TEXT,             -- user-provided context if no URL
    raw_path TEXT,                -- path to cached original in ~/.probe/raw/
    metadata JSON                -- source-specific extras
)

-- Chunks with embeddings
chunks (
    id TEXT PRIMARY KEY,
    document_id TEXT REFERENCES documents(id),
    content TEXT NOT NULL,
    section TEXT,                 -- 'abstract', 'risk_factors', 'paragraph_3', etc.
    chunk_index INTEGER,
    embedding BLOB               -- 384d float32 via sqlite-vec
)

-- FTS5 virtual table for keyword search
chunks_fts (content) -- mirrors chunks.content

-- Structured extractions (skill-specific output)
extractions (
    id TEXT PRIMARY KEY,
    document_id TEXT REFERENCES documents(id),
    skill_type TEXT NOT NULL,     -- 'paper', 'financial', 'general'
    output JSON NOT NULL,         -- skill-specific structured data
    prompt_version TEXT,          -- which prompt produced this
    created_at TEXT
)

-- Analysis results (RAG connections)
analyses (
    id TEXT PRIMARY KEY,
    document_id TEXT REFERENCES documents(id),
    connections JSON NOT NULL,    -- what this connects to
    new_information JSON,         -- what's genuinely new
    contradictions JSON,          -- what conflicts with existing knowledge
    open_questions JSON,          -- what to investigate next
    rag_context_ids JSON,         -- which chunks were used as context
    prompt_version TEXT,
    created_at TEXT
)

-- Investment theses (versioned first-class objects)
theses (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,            -- 'Palantir bull case'
    status TEXT DEFAULT 'active',  -- 'active', 'closed', 'invalidated'
    core_claim TEXT NOT NULL,
    evidence JSON,                -- [{chunk_id, summary, supports_or_contradicts}]
    risks JSON,
    last_evaluated TEXT,
    created_at TEXT,
    updated_at TEXT
)
```

---

## Skills (pluggable modules)

Each skill is a Python module with three functions. The core engine calls them.

```python
# skills/base.py
class Skill(ABC):
    name: str
    source_types: list[str]

    @abstractmethod
    def can_handle(self, source_ref: str, source_type: str | None) -> bool:
        """Can this skill process this source?"""

    @abstractmethod
    def ingest(self, source_ref: str) -> IngestResult:
        """Fetch, parse, chunk. Returns chunks + provenance metadata."""

    @abstractmethod
    def extract(self, chunks: list[Chunk], llm: LLMClient) -> dict:
        """Domain-specific structured extraction via Anthropic API."""
```

### Ingestion Skills (Day 1)

**WebSkill** — handles Substack, blog posts, any web page:
```
Input:  URL
Steps:  httpx.get → BeautifulSoup → clean HTML → chunk at ~400 tokens
Output: chunks with section headers as metadata
Provenance: URL, title, author (from meta tags), accessed_at
```

**PDFSkill** — handles arXiv papers, earnings transcripts, reports:
```
Input:  file path or URL ending in .pdf
Steps:  pymupdf4llm → markdown text → chunk with page numbers
Output: chunks with page_number and section as metadata
Provenance: URL or path, title (from first page), accessed_at
```

**TweetSkill** — handles pasted tweet text:
```
Input:  --type tweet flag triggers interactive prompt
Steps:  CLI asks for: tweet text, URL, author
Output: single chunk (tweets are atomic)
Provenance: URL, author, accessed_at (published_at if parseable from URL)
```

**MarkdownSkill** — handles your own notes, thesis docs:
```
Input:  .md file path
Steps:  read → split on headers → chunk
Output: chunks with header hierarchy as section metadata
Provenance: file path, accessed_at
```

### Extraction Skills (Day 2)

**PaperExtraction:**
```python
output_schema = {
    "claimed_contribution": str,
    "method": str,
    "key_findings": list[str],
    "baselines": list[str],
    "limitations": list[str],
    "builds_on": list[str],
}
```

**FinancialExtraction:**
```python
output_schema = {
    "core_claim": str,           # the thesis or main argument
    "evidence_chain": list[str], # supporting data points
    "implied_positions": list[str],
    "risks_acknowledged": list[str],
    "risks_ignored": list[str],  # what the author didn't address
    "key_metrics": dict,         # any numbers worth tracking
}
```

**GeneralExtraction** (fallback):
```python
output_schema = {
    "main_topic": str,
    "key_points": list[str],
    "entities_mentioned": list[str],
    "author_stance": str,
}
```

### Analysis Skill (Day 2)

This is the domain-agnostic RAG layer. Not a pluggable skill per source type — one universal analysis step.

```
Input:  extraction output + RAG context (top-5 similar chunks from index)
Prompt to Anthropic API:

    "Here is a newly ingested document:
    [extraction output]

    Here are the most relevant documents from my existing knowledge base:
    [RAG results with provenance]

    Tell me:
    1. What new information does this add that I didn't have before?
    2. What existing documents or theses does this support or contradict?
       Reference specific sources by title and date.
    3. What connections exist that aren't immediately obvious?
    4. What questions should I be asking now?

    Respond as JSON."

Output stored in analyses table.
```

---

## Provenance Rules

Every chunk must have enough metadata to find the original source:

| Source type | Required provenance |
|---|---|
| Substack/web | URL, title, author, accessed_at |
| arXiv paper | URL, title, authors, accessed_at |
| Tweet | tweet URL, author handle, tweet text, accessed_at |
| PDF (local) | file path, description (prompted), accessed_at |
| PDF (URL) | URL, title, accessed_at |
| SEC filing | EDGAR URL, company, filing type, period, accessed_at |
| Markdown | file path, accessed_at |

If a required field can't be auto-extracted, the CLI prompts for it. Never store a chunk without traceable provenance.

---

## MCP Server

`probe serve` starts a local MCP server on `localhost:7433`.

**Tools exposed:**

```python
search_knowledge(query: str, limit: int = 5) -> list[SearchResult]
# Hybrid: sqlite-vec cosine + FTS5 keyword, reciprocal rank fusion
# Returns chunks with provenance and document context

get_document(doc_id: str) -> DocumentDetail
# Full document with all chunks, extractions, analyses

list_theses(status: str = "active") -> list[ThesisSummary]
# Your tracked investment theses

evaluate_thesis(thesis_id: str, new_info: str) -> ThesisEvaluation
# Given new information, does it support or contradict the thesis?

add_note(content: str, tags: list[str] = []) -> Document
# Quick capture — stores as markdown type, extracts, analyzes
```

**MCP config for Claude Code:**
```json
{
  "mcpServers": {
    "probe": {
      "command": "probe",
      "args": ["serve"],
      "type": "stdio"
    }
  }
}
```

---

## Project Structure

```
probe/
├── pyproject.toml
├── README.md
├── CLAUDE.md                     # context for Claude Code sessions
├── src/
│   └── probe/
│       ├── __init__.py
│       ├── cli.py                # typer CLI
│       ├── config.py             # ~/.probe/config.yaml loading
│       ├── db.py                 # SQLite + sqlite-vec + FTS5 setup
│       ├── models.py             # dataclasses: Document, Chunk, Extraction, etc.
│       ├── llm.py                # Anthropic API client wrapper
│       ├── embeddings.py         # sentence-transformers local embedding
│       ├── search.py             # hybrid search (vector + FTS5 + RRF)
│       ├── skills/
│       │   ├── __init__.py
│       │   ├── base.py           # Skill ABC
│       │   ├── web.py            # Substack, blogs, any URL
│       │   ├── pdf.py            # papers, transcripts, reports
│       │   ├── tweet.py          # pasted tweets
│       │   ├── markdown.py       # local .md files
│       │   └── edgar.py          # SEC filings (Day 3 stretch)
│       ├── extraction/
│       │   ├── __init__.py
│       │   ├── paper.py          # paper-specific extraction prompt
│       │   ├── financial.py      # financial-specific extraction prompt
│       │   └── general.py        # fallback extraction
│       ├── analysis.py           # RAG analysis layer
│       ├── thesis.py             # thesis CRUD + evaluation
│       └── mcp_server.py         # MCP stdio server
├── tests/
│   ├── test_ingest.py
│   ├── test_search.py
│   └── fixtures/
└── prompts/                      # extraction/analysis prompt templates
    ├── extract_paper.md
    ├── extract_financial.md
    ├── extract_general.md
    └── analyze.md
```

---

## CLAUDE.md (for Claude Code sessions)

```markdown
# Probe — Personal Research CLI

## What is this
A CLI tool for ingesting research documents (papers, filings, Substack,
tweets), extracting structured information, and connecting new info to
existing knowledge via RAG. Exposes an MCP server.

## Tech stack
- Python 3.12, typer for CLI, sqlite3 + sqlite-vec + FTS5 for storage
- Anthropic API (claude-sonnet-4-20250514) for extraction/analysis
- sentence-transformers (all-MiniLM-L6-v2) for local embeddings
- httpx for fetching, pymupdf4llm for PDFs, beautifulsoup4 for HTML

## Key patterns
- Skills are pluggable: each source type has an ingestion skill in src/probe/skills/
- Extraction is domain-specific: prompts in prompts/ directory, output schemas in src/probe/extraction/
- Analysis is domain-agnostic: RAG over existing index, prompt in prompts/analyze.md
- Every chunk has full provenance (source URL, author, date, section)
- Hybrid search: sqlite-vec cosine similarity + FTS5 BM25 + reciprocal rank fusion
- MCP server uses stdio transport for Claude Code integration

## Commands
- `probe ingest <url_or_file>` — auto-detects source type, ingests + embeds
- `probe ingest --type tweet` — interactive tweet capture
- `probe extract <doc_id>` — runs domain-specific extraction
- `probe analyze <doc_id>` — RAG analysis against existing index
- `probe search "query"` — hybrid search
- `probe thesis create|list|show|evaluate` — thesis management
- `probe serve` — start MCP server
- `probe stats` — database stats

## Config
~/.probe/config.yaml — API keys, embedding model, db path
~/.probe/probe.db — SQLite database (single file)
~/.probe/raw/ — cached original documents

## Testing
pytest. Fixtures in tests/fixtures/. Mock Anthropic API calls in tests.
```

---

## 3-Day Build Order

### Day 1: Core Engine + Ingestion (get data in)
1. `pyproject.toml`, project structure, `config.py`
2. `db.py` — SQLite schema creation, sqlite-vec setup, FTS5 virtual table
3. `models.py` — dataclasses for Document, Chunk, IngestResult
4. `embeddings.py` — sentence-transformers wrapper (embed text → numpy → blob)
5. `skills/base.py` — Skill ABC
6. `skills/web.py` — fetch URL, parse HTML, chunk, extract provenance
7. `skills/pdf.py` — pymupdf4llm, chunk with page numbers
8. `skills/tweet.py` — interactive CLI prompt for text + URL + author
9. `skills/markdown.py` — read file, split on headers
10. `cli.py` — `probe ingest` command with auto-detection
11. `search.py` — basic vector search (sqlite-vec cosine), FTS5 keyword, RRF merge
12. `cli.py` — `probe search` command

**End of Day 1:** you can ingest a Substack post, a PDF, a tweet, and a markdown file, then search across all of them.

### Day 2: Extraction + Analysis + Thesis (make it smart)
1. `llm.py` — Anthropic API client (structured output via tool_use or JSON mode)
2. `prompts/extract_paper.md`, `prompts/extract_financial.md`, `prompts/extract_general.md`
3. `extraction/paper.py`, `extraction/financial.py`, `extraction/general.py`
4. `cli.py` — `probe extract` command (auto-selects extraction type by source_type)
5. `prompts/analyze.md` — the RAG analysis prompt
6. `analysis.py` — fetch top-5 similar chunks, build context, call Anthropic, store result
7. `cli.py` — `probe analyze` command
8. `thesis.py` — CRUD for theses, `evaluate_thesis` (takes thesis + new doc, asks Claude if it supports/contradicts)
9. `cli.py` — `probe thesis create|list|show|evaluate` commands

**End of Day 2:** you can ingest a Burry Substack post, extract the financial thesis, run analysis against your existing index, and track it as a thesis.

### Day 3: MCP Server + Polish + Stretch
1. `mcp_server.py` — stdio MCP server with `search_knowledge`, `get_document`, `list_theses`, `evaluate_thesis`, `add_note`
2. `cli.py` — `probe serve` command
3. Test MCP integration with Claude Code
4. `cli.py` — `probe stats` command
5. `probe ingest` enhancement: auto-chain ingest → extract → analyze in one command (`probe ingest --full`)
6. **Stretch:** `skills/edgar.py` using `edgartools` for 10-K/10-Q ingestion
7. **Stretch:** `rich` tables for prettier CLI output
8. **Stretch:** Contextual retrieval (prepend chunk context before embedding, Anthropic pattern)

**End of Day 3:** Claude Code can query your research index via MCP. You have a working end-to-end pipeline.

---

## Dependencies

```toml
[project]
name = "probe"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "typer>=0.12",
    "rich>=13",
    "httpx>=0.27",
    "beautifulsoup4>=4.12",
    "pymupdf4llm>=0.0.17",
    "anthropic>=0.42",
    "sentence-transformers>=3",
    "sqlite-vec>=0.1",
    "numpy>=1.26",
    "pyyaml>=6",
    "pydantic>=2",
]

[project.scripts]
probe = "probe.cli:app"
```

---

## What NOT to Build (Weekend Scope)

- No web UI — CLI only
- No user auth — single user, local files
- No Postgres/Chroma/Pinecone — sqlite-vec only
- No async ingestion pipeline — synchronous is fine for personal use
- No automatic re-indexing on prompt changes — manual `probe extract` re-run
- No fancy chunking (late chunking, contextual retrieval) in v1 — recursive 400-token split
- No EDGAR integration in v1 unless Day 3 goes fast — add via `edgartools` later
