from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
assert FIXTURES.is_dir(), f"Fixture directory not found: {FIXTURES}"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def sample_md_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "sample.md"


@pytest.fixture
def sample_md_text(sample_md_path: Path) -> str:
    return sample_md_path.read_text()


@pytest.fixture
def tweet_url(fixtures_dir: Path) -> str:
    return (fixtures_dir / "test_tweet.txt").read_text().strip()


@pytest.fixture
def db():
    # Import inside the fixture so conftest.py stays importable before src/probe/db.py exists (TDD).
    from probe.db import connect

    conn = connect(":memory:")
    try:
        yield conn
    finally:
        conn.close()
