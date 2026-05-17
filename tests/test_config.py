from pathlib import Path

import pytest

from probe.config import Config, load


DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
DEFAULT_EXTRACTION_MODEL = "claude-sonnet-4-20250514"


@pytest.fixture
def fake_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect HOME so load() never touches the real ~/.probe/."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    return tmp_path


def test_missing_config_file_returns_defaults(fake_home: Path) -> None:
    cfg = load()

    assert isinstance(cfg, Config)
    assert cfg.db_path == (fake_home / ".probe" / "probe.db").resolve()
    assert cfg.raw_dir == (fake_home / ".probe" / "raw").resolve()
    assert cfg.anthropic_api_key is None
    assert cfg.embedding_model == DEFAULT_EMBEDDING_MODEL
    assert cfg.extraction_model == DEFAULT_EXTRACTION_MODEL


def test_empty_yaml_returns_defaults(fake_home: Path) -> None:
    probe_dir = fake_home / ".probe"
    probe_dir.mkdir()
    (probe_dir / "config.yaml").write_text("{}\n")

    cfg = load()

    assert cfg.db_path == (fake_home / ".probe" / "probe.db").resolve()
    assert cfg.raw_dir == (fake_home / ".probe" / "raw").resolve()
    assert cfg.anthropic_api_key is None
    assert cfg.embedding_model == DEFAULT_EMBEDDING_MODEL
    assert cfg.extraction_model == DEFAULT_EXTRACTION_MODEL


def test_partial_yaml_overrides_only_specified_field(
    fake_home: Path, tmp_path: Path
) -> None:
    probe_dir = fake_home / ".probe"
    probe_dir.mkdir()
    custom_db = tmp_path / "custom" / "probe.db"
    (probe_dir / "config.yaml").write_text(f"db_path: {custom_db}\n")

    cfg = load()

    assert cfg.db_path == custom_db.resolve()
    # Everything else stays default.
    assert cfg.raw_dir == (fake_home / ".probe" / "raw").resolve()
    assert cfg.anthropic_api_key is None
    assert cfg.embedding_model == DEFAULT_EMBEDDING_MODEL
    assert cfg.extraction_model == DEFAULT_EXTRACTION_MODEL


def test_full_yaml_overrides_all_fields(fake_home: Path, tmp_path: Path) -> None:
    probe_dir = fake_home / ".probe"
    probe_dir.mkdir()
    custom_db = tmp_path / "custom" / "probe.db"
    custom_raw = tmp_path / "custom" / "raw"
    yaml_body = (
        f"db_path: {custom_db}\n"
        f"raw_dir: {custom_raw}\n"
        "anthropic_api_key: sk-ant-from-yaml\n"
        "embedding_model: custom-embed-model\n"
        "extraction_model: custom-extract-model\n"
    )
    (probe_dir / "config.yaml").write_text(yaml_body)

    cfg = load()

    assert cfg.db_path == custom_db.resolve()
    assert cfg.raw_dir == custom_raw.resolve()
    assert cfg.anthropic_api_key == "sk-ant-from-yaml"
    assert cfg.embedding_model == "custom-embed-model"
    assert cfg.extraction_model == "custom-extract-model"


def test_api_key_yaml_wins_over_env(
    fake_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-env")
    probe_dir = fake_home / ".probe"
    probe_dir.mkdir()
    (probe_dir / "config.yaml").write_text("anthropic_api_key: sk-ant-from-yaml\n")

    cfg = load()

    assert cfg.anthropic_api_key == "sk-ant-from-yaml"


def test_api_key_from_env_when_yaml_omits(
    fake_home: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-ant-from-env")
    probe_dir = fake_home / ".probe"
    probe_dir.mkdir()
    (probe_dir / "config.yaml").write_text("embedding_model: all-MiniLM-L6-v2\n")

    cfg = load()

    assert cfg.anthropic_api_key == "sk-ant-from-env"


def test_api_key_none_when_neither_source(fake_home: Path) -> None:
    # fake_home fixture already deletes ANTHROPIC_API_KEY.
    cfg = load()

    assert cfg.anthropic_api_key is None


def test_probe_dir_created_if_missing(fake_home: Path) -> None:
    probe_dir = fake_home / ".probe"
    assert not probe_dir.exists()

    load()

    assert probe_dir.is_dir()


def test_paths_are_absolute_path_objects(fake_home: Path) -> None:
    cfg = load()

    assert isinstance(cfg.db_path, Path)
    assert isinstance(cfg.raw_dir, Path)
    assert cfg.db_path.is_absolute()
    assert cfg.raw_dir.is_absolute()


def test_paths_absolute_when_yaml_provides_relative(
    fake_home: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    probe_dir = fake_home / ".probe"
    probe_dir.mkdir()
    (probe_dir / "config.yaml").write_text(
        "db_path: rel/probe.db\nraw_dir: rel/raw\n"
    )
    monkeypatch.chdir(tmp_path)

    cfg = load()

    assert isinstance(cfg.db_path, Path)
    assert isinstance(cfg.raw_dir, Path)
    assert cfg.db_path.is_absolute()
    assert cfg.raw_dir.is_absolute()


def test_explicit_path_overrides_default_location(
    fake_home: Path, tmp_path: Path
) -> None:
    # Put a config file somewhere that's NOT ~/.probe/config.yaml.
    custom_cfg = tmp_path / "elsewhere" / "myconfig.yaml"
    custom_cfg.parent.mkdir(parents=True)
    custom_db = tmp_path / "elsewhere" / "probe.db"
    custom_cfg.write_text(
        f"db_path: {custom_db}\nembedding_model: from-explicit-path\n"
    )

    # Also create a default config that should be ignored.
    default_dir = fake_home / ".probe"
    default_dir.mkdir()
    (default_dir / "config.yaml").write_text(
        "embedding_model: from-default-path\n"
    )

    cfg = load(path=custom_cfg)

    assert cfg.db_path == custom_db.resolve()
    assert cfg.embedding_model == "from-explicit-path"
