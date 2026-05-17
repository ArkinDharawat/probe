from typer.testing import CliRunner

from probe.cli import app

runner = CliRunner()


def test_root_help_lists_serve_and_stats():
    result = runner.invoke(app, ["--help"])
    assert result.exit_code == 0
    assert "serve" in result.stdout
    assert "stats" in result.stdout


def test_serve_help_exits_zero():
    result = runner.invoke(app, ["serve", "--help"])
    assert result.exit_code == 0
    assert result.stdout.strip() != ""


def test_stats_help_exits_zero():
    result = runner.invoke(app, ["stats", "--help"])
    assert result.exit_code == 0
    assert result.stdout.strip() != ""


def test_stats_empty_db_prints_zero_counts(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    result = runner.invoke(app, ["stats"])
    assert result.exit_code == 0, result.stdout

    for table in ("documents", "chunks", "extractions", "analyses", "theses"):
        assert table in result.stdout, (
            f"Expected table name {table!r} in stats output; got: {result.stdout!r}"
        )
    assert "0" in result.stdout


def test_stats_after_ingest_shows_nonzero_documents_and_chunks(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))

    from probe.config import load
    from probe.db import connect, persist
    from probe.ingest import ingest
    from probe.data_classes import Provenance

    config = load()
    db_path = config.db_path

    conn = connect(db_path)
    try:
        result = ingest(
            content="A very short note.",
            provenance=Provenance(source_url="https://example.com/short"),
            source_type="web",
        )
        persist(conn, result)
    finally:
        conn.close()

    cli_result = runner.invoke(app, ["stats"])
    assert cli_result.exit_code == 0, cli_result.stdout

    for table in ("documents", "chunks", "extractions", "analyses", "theses"):
        assert table in cli_result.stdout, (
            f"Expected table name {table!r} in stats output; got: {cli_result.stdout!r}"
        )

    lines = [line for line in cli_result.stdout.splitlines() if "documents" in line]
    assert any(
        any(token.isdigit() and int(token) > 0 for token in line.replace(":", " ").split())
        for line in lines
    ), f"Expected a positive document count in stats output; got: {cli_result.stdout!r}"

    chunk_lines = [line for line in cli_result.stdout.splitlines() if "chunks" in line]
    assert any(
        any(token.isdigit() and int(token) > 0 for token in line.replace(":", " ").split())
        for line in chunk_lines
    ), f"Expected a positive chunk count in stats output; got: {cli_result.stdout!r}"


def test_serve_invokes_mcp_server_run_once(monkeypatch):
    calls = {"count": 0}

    def fake_run():
        calls["count"] += 1

    import probe.mcp_server

    monkeypatch.setattr(probe.mcp_server, "run", fake_run)

    result = runner.invoke(app, ["serve"])
    assert result.exit_code == 0, result.stdout
    assert calls["count"] == 1
