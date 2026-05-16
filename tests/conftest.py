from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


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
def sample_html_text(fixtures_dir: Path) -> str:
    return (fixtures_dir / "sample.html").read_text()


@pytest.fixture
def tweet_url(fixtures_dir: Path) -> str:
    return (fixtures_dir / "test_tweet.txt").read_text().strip()


@pytest.fixture
def pdf_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / "1810.04805v2.pdf"
