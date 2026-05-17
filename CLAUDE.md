# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

A local-first personal research **MCP server** (`probe`) that ingests research sources (papers, SEC filings, Substack, tweets, notes), extracts structured information, and connects new content to existing knowledge via RAG. Claude Code is the client: it parses URLs/PDFs/HTML and calls Probe's MCP tools to store, embed, search, and reason.

See `PROJECT_PROBE.md` for the full spec, data model, 3-day build order, and all design decisions.

## Commands

```bash
# Install (editable, with dev deps)
pip install -e ".[dev]"

# CLI — launcher only
probe serve                        # start the stdio MCP server (primary entry point)
probe stats                        # out-of-band DB stats (debug)

# Tests
pytest
pytest tests/test_ingest.py::test_name   # single test
```

Everything else (ingest, search, extract, analyze, thesis) is an **MCP tool**, not a CLI command. Don't add `probe ingest` / `probe search` back.

### Day 2 wiring (in progress)

- `probe serve` boots the stdio MCP server with a single sqlite connection at server scope (shared across tool calls in the process).
- `probe stats` is the only out-of-band debug command: prints doc / chunk / extraction / analysis / thesis counts.
- Config is loaded via `probe.config.load()` which resolves `~/.probe/config.yaml` (optional) and defaults the DB path to `~/.probe/probe.db`.
- Day 2 MCP tool surface is intentionally minimal: `ingest` and `search_personal_knowledge`. Day 3 adds `get_document`, `extract`, `analyze`, `evaluate_thesis`, `list_theses`, `add_note`.

## Tech Stack

- Python 3.12, `typer` CLI (launcher only), `rich` for output
- `sqlite3` + `sqlite-vec` (vector similarity) + `FTS5` (keyword search) — single `~/.probe/probe.db` file
- `anthropic` SDK (claude-sonnet-4-20250514) for extraction and analysis
- `sentence-transformers` (all-MiniLM-L6-v2, 384d) for local embeddings
- `mcp` for the stdio MCP server

No server-side URL fetching, HTML parsing, or PDF parsing — Claude (the MCP client) does that and passes markdown + provenance through `ingest`.

## Architecture

Data flows one-way: **ingest() → DB → Extraction → Analysis → Thesis**

```
src/probe/
├── cli.py           # Day 2 — being wired: typer launcher; `probe serve` + `probe stats` only
├── config.py        # ~/.probe/config.yaml loading
├── db.py            # schema creation, sqlite-vec setup, FTS5 virtual table
├── data_classes.py  # dataclasses: Document, Chunk, Provenance, IngestResult, etc.
├── embeddings.py    # sentence-transformers wrapper → numpy → BLOB for sqlite-vec
├── search.py        # hybrid search: vector cosine + FTS5 BM25, merged via RRF
├── ingest.py        # single ingest(content, provenance, source_type) entry; per-source_type chunking
├── markdown_split.py# H1 → title, H2 → sections helper for source_type='markdown'
├── mcp_server.py    # Day 2 — being wired: stdio MCP server exposing ingest + search_personal_knowledge
├── llm.py           # Day 3: Anthropic client wrapper; structured output via tool_use
├── analysis.py      # Day 3: domain-agnostic RAG: top-5 chunks → Anthropic → analyses table
├── thesis.py        # Day 3: thesis CRUD + evaluate_thesis (Claude judges support/contradiction)
└── extraction/      # Day 3: domain-specific LLM extraction; prompts live in prompts/
    ├── paper.py     # PaperExtraction schema
    ├── financial.py # FinancialExtraction schema
    └── general.py   # GeneralExtraction fallback
```

## Key Invariants

**Provenance is mandatory** — every chunk must be traceable to its source. `Provenance` with no `source_url` and no `raw_path` is rejected. Per-source-type required fields (e.g. tweet needs `author` + `source_url`) are enforced in `ingest.py`. See `PROJECT_PROBE.md` for the full provenance table.

**`source_type` is a string discriminator, not a class hierarchy** — `ingest(content, provenance, source_type)` is the single entry point. `source_type` drives per-type chunking and required-field rules inside `ingest.py`. There is no `Skill` ABC, no `can_handle()`, no per-source subclass.

The vocabulary is **open**, not enumerated. `src/probe/ingest.py` only special-cases two small sets:

- `_LOCAL_TYPES = {"markdown", "pdf"}` — may be ingested with just `raw_path` (no URL required); `markdown` also gets H1/H2 splitting via `markdown_split.py`.
- `_ATOMIC_TYPES = {"tweet"}` — one chunk per call; requires both `source_url` and `author`.

Anything else (`web`, `substack`, `medium`, `blog`, …) is treated as web-like: generic ~1600-char chunker and `source_url` required. Don't gate on a closed enum — let Claude pick a descriptive `source_type` string and route it through the generic path.

**Hybrid search** — `search.py` runs sqlite-vec cosine similarity and FTS5 BM25 independently, then merges results via reciprocal rank fusion (RRF). Never call one without the other.

**Config and data paths** — `~/.probe/config.yaml` (API keys, model, db path), `~/.probe/probe.db` (everything), `~/.probe/raw/` (cached originals). `config.py` owns all path resolution.

**LLM calls use prompt files** — prompts live in `prompts/*.md`, not hardcoded in Python. `extraction/*.py` modules load the relevant prompt file and call `llm.py`. Mock `llm.py` in tests; do not hit the real API.

## TDD Rules

This project uses test-driven development. Tests are written first and define the contract.

**Never modify test logic when implementing the corresponding code.** If a test is failing, fix the implementation — not the test. The only permitted edits to test files are mechanical renames (e.g. updating an import path when a module is renamed) that do not change what the test asserts.

## Out of Scope (do not add)

No web UI, no human-facing CLI for ingest/search/extract/analyze, no server-side URL fetching or HTML/PDF parsing, no user auth, no Postgres/Chroma/Pinecone, no async pipeline, no automatic re-indexing. Single-user, local, synchronous only.
