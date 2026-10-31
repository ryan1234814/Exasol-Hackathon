"""Lineage-registry tests — no database.

``/api/lineage`` is what lets the Trust page claim "every number on screen has a
file behind it". That claim only holds while the registry and the SQL whitelist
agree, so the drift is asserted here rather than trusted to review.
"""

from pathlib import Path

from backend.app import LINEAGE, SQL_WHITELIST

REPO_ROOT = Path(__file__).resolve().parents[2]


def test_every_claimed_step_is_a_real_sql_file():
    missing = [row["SQL_STEP"] for row in LINEAGE if row["SQL_STEP"] not in SQL_WHITELIST]
    assert missing == [], f"lineage names steps that /api/sql cannot serve: {missing}"


def test_no_endpoint_is_listed_twice():
    endpoints = [row["ENDPOINT"] for row in LINEAGE]
    assert len(endpoints) == len(set(endpoints))


def test_every_row_is_renderable():
    for row in LINEAGE:
        assert set(row) == {"ENDPOINT", "SQL_STEP", "TABLES", "NOTE"}
        assert all(str(value).strip() for value in row.values()), f"empty field in {row}"


def test_the_registry_covers_the_whole_read_surface():
    # A new read endpoint that forgets to register itself makes the Trust page
    # quietly incomplete, which is the one failure mode this page cannot have.
    assert len(LINEAGE) >= 12
    endpoints = {row["ENDPOINT"] for row in LINEAGE}
    for expected in ("/api/summary", "/api/wards", "/api/anomalies", "/api/leaderboard",
                     "/api/heatmap", "/api/disagreements", "/api/brief", "/api/complaints",
                     "/api/data-quality", "/api/forecast.ics", "/feed/brief.xml"):
        assert expected in endpoints, f"{expected} is missing from LINEAGE"


def test_every_whitelisted_step_points_at_a_file_on_disk():
    # The Trust page prints `run_sql.py db/<file>` next to each row. Deriving the
    # path from SQL_WHITELIST means that command can only be wrong if the
    # whitelist names a file that does not exist.
    missing = [
        (step, f"db/{name}")
        for step, name in SQL_WHITELIST.items()
        if not (REPO_ROOT / "db" / name).is_file()
    ]
    assert missing == [], f"whitelist names files that are not in the repo: {missing}"
