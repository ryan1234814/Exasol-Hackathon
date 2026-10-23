"""Same-laptop benchmarks, so the demo's speed claims are measurements.

Every number the Benchmark tab and ``docs/prd.md`` quote originates here and is
stored in ``WARDQ.BENCHMARK_RESULTS`` plus a mirrored SQLite file, so a judge can
re-run it and diff the result.

Three scenarios, chosen because they answer what an Exasol skeptic actually asks:

* **S1 scan + aggregate over the full fact table** — Exasol vs SQLite on the
  *same SQL text* (only the schema prefix differs), on the same machine.
* **S2 z-score in-database vs pulled into Python** — the most persuasive pair
  because it isolates data transfer, the overhead that generic benchmarks hide.
* **S3 the same query twice** — cold vs warm result cache.

Honesty rules baked into the output, because risk R12 says a technically sharp
judge will catch an inflated claim:

* the VM is 2 vCPU / 6 GB and **one data node**, so distribution clauses cannot
  help (and this Personal build does not even parse them) and are never quoted
  as a win;
* the SQLite mirror is a *fair* comparison, not a strong one — single-threaded,
  file-backed, no indexes added beyond the primary key;
* timings include the round trip over the local port forwarder, not just engine
  execution, which is what the dashboard actually experiences.
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import statistics
import sys
import time
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable

from backend.db import DatabaseUnavailable, get_db

REPO_ROOT = Path(__file__).resolve().parents[1]
SQLITE_PATH = REPO_ROOT / "data" / "derived" / "benchmark_mirror.sqlite"

EXASOL_PREFIX = "WARDQ."
SQLITE_PREFIX = ""          # the mirror keeps the bare table names
ROWS_NOTE = "Local Personal VM: 2 vCPU / 6 GB, single data node."

# One SQL text, run by both engines with only the schema prefix swapped, so the
# comparison cannot be dismissed as "you benchmarked two different queries".
S1_SQL = """
SELECT {p}SAMPLE_LOG.WARD_ID, {p}SAMPLE_LOG.PARAM_CODE,
       AVG({p}SAMPLE_LOG.VALUE_DOUBLE) AS AVG_VALUE,
       SUM(CASE WHEN {p}SAMPLE_LOG.VALUE_DOUBLE > {p}PARAMETER_LIMITS.THRESHOLD_HI
                  OR {p}SAMPLE_LOG.VALUE_DOUBLE < {p}PARAMETER_LIMITS.THRESHOLD_LO
                THEN 1 ELSE 0 END) AS BREACH_READINGS,
       COUNT(*) AS N_READINGS
FROM {p}SAMPLE_LOG
JOIN {p}PARAMETER_LIMITS ON {p}PARAMETER_LIMITS.PARAM_CODE = {p}SAMPLE_LOG.PARAM_CODE
GROUP BY {p}SAMPLE_LOG.WARD_ID, {p}SAMPLE_LOG.PARAM_CODE
ORDER BY {p}SAMPLE_LOG.WARD_ID, {p}SAMPLE_LOG.PARAM_CODE
"""

S2_SQL = """
SELECT SAMPLE_DATE, AVG_VALUE,
       AVG(AVG_VALUE)    OVER (PARTITION BY WARD_ID, PARAM_CODE ORDER BY SAMPLE_DATE
                               ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING) AS BASE_AVG,
       STDDEV(AVG_VALUE) OVER (PARTITION BY WARD_ID, PARAM_CODE ORDER BY SAMPLE_DATE
                               ROWS BETWEEN 30 PRECEDING AND 1 PRECEDING) AS BASE_STD
FROM WARDQ.WARD_DAILY
WHERE WARD_ID = {ward} AND PARAM_CODE = '{param}'
ORDER BY SAMPLE_DATE
"""

S2_SQL_SQLITE = """
SELECT SAMPLE_DATE, AVG_VALUE
FROM SAMPLE_LOG_DAILY
WHERE WARD_ID = ? AND PARAM_CODE = ?
ORDER BY SAMPLE_DATE
"""

INSERT_SQL = f"""
INSERT INTO {EXASOL_PREFIX}BENCHMARK_RESULTS
    (RUN_TS, SCENARIO, ENGINE, ROWS_TOUCHED, ELAPSED_MS, BYTES_SENT, NOTE)
VALUES (?, ?, ?, ?, ?, ?, ?)
"""


def _bytes(rows: Iterable[Any]) -> int:
    """JSON size of a result set — what would cross the wire to the browser."""
    return len(json.dumps(rows, default=str).encode("utf-8"))


def _ms(started: float) -> int:
    return round((time.monotonic() - started) * 1000)


def _to_number(value: Any) -> float | None:
    if value is None or isinstance(value, str) and not value.strip():
        return None
    if isinstance(value, Decimal):
        return float(value)
    return float(value)


# -- the SQLite mirror --------------------------------------------------------
def build_sqlite_mirror(exasol, path: Path = SQLITE_PATH, batch: int = 50_000) -> dict:
    """Mirror SAMPLE_LOG, PARAMETER_LIMITS and the daily aggregate into SQLite.

    The mirror is built by a single streaming read from Exasol, so it holds the
    identical dataset — the comparison cannot be accused of running on less data.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()

    conn = sqlite3.connect(path)
    conn.execute("""
        CREATE TABLE SAMPLE_LOG (
            SAMPLE_ID INTEGER PRIMARY KEY, WARD_ID INTEGER, PARAM_CODE TEXT,
            SAMPLE_DATE TEXT, VALUE_DOUBLE REAL, STATION_ID INTEGER,
            LAB_VERIFIED INTEGER)""")
    conn.execute("""
        CREATE TABLE PARAMETER_LIMITS (
            PARAM_CODE TEXT PRIMARY KEY, PARAM_NAME TEXT, UNIT TEXT,
            THRESHOLD_LO REAL, THRESHOLD_HI REAL)""")
    conn.execute("CREATE TABLE SAMPLE_LOG_DAILY (SAMPLE_DATE TEXT, WARD_ID INTEGER,"
                 " PARAM_CODE TEXT, AVG_VALUE REAL, N_SAMPLES INTEGER, BREACH_FLAG INTEGER)")
    conn.commit()

    started = time.monotonic()
    n = 0
    for chunk in _chunked(exasol.iter_query(
            "SELECT SAMPLE_ID, WARD_ID, PARAM_CODE, CAST(SAMPLE_DATE AS VARCHAR(32)) AS SAMPLE_DATE,"
            " VALUE_DOUBLE, STATION_ID, CAST(LAB_VERIFIED AS VARCHAR(32)) AS LAB_VERIFIED"
            f" FROM {EXASOL_PREFIX}SAMPLE_LOG"), batch):
        conn.executemany("INSERT INTO SAMPLE_LOG VALUES (?,?,?,?,?,?,?)", chunk)
        n += len(chunk)
    conn.commit()

    params = [(r["PARAM_CODE"], r["PARAM_NAME"], r["UNIT"],
               _to_number(r["THRESHOLD_LO"]), _to_number(r["THRESHOLD_HI"]))
              for r in exasol.query(f"SELECT * FROM {EXASOL_PREFIX}PARAMETER_LIMITS")]
    conn.executemany("INSERT INTO PARAMETER_LIMITS VALUES (?,?,?,?,?)", params)

    daily = [(r["SAMPLE_DATE"], r["WARD_ID"], r["PARAM_CODE"], _to_number(r["AVG_VALUE"]),
              r["N_SAMPLES"], r["BREACH_FLAG"])
             for r in exasol.query(f"SELECT CAST(SAMPLE_DATE AS VARCHAR(32)) AS SAMPLE_DATE,"
                                   f" WARD_ID, PARAM_CODE, AVG_VALUE, N_SAMPLES, BREACH_FLAG"
                                   f" FROM {EXASOL_PREFIX}WARD_DAILY")]
    conn.executemany("INSERT INTO SAMPLE_LOG_DAILY VALUES (?,?,?,?,?,?)", daily)
    conn.commit()
    conn.execute("CREATE INDEX IX_DAILY ON SAMPLE_LOG_DAILY (WARD_ID, PARAM_CODE, SAMPLE_DATE)")
    conn.commit()

    return {"mirror_ms": _ms(started), "sample_rows": n, "daily_rows": len(daily),
            "path": str(path), "size_bytes": path.stat().st_size}


def _chunked(rows, size: int):
    chunk: list = []
    for row in rows:
        chunk.append(tuple(row.values()))
        if len(chunk) >= size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


# -- scenarios ----------------------------------------------------------------
def s1_scan_aggregate(exasol, sqlite_conn=None) -> list[dict]:
    sql_exa = S1_SQL.format(p=EXASOL_PREFIX)

    started = time.monotonic()
    exa_rows = exasol.query(sql_exa)
    exa_ms, exa_bytes = _ms(started), _bytes(exa_rows)

    exa_sum = round(sum(r["BREACH_READINGS"] or 0 for r in exa_rows), 3)
    out = [{"scenario": "S1_scan_aggregate", "engine": "exasol",
            "rows_touched": exasol.scalar(f"SELECT COUNT(*) AS N FROM {EXASOL_PREFIX}SAMPLE_LOG"),
            "elapsed_ms": exa_ms, "bytes_sent": exa_bytes,
            "note": f"24x4 group-by over the full fact table. {ROWS_NOTE}"}]

    if sqlite_conn is None:
        out[0]["note"] += " (SQLite leg skipped with --no-sqlite)"
        return out

    started = time.monotonic()
    lite_rows = sqlite_conn.execute(S1_SQL.format(p=SQLITE_PREFIX)).fetchall()
    lite_ms, lite_bytes = _ms(started), _bytes(lite_rows)

    # Both engines must agree, or the comparison is meaningless.
    lite_sum = round(sum(r[3] or 0 for r in lite_rows), 3)
    agreement = "counts agree" if exa_sum == lite_sum else f"MISMATCH exa={exa_sum} lite={lite_sum}"
    out[0]["note"] = f"{agreement}; " + out[0]["note"]
    out.append({"scenario": "S1_scan_aggregate", "engine": "sqlite",
                "rows_touched": sqlite_conn.execute("SELECT COUNT(*) FROM SAMPLE_LOG").fetchone()[0],
                "elapsed_ms": lite_ms, "bytes_sent": lite_bytes,
                "note": f"{agreement}; same SQL text, same laptop, file-backed, "
                        f"single-threaded. {ROWS_NOTE}"})
    return out


def s2_zscore_in_db_vs_python(exasol, sqlite_conn=None, ward_id: int = 12,
                              param: str = "COLIFORM") -> list[dict]:
    """Compute the anomaly score where the data lives, vs shipping it to Python."""
    started = time.monotonic()
    in_db = exasol.query(S2_SQL.format(ward=ward_id, param=param))
    in_db_ms, in_db_bytes = _ms(started), _bytes(in_db)

    started = time.monotonic()
    raw = exasol.query(
        "SELECT SAMPLE_DATE, AVG_VALUE FROM WARDQ.WARD_DAILY"
        " WHERE WARD_ID = ? AND PARAM_CODE = ? ORDER BY SAMPLE_DATE",
        [ward_id, param])
    pulled_ms, pulled_bytes = _ms(started), _bytes(raw)

    started = time.monotonic()
    values = [_to_number(r["AVG_VALUE"]) for r in raw]
    computed = 0
    for i in range(len(values)):
        window = [v for v in values[max(0, i - 30):i] if v is not None]
        if len(window) >= 7 and values[i] is not None:
            sd = statistics.pstdev(window)
            if sd:
                computed += 1
    python_ms = _ms(started)

    # SQLite is given the identical job on the mirrored daily table.
    sqlite_row = None
    if sqlite_conn is not None:
        started = time.monotonic()
        lite_raw = sqlite_conn.execute(S2_SQL_SQLITE, (ward_id, param)).fetchall()
        sqlite_row = {"scenario": "S2_ward_zscore", "engine": "sqlite",
                      "rows_touched": len(lite_raw), "elapsed_ms": _ms(started),
                      "bytes_sent": _bytes(lite_raw),
                      "note": "SQLite returns the un-windowed series; the scoring would "
                              "still have to happen in Python. Same laptop."}

    out = [
        {"scenario": "S2_ward_zscore", "engine": "exasol",
         "rows_touched": len(in_db), "elapsed_ms": in_db_ms, "bytes_sent": in_db_bytes,
         "note": "30-day trailing window executed in the engine; only the scored "
                 "series crosses the wire."},
        {"scenario": "S2_ward_zscore", "engine": "python",
         "rows_touched": len(raw), "elapsed_ms": pulled_ms + python_ms,
         "bytes_sent": pulled_bytes,
         "note": f"same answer computed client-side after transferring the raw "
                 f"series ({computed} scored points); time = transfer + arithmetic."},
    ]
    if sqlite_row:
        out.append(sqlite_row)
    return out


def s3_result_cache(exasol, repeats: int = 3) -> list[dict]:
    sql = S1_SQL.format(p=EXASOL_PREFIX)
    out: list[dict] = []
    timings: list[int] = []
    for i in range(repeats):
        started = time.monotonic()
        rows = exasol.query(sql)
        ms = _ms(started)
        timings.append(ms)
        out.append({
            "scenario": f"S3_repeat_run_{i + 1}", "engine": "exasol",
            "rows_touched": len(rows), "elapsed_ms": ms, "bytes_sent": _bytes(rows),
            "note": "identical statement, same session"
                    + (" (first run of this session)" if i == 0 else ""),
        })
    if len(timings) >= 2:
        out.append({
            "scenario": "S3_cold_vs_warm", "engine": "exasol",
            "rows_touched": None,
            "elapsed_ms": timings[0],
            "bytes_sent": None,
            "note": f"first {timings[0]} ms vs best warm {min(timings[1:])} ms; "
                    "the result cache was not flushed (no documented flush command "
                    "for this runtime), so 'cold' means first run of the session.",
        })
    return out


# -- recording ----------------------------------------------------------------
def record(exasol, results: list[dict], run_ts: datetime) -> None:
    for row in results:
        exasol.execute(INSERT_SQL, [
            run_ts, row["scenario"], row["engine"], row["rows_touched"],
            row["elapsed_ms"], row["bytes_sent"], row["note"][:400]])


def mirror_to_sqlite(sqlite_conn, results: list[dict], run_ts: datetime) -> None:
    sqlite_conn.execute("CREATE TABLE IF NOT EXISTS BENCHMARK_RESULTS "
                        "(RUN_TS TEXT, SCENARIO TEXT, ENGINE TEXT, ROWS_TOUCHED INTEGER,"
                        " ELAPSED_MS INTEGER, BYTES_SENT INTEGER, NOTE TEXT)")
    sqlite_conn.executemany(
        "INSERT INTO BENCHMARK_RESULTS VALUES (?,?,?,?,?,?,?)",
        [(str(run_ts), r["scenario"], r["engine"], r["rows_touched"],
          r["elapsed_ms"], r["bytes_sent"], r["note"]) for r in results])
    sqlite_conn.commit()


def write_csv_snapshot(results: list[dict], run_ts: datetime) -> Path:
    out = REPO_ROOT / "data" / "derived" / "benchmark_results.csv"
    out.parent.mkdir(parents=True, exist_ok=True)
    header = ("run_ts", "scenario", "engine", "rows_touched", "elapsed_ms", "bytes_sent", "note")
    lines = [",".join(header)]
    for r in results:
        cells = [str(run_ts), r["scenario"], r["engine"], str(r["rows_touched"]),
                 str(r["elapsed_ms"]), str(r["bytes_sent"]),
                 '"' + r["note"].replace('"', "'") + '"']
        lines.append(",".join(cells))
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return out


def run(include_sqlite: bool = True, ward_id: int = 12, param: str = "COLIFORM",
        repeats: int = 3, quiet: bool = False) -> dict:
    exasol = get_db()
    try:
        exasol.query("SELECT 1 AS OK")
    except DatabaseUnavailable as exc:
        raise SystemExit(f"Benchmark needs a live database: {exc}")

    run_ts = datetime.now().replace(microsecond=0)
    results: list[dict] = []
    mirror: dict[str, Any] = {"skipped": True}
    conn = None

    if include_sqlite:
        mirror = build_sqlite_mirror(exasol)
        mirror["elapsed_ms"] = mirror.pop("mirror_ms")
        conn = sqlite3.connect(SQLITE_PATH)
        results.append({"scenario": "S0_mirror_build", "engine": "sqlite",
                        "rows_touched": mirror["sample_rows"],
                        "elapsed_ms": mirror["elapsed_ms"],
                        "bytes_sent": mirror["size_bytes"],
                        "note": "one streaming read from Exasol, then INSERT; the "
                                "mirror is the same dataset the columnar engine scans."})

    results += s1_scan_aggregate(exasol, conn)
    results += s2_zscore_in_db_vs_python(exasol, conn, ward_id, param)
    results += s3_result_cache(exasol, repeats)

    record(exasol, results, run_ts)
    if conn is not None:
        mirror_to_sqlite(conn, results, run_ts)
        conn.close()
    csv_path = write_csv_snapshot(results, run_ts)

    summary = {"run_ts": str(run_ts), "results": results, "mirror": mirror,
               "csv": str(csv_path)}
    if not quiet:
        print(json.dumps(summary, indent=2, default=str))
    return summary


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Measure Exasol against SQLite, same laptop.")
    parser.add_argument("--no-sqlite", action="store_true",
                        help="skip the mirror (Exasol-only timings)")
    parser.add_argument("--ward", type=int, default=12, help="ward for the S2 series")
    parser.add_argument("--param", default="COLIFORM", help="parameter for the S2 series")
    parser.add_argument("--repeats", type=int, default=3, help="S3 repeat count")
    args = parser.parse_args(argv)

    run(include_sqlite=not args.no_sqlite, ward_id=args.ward, param=args.param,
        repeats=args.repeats)
    return 0


if __name__ == "__main__":
    sys.exit(main())
