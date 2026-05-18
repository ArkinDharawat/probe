from __future__ import annotations

import pytest

from probe.extraction import paper, financial, general


PAPER_REQUIRED = {
    "claimed_contribution",
    "method",
    "key_findings",
    "baselines",
    "limitations",
    "builds_on",
}

FINANCIAL_REQUIRED = {
    "core_claim",
    "evidence_chain",
    "implied_positions",
    "risks_acknowledged",
    "risks_ignored",
    "key_metrics",
}

GENERAL_REQUIRED = {
    "main_topic",
    "key_points",
    "entities_mentioned",
    "author_stance",
}


PAPER_STUB = {
    "claimed_contribution": "c",
    "method": "m",
    "key_findings": ["f"],
    "baselines": ["b"],
    "limitations": ["l"],
    "builds_on": ["x"],
}

FINANCIAL_STUB = {
    "core_claim": "c",
    "evidence_chain": ["e"],
    "implied_positions": ["p"],
    "risks_acknowledged": ["ra"],
    "risks_ignored": ["ri"],
    "key_metrics": {"revenue": "100"},
}

GENERAL_STUB = {
    "main_topic": "t",
    "key_points": ["k"],
    "entities_mentioned": ["e"],
    "author_stance": "neutral",
}


MODULES = [
    pytest.param(paper, PAPER_REQUIRED, PAPER_STUB, id="paper"),
    pytest.param(financial, FINANCIAL_REQUIRED, FINANCIAL_STUB, id="financial"),
    pytest.param(general, GENERAL_REQUIRED, GENERAL_STUB, id="general"),
]


@pytest.mark.parametrize("mod,required,stub", MODULES)
def test_module_exposes_expected_symbols(mod, required, stub):
    assert hasattr(mod, "PROMPT_VERSION")
    assert isinstance(mod.PROMPT_VERSION, str) and mod.PROMPT_VERSION
    assert hasattr(mod, "SCHEMA")
    assert isinstance(mod.SCHEMA, dict)
    assert hasattr(mod, "PROMPT_PATH")
    assert hasattr(mod, "run") and callable(mod.run)


@pytest.mark.parametrize("mod,required,stub", MODULES)
def test_prompt_path_exists_on_disk(mod, required, stub):
    assert mod.PROMPT_PATH.is_file(), f"missing prompt file: {mod.PROMPT_PATH}"


@pytest.mark.parametrize("mod,required,stub", MODULES)
def test_schema_has_expected_required_keys(mod, required, stub):
    props = mod.SCHEMA.get("properties", {})
    assert set(props.keys()) >= required, (
        f"missing properties: {required - set(props.keys())}"
    )
    req_list = mod.SCHEMA.get("required", [])
    assert set(req_list) >= required, (
        f"missing required entries: {required - set(req_list)}"
    )


@pytest.mark.parametrize("mod,required,stub", MODULES)
def test_run_passes_content_as_prompt(mod, required, stub, monkeypatch):
    captured: dict = {}

    def fake_structured_call(**kwargs):
        captured.update(kwargs)
        return stub

    monkeypatch.setattr(
        f"probe.extraction.{mod.__name__.rsplit('.', 1)[-1]}.structured_call",
        fake_structured_call,
    )

    mod.run("doc content here")
    assert captured["prompt"] == "doc content here"


@pytest.mark.parametrize("mod,required,stub", MODULES)
def test_run_passes_prompt_file_text_as_system(mod, required, stub, monkeypatch):
    captured: dict = {}

    def fake_structured_call(**kwargs):
        captured.update(kwargs)
        return stub

    monkeypatch.setattr(
        f"probe.extraction.{mod.__name__.rsplit('.', 1)[-1]}.structured_call",
        fake_structured_call,
    )

    mod.run("x")
    assert captured["system"] == mod.PROMPT_PATH.read_text()


@pytest.mark.parametrize("mod,required,stub", MODULES)
def test_run_passes_module_schema_as_output_schema(mod, required, stub, monkeypatch):
    captured: dict = {}

    def fake_structured_call(**kwargs):
        captured.update(kwargs)
        return stub

    monkeypatch.setattr(
        f"probe.extraction.{mod.__name__.rsplit('.', 1)[-1]}.structured_call",
        fake_structured_call,
    )

    mod.run("x")
    assert captured["output_schema"] is mod.SCHEMA


@pytest.mark.parametrize("mod,required,stub", MODULES)
def test_run_returns_structured_call_result_unchanged(mod, required, stub, monkeypatch):
    def fake_structured_call(**kwargs):
        return stub

    monkeypatch.setattr(
        f"probe.extraction.{mod.__name__.rsplit('.', 1)[-1]}.structured_call",
        fake_structured_call,
    )

    assert mod.run("x") == stub
