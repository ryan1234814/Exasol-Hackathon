"""Benchmark tests against a stand-in driver.

The benchmark is the artifact the speed claims are quoted from, so a broken
scenario should fail here rather than halfway through a judged demo. The stub
returns tiny series; the point is the contract, not the numbers.
"""

import re
import sqlite3
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from backend import benchmark as B

SCHEMA_SQL = Path(__file__).resolve().parents[2] / "db" / "10_schema.sql"


def _series(n=40):
    return [{"SAMPLE_DATE": date(2024, 10, 1) + timedelta(days=i),
             "AVG_VALUE": 5.0 + (i % 7),
             "WARD_ID": 12, "PARAM_CODE": "COLIFORM", "N_SAMPLES": 4, "BREACH_FLAG": 1}
            for i in range(n)]


class StubExasol:
    """Answers the benchmark's reads from small in-memory series."""

    def __init__(self):
        self.executed = []
        self.series = _series()

    def query(self, sql, params=None):
        joined = " ".join(sql.split())
        if joined.startswith("SELECT 1"):
            return [{"OK": 1}]
        if joined.startswith("SELECT COUNT(*)"):
            return [{"N": len(self.series)}]
        if "GROUP BY" in joined and "SAMPLE_LOG" in joined:          # S1
            return [{"WARD_ID": 12, "PARAM_CODE": "COLIFORM", "AVG_VALUE": 7.5,
                     "BREACH_READINGS": 40, "N_READINGS": len(self.series)}]
        if "OVER (PARTITION BY" in joined:                            # S2 in-database
            return [{"SAMPLE_DATE": r["SAMPLE_DATE"], "AVG_VALUE": r["AVG_VALUE"],
                     "BASE_AVG": 6.0, "BASE_STD": 1.4} for r in self.series]
        if "WARD_DAILY" in joined and "N_SAMPLES" in joined:         # the mirror's daily pull
            return [{k: v for k, v in r.items() if k in
                     ("SAMPLE_DATE", "WARD_ID", "PARAM_CODE", "AVG_VALUE", "N_SAMPLES", "BREACH_FLAG")}
                    for r in self.series]
        if "WARD_DAILY" in joined and "AVG_VALUE" in joined:          # S2 raw pull
            return [{"SAMPLE_DATE": r["SAMPLE_DATE"], "AVG_VALUE": r["AVG_VALUE"]}
                    for r in self.series]
        if "FROM WARDQ.PARAMETER_LIMITS" in joined:
            return [{"PARAM_CODE": "COLIFORM", "PARAM_NAME": "Total Coliform",
                     "UNIT": "CFU/100ml", "THRESHOLD_LO": None, "THRESHOLD_HI": Decimal("0.0")}]
        if "FROM WARDQ.SAMPLE_LOG" in joined:
            return [{"SAMPLE_ID": i + 1, "WARD_ID": 12, "PARAM_CODE": "COLIFORM",
                     "SAMPLE_DATE": r["SAMPLE_DATE"], "VALUE_DOUBLE": r["AVG_VALUE"],
                     "STATION_ID": 1, "LAB_VERIFIED": "TRUE"}
                    for i, r in enumerate(self.series)]
        raise AssertionError(f"unhandled query: {joined[:90]}")

    def scalar(self, sql, params=None):
        return next(iter(self.query(sql, params)[0].values()))

    def iter_query(self, sql, batch_size=50_000):
        yield from self.query(sql)

    def execute(self, sql, params=None):
        self.executed.append(params)


@pytest.fixture
def stub():
    return StubExasol()


@pytest.fixture
def mirror(tmp_path, stub):
    """A real SQLite mirror built through the production code path."""
    path = tmp_path / "mirror.sqlite"
    B.build_sqlite_mirror(stub, path=path)
    conn = sqlite3.connect(path)
    yield conn
    conn.close()


RESULT_KEYS = {"scenario", "engine", "rows_touched", "elapsed_ms", "bytes_sent", "note"}


@pytest.mark.parametrize("rows", [
    pytest.param(lambda stub, mirror: B.s1_scan_aggregate(stub, mirror), id="s1"),
    pytest.param(lambda stub, mirror: B.s2_zscore_in_db_vs_python(stub, mirror), id="s2"),
    pytest.param(lambda stub, mirror: B.s3_result_cache(stub, 2), id="s3"),
])
def test_every_scenario_returns_the_declared_contract(stub, mirror, rows):
    for row in rows(stub, mirror):
        assert set(row) == RESULT_KEYS
        assert row["elapsed_ms"] is None or row["elapsed_ms"] >= 0
        assert row["note"], "a number without a caveat is not quotable in the PRD"


def test_s1_reports_both_engines_and_checks_agreement(stub, mirror):
    rows = B.s1_scan_aggregate(stub, mirror)
    engines = {r["engine"] for r in rows}
    assert engines == {"exasol", "sqlite"}
    assert "counts agree" in rows[0]["note"] or "MISMATCH" in rows[0]["note"]
    # the same SQL text must have run on both sides
    assert "same SQL text" in rows[1]["note"]


def test_s1_without_a_mirror_still_produces_the_exasol_leg(stub):
    rows = B.s1_scan_aggregate(stub)
    assert [r["engine"] for r in rows] == ["exasol"]
    assert "--no-sqlite" in rows[0]["note"]


def test_s2_returns_the_three_way_comparison(stub, mirror):
    rows = B.s2_zscore_in_db_vs_python(stub, mirror, 12, "COLIFORM")
    assert {r["engine"] for r in rows} == {"exasol", "python", "sqlite"}
    python_leg = next(r for r in rows if r["engine"] == "python")
    assert "transfer + arithmetic" in python_leg["note"]


def test_s2_without_a_mirror_drops_only_the_sqlite_leg(stub):
    rows = B.s2_zscore_in_db_vs_python(stub, None, 12, "COLIFORM")
    assert {r["engine"] for r in rows} == {"exasol", "python"}


def test_s3_records_each_repeat_and_a_summary_row(stub):
    rows = B.s3_result_cache(stub, repeats=3)
    assert len(rows) == 4
    assert rows[-1]["scenario"] == "S3_cold_vs_warm"
    # the caveat is a requirement, not decoration: the cache was never flushed
    assert "result cache was not flushed" in rows[-1]["note"]


def test_mirror_holds_the_same_dataset_as_the_engine(stub, mirror):
    mirrored = mirror.execute("SELECT COUNT(*) FROM SAMPLE_LOG").fetchone()[0]
    assert mirrored == len(stub.series)
    daily = mirror.execute("SELECT COUNT(*) FROM SAMPLE_LOG_DAILY").fetchone()[0]
    assert daily == len(stub.series)
    assert mirror.execute("SELECT PARAM_CODE FROM PARAMETER_LIMITS").fetchone()[0] == "COLIFORM"


def test_s1_sql_is_valid_for_both_engines_by_running_on_the_mirror(stub, mirror):
    # This is the check that the {p} prefix substitution has not left a
    # "WARDQ." in front of a SQLite table.
    rows = mirror.execute(B.S1_SQL.format(p=B.SQLITE_PREFIX)).fetchall()
    assert rows
    assert len(rows[0]) == 5


def test_insert_statement_columns_exist_in_the_ddl():
    ddl = SCHEMA_SQL.read_text(encoding="utf-8")
    block = ddl.split("CREATE OR REPLACE TABLE WARDQ.BENCHMARK_RESULTS", 1)[1] \
               .split("COMMENT ON", 1)[0]
    declared = set(re.findall(
        r"^\s*([A-Z_][A-Z0-9_]*)\s+(?:DECIMAL|VARCHAR|DOUBLE|TIMESTAMP|BOOLEAN)",
        block, re.MULTILINE))
    used = set(re.findall(r"\b([A-Z_][A-Z0-9_]*)\b",
                          B.INSERT_SQL.split("(", 1)[1].split(")", 1)[0]))
    assert used <= declared, f"insert names not in the table: {sorted(used - declared)}"
    placeholders = B.INSERT_SQL.count("?")
    assert placeholders == len(used) == 7


def test_record_sends_one_parameter_set_per_result(stub):
    results = B.s3_result_cache(stub, repeats=2)
    B.record(stub, results, datetime(2026, 10, 23))
    assert len(stub.executed) == len(results)
    assert all(len(p) == 7 for p in stub.executed)


def test_note_is_truncated_to_the_column_width(stub):
    long_note = [{"scenario": "S", "engine": "exasol", "rows_touched": 1,
                  "elapsed_ms": 1, "bytes_sent": 1, "note": "x" * 900}]
    B.record(stub, long_note, datetime(2026, 10, 23))
    assert len(stub.executed[0][6]) <= 400


def test_csv_snapshot_is_written_and_readable(tmp_path, stub, monkeypatch):
    monkeypatch.setattr(B, "REPO_ROOT", tmp_path)
    results = B.s1_scan_aggregate(stub)
    path = B.write_csv_snapshot(results, datetime(2026, 10, 23))
    lines = path.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 1 + len(results)
    assert lines[0].startswith("run_ts,scenario,engine")


def test_single_node_caveat_is_attached_to_every_exasol_note(stub, mirror):
    for row in B.s1_scan_aggregate(stub, mirror) + B.s3_result_cache(stub, 2):
        if row["engine"] == "exasol":
            assert "single data node" in row["note"] or "session" in row["note"]
