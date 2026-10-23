"""Load the COMPLAINT table: parse the real-shaped exports, then scale them up.

Run order matters and is encoded in the Makefile: ``db/10_schema.sql`` and
``db/20_seed_dims.sql`` must already have been applied, because the ward list is
read **from the database** rather than duplicated in Python. That is what keeps
``WARD_ID`` in the complaints pointing at wards that actually exist.

The complaint corpus is built in Python rather than SQL on purpose: the tagging
has to come from the same ``nlp_rules.classify`` the live ingest endpoint uses,
otherwise the demo would prove the rules work in one place and something else in
another.

Usage:
    python -m backend.load              # truncate + load + report
    python -m backend.load --dry-run    # build and validate, write nothing
    python -m backend.load --check      # compare the table against a rebuild
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime

from backend.db import DatabaseUnavailable, get_db
from backend.ingest.load_complaints import COLUMNS, build_all
from backend.nlp_rules import CATEGORIES, RULE_VERSION

INSERT_SHAPE = f"WARDQ.COMPLAINT ({', '.join(COLUMNS)})"
EXPECTED_WARDS = 24


def _wards_from_db(db) -> list[tuple[int, str]]:
    rows = db.query("SELECT WARD_ID, WARD_NAME FROM WARDQ.WARD ORDER BY WARD_ID")
    if not rows:
        raise SystemExit(
            "WARDQ.WARD is empty or missing. Apply db/10_schema.sql and "
            "db/20_seed_dims.sql first (see `make load`).")
    if len(rows) != EXPECTED_WARDS:
        # The seeded corpus and the planted signals assume 24 wards; a different
        # count means the seed did not run to completion, which would silently
        # shift every ward-level statistic.
        raise SystemExit(f"expected {EXPECTED_WARDS} wards in WARDQ.WARD, found {len(rows)}; "
                         "re-run db/20_seed_dims.sql")
    return [(int(r["WARD_ID"]), str(r["WARD_NAME"])) for r in rows]


def _tuples(rows: list[dict]) -> list[tuple]:
    # tuple(...) and not a bare comprehension: a generator inside the row list
    # would be consumed once by insert_multi and arrive empty.
    return [tuple(row[col] for col in COLUMNS) for row in rows]


def _stamp_run(db, step: str, rows: int, elapsed_ms: int, source: str) -> None:
    db.execute(
        "INSERT INTO WARDQ.LOAD_RUN (RUN_TS, STEP, ROWS_LOADED, ELAPSED_MS, LOAD_SOURCE) "
        "VALUES (?, ?, ?, ?, ?)",
        [datetime.now().replace(microsecond=0), step, rows, elapsed_ms, source[:200]])


def load(dry_run: bool = False) -> dict:
    db = get_db()
    wards = _wards_from_db(db)
    started = time.monotonic()
    rows, summary = build_all(wards)
    build_ms = round((time.monotonic() - started) * 1000)

    # Validate before a single byte is written: a partially loaded complaint
    # table is worse than an empty one because the dashboard would still render.
    _validate(rows, summary, wards)

    if not dry_run:
        db.execute("TRUNCATE TABLE WARDQ.COMPLAINT")
        started = time.monotonic()
        inserted = db.insert_many(INSERT_SHAPE, _tuples(rows))
        insert_ms = round((time.monotonic() - started) * 1000)
        _stamp_run(db, "complaints", inserted, insert_ms,
                   f"backend/load.py rule_engine={RULE_VERSION}")
        summary["insert_ms"] = insert_ms
        summary["inserted"] = inserted

    summary["build_ms"] = build_ms
    summary["wards_in_db"] = len(wards)
    return summary


def _validate(rows: list[dict], summary: dict, wards: list[tuple[int, str]]) -> None:
    ids = [r["COMPLAINT_ID"] for r in rows]
    if len(ids) != len(set(ids)):
        raise SystemExit("duplicate COMPLAINT_ID — the table has a primary key and would reject this")
    if len(rows) != summary["total_rows"]:
        raise SystemExit("row count disagrees with the summary")

    valid_wards = {wid for wid, _ in wards}
    stray = {r["WARD_ID"] for r in rows if r["WARD_ID"] is not None} - valid_wards
    if stray:
        raise SystemExit(f"complaints reference wards that do not exist: {sorted(stray)}")

    for row in rows:
        if row["CATEGORY"] not in CATEGORIES:
            raise SystemExit(f"unknown category {row['CATEGORY']!r} on complaint {row['COMPLAINT_ID']}")
        if not (0.0 <= float(row["CONFIDENCE"]) <= 1.0):
            raise SystemExit(f"confidence out of range on complaint {row['COMPLAINT_ID']}")
        if len(str(row["RAW_TEXT"])) > 2000 or len(str(row["RULE_EVIDENCE"])) > 400:
            raise SystemExit(f"text too long for the column on complaint {row['COMPLAINT_ID']}")

    contamination = summary["by_category"].get("contamination", 0)
    if contamination == 0:
        raise SystemExit("no contamination complaints were generated; the demo has nothing to show")


def check() -> dict:
    """Rebuild in Python and compare against what is stored, without writing."""
    db = get_db()
    stored = int(db.scalar("SELECT COUNT(*) AS N FROM WARDQ.COMPLAINT") or 0)
    wards = _wards_from_db(db)
    rows, summary = build_all(wards)
    per_category = db.query(
        "SELECT CATEGORY, COUNT(*) AS N FROM WARDQ.COMPLAINT GROUP BY CATEGORY")
    return {
        "stored_rows": stored,
        "rebuild_rows": summary["total_rows"],
        "matches": stored == summary["total_rows"],
        "stored_by_category": {r["CATEGORY"]: int(r["N"]) for r in per_category},
        "rebuild_by_category": summary["by_category"],
        "unattributed": int(db.scalar(
            "SELECT COUNT(*) AS N FROM WARDQ.COMPLAINT WHERE WARD_ID IS NULL") or 0),
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Load WARDQ.COMPLAINT from the fixtures + corpus.")
    parser.add_argument("--dry-run", action="store_true", help="build and validate only")
    parser.add_argument("--check", action="store_true", help="compare stored vs rebuild")
    args = parser.parse_args(argv)

    try:
        result = check() if args.check else load(dry_run=args.dry_run)
    except DatabaseUnavailable as exc:
        raise SystemExit(f"database unavailable: {exc}")

    # The parse reports are the honest part of the demo: they say how many lines
    # a real export refused to parse, so print them rather than hiding them.
    printable = dict(result)
    if "fixture_reports" in printable:
        printable["fixture_reports"] = [
            {k: (str(v) if isinstance(v, datetime) else v)
             for k, v in report.items() if k != "senders"}
            for report in printable["fixture_reports"]]
    print(json.dumps(printable, indent=2, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
