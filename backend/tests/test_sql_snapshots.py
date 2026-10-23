"""SQL snapshot tests.

Two groups, deliberately:

* the *static* checks run everywhere, with no database, and protect the property
  that makes the saved queries usable live — one statement, no leading comment,
  no stray semicolon, whitelist matching what is on disk;
* the *live* checks run only when the local database answers, and assert each
  demo query actually returns rows, so a silent empty result cannot be mistaken
  for a working demo.

The live group skips instead of failing when the database is down, because a
developer checkout has no reason to require a running VM to run the suite.
"""

import re
from functools import lru_cache
from pathlib import Path

import pytest

from backend.app import SQL_WHITELIST
from backend.db import DatabaseUnavailable, get_db

SQL_DIR = Path(__file__).resolve().parents[2] / "db" / "sql"
DEMO_QUERIES = sorted(SQL_DIR.glob("*.sql"))


@lru_cache(maxsize=1)
def database_up() -> bool:
    try:
        get_db().query("SELECT 1 AS OK")
        return True
    except DatabaseUnavailable:
        return False


requires_db = pytest.mark.skipif(not database_up(),
                                 reason="local Exasol database is not running")


# -- static: these always run -------------------------------------------------
def test_the_six_demo_queries_exist():
    names = {p.name for p in DEMO_QUERIES}
    assert names == {
        "latest_risk.sql", "monsoon_turbidity.sql", "outbreak_detection.sql",
        "deteriorating_wards.sql", "complaint_vs_lab_disagreement.sql",
        "complaint_category_mix.sql"}


@pytest.mark.parametrize("path", DEMO_QUERIES, ids=lambda p: p.name)
def test_each_demo_query_is_one_pasteable_statement(path):
    """exakit sql refuses anything but a single read statement.

    A leading comment line or a trailing semicolon is enough to make the live
    "show me the SQL that produced this number" moment fail, so the shape is
    asserted rather than remembered.
    """
    text = path.read_text(encoding="utf-8").strip()
    assert text.upper().startswith("SELECT"), f"{path.name} must be a read-only SELECT"
    assert ";" not in text, f"{path.name} has a statement terminator; exakit splits on it"
    assert "--" not in text, f"{path.name} contains a comment line"
    assert "\n(" not in text, f"{path.name} does not start with a SELECT"
    assert text.count("SELECT") >= 1
    assert re.search(r"\bLIMIT\s+\d+", text, re.IGNORECASE), \
        f"{path.name} must bound its own output; Exasol has no FETCH FIRST"


@pytest.mark.parametrize("name, filename", sorted(SQL_WHITELIST.items()))
def test_the_apps_sql_viewer_only_points_at_files_that_exist(name, filename):
    path = SQL_DIR.parent / filename
    assert path.is_file(), f"/api/sql/{name} would 404: {filename} is missing"
    assert path.read_text(encoding="utf-8").strip()


def test_the_ods_layer_files_are_present_and_ordered():
    db_dir = SQL_DIR.parent
    for expected in ("10_schema.sql", "20_seed_dims.sql", "30_generate_readings.sql",
                     "40_anomaly_window.sql", "50_udf_ward_risk.lua.sql",
                     "60_materialize.sql", "61_materialize_no_udf.sql", "70_verify.sql"):
        assert (db_dir / expected).is_file(), f"missing {expected}"


def test_no_demo_query_touches_the_raw_fact_table_without_aggregating():
    """The plan's performance promise: reads come from the materialized layer.

    SAMPLE_LOG is 289k rows and appears in exactly one saved query (the lab-vs-
    sensor view is already aggregated); a new query scanning it row-by-row would
    quietly break the sub-second claim.
    """
    offenders = [p.name for p in DEMO_QUERIES
                 if re.search(r"FROM\s+WARDQ\.SAMPLE_LOG", p.read_text(encoding="utf-8"),
                              re.IGNORECASE)]
    assert offenders == [], f"{offenders} read SAMPLE_LOG directly"


# -- live: skipped unless the database answers -------------------------------
@requires_db
@pytest.mark.parametrize("path", DEMO_QUERIES, ids=lambda p: p.name)
def test_each_demo_query_returns_rows(path):
    db = get_db()
    rows = db.query(path.read_text(encoding="utf-8").strip())
    assert rows, f"{path.name} returned nothing — the planted signal it proves is missing"
    assert all(row is not None for row in rows)


@requires_db
def test_planted_signals_are_detectable_not_just_present():
    """The assertions the demo narrative actually rests on."""
    db = get_db()

    outbreak = db.query("""
        SELECT COUNT(*) AS N FROM WARDQ.ANOMALY_EVENT
        WHERE WARD_ID = 12 AND PARAM_CODE = 'COLIFORM' AND Z_SCORE >= 2
    """)[0]["N"]
    assert int(outbreak) > 0, "the coliform outbreak must surface as an anomaly event"

    sensor_only = db.query("""
        SELECT COUNT(*) AS N FROM WARDQ.V_LAB_VS_SENSOR
        WHERE WARD_ID IN (9, 14) AND PARAM_CODE = 'PH'
          AND SENSOR_BREACHES > 0 AND LAB_BREACHES = 0
    """)[0]["N"]
    assert int(sensor_only) > 0, "the pH sensor-drift false positive must be detectable"

    monsoon = db.query("""
        SELECT SUM(CASE WHEN w.DOWNSTREAM THEN d.AVG_VALUE ELSE 0 END) AS DOWN,
               SUM(CASE WHEN NOT w.DOWNSTREAM THEN d.AVG_VALUE ELSE 0 END) AS UP
        FROM WARDQ.WARD_DAILY d JOIN WARDQ.WARD w ON w.WARD_ID = d.WARD_ID
        WHERE d.PARAM_CODE = 'TURBIDITY'
          AND SUBSTR(CAST(d.SAMPLE_DATE AS VARCHAR(32)), 6, 2) IN ('07','08','09')
    """)[0]
    down = float(monsoon["DOWN"])
    up = float(monsoon["UP"])
    # downstream wards carry per-ward means; the signal is a higher mean, and
    # the ward counts differ, so compare averages rather than sums
    down_n = int(db.query("""
        SELECT COUNT(*) AS N FROM WARDQ.WARD_DAILY d JOIN WARDQ.WARD w ON w.WARD_ID = d.WARD_ID
        WHERE d.PARAM_CODE='TURBIDITY' AND w.DOWNSTREAM
          AND SUBSTR(CAST(d.SAMPLE_DATE AS VARCHAR(32)),6,2) IN ('07','08','09')""")[0]["N"])
    up_n = int(db.query("""
        SELECT COUNT(*) AS N FROM WARDQ.WARD_DAILY d JOIN WARDQ.WARD w ON w.WARD_ID = d.WARD_ID
        WHERE d.PARAM_CODE='TURBIDITY' AND NOT w.DOWNSTREAM
          AND SUBSTR(CAST(d.SAMPLE_DATE AS VARCHAR(32)),6,2) IN ('07','08','09')""")[0]["N"])
    assert down / down_n > up / up_n, "monsoon turbidity must be higher downstream"


@requires_db
def test_the_materialized_layer_is_populated_and_fresh():
    db = get_db()
    for table in ("WARD_DAILY", "ANOMALY_EVENT", "WARD_MONTH_RISK", "COMPLAINT_SUMMARY"):
        n = int(db.scalar(f"SELECT COUNT(*) AS N FROM WARDQ.{table}"))
        assert n > 0, f"{table} is empty; run `make refresh`"
    assert db.scalar("SELECT MAX(GENERATED_AT) AS G FROM WARDQ.WARD_MONTH_RISK")


@requires_db
def test_row_counts_match_the_generator_promise():
    db = get_db()
    samples = int(db.scalar("SELECT COUNT(*) AS N FROM WARDQ.SAMPLE_LOG"))
    assert samples > 250_000, f"expected ~289k generated readings, found {samples}"
    complaints = int(db.scalar("SELECT COUNT(*) AS N FROM WARDQ.COMPLAINT"))
    assert complaints > 10_000, f"expected ~15k complaints, found {complaints}"


@requires_db
def test_risk_scores_stay_inside_the_documented_range():
    db = get_db()
    bad = db.query("""
        SELECT COUNT(*) AS N FROM WARDQ.WARD_MONTH_RISK
        WHERE RISK_SCORE < 0 OR RISK_SCORE > 100
    """)[0]["N"]
    assert int(bad) == 0, "RISK_SCORE is defined as 0..100; a value outside it means " \
                          "the UDF and the SQL fallback disagree"
