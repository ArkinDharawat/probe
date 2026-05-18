import json
import uuid

import pytest


def test_create_returns_uuid(db):
    from probe.thesis import create_thesis

    tid = create_thesis(db, name="t1", core_claim="claim")
    assert isinstance(tid, str)
    assert tid
    parsed = uuid.UUID(tid)
    assert parsed.version == 4


def test_round_trip(db):
    from probe.thesis import create_thesis, get_thesis

    tid = create_thesis(
        db,
        name="Palantir bull case",
        core_claim="Palantir has a durable moat",
        evidence=["AIP traction", "Gov contracts"],
        risks=["valuation", "exec risk"],
    )
    out = get_thesis(db, tid)
    assert out is not None
    assert out["id"] == tid
    assert out["name"] == "Palantir bull case"
    assert out["core_claim"] == "Palantir has a durable moat"
    assert out["evidence"] == ["AIP traction", "Gov contracts"]
    assert out["risks"] == ["valuation", "exec risk"]
    assert out["status"] == "active"
    assert out["created_at"]
    assert out["updated_at"]
    assert out["created_at"] == out["updated_at"]
    assert out["last_evaluated"] is None


def test_evidence_risks_default_none(db):
    from probe.thesis import create_thesis, get_thesis

    tid = create_thesis(db, name="bare", core_claim="just a claim")
    out = get_thesis(db, tid)
    assert out is not None
    assert out["evidence"] is None
    assert out["risks"] is None

    raw = db.execute(
        "SELECT evidence, risks FROM theses WHERE id = ?", (tid,)
    ).fetchone()
    assert raw[0] is None
    assert raw[1] is None


def test_get_nonexistent_returns_none(db):
    from probe.thesis import get_thesis

    assert get_thesis(db, "missing") is None


def test_list_filters_by_status(db):
    from probe.thesis import create_thesis, list_theses, update_thesis

    a = create_thesis(db, name="a", core_claim="x")
    b = create_thesis(db, name="b", core_claim="y")
    c = create_thesis(db, name="c", core_claim="z")
    update_thesis(db, c, status="archived")

    active = list_theses(db, "active")
    archived = list_theses(db, "archived")

    assert {t["id"] for t in active} == {a, b}
    assert {t["id"] for t in archived} == {c}


def test_list_orders_by_created_at_desc(db, monkeypatch):
    from probe import thesis as thesis_mod
    from probe.thesis import create_thesis, list_theses

    times = iter(["2026-01-01T00:00:00", "2026-01-02T00:00:00", "2026-01-03T00:00:00"])
    monkeypatch.setattr(thesis_mod, "_utc_now_iso", lambda: next(times))

    first = create_thesis(db, name="first", core_claim="a")
    second = create_thesis(db, name="second", core_claim="b")
    third = create_thesis(db, name="third", core_claim="c")

    ordered = list_theses(db, "active")
    ids = [t["id"] for t in ordered]
    assert ids == [third, second, first]


def test_update_partial_fields(db):
    from probe.thesis import create_thesis, get_thesis, update_thesis

    tid = create_thesis(
        db,
        name="original",
        core_claim="original claim",
        evidence=["e1"],
        risks=["r1"],
    )
    update_thesis(db, tid, name="renamed")
    out = get_thesis(db, tid)
    assert out["name"] == "renamed"
    assert out["core_claim"] == "original claim"
    assert out["evidence"] == ["e1"]
    assert out["risks"] == ["r1"]
    assert out["status"] == "active"


def test_update_bumps_updated_at(db, monkeypatch):
    from probe import thesis as thesis_mod
    from probe.thesis import create_thesis, get_thesis, update_thesis

    times = iter(["2026-01-01T00:00:00", "2026-02-01T00:00:00"])
    monkeypatch.setattr(thesis_mod, "_utc_now_iso", lambda: next(times))

    tid = create_thesis(db, name="t", core_claim="c")
    before = get_thesis(db, tid)
    update_thesis(db, tid, name="t2")
    after = get_thesis(db, tid)

    assert before["created_at"] == "2026-01-01T00:00:00"
    assert after["created_at"] == "2026-01-01T00:00:00"
    assert after["updated_at"] == "2026-02-01T00:00:00"
    assert after["updated_at"] != before["updated_at"]


def test_update_serializes_evidence_risks(db):
    from probe.thesis import create_thesis, get_thesis, update_thesis

    tid = create_thesis(db, name="t", core_claim="c")
    update_thesis(db, tid, evidence=["a", "b"], risks=["r"])
    out = get_thesis(db, tid)
    assert out["evidence"] == ["a", "b"]
    assert out["risks"] == ["r"]

    raw = db.execute(
        "SELECT evidence, risks FROM theses WHERE id = ?", (tid,)
    ).fetchone()
    assert json.loads(raw[0]) == ["a", "b"]
    assert json.loads(raw[1]) == ["r"]


def test_update_unknown_id_raises_keyerror(db):
    from probe.thesis import update_thesis

    with pytest.raises(KeyError):
        update_thesis(db, "missing", name="x")


def test_update_rejects_disallowed_field(db):
    from probe.thesis import create_thesis, update_thesis

    tid = create_thesis(db, name="t", core_claim="c")
    with pytest.raises(ValueError):
        update_thesis(db, tid, foo="bar")
    with pytest.raises(ValueError):
        update_thesis(db, tid, id="other")
