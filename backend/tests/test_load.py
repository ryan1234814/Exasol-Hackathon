"""Loader tests with a stand-in database.

The real loader writes into Exasol, which is not reachable from a test run (and
must not be, from CI). A fake that records statements gives the same guarantees
that matter: the bulk insert shape matches the DDL, nothing is written during a
dry run, and the validator refuses a bad corpus before it can half-load.
"""

import re
from pathlib import Path

import pytest

from backend import load as LOADER
from backend.db import DatabaseUnavailable
from backend.ingest.load_complaints import COLUMNS, build_all, wards_from_seed_sql
from backend.load import INSERT_SHAPE, _validate

SCHEMA_SQL = Path(__file__).resolve().parents[2] / "db" / "10_schema.sql"


class FakeDB:
    """Records statements; answers the handful of reads the loader issues."""

    def __init__(self, wards, complaint_rows=0):
        self.wards = wards
        self.stored = complaint_rows
        self.statements: list[tuple[str, object]] = []
        self.bulk: list[tuple[str, list[tuple]]] = []
        self.last_query_ms = 0

    def query(self, sql, params=None):
        self.statements.append(("query", sql.strip()))
        joined = " ".join(sql.split())
        if "FROM WARDQ.WARD" in joined:
            return [{"WARD_ID": wid, "WARD_NAME": name} for wid, name in self.wards]
        if "GROUP BY CATEGORY" in joined:
            return [] if not self.stored else [{"CATEGORY": "contamination", "N": self.stored}]
        if "COUNT(*)" in joined:
            return [{"N": self.stored}]
        raise AssertionError(f"unexpected query: {joined[:80]}")

    def scalar(self, sql, params=None):
        return next(iter(self.query(sql, params)[0].values()))

    def execute(self, sql, params=None):
        self.statements.append(("execute", " ".join(sql.split())))

    def insert_many(self, statement, rows, batch_size=5_000):
        self.bulk.append((statement, list(rows)))
        return len(rows)


@pytest.fixture
def wards():
    return wards_from_seed_sql()


def _patch(monkeypatch, fake):
    monkeypatch.setattr(LOADER, "get_db", lambda: fake)


# -- the shape of what gets written ------------------------------------------
def test_insert_shape_matches_the_ddl_column_for_column():
    """COLUMNS must equal the COMPLAINT table's columns, in declared order.

    This is the check that catches the failure mode where Python and the schema
    drift apart and the load dies on stage with a mis-ordered bulk insert.
    """
    ddl = SCHEMA_SQL.read_text(encoding="utf-8")
    # Slice from the table header to its first COMMENT ON, which is where the
    # column list ends. Cutting at the first ")" instead would stop inside
    # "DECIMAL(18,0)" and silently report no columns at all.
    block = ddl.split("CREATE OR REPLACE TABLE WARDQ.COMPLAINT", 1)[1].split("COMMENT ON", 1)[0]
    declared = re.findall(r"^\s*([A-Z_][A-Z0-9_]*)\s+(?:DECIMAL|VARCHAR|DOUBLE|TIMESTAMP|BOOLEAN)",
                          block, re.MULTILINE)
    assert declared, "the DDL slice found no columns; the parser is wrong, not the schema"
    assert declared == list(COLUMNS)
    assert INSERT_SHAPE == f"WARDQ.COMPLAINT ({', '.join(declared)})"


def test_every_generated_row_has_a_value_for_each_column(wards):
    rows, summary = build_all(wards)
    assert len(rows) == summary["total_rows"]
    assert all(set(row) == set(COLUMNS) for row in rows)


# -- what is written, and when ----------------------------------------------
def test_dry_run_writes_nothing(monkeypatch, wards):
    fake = FakeDB(wards)
    _patch(monkeypatch, fake)
    summary = LOADER.load(dry_run=True)
    assert not fake.bulk, "a dry run must not touch the table"
    assert not any("TRUNCATE" in sql for kind, sql in fake.statements if kind == "execute")
    assert summary["total_rows"] == summary["fixture_rows"] + summary["bulk_rows"]


def test_real_load_truncates_then_bulk_inserts(monkeypatch, wards):
    fake = FakeDB(wards)
    _patch(monkeypatch, fake)
    summary = LOADER.load()
    executes = [sql for kind, sql in fake.statements if kind == "execute"]
    assert any(sql.startswith("TRUNCATE TABLE WARDQ.COMPLAINT") for sql in executes)
    assert len(fake.bulk) == 1
    statement, tuples = fake.bulk[0]
    assert statement == INSERT_SHAPE
    assert len(tuples) == summary["total_rows"]
    # Regression: _tuples once returned a list of generators, which insert_multi
    # consumes into nothing. Type as well as length has to be right.
    assert all(isinstance(t, tuple) for t in tuples)
    assert all(len(t) == len(COLUMNS) for t in tuples)
    assert summary["inserted"] == summary["total_rows"]


def test_load_run_is_stamped_so_the_footer_can_be_honest(monkeypatch, wards):
    fake = FakeDB(wards)
    _patch(monkeypatch, fake)
    LOADER.load()
    inserts = [sql for kind, sql in fake.statements
               if kind == "execute" and "LOAD_RUN" in sql]
    assert inserts and "INSERT INTO WARDQ.LOAD_RUN" in inserts[0]


def test_a_dead_database_raises_the_domain_error(monkeypatch, wards):
    class Dead(FakeDB):
        def query(self, sql, params=None):
            raise DatabaseUnavailable("Connection refused on 127.0.0.1:8563")

    monkeypatch.setattr(LOADER, "get_db", lambda: Dead(wards))
    with pytest.raises(DatabaseUnavailable):
        LOADER.load()


def test_missing_ward_table_is_a_clear_stop(monkeypatch):
    fake = FakeDB([])
    _patch(monkeypatch, fake)
    with pytest.raises(SystemExit) as exc:
        LOADER.load()
    assert "10_schema.sql" in str(exc.value)


def test_a_partial_seed_is_refused_not_silently_used(monkeypatch, wards):
    fake = FakeDB(wards[:20])
    _patch(monkeypatch, fake)
    with pytest.raises(SystemExit) as exc:
        LOADER.load()
    assert "expected 24 wards" in str(exc.value)


# -- the validator -----------------------------------------------------------
def test_validator_rejects_duplicate_ids(wards):
    rows, summary = _build(wards)
    rows[5]["COMPLAINT_ID"] = rows[4]["COMPLAINT_ID"]
    with pytest.raises(SystemExit, match="duplicate"):
        _validate(rows, summary, wards)


def test_validator_rejects_a_ward_that_does_not_exist(wards):
    rows, summary = _build(wards)
    rows[0]["WARD_ID"] = 999
    with pytest.raises(SystemExit, match="wards that do not exist"):
        _validate(rows, summary, wards)


def test_validator_rejects_text_wider_than_the_column(wards):
    rows, summary = _build(wards)
    rows[0]["RAW_TEXT"] = "x" * 2001
    with pytest.raises(SystemExit, match="too long"):
        _validate(rows, summary, wards)


def test_validator_rejects_an_unmapped_category(wards):
    rows, summary = _build(wards)
    rows[0]["CATEGORY"] = "pilferage"
    with pytest.raises(SystemExit, match="unknown category"):
        _validate(rows, summary, wards)


def test_validator_accepts_the_real_corpus(wards):
    rows, summary = _build(wards)
    _validate(rows, summary, wards)      # no exception


def test_check_compares_stored_against_a_rebuild(monkeypatch, wards):
    _, summary = _build(wards)
    fake = FakeDB(wards, complaint_rows=summary["total_rows"])
    _patch(monkeypatch, fake)
    result = LOADER.check()
    assert result["matches"] is True
    assert result["rebuild_rows"] == summary["total_rows"]

    stale = FakeDB(wards, complaint_rows=7)
    _patch(monkeypatch, stale)
    assert LOADER.check()["matches"] is False


# -- helpers -----------------------------------------------------------------
def _build(wards):
    return build_all(wards)
