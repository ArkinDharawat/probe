from __future__ import annotations

import typer

from probe import mcp_server
from probe.config import load
from probe.db import connect

app = typer.Typer(help="Probe — personal research MCP server.")

_TABLES = ("documents", "chunks", "extractions", "analyses", "theses")


@app.command()
def serve() -> None:
    """Start the MCP stdio server (blocking)."""
    mcp_server.run()


@app.command()
def stats() -> None:
    """Print DB row counts for core tables."""
    config = load()
    conn = connect(config.db_path)
    try:
        for table in _TABLES:
            (count,) = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()
            typer.echo(f"{table}: {count}")
    finally:
        conn.close()
