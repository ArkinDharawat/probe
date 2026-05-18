from __future__ import annotations

import pytest

from probe.config import Config


class FakeBlock:
    def __init__(self, type, name=None, input=None, text=None):
        self.type = type
        self.name = name
        self.input = input
        self.text = text


class FakeResponse:
    def __init__(self, blocks):
        self.content = blocks


class FakeMessages:
    def __init__(self, response, captured):
        self._response = response
        self._captured = captured

    def create(self, **kwargs):
        self._captured.update(kwargs)
        return self._response


class FakeClient:
    response: FakeResponse | None = None
    last_kwargs: dict = {}

    def __init__(self, api_key=None):
        self.api_key = api_key
        self.messages = FakeMessages(FakeClient.response, FakeClient.last_kwargs)


def _make_config(api_key="sk-fake", extraction_model="claude-test-model"):
    from pathlib import Path

    return Config(
        db_path=Path("/tmp/probe-test.db"),
        raw_dir=Path("/tmp/probe-raw"),
        anthropic_api_key=api_key,
        embedding_model="all-MiniLM-L6-v2",
        extraction_model=extraction_model,
    )


@pytest.fixture(autouse=True)
def _reset_fake_client():
    FakeClient.response = None
    FakeClient.last_kwargs = {}
    yield


@pytest.fixture
def patched_env(monkeypatch):
    def _patch(response, config=None):
        FakeClient.response = response
        cfg = config if config is not None else _make_config()
        monkeypatch.setattr("probe.llm.Anthropic", FakeClient)
        monkeypatch.setattr("probe.llm.load", lambda: cfg)
        return cfg

    return _patch


def test_structured_call_returns_tool_use_input(patched_env):
    response = FakeResponse([
        FakeBlock(type="tool_use", name="structured_output", input={"x": 1}),
    ])
    patched_env(response)

    from probe.llm import structured_call

    result = structured_call("hello", {"type": "object", "properties": {"x": {"type": "integer"}}})

    assert result == {"x": 1}


def test_structured_call_request_shape(patched_env):
    schema = {
        "type": "object",
        "properties": {"x": {"type": "integer"}},
        "required": ["x"],
    }
    response = FakeResponse([
        FakeBlock(type="tool_use", name="structured_output", input={"x": 42}),
    ])
    patched_env(response)

    from probe.llm import structured_call

    structured_call("hello", schema)

    kwargs = FakeClient.last_kwargs
    assert kwargs["model"] == "claude-test-model"
    assert kwargs["max_tokens"] == 4096
    assert isinstance(kwargs["tools"], list)
    assert len(kwargs["tools"]) == 1
    tool = kwargs["tools"][0]
    assert tool["name"] == "structured_output"
    assert tool["input_schema"] == schema
    assert kwargs["tool_choice"] == {"type": "tool", "name": "structured_output"}


def test_structured_call_omits_system_when_none(patched_env):
    response = FakeResponse([
        FakeBlock(type="tool_use", name="structured_output", input={}),
    ])
    patched_env(response)

    from probe.llm import structured_call

    structured_call("hi", {"type": "object"})

    assert "system" not in FakeClient.last_kwargs


def test_structured_call_includes_system_when_provided(patched_env):
    response = FakeResponse([
        FakeBlock(type="tool_use", name="structured_output", input={}),
    ])
    patched_env(response)

    from probe.llm import structured_call

    structured_call("hi", {"type": "object"}, system="you are a helper")

    assert FakeClient.last_kwargs["system"] == "you are a helper"


def test_structured_call_uses_config_model_by_default(patched_env):
    response = FakeResponse([
        FakeBlock(type="tool_use", name="structured_output", input={}),
    ])
    cfg = _make_config(api_key="sk-fake", extraction_model="claude-test-model")
    patched_env(response, config=cfg)

    from probe.llm import structured_call

    structured_call("hi", {"type": "object"})

    assert FakeClient.last_kwargs["model"] == "claude-test-model"


def test_structured_call_explicit_model_overrides_config(patched_env):
    response = FakeResponse([
        FakeBlock(type="tool_use", name="structured_output", input={}),
    ])
    patched_env(response)

    from probe.llm import structured_call

    structured_call("hi", {"type": "object"}, model="claude-other")

    assert FakeClient.last_kwargs["model"] == "claude-other"


def test_structured_call_raises_when_api_key_missing(patched_env):
    response = FakeResponse([
        FakeBlock(type="tool_use", name="structured_output", input={}),
    ])
    cfg = _make_config(api_key=None)
    patched_env(response, config=cfg)

    from probe.llm import structured_call

    with pytest.raises(RuntimeError) as exc:
        structured_call("hi", {"type": "object"})

    assert "api key" in str(exc.value).lower()


def test_structured_call_raises_when_no_tool_use_block(patched_env):
    response = FakeResponse([
        FakeBlock(type="text", text="just text, no tool use"),
    ])
    patched_env(response)

    from probe.llm import structured_call

    with pytest.raises(RuntimeError):
        structured_call("hi", {"type": "object"})
