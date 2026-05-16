# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A local-first personal research CLI (`probe`) that ingests research sources (papers, SEC filings, Substack, tweets), extracts structured information, and connects new content to existing knowledge via RAG. Exposes an MCP server so Claude Code can query the knowledge base.

See `PROJECT_PROBE.md` for the full spec, data model, 3-day build order, and all design decisions.

## Commands

```bash
# Install (editable, with all deps)
pip install -e .

# Run CLI
probe ingest <url_or_file>
probe ingest --type tweet          # interactive prompt
probe ingest --full <url>          # ingest + extract + analyze in one shot
probe extract <doc_id>
probe analyze <doc_id>
probe search "query"
probe thesis create|list|show|evaluate
probe serve                        # starts MCP server on localhost:7433
probe stats

# Tests
pytest
pytest tests/test_ingest.py::test_name   # single test
```

## Tech Stack

- Python 3.12, `typer` CLI, `rich` for output
- `sqlite3` + `sqlite-vec` (vector similarity) + `FTS5` (keyword search) — single `~/.probe/probe.db` file
- `anthropic` SDK (claude-sonnet-4-20250514) for extraction and analysis
- `sentence-transformers` (all-MiniLM-L6-v2, 384d) for local embeddings
- `httpx` + `beautifulsoup4` for web, `pymupdf4llm` for PDFs

## Architecture

Data flows one-way: **Skill → DB → Extraction → Analysis → Thesis**

```
src/probe/
├── cli.py           # typer app; thin layer, delegates to skills/modules
├── db.py            # schema creation, sqlite-vec setup, FTS5 virtual table
├── models.py        # dataclasses: Document, Chunk, IngestResult, etc.
├── embeddings.py    # sentence-transformers wrapper → numpy → BLOB for sqlite-vec
├── search.py        # hybrid search: vector cosine + FTS5 BM25, merged via RRF
├── llm.py           # Anthropic client wrapper; structured output via tool_use
├── analysis.py      # domain-agnostic RAG: top-5 chunks → Anthropic → analyses table
├── thesis.py        # thesis CRUD + evaluate_thesis (Claude judges support/contradiction)
├── mcp_server.py    # stdio MCP server exposing search_knowledge, get_document, etc.
├── config.py        # ~/.probe/config.yaml loading
├── skills/          # pluggable ingestion — one module per source type
│   ├── base.py      # Skill ABC: can_handle(), ingest(), extract()
│   ├── web.py       # Substack/blogs: httpx → BS4 → ~400-token chunks
│   ├── pdf.py       # papers/transcripts: pymupdf4llm → chunk with page numbers
│   ├── tweet.py     # interactive CLI prompt → single chunk
│   └── markdown.py  # local .md → split on headers
└── extraction/      # domain-specific LLM extraction; prompts live in prompts/
    ├── paper.py     # PaperExtraction schema
    ├── financial.py # FinancialExtraction schema
    └── general.py   # GeneralExtraction fallback
```

## Key Invariants

**Provenance is mandatory** — every chunk must be traceable to its source. If a required field can't be auto-extracted (URL, author, title), the CLI prompts for it. Never store a chunk without provenance. See `PROJECT_PROBE.md` for the full provenance table per source type.

**Skills are selected by URL pattern / file extension** — `cli.py` calls `skill.can_handle()` on each registered skill in order; first match wins. Skills are stateless and must not write to the DB themselves — they return `IngestResult`, and `cli.py` persists it.

**Hybrid search** — `search.py` runs sqlite-vec cosine similarity and FTS5 BM25 independently, then merges results via reciprocal rank fusion (RRF). Never call one without the other.

**Config and data paths** — `~/.probe/config.yaml` (API keys, model, db path), `~/.probe/probe.db` (everything), `~/.probe/raw/` (cached originals). `config.py` owns all path resolution.

**LLM calls use prompt files** — prompts live in `prompts/*.md`, not hardcoded in Python. `extraction/*.py` modules load the relevant prompt file and call `llm.py`. Mock `llm.py` in tests; do not hit the real API.

## Out of Scope (do not add)

No web UI, no user auth, no Postgres/Chroma/Pinecone, no async pipeline, no automatic re-indexing. Single-user, local, synchronous only.
