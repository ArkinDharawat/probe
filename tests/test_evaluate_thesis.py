from __future__ import annotations

from pathlib import Path


PROMPT_PATH = (
    Path(__file__).resolve().parents[1] / "prompts" / "evaluate_thesis.md"
)


def _stub_llm_dict():
    return {
        "verdict": "insufficient_evidence",
        "reasoning": "stub",
        "supporting": [],
        "contradicting": [],
    }


def _make_capture(return_value=None):
    captured: dict = {}

    def _fake(*args, **kwargs):
        captured["args"] = args
        captured["kwargs"] = kwargs
        return return_value if return_value is not None else _stub_llm_dict()

    return _fake, captured


def test_id_path_uses_core_claim(db, monkeypatch):
    from probe import thesis as thesis_mod
    from probe.thesis import create_thesis, evaluate_thesis

    tid = create_thesis(db, name="t", core_claim="X is undervalued")

    monkeypatch.setattr(thesis_mod, "hybrid_search", lambda conn, q, n: [])
    fake_call, captured = _make_capture()
    monkeypatch.setattr(thesis_mod, "structured_call", fake_call)

    evaluate_thesis(db, tid)

    prompt = captured["kwargs"]["prompt"]
    assert "X is undervalued" in prompt


def test_claim_path_uses_string_directly(db, monkeypatch):
    from probe import thesis as thesis_mod
    from probe.thesis import evaluate_thesis

    monkeypatch.setattr(thesis_mod, "hybrid_search", lambda conn, q, n: [])
    fake_call, captured = _make_capture()
    monkeypatch.setattr(thesis_mod, "structured_call", fake_call)

    evaluate_thesis(db, "Random unsaved claim")

    prompt = captured["kwargs"]["prompt"]
    assert "Random unsaved claim" in prompt


def test_returns_thesis_id_for_id_path(db, monkeypatch):
    from probe import thesis as thesis_mod
    from probe.thesis import create_thesis, evaluate_thesis

    tid = create_thesis(db, name="t", core_claim="Some core claim")

    monkeypatch.setattr(thesis_mod, "hybrid_search", lambda conn, q, n: [])
    fake_call, _ = _make_capture()
    monkeypatch.setattr(thesis_mod, "structured_call", fake_call)

    out = evaluate_thesis(db, tid)
    assert out["thesis_id"] == tid
    assert out["claim"] == "Some core claim"


def test_returns_none_thesis_id_for_ad_hoc(db, monkeypatch):
    from probe import thesis as thesis_mod
    from probe.thesis import evaluate_thesis

    monkeypatch.setattr(thesis_mod, "hybrid_search", lambda conn, q, n: [])
    fake_call, _ = _make_capture()
    monkeypatch.setattr(thesis_mod, "structured_call", fake_call)

    out = evaluate_thesis(db, "the claim string")
    assert out["thesis_id"] is None
    assert out["claim"] == "the claim string"


def test_id_path_updates_last_evaluated(db, monkeypatch):
    from probe import thesis as thesis_mod
    from probe.thesis import create_thesis, evaluate_thesis, get_thesis

    tid = create_thesis(db, name="t", core_claim="c")
    before = get_thesis(db, tid)
    assert before["last_evaluated"] is None

    monkeypatch.setattr(thesis_mod, "hybrid_search", lambda conn, q, n: [])
    fake_call, _ = _make_capture()
    monkeypatch.setattr(thesis_mod, "structured_call", fake_call)

    evaluate_thesis(db, tid)

    after = get_thesis(db, tid)
    assert isinstance(after["last_evaluated"], str)
    assert after["last_evaluated"]
    assert after["created_at"] == before["created_at"]


def test_claim_path_does_not_write_to_theses(db, monkeypatch):
    from probe import thesis as thesis_mod
    from probe.thesis import evaluate_thesis

    monkeypatch.setattr(thesis_mod, "hybrid_search", lambda conn, q, n: [])
    fake_call, _ = _make_capture()
    monkeypatch.setattr(thesis_mod, "structured_call", fake_call)

    before = db.execute("SELECT COUNT(*) FROM theses").fetchone()[0]
    evaluate_thesis(db, "ad hoc claim")
    after = db.execute("SELECT COUNT(*) FROM theses").fetchone()[0]
    assert before == after


def test_passes_evaluate_schema(db, monkeypatch):
    from probe import thesis as thesis_mod
    from probe.thesis import EVALUATE_SCHEMA, evaluate_thesis

    monkeypatch.setattr(thesis_mod, "hybrid_search", lambda conn, q, n: [])
    fake_call, captured = _make_capture()
    monkeypatch.setattr(thesis_mod, "structured_call", fake_call)

    evaluate_thesis(db, "some claim")
    assert captured["kwargs"]["output_schema"] is EVALUATE_SCHEMA


def test_passes_system_prompt_from_file(db, monkeypatch):
    from probe import thesis as thesis_mod
    from probe.thesis import evaluate_thesis

    monkeypatch.setattr(thesis_mod, "hybrid_search", lambda conn, q, n: [])
    fake_call, captured = _make_capture()
    monkeypatch.setattr(thesis_mod, "structured_call", fake_call)

    evaluate_thesis(db, "some claim")
    expected = PROMPT_PATH.read_text()
    assert captured["kwargs"]["system"] == expected


def test_context_includes_chunk_metadata(db, monkeypatch):
    from probe import thesis as thesis_mod
    from probe.data_classes import SearchResult
    from probe.thesis import evaluate_thesis

    results = [
        SearchResult(
            chunk_id="chunk-aaa",
            document_id="doc-aaa",
            content="First chunk content body.",
            score=0.9,
        ),
        SearchResult(
            chunk_id="chunk-bbb",
            document_id="doc-bbb",
            content="Second chunk content body.",
            score=0.5,
        ),
    ]
    monkeypatch.setattr(thesis_mod, "hybrid_search", lambda conn, q, n: results)
    fake_call, captured = _make_capture()
    monkeypatch.setattr(thesis_mod, "structured_call", fake_call)

    evaluate_thesis(db, "any claim")
    prompt = captured["kwargs"]["prompt"]
    assert "chunk-aaa" in prompt
    assert "chunk-bbb" in prompt
    assert "First chunk content body." in prompt
    assert "Second chunk content body." in prompt


def test_empty_results_produces_no_chunks_marker(db, monkeypatch):
    from probe import thesis as thesis_mod
    from probe.thesis import evaluate_thesis

    monkeypatch.setattr(thesis_mod, "hybrid_search", lambda conn, q, n: [])
    fake_call, captured = _make_capture()
    monkeypatch.setattr(thesis_mod, "structured_call", fake_call)

    evaluate_thesis(db, "any claim")
    prompt = captured["kwargs"]["prompt"]
    assert "(no chunks found in the personal knowledge base)" in prompt


def test_returns_llm_fields_unchanged(db, monkeypatch):
    from probe import thesis as thesis_mod
    from probe.thesis import evaluate_thesis

    llm_out = {
        "verdict": "supported",
        "reasoning": "because reasons",
        "supporting": [
            {"chunk_id": "c1", "document_id": "d1", "quote": "quote a"}
        ],
        "contradicting": [],
    }
    monkeypatch.setattr(thesis_mod, "hybrid_search", lambda conn, q, n: [])
    fake_call, _ = _make_capture(return_value=llm_out)
    monkeypatch.setattr(thesis_mod, "structured_call", fake_call)

    out = evaluate_thesis(db, "claim")
    assert out["verdict"] == "supported"
    assert out["reasoning"] == "because reasons"
    assert out["supporting"] == [
        {"chunk_id": "c1", "document_id": "d1", "quote": "quote a"}
    ]
    assert out["contradicting"] == []
