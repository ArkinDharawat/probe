# Probe — Personal Research CLI

## What This Is

A CLI tool that ingests diverse research sources (papers, SEC filings, Substack posts, tweets, earnings transcripts), extracts structured information, stores everything in a local searchable index, and connects new information to what you already know via RAG. Exposes the knowledge base via MCP so Claude can query it.

**3-day build. Python. Single-user. Local-first.**

---

## Architecture (keep it simple)

Probe is an **MCP server first**. The user's local Claude is the only client. Claude parses PDFs and HTML natively and hands the server already-extracted markdown plus provenance. The server doesn't fetch URLs or parse binary formats.

```
Claude Code (MCP client)
  │ stdio
  ▼
probe serve (MCP server)
  │
  ├─ ingest(content, provenance, source_type)   → Chunks + Provenance → SQLite
  ├─ search_personal_knowledge(query, limit)    → sqlite-vec + FTS5 + RRF
  ├─ get_document(doc_id)                       → full doc + extractions + analyses
  ├─ extract(doc_id)                            → Anthropic API → structured output
  ├─ analyze(doc_id)                            → RAG context + Anthropic API → connections
  ├─ evaluate_thesis(claim_or_id)               → RAG → support/contradict verdict
  ├─ list_theses(status)                        → tracked theses
  └─ add_note(content, tags)                    → ergonomic ingest wrapper
```

The CLI surface collapses to a launcher: `probe serve` (start the MCP server) and optional `probe stats` (out-of-band DB debugging from the terminal). Everything else lives behind MCP tools.

**Key reuse decisions (from research):**
- `sqlite-vec` for vectors, `FTS5` for keyword search, plain `sqlite3` for everything else — one file, zero ops
- Anthropic API (claude-sonnet-4-20250514) for extraction and analysis — you already pay for Pro
- `sentence-transformers` (all-MiniLM-L6-v2) for local embeddings — fast, free, 384d, good enough to start
- No `httpx` / `beautifulsoup4` / `pymupdf4llm` server-side — Claude parses client-side and passes the result through `ingest`
- `edgartools` for SEC filings if you want EDGAR support (add in Day 3) — only data source Claude can't easily reach itself

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
    metadata JSON,                -- per-chunk extras (e.g. page_number for PDFs)
    embedding BLOB               -- 384d float32 via sqlite-vec
)

-- FTS5 virtual table for keyword search
chunks_fts (content) -- mirrors chunks.content

-- Structured extractions (domain-specific output)
extractions (
    id TEXT PRIMARY KEY,
    document_id TEXT REFERENCES documents(id),
    extraction_type TEXT NOT NULL, -- 'paper', 'financial', 'general'
    output JSON NOT NULL,          -- domain-specific structured data
    prompt_version TEXT,           -- which prompt produced this
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

## Ingestion (single entry point)

Original spec had four pluggable `Skill` classes (`WebSkill`, `PDFSkill`, `TweetSkill`, `MarkdownSkill`). With Claude as the MCP client, this collapses: Claude parses PDFs and HTML and hands the server already-extracted markdown plus provenance. The server exposes one entry point.

```python
def ingest(
    content: str,           # already-parsed markdown (Claude does the parsing)
    provenance: Provenance, # source_url, title, author, raw_path, accessed_at, metadata
    source_type: str,       # 'markdown' | 'tweet' | 'web' | 'pdf' | ...
) -> IngestResult:
    """Chunk content, attach provenance, return Document + Chunks. No I/O outside DB."""
```

The `source_type` discriminator drives per-type behavior:

| `source_type` | Required provenance | Chunking behavior |
|---|---|---|
| `markdown` | `raw_path` (URL not required for local notes) | split on H2 headers; H1 → document title |
| `tweet` | `source_url` + `author` | one chunk per call — tweets are atomic |
| `web` | `source_url` | recursive ~400-token split over the parsed body |
| `pdf` | `source_url` or `raw_path` | recursive ~400-token split; caller passes `page_number` in `metadata` so chunks inherit it |

**Helpers (server-side):**
- `markdown_split(text) → (title, sections)` — pulls H1 as title and splits on H2 for the markdown path
- Generic recursive ~400-token chunker for non-markdown content

**Invariants:**
- Every chunk carries `document_id` linking back to its `Document`
- `Provenance` with neither `source_url` nor `raw_path` is rejected (no untraceable content)
- `accessed_at` is auto-set if the caller omits it

### Extraction (Day 2)

Domain-specific structured extraction selected by `source_type`. One Python module per domain, each loading its prompt from `prompts/*.md`.

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

### Analysis (Day 2)

Domain-agnostic RAG layer — one universal step regardless of `source_type`.

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

`probe serve` starts a local MCP server over stdio.

**Tools exposed:**

```python
ingest(content: str, provenance: Provenance, source_type: str) -> IngestResult
# Single ingest entry. Claude has already parsed the source (PDF, HTML, etc.)
# and passes markdown + provenance fields.

search_personal_knowledge(query: str, limit: int = 5) -> list[SearchResult]
# Hybrid: sqlite-vec cosine + FTS5 keyword, reciprocal rank fusion.
# Returns chunks with provenance and document context.
# Renamed from search_knowledge to make the "local DB, not Claude's training data"
# boundary obvious.

get_document(doc_id: str) -> DocumentDetail
# Full document with all chunks, extractions, analyses.

extract(doc_id: str) -> Extraction
# Run domain-specific structured extraction (paper / financial / general)
# selected by source_type. Stores in extractions table.

analyze(doc_id: str) -> Analysis
# RAG analysis: top-5 similar chunks → Anthropic → connections,
# new info, contradictions, open questions.

list_theses(status: str = "active") -> list[ThesisSummary]
# Your tracked investment theses.

evaluate_thesis(claim_or_id: str) -> ThesisEvaluation
# Generalized from the original evaluate_thesis(thesis_id, new_info):
# accepts either a stored thesis_id OR an ad-hoc claim string,
# RAG-searches personal knowledge, and returns support / contradiction
# with provenance. Lets a Claude Code slash command like `/thesis <claim>`
# invoke it without first persisting the thesis.

add_note(content: str, tags: list[str] = []) -> Document
# Ergonomic wrapper over ingest with source_type='markdown'.
```

**Claude Code slash command pattern (optional, client-side):**

Slash commands like `/thesis Palantir drops to $10 a share` wrap a call to `evaluate_thesis(claim)`. The MCP server exposes the tool; the slash command lives in Claude Code config — different layers, easy to confuse with the old "Skill" terminology.

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
│       ├── cli.py                # typer CLI — `probe serve` + `probe stats` only
│       ├── config.py             # ~/.probe/config.yaml loading
│       ├── db.py                 # SQLite + sqlite-vec + FTS5 setup
│       ├── models.py             # dataclasses: Document, Chunk, Provenance, IngestResult, etc.
│       ├── llm.py                # Anthropic API client wrapper
│       ├── embeddings.py         # sentence-transformers local embedding
│       ├── search.py             # hybrid search (vector + FTS5 + RRF)
│       ├── ingest.py             # single ingest entry — chunks content + persists with provenance
│       ├── markdown_split.py     # H1 → title, H2 → sections; helper for source_type='markdown'
│       ├── extraction/
│       │   ├── __init__.py
│       │   ├── paper.py          # paper-specific extraction prompt
│       │   ├── financial.py      # financial-specific extraction prompt
│       │   └── general.py        # fallback extraction
│       ├── analysis.py           # RAG analysis layer
│       ├── thesis.py             # thesis CRUD + evaluation (claim_or_id)
│       └── mcp_server.py         # MCP stdio server — exposes ingest/search/extract/analyze/etc.
├── tests/
│   ├── conftest.py               # fixture loaders for tests/fixtures/
│   ├── test_ingest.py            # Day 1: ingest() contract over markdown/tweet/web/pdf payloads
│   ├── test_provenance.py        # Day 1: invariant + per-source-type required fields
│   ├── test_markdown_split.py    # Day 1: header-splitting helper
│   ├── test_search.py            # Day 2
│   └── fixtures/
└── prompts/                      # extraction/analysis prompt templates
    ├── extract_paper.md
    ├── extract_financial.md
    ├── extract_general.md
    └── analyze.md
```

Note: the old `src/probe/skills/` directory (per-source `Skill` subclasses) is gone — `ingest.py` + `markdown_split.py` + `source_type` discriminator replace it. The empty `src/probe/skills/` shell in the current scaffold can be removed when Day 1 implementation lands.

---

## CLAUDE.md (for Claude Code sessions)

```markdown
# Probe — Personal Research MCP Server

## What is this
An MCP server that ingests research documents (papers, filings, Substack,
tweets, notes), extracts structured information, and connects new info to
existing knowledge via RAG. Claude (the MCP client) does the parsing of
PDFs and HTML; the server stores, embeds, searches, and reasons.

## Tech stack
- Python 3.12, typer for the launcher CLI, sqlite3 + sqlite-vec + FTS5 for storage
- Anthropic API (claude-sonnet-4-20250514) for extraction/analysis
- sentence-transformers (all-MiniLM-L6-v2) for local embeddings
- No server-side URL fetching, HTML, or PDF parsing — client does that

## Key patterns
- Single ingest entry: `ingest(content, provenance, source_type)`; `source_type`
  is a string discriminator (`markdown` / `tweet` / `web` / `pdf` / ...)
- Markdown splitting (H1 → title, H2 → sections) lives in `markdown_split.py`
- Extraction is domain-specific: prompts in prompts/, output schemas in src/probe/extraction/
- Analysis is domain-agnostic: RAG over existing index, prompt in prompts/analyze.md
- Every chunk has full provenance (source URL, author, date, section);
  `Provenance` with no `source_url` and no `raw_path` is rejected
- Hybrid search: sqlite-vec cosine similarity + FTS5 BM25 + reciprocal rank fusion
- MCP server uses stdio transport for Claude Code integration

## CLI
- `probe serve` — start the MCP server (the primary entry point)
- `probe stats` — out-of-band DB stats (optional, terminal-only debug)

Everything else (ingest, search, extract, analyze, thesis) is an MCP tool,
not a CLI command. Don't add `probe ingest` / `probe search` etc. back.

## MCP tools
- `ingest(content, provenance, source_type)` — chunk + persist
- `search_personal_knowledge(query, limit)` — hybrid search over the local DB
- `get_document(doc_id)` — full doc + extractions + analyses
- `extract(doc_id)` — structured extraction (paper/financial/general)
- `analyze(doc_id)` — RAG analysis (connections, contradictions, open Qs)
- `evaluate_thesis(claim_or_id)` — accepts a stored thesis ID OR an ad-hoc claim
- `list_theses(status)`
- `add_note(content, tags)` — ergonomic wrapper over ingest

## Config
~/.probe/config.yaml — API keys, embedding model, db path
~/.probe/probe.db — SQLite database (single file)
~/.probe/raw/ — cached original documents

## Testing
pytest. Fixtures in tests/fixtures/. Mock Anthropic API calls in tests.
Day 1 tests live in test_ingest.py / test_provenance.py / test_markdown_split.py.
```

---

## 3-Day Build Order

### Day 1: Core Engine + Ingestion (get data in)
1. `pyproject.toml`, project structure, `config.py`
2. `db.py` — SQLite schema creation, sqlite-vec setup, FTS5 virtual table
3. `models.py` — dataclasses for `Document`, `Chunk`, `Provenance`, `IngestResult`
4. `embeddings.py` — sentence-transformers wrapper (embed text → numpy → blob)
5. `markdown_split.py` — H1 → title, H2 → sections helper
6. `ingest.py` — single `ingest(content, provenance, source_type)` entry; per-`source_type` chunking; provenance invariants
7. `search.py` — basic vector search (sqlite-vec cosine), FTS5 keyword, RRF merge

**Day 1 tests (TDD — already on `claude/write-day1-tests-bqThr`):**
- `tests/test_ingest.py` — `ingest()` contract over markdown / tweet / web / pdf payloads, chunk sizing, document linkage
- `tests/test_provenance.py` — invariant + per-source-type required fields
- `tests/test_markdown_split.py` — header splitting helper

**End of Day 1:** the `ingest()` function persists Documents + Chunks with traceable provenance, embeddings + FTS rows are populated, and you can `search.py` across them. No MCP wiring yet — exercised via tests.

### Day 2: Extraction + Analysis + Thesis (make it smart)
1. `llm.py` — Anthropic API client (structured output via tool_use or JSON mode)
2. `prompts/extract_paper.md`, `prompts/extract_financial.md`, `prompts/extract_general.md`
3. `extraction/paper.py`, `extraction/financial.py`, `extraction/general.py`
4. `extract(doc_id)` entry — auto-selects extraction type by `source_type`
5. `prompts/analyze.md` — the RAG analysis prompt
6. `analysis.py` — fetch top-5 similar chunks, build context, call Anthropic, store result
7. `thesis.py` — CRUD for theses; `evaluate_thesis(claim_or_id)` accepting either a stored thesis ID or an ad-hoc claim string

**End of Day 2:** you can ingest a Burry Substack post, extract the financial thesis, run analysis against your existing index, and track it as a thesis. All via direct function calls (still no MCP wiring).

### Day 3: MCP Server + Polish + Stretch
1. `mcp_server.py` — stdio MCP server exposing `ingest`, `search_personal_knowledge`, `get_document`, `extract`, `analyze`, `list_theses`, `evaluate_thesis`, `add_note`
2. `cli.py` — `probe serve` command (launcher only)
3. Test MCP integration with Claude Code; configure a `/thesis <claim>` slash command that calls `evaluate_thesis`
4. `cli.py` — `probe stats` command for out-of-band debugging
5. **Stretch:** `edgartools` for SEC filings — server-side because Claude can't easily reach EDGAR programmatically
6. **Stretch:** `rich` tables for prettier `probe stats` output
7. **Stretch:** Contextual retrieval (prepend chunk context before embedding, Anthropic pattern)

**End of Day 3:** Claude Code calls Probe's MCP tools to ingest, search, and reason over your research index. The slash-command UX (`/thesis ...`) wraps the heavier MCP tools for one-shot reasoning.

---

## Dependencies

```toml
[project]
name = "probe"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "typer>=0.12",                 # `probe serve` / `probe stats` only
    "rich>=13",
    "anthropic>=0.42",
    "mcp>=1.0",                    # stdio MCP server
    "sentence-transformers>=3",
    "sqlite-vec>=0.1",
    "numpy>=1.26",
    "pyyaml>=6",
    "pydantic>=2",
]

[project.scripts]
probe = "probe.cli:app"
```

Dropped from the original list: `httpx`, `beautifulsoup4`, `pymupdf4llm`. The server doesn't fetch URLs or parse binary formats — Claude does both client-side and passes the result through `ingest`.

---

## What NOT to Build (Weekend Scope)

- No web UI — MCP server only; Claude Code is the UI
- No human-facing CLI for ingest/search/extract/analyze — those are MCP tools, not commands. The CLI is `probe serve` (+ `probe stats` for debugging)
- No server-side URL fetching or HTML/PDF parsing — Claude parses client-side and passes markdown + provenance through `ingest`
- No user auth — single user, local files
- No Postgres/Chroma/Pinecone — sqlite-vec only
- No async ingestion pipeline — synchronous is fine for personal use
- No automatic re-indexing on prompt changes — manual `extract` re-run via MCP
- No fancy chunking (late chunking, contextual retrieval) in v1 — recursive 400-token split
- No EDGAR integration in v1 unless Day 3 goes fast — add via `edgartools` later
