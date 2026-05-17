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

## Wiring up the MCP server

Add this to your Claude Code MCP config (`~/.claude.json` or project `.mcp.json`):

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

Start the server manually to verify:

```bash
probe serve
```

---

## Commands

```bash
probe serve      # start MCP server on stdio (main entrypoint)
probe stats      # print DB stats for debugging
```
