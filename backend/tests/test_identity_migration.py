"""Renaming the database must copy persisted data without damaging its source."""
import importlib.util
from pathlib import Path
import sqlite3

import pytest


def migration():
    path = Path(__file__).resolve().parents[2] / "scripts" / "migrate_identity.py"
    spec = importlib.util.spec_from_file_location("identity_migration", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.migrate


def test_copies_database_and_uploads_without_changing_source(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    with sqlite3.connect(source / "previous.db") as db:
        db.execute("CREATE TABLE shipments (reference TEXT)")
        db.execute("INSERT INTO shipments VALUES ('TEST-42')")
    (source / "uploads").mkdir()
    (source / "uploads" / "document.txt").write_text("Shipment attachment")
    (source / "secret_key").write_text("existing-key")
    before = (source / "previous.db").read_bytes()
    target = tmp_path / "new"
    migration()(source, "previous.db", target)
    with sqlite3.connect(target / "emcargo.db") as db:
        assert db.execute("SELECT reference FROM shipments").fetchone() == ("TEST-42",)
    assert (source / "previous.db").read_bytes() == before
    assert (target / "uploads" / "document.txt").read_text() == "Shipment attachment"
    assert (target / "secret_key").read_text() == "existing-key"
    assert not (target / "previous.db").exists()
    with pytest.raises(ValueError, match="new destination"):
        migration()(source, "previous.db", target)


def test_rejects_corrupt_database_before_copying(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    (source / "previous.db").write_text("not a database")
    target = tmp_path / "new"
    with pytest.raises(sqlite3.DatabaseError):
        migration()(source, "previous.db", target)
    assert not target.exists()
