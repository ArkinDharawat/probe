def test_db_fixture_yields_usable_connection(db):
    assert db.execute("SELECT 1").fetchone()[0] == 1
