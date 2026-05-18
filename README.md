# probe

Personal research MCP server. Ingests research sources (papers, filings, Substack, tweets, notes), extracts structured information, and connects new content to existing knowledge via RAG. Exposes the knowledge base as an MCP server so Claude Code can query it.

See [PROJECT_PROBE.md](PROJECT_PROBE.md) for the full spec and design decisions.

---

## Setup

**Requirements:** Python 3.12, Homebrew (macOS)

### 1. Create and activate a virtual environment

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

### 2. Install the package and dev dependencies

```bash
pip install -e ".[dev]"
```

This installs `probe` in editable mode along with test and lint tools (`pytest`, `ruff`).

### 3. Configure API keys

`~/.probe/config.yaml` is optional for `ingest` and `search_personal_knowledge` — those run fully locally and the DB lands at `~/.probe/probe.db` by default. An `ANTHROPIC_API_KEY` (env var or config file) is required for `extract`, `analyze`, and `evaluate_thesis`. To override defaults:

```bash
mkdir -p ~/.probe
cat > ~/.probe/config.yaml << 'EOF'
anthropic_api_key: "sk-ant-..."
model: "claude-sonnet-4-20250514"
db_path: "~/.probe/probe.db"
EOF
```

### 4. Verify the install

```bash
probe --help
```

---

## Running tests

```bash
pytest                                      # all tests
pytest tests/test_ingest.py                 # single file
pytest tests/test_ingest.py::test_name      # single test
```

---

## Wiring into Claude Code / Claude Desktop

Add this to your MCP config:

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

- **Claude Code:** `~/.claude.json` or project-local `.mcp.json`
- **Claude Desktop (macOS):** `~/Library/Application Support/Claude/claude_desktop_config.json`

Start the server manually to verify:

```bash
probe serve
```

---

## Commands

```bash
probe serve      # start the stdio MCP server (primary entrypoint)
probe stats      # print doc / chunk / extraction / analysis / thesis counts (debug)
```

---

## MCP tools exposed

- `ingest(content, provenance, source_type)` — chunk + persist already-parsed markdown with provenance
- `search_personal_knowledge(query, limit)` — hybrid sqlite-vec + FTS5 search merged via RRF
- `get_document(doc_id)` — full document with all chunks, extractions, and analyses
- `extract(doc_id, extraction_type=None)` — domain-specific structured extraction (paper / financial / general); auto-routed by `source_type` unless overridden; upserts on `(document_id, extraction_type)`
- `analyze(doc_id)` — RAG analysis connecting the doc to existing knowledge; requires a prior `extract` call on the same doc
- `list_theses(status="active")` — list stored research theses by status
- `evaluate_thesis(claim_or_id)` — judge a stored thesis (by id) or ad-hoc claim string against the knowledge base via RAG, returning a verdict plus supporting / contradicting chunks

---

## Claude Code slash commands

`.claude/commands/thesis.md` wraps `evaluate_thesis` for one-shot reasoning. Once Probe is wired in as an MCP server, run:

```
/thesis Palantir will trade above $50 by end of year
```

Claude Code calls `evaluate_thesis(claim_or_id="Palantir will trade above $50 by end of year")`, which RAG-searches your personal index and returns a structured verdict with supporting and contradicting chunks. The argument can also be a stored thesis id from `list_theses`.
