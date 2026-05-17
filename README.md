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

### 3. Configure API keys (optional)

`~/.probe/config.yaml` is optional — all defaults work for Day 2 (ingest + search). The DB lands at `~/.probe/probe.db` and no API key is needed until Day 3 (extraction / analysis). To override defaults:

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

Day 2 (now):

- `ingest(content, provenance, source_type)` — chunk + persist already-parsed markdown with provenance
- `search_personal_knowledge(query, limit)` — hybrid sqlite-vec + FTS5 search merged via RRF

Day 3 (deferred): `get_document`, `extract`, `analyze`, `evaluate_thesis`, `list_theses`, `add_note`.
