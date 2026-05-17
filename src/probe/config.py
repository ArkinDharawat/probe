from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import yaml


DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
DEFAULT_EXTRACTION_MODEL = "claude-sonnet-4-20250514"


@dataclass(frozen=True)
class Config:
    db_path: Path
    raw_dir: Path
    anthropic_api_key: str | None
    embedding_model: str
    extraction_model: str


def _resolve_path(value: str) -> Path:
    return Path(value).expanduser().resolve()


def load(path: Path | None = None) -> Config:
    cfg_path = path if path is not None else Path("~/.probe/config.yaml").expanduser()

    data: dict = {}
    if cfg_path.is_file():
        loaded = yaml.safe_load(cfg_path.read_text())
        if isinstance(loaded, dict):
            data = loaded

    db_path = _resolve_path(data.get("db_path") or "~/.probe/probe.db")
    raw_dir = _resolve_path(data.get("raw_dir") or "~/.probe/raw")
    api_key = data.get("anthropic_api_key") or os.environ.get("ANTHROPIC_API_KEY")
    embedding_model = data.get("embedding_model") or DEFAULT_EMBEDDING_MODEL
    extraction_model = data.get("extraction_model") or DEFAULT_EXTRACTION_MODEL

    db_path.parent.mkdir(parents=True, exist_ok=True)

    return Config(
        db_path=db_path,
        raw_dir=raw_dir,
        anthropic_api_key=api_key,
        embedding_model=embedding_model,
        extraction_model=extraction_model,
    )
