# Claude conversation handoff

Probe is a local research MCP server. The current repo contains implementations and tests for ingestion, search, extraction, analysis, and theses; `README.md` and `CLAUDE.md` describe the current interface. An older Claude memory entry says implementation had not started and Day 1 was blocked on test naming. That entry is stale; do not resume from it.

Durable decisions recovered from Claude memory:

- Use a fresh SQLite `:memory:` database per database test. Exercise the real database layer; mock external LLM calls where needed.
- Tests define the contract during implementation. Change application code to satisfy them; only mechanical import fixes are permitted in tests after a module rename.
- `documents.source_type` is an open vocabulary with no database `CHECK` constraint. `ingest.py` applies special rules only where a type needs them; generic web-like types require a source URL.
- Existing SQLite query code unpacks rows positionally. Keep SELECT column order aligned with the call site. Avoid introducing a different row access style in one isolated area.
- For long sources passed through an MCP client, summarize before sending `ingest(content=...)` and retain provenance. Full document text in a tool argument is slow to generate. Short sources can be ingested directly.

Source notes: `~/.claude/projects/-Users-arkin-claude-code-stuff-probe/memory/`. The prompt-only history is at `../.claude-conversations/probe-prompts.md`. Check the current repo and Git state before acting on any historical task.
