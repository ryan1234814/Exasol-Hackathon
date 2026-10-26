"""FastAPI application — the only HTTP surface the dashboard talks to.

Two rules shape every endpoint here, and they are the reason the demo stays fast
and stays honest:

1. **Reads touch the materialized layer only** (``WARD_DAILY``, ``ANOMALY_EVENT``,
   ``WARD_MONTH_RISK``, ``COMPLAINT_SUMMARY``) — never the 289k-row ``SAMPLE_LOG``,
   never a live UDF call. On the 2 vCPU / 6 GB local VM that is the difference
   between sub-second and a spinning wheel.

   One documented exception: ``/api/disagreements`` reads the pre-aggregated view
   ``WARDQ.V_LAB_VS_SENSOR``. That view groups the whole fact table, but the same
   aggregate measures **15 ms** on this VM (``BENCHMARK_RESULTS``,
   ``S1_scan_aggregate``/exasol), and materialising it into a fourth summary table
   would add three pipeline files to save single-digit milliseconds.
2. **Everything is SELECT-only or preview-only.** The ingest endpoints parse and
   classify and return what *would* be written; they write nothing, so the demo
   can be re-run on stage as often as a judge likes (see risk R10 in the plan).

Every value comes from a query, and every query is timed by ``db.ExasolDB`` so
``/api/benchmark`` can quote a measurement instead of an estimate.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import Body, FastAPI, File, HTTPException, Query, UploadFile
from fastapi.staticfiles import StaticFiles

from backend import brief, forecast, nlp_rules
from backend.db import DatabaseUnavailable, get_db
from backend.ingest.load_complaints import build_ward_map, ward_from_filename
from backend.ingest.tabular import UPLOAD_ID_BASE, load_tabular
from backend.ingest.whatsapp_parser import parse_chat

REPO_ROOT = Path(__file__).resolve().parents[1]
DIST_DIR = REPO_ROOT / "frontend" / "dist"
DB_DIR = REPO_ROOT / "db"

# The spine date 30_generate_readings.sql was built on; bucketing is arithmetic
# against it rather than DATE_TRUNC, which is not relied upon anywhere.
SPINE_START_SQL = "DATE '2024-10-01'"

# Only these files are ever served back as text, so the SQL viewer cannot be
# turned into a general file reader.
SQL_WHITELIST = {
    "anomaly_window": "40_anomaly_window.sql",
    "udf_risk": "50_udf_ward_risk.lua.sql",
    "materialize": "60_materialize.sql",
    "verify": "70_verify.sql",
    "latest_risk": "sql/latest_risk.sql",
    "monsoon_turbidity": "sql/monsoon_turbidity.sql",
    "complaint_vs_lab_disagreement": "sql/complaint_vs_lab_disagreement.sql",
    "outbreak_detection": "sql/outbreak_detection.sql",
    "deteriorating_wards": "sql/deteriorating_wards.sql",
    "complaint_category_mix": "sql/complaint_category_mix.sql",
    "forecast_eta": "sql/forecast_eta.sql",
    "sensor_vs_lab": "sql/sensor_vs_lab.sql",
    "ward_month_matrix": "sql/ward_month_matrix.sql",
    "morning_brief": "sql/morning_brief.sql",
}

MAX_TREND_POINTS = 500

# One pattern for every endpoint that takes a parameter, so a new parameter
# cannot be accepted by one route and rejected by another.
PARAM_PATTERN = "^(TURBIDITY|CHLORINE|COLIFORM|PH)$"

app = FastAPI(
    title="Ward Water Quality & Complaint Triage",
    version="1.0",
    description="Analytics executed inside a local Exasol Personal database.",
)


# -- plumbing -----------------------------------------------------------------
def _rows(sql: str, params: list[Any] | None = None) -> list[dict]:
    """Run a read, translating a dead database into a clear 503.

    The detail text names the remedy because on stage the person reading it is
    not the person who wrote it.
    """
    try:
        return get_db().query(sql, params)
    except DatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _one(sql: str, params: list[Any] | None = None) -> dict:
    rows = _rows(sql, params)
    return rows[0] if rows else {}


def _scalar(sql: str, params: list[Any] | None = None):
    try:
        return get_db().scalar(sql, params)
    except DatabaseUnavailable as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


def _latest_month() -> str:
    """Newest materialized month, or a 503 telling the operator to refresh."""
    month = _scalar("SELECT MAX(SAMPLE_MONTH) AS M FROM WARDQ.WARD_MONTH_RISK")
    if not month:
        raise HTTPException(
            status_code=503,
            detail="WARD_MONTH_RISK is empty — run `make load` then `make refresh`.",
        )
    return str(month)


def _wards() -> list[tuple[int, str]]:
    rows = _rows("SELECT WARD_ID, WARD_NAME FROM WARDQ.WARD ORDER BY WARD_ID")
    return [(int(r["WARD_ID"]), str(r["WARD_NAME"])) for r in rows]


def _moving_average(values: list[float], window: int) -> list[float | None]:
    """Trailing mean over the *displayed* series.

    This is presentation smoothing of an already-small (<500 point) payload.
    The analytical windowing that matters — 30-day baseline, z-score, slope —
    lives in 40_anomaly_window.sql and is materialized, not recomputed here.
    """
    out: list[float | None] = []
    for i in range(len(values)):
        start = max(0, i - window + 1)
        chunk = [v for v in values[start:i + 1] if v is not None]
        out.append(round(sum(chunk) / len(chunk), 4) if chunk else None)
    return out


# -- health and summary -------------------------------------------------------
@app.get("/api/health")
def health() -> dict:
    """Reachability plus how fresh the materialized layer is."""
    payload: dict[str, Any] = get_db().health()
    if payload.get("database") == "up":
        payload["generated_at"] = _scalar(
            "SELECT MAX(GENERATED_AT) AS G FROM WARDQ.WARD_MONTH_RISK")
        payload["materialized_months"] = _scalar(
            "SELECT COUNT(DISTINCT SAMPLE_MONTH) AS N FROM WARDQ.WARD_MONTH_RISK")
        payload["mock"] = False
    else:
        payload["mock"] = True
    return payload


def _summary_payload() -> dict:
    """The header strip: scale, freshness, and tonight's worst ward.

    Shared with ``/api/brief`` so the two cannot drift into different numbers.
    """
    month = _latest_month()
    counts = {
        "sample_rows": _scalar("SELECT COUNT(*) AS N FROM WARDQ.SAMPLE_LOG"),
        "complaint_rows": _scalar("SELECT COUNT(*) AS N FROM WARDQ.COMPLAINT"),
        "wards": _scalar("SELECT COUNT(*) AS N FROM WARDQ.WARD"),
        "high_severity_complaints": _scalar(
            "SELECT COUNT(*) AS N FROM WARDQ.COMPLAINT WHERE SEVERITY = 'high'"),
    }
    worst = _one("""
        SELECT r.WARD_ID, w.WARD_NAME, w.CITY, r.RISK_SCORE, r.WORST_PARAM,
               r.COMPLAINT_DENSITY, r.RANK_IN_MONTH
        FROM WARDQ.WARD_MONTH_RISK r
        JOIN WARDQ.WARD w ON w.WARD_ID = r.WARD_ID
        WHERE r.SAMPLE_MONTH = ? AND r.RANK_IN_MONTH = 1
    """, [month])
    trend = _rows("""
        SELECT SAMPLE_MONTH, AVG(RISK_SCORE) AS AVG_RISK, MAX(RISK_SCORE) AS MAX_RISK,
               SUM(COMPLAINT_DENSITY) AS DENSITY
        FROM WARDQ.WARD_MONTH_RISK
        GROUP BY SAMPLE_MONTH
        ORDER BY SAMPLE_MONTH
    """)
    as_of = _one("""
        SELECT MAX(RUN_TS) AS LAST_RUN_TS, LOAD_SOURCE
        FROM WARDQ.LOAD_RUN
        GROUP BY LOAD_SOURCE
        ORDER BY LAST_RUN_TS DESC
        LIMIT 1
    """)
    return {
        "month": month,
        "counts": counts,
        "worst_ward": worst,
        "risk_trend": trend,
        "data_as_of": as_of,
    }


@app.get("/api/summary")
def summary() -> dict:
    """/api/brief calls the same builder; this endpoint is the header strip."""
    return _summary_payload()


# -- wards --------------------------------------------------------------------
@app.get("/api/wards")
def wards() -> list[dict]:
    """Every ward with its current risk, which is what the heatmap renders."""
    month = _latest_month()
    return _rows("""
        SELECT w.WARD_ID, w.WARD_NAME, w.CITY, w.CITY_ZONE, w.POPULATION, w.CONNECTIONS,
               w.DOWNSTREAM, r.SAMPLE_MONTH, r.RISK_SCORE, r.WORST_PARAM,
               r.COMPLAINT_DENSITY, r.RANK_IN_MONTH,
               r.Z_COMPONENT, r.BREACH_COMPONENT, r.SLOPE_COMPONENT, r.COMPLAINT_COMP
        FROM WARDQ.WARD w
        LEFT JOIN WARDQ.WARD_MONTH_RISK r
               ON r.WARD_ID = w.WARD_ID AND r.SAMPLE_MONTH = ?
        ORDER BY r.RISK_SCORE DESC NULLS LAST, w.WARD_ID
    """, [month])


@app.get("/api/wards/{ward_id}/trend")
def ward_trend(ward_id: int,
               param: str = Query("TURBIDITY", pattern=PARAM_PATTERN),
               bucket_days: int = Query(7, ge=1, le=31),
               limit: int = Query(MAX_TREND_POINTS, ge=10, le=MAX_TREND_POINTS)) -> dict:
    """One ward x one parameter, bucketed server-side to <=500 points.

    ``bucket_days`` is a day count rather than a keyword (``week``/``month``) so
    the bucketing stays integer arithmetic on the spine date and never depends
    on a date-truncation function the local dialect may not offer.
    """
    ward = _one("SELECT * FROM WARDQ.WARD WHERE WARD_ID = ?", [ward_id])
    if not ward:
        raise HTTPException(status_code=404, detail=f"ward {ward_id} not found")

    threshold = _one("SELECT * FROM WARDQ.PARAMETER_LIMITS WHERE PARAM_CODE = ?", [param])
    series = _rows(f"""
        SELECT BUCKET,
               MIN(SUBSTR(CAST(SAMPLE_DATE AS VARCHAR(32)), 1, 10)) AS BUCKET_START,
               AVG(AVG_VALUE)  AS AVG_VALUE,
               MIN(MIN_VALUE)  AS MIN_VALUE,
               MAX(MAX_VALUE)  AS MAX_VALUE,
               SUM(N_SAMPLES)  AS N_SAMPLES,
               SUM(BREACH_FLAG) AS BREACH_READINGS,
               COUNT(*)        AS N_DAYS
        FROM (
            SELECT FLOOR(DAYS_BETWEEN(SAMPLE_DATE, {SPINE_START_SQL}) / ?) AS BUCKET,
                   SAMPLE_DATE, AVG_VALUE, MIN_VALUE, MAX_VALUE, N_SAMPLES, BREACH_FLAG
            FROM WARDQ.WARD_DAILY
            WHERE WARD_ID = ? AND PARAM_CODE = ?
        ) DAILY
        GROUP BY BUCKET
        ORDER BY BUCKET
        LIMIT ?
    """, [bucket_days, ward_id, param, limit])

    anomalies = _rows("""
        SELECT SAMPLE_MONTH, Z_SCORE, MOVING_AVG, BREACH_DAYS, CONSECUTIVE_RUN,
               SLOPE_12M, SEVERITY
        FROM WARDQ.ANOMALY_EVENT
        WHERE WARD_ID = ? AND PARAM_CODE = ?
        ORDER BY SAMPLE_MONTH
    """, [ward_id, param])

    values = [r["AVG_VALUE"] for r in series]
    for row, smoothed, trailing in zip(series, values, _moving_average(values, 4)):
        row["DISPLAY_VALUE"] = smoothed
        row["TRAILING_AVG"] = trailing

    return {
        "ward": ward,
        "parameter": threshold,
        "bucket_days": bucket_days,
        "points": len(series),
        "series": series,
        "anomalies": anomalies,
        "query_ms": get_db().last_query_ms,
    }


# -- anomalies and leaderboard ------------------------------------------------
@app.get("/api/anomalies")
def anomalies(month: str | None = None,
              ward_id: int | None = None,
              param: str | None = Query(None, pattern=PARAM_PATTERN),
              limit: int = Query(200, ge=1, le=1000)) -> dict:
    """Flagged ward x parameter x month rows, worst first."""
    month = month or _latest_month()
    where = ["a.SAMPLE_MONTH = ?"]
    params: list[Any] = [month]
    if ward_id is not None:
        where.append("a.WARD_ID = ?")
        params.append(ward_id)
    if param:
        where.append("a.PARAM_CODE = ?")
        params.append(param)
    params.append(limit)

    rows = _rows(f"""
        SELECT a.SAMPLE_MONTH, a.WARD_ID, w.WARD_NAME, w.CITY, w.DOWNSTREAM,
               a.PARAM_CODE, p.PARAM_NAME, p.UNIT, p.THRESHOLD_LO, p.THRESHOLD_HI,
               a.MOVING_AVG, a.BASELINE_STDDEV, a.Z_SCORE, a.BREACH_DAYS,
               a.CONSECUTIVE_RUN, a.SLOPE_12M, a.SEVERITY
        FROM WARDQ.ANOMALY_EVENT a
        JOIN WARDQ.WARD w ON w.WARD_ID = a.WARD_ID
        JOIN WARDQ.PARAMETER_LIMITS p ON p.PARAM_CODE = a.PARAM_CODE
        WHERE {' AND '.join(where)}
        ORDER BY ABS(a.Z_SCORE) DESC, a.CONSECUTIVE_RUN DESC
        LIMIT ?
    """, params)
    return {"month": month, "count": len(rows), "rows": rows,
            "explanation_step": "anomaly_window", "source_step": "materialize"}


@app.get("/api/leaderboard")
def leaderboard(month: str | None = None,
                 limit: int = Query(10, ge=1, le=24)) -> dict:
    """The wards to visit first, with the complaint volume that agrees with them."""
    month = month or _latest_month()
    rows = _rows("""
        SELECT r.SAMPLE_MONTH, r.WARD_ID, w.WARD_NAME, w.CITY, w.CITY_ZONE, w.CONNECTIONS,
               r.RISK_SCORE, r.RANK_IN_MONTH, r.WORST_PARAM, r.COMPLAINT_DENSITY,
               r.Z_COMPONENT, r.BREACH_COMPONENT, r.SLOPE_COMPONENT, r.COMPLAINT_COMP,
               s.N_COMPLAINTS, s.N_HIGH_SEV
        FROM WARDQ.WARD_MONTH_RISK r
        JOIN WARDQ.WARD w ON w.WARD_ID = r.WARD_ID
        LEFT JOIN (
            SELECT WARD_ID, SAMPLE_MONTH,
                   SUM(N_COMPLAINTS) AS N_COMPLAINTS,
                   SUM(N_HIGH_SEV)   AS N_HIGH_SEV
            FROM WARDQ.COMPLAINT_SUMMARY
            GROUP BY WARD_ID, SAMPLE_MONTH
        ) s ON s.WARD_ID = r.WARD_ID AND s.SAMPLE_MONTH = r.SAMPLE_MONTH
        WHERE r.SAMPLE_MONTH = ?
        ORDER BY r.RISK_SCORE DESC
        LIMIT ?
    """, [month, limit])
    return {"month": month, "rows": rows}


# -- time machine, forecast, disagreements, morning brief ---------------------
@app.get("/api/heatmap")
def heatmap(months: int = Query(13, ge=1, le=25)) -> dict:
    """Ward x month risk for the replay slider, prefetched in one payload.

    The whole table is ~600 rows, so one query beats re-fetching per slider tick
    during the replay; the browser then animates with no network at all.
    """
    rows = _rows("""
        SELECT SAMPLE_MONTH, WARD_ID, RISK_SCORE, WORST_PARAM, RANK_IN_MONTH,
               COMPLAINT_DENSITY
        FROM WARDQ.WARD_MONTH_RISK
        ORDER BY SAMPLE_MONTH DESC, WARD_ID
    """)
    window = set(sorted({str(r["SAMPLE_MONTH"]) for r in rows}, reverse=True)[:months])
    cells = sorted((r for r in rows if str(r["SAMPLE_MONTH"]) in window),
                   key=lambda r: (str(r["SAMPLE_MONTH"]), int(r["WARD_ID"])))
    dims = _rows("""
        SELECT WARD_ID, WARD_NAME, CITY, CITY_ZONE, POPULATION, CONNECTIONS, DOWNSTREAM
        FROM WARDQ.WARD ORDER BY WARD_ID
    """)
    return {"months": sorted(window), "wards": dims, "cells": cells,
            "months_returned": len(window), "query_ms": get_db().last_query_ms}


@app.get("/api/wards/{ward_id}/forecast")
def ward_forecast(ward_id: int,
                  param: str | None = Query(None, pattern=PARAM_PATTERN),
                  horizon_days: int = Query(90, ge=30, le=365)) -> dict:
    """Breach ETA per parameter, from the 30-day mean and the 12-month slope.

    ``param`` is optional so the ward case file can ask for all four parameters
    in one round trip. The arithmetic lives in ``backend.forecast`` — this
    endpoint only gathers and labels.
    """
    ward = _one("SELECT * FROM WARDQ.WARD WHERE WARD_ID = ?", [ward_id])
    if not ward:
        raise HTTPException(status_code=404, detail=f"ward {ward_id} not found")

    where = ["WARD_ID = ?"]
    params: list[Any] = [ward_id]
    if param:
        where.append("PARAM_CODE = ?")
        params.append(param)
    rows = _rows(f"""
        SELECT * FROM WARDQ.V_WARD_FORECAST
        WHERE {' AND '.join(where)}
        ORDER BY PARAM_CODE
    """, params)

    items = [forecast.summarise(row, horizon_days) for row in rows]
    return {
        "ward": ward,
        "horizon_days": horizon_days,
        "items": items,
        "item": items[0] if param and items else None,
        "method": ("trailing 12-month ordinary-least-squares slope over the daily "
                   "aggregate, extended linearly; the band is 1.96 sigma of the last "
                   "30 daily means widening as sqrt(days / 7)"),
        "query_ms": get_db().last_query_ms,
    }


def _verdict(row: dict) -> str:
    """Did the lab agree with the sensor this month?"""
    sensor = int(row.get("SENSOR_BREACHES") or 0)
    lab = int(row.get("LAB_BREACHES") or 0)
    if lab > 0:
        return "lab_confirmed"
    if sensor > 0:
        return "instrument_suspect"
    return "consistent"


def _disagreement_rows(month: str, ward_id: int | None = None,
                       param: str | None = None, limit: int = 100) -> list[dict]:
    """Sensor-only breaches, lab-confirmed breaches and the complaints beside them."""
    where = ["lv.SAMPLE_MONTH = ?"]
    params: list[Any] = [month]
    if ward_id is not None:
        where.append("lv.WARD_ID = ?")
        params.append(ward_id)
    if param:
        where.append("lv.PARAM_CODE = ?")
        params.append(param)
    params.append(limit)

    rows = _rows(f"""
        SELECT lv.SAMPLE_MONTH, lv.WARD_ID, lv.WARD_NAME, lv.PARAM_CODE, lv.UNIT,
               lv.THRESHOLD_LO, lv.THRESHOLD_HI,
               lv.SENSOR_READINGS, lv.LAB_READINGS,
               lv.SENSOR_BREACHES, lv.LAB_BREACHES,
               COALESCE(c.N_COMPLAINTS, 0) AS CITIZEN_COMPLAINTS_THAT_MONTH
        FROM WARDQ.V_LAB_VS_SENSOR lv
        LEFT JOIN (
            SELECT SAMPLE_MONTH, WARD_ID, SUM(N_COMPLAINTS) AS N_COMPLAINTS
            FROM WARDQ.COMPLAINT_SUMMARY
            WHERE CATEGORY = 'contamination'
            GROUP BY SAMPLE_MONTH, WARD_ID
        ) c ON c.SAMPLE_MONTH = lv.SAMPLE_MONTH AND c.WARD_ID = lv.WARD_ID
        WHERE {' AND '.join(where)}
        ORDER BY lv.SENSOR_BREACHES DESC, lv.LAB_BREACHES, lv.WARD_ID
        LIMIT ?
    """, params)
    for row in rows:
        row["VERDICT"] = _verdict(row)
    return rows


@app.get("/api/disagreements")
def disagreements(month: str | None = None,
                  ward_id: int | None = None,
                  param: str | None = Query(None, pattern=PARAM_PATTERN),
                  limit: int = Query(100, ge=1, le=500)) -> dict:
    """The 'but the lab says compliant' view, one month at a time."""
    month = month or _latest_month()
    rows = _disagreement_rows(month, ward_id, param, limit)
    mix: dict[str, int] = {}
    for row in rows:
        mix[row["VERDICT"]] = mix.get(row["VERDICT"], 0) + 1
    return {"month": month, "count": len(rows), "verdict_mix": mix, "rows": rows,
            "note": ("SENSOR_BREACHES counts readings outside the BIS limit from "
                     "unverified probes; LAB_BREACHES counts lab-confirmed ones. "
                     "One 288k-row aggregate per request — 15 ms measured."),
            "query_ms": get_db().last_query_ms}


@app.get("/api/brief")
def morning_brief(month: str | None = None) -> dict:
    """Three prioritised actions, composed from SQL results by backend/brief.py."""
    month = month or _latest_month()

    counts = _one("""
        SELECT (SELECT COUNT(*) FROM WARDQ.SAMPLE_LOG)              AS SAMPLE_ROWS,
               (SELECT COUNT(*) FROM WARDQ.COMPLAINT)               AS COMPLAINT_ROWS,
               (SELECT COUNT(*) FROM WARDQ.WARD)                    AS WARDS,
               (SELECT COUNT(*) FROM WARDQ.COMPLAINT
                 WHERE SEVERITY = 'high')                AS HIGH_SEVERITY_COMPLAINTS
    """)
    # brief.py speaks lowercase count keys, which is also what /api/summary returns.
    counts = {str(k).lower(): v for k, v in counts.items()}

    ranked = _rows("""
        SELECT r.WARD_ID, w.WARD_NAME, w.CITY, r.RISK_SCORE, r.RANK_IN_MONTH,
               r.WORST_PARAM, r.Z_COMPONENT, r.BREACH_COMPONENT, r.SLOPE_COMPONENT,
               r.COMPLAINT_COMP,
               COALESCE(s.N_COMPLAINTS, 0) AS N_COMPLAINTS,
               COALESCE(s.N_HIGH_SEV, 0)   AS N_HIGH_SEV
        FROM WARDQ.WARD_MONTH_RISK r
        JOIN WARDQ.WARD w ON w.WARD_ID = r.WARD_ID
        LEFT JOIN (
            SELECT WARD_ID, SUM(N_COMPLAINTS) AS N_COMPLAINTS,
                   SUM(N_HIGH_SEV) AS N_HIGH_SEV
            FROM WARDQ.COMPLAINT_SUMMARY
            WHERE SAMPLE_MONTH = ?
            GROUP BY WARD_ID
        ) s ON s.WARD_ID = r.WARD_ID
        WHERE r.SAMPLE_MONTH = ?
        ORDER BY r.RANK_IN_MONTH
        LIMIT 6
    """, [month, month])

    forecast_items = [forecast.summarise(row)
                      for row in _rows("SELECT * FROM WARDQ.V_WARD_FORECAST")]
    findings = _disagreement_rows(month, limit=200)
    freshness = _one("""
        SELECT MAX(RUN_TS) AS LAST_RUN_TS, LOAD_SOURCE
        FROM WARDQ.LOAD_RUN
        GROUP BY LOAD_SOURCE
        ORDER BY LAST_RUN_TS DESC
        LIMIT 1
    """)

    payload = brief.build_brief(month=month, counts=counts, ranked=ranked,
                                forecast_items=forecast_items,
                                disagreements=findings, freshness=freshness)
    payload["query_ms"] = get_db().last_query_ms
    return payload


# -- complaints ---------------------------------------------------------------
_SEVERITY_RANK = ("CASE c.SEVERITY WHEN 'high' THEN 0 WHEN 'medium' THEN 1 "
                  "WHEN 'low' THEN 2 ELSE 3 END")


@app.get("/api/complaints")
def complaints(category: str | None = None,
               ward_id: int | None = None,
               q: str | None = None,
               since: str | None = Query(None, pattern=r"^\d{4}-\d{2}(-\d{2})?$"),
               limit: int = Query(50, ge=1, le=500),
               offset: int = Query(0, ge=0, le=100000)) -> dict:
    """The triage queue: filterable, searchable, paged with ``LIMIT/OFFSET``.

    ``q`` is bound as a parameter, never concatenated, so a judge typing an
    apostrophe into the search box gets a result rather than a syntax error.
    """
    where, params = [], []
    if category:
        where.append("LOWER(c.CATEGORY) = ?")
        params.append(category.lower())
    if ward_id is not None:
        where.append("c.WARD_ID = ?")
        params.append(ward_id)
    if q:
        where.append("(UPPER(c.RAW_TEXT) LIKE ? OR UPPER(c.RULE_EVIDENCE) LIKE ?)")
        like = f"%{q.upper()}%"
        params.extend([like, like])
    if since:
        # ISO string comparison on a timestamp renders as 'YYYY-MM-DD ...'
        where.append("SUBSTR(CAST(c.RECEIVED_TS AS VARCHAR(32)), 1, 10) >= ?")
        params.append(since if len(since) == 10 else f"{since}-01")

    clause = ("WHERE " + " AND ".join(where)) if where else ""
    total = _scalar(f"""
        SELECT COUNT(*) AS N FROM WARDQ.COMPLAINT c {clause}
    """, list(params))

    rows = _rows(f"""
        SELECT c.COMPLAINT_ID, c.WARD_ID, w.WARD_NAME, c.RECEIVED_TS, c.SENDER_HANDLE,
               c.RAW_TEXT, c.CATEGORY, c.SEVERITY, c.CONFIDENCE, c.RULE_EVIDENCE,
               c.RULE_VERSION, c.CHANNEL
        FROM WARDQ.COMPLAINT c
        LEFT JOIN WARDQ.WARD w ON w.WARD_ID = c.WARD_ID
        {clause}
        ORDER BY {_SEVERITY_RANK}, c.RECEIVED_TS DESC, c.COMPLAINT_ID
        LIMIT ? OFFSET ?
    """, [*params, limit, offset])

    mix = _rows(f"""
        SELECT c.CATEGORY, COUNT(*) AS N,
               SUM(CASE WHEN c.SEVERITY = 'high' THEN 1 ELSE 0 END) AS N_HIGH
        FROM WARDQ.COMPLAINT c {clause}
        GROUP BY c.CATEGORY
        ORDER BY N DESC
    """, list(params))

    return {"total": total, "limit": limit, "offset": offset,
            "category_mix": mix, "rows": rows}


# -- ingest (preview only, never writes) --------------------------------------
@app.post("/api/ingest/chat")
async def ingest_chat(file: UploadFile = File(...),
                      ward_id: int | None = Query(None)) -> dict:
    """Parse a WhatsApp export and classify it, without touching the database.

    The ward default is taken from ``--ward`` when supplied, otherwise from the
    filename, because ``ward_4_dharavi_export.txt`` genuinely is that ward's
    group and a message that names no place should still land somewhere useful.
    Anything left unresolved stays NULL and is reported, not guessed.
    """
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="empty upload")
    raw = content.decode("utf-8", errors="replace")

    wards = _wards()
    ward_map = build_ward_map(wards)
    stem = Path(file.filename or "chat").stem.replace("_export", "")
    default_ward = ward_id or ward_from_filename(stem, ward_map)

    messages, report = parse_chat(raw, ward_map=ward_map,
                                  default_ward_id=default_ward, channel="whatsapp")

    tagged, mix = [], {}
    for message in messages:
        tag = nlp_rules.classify(message["text"])
        mix[tag["category"]] = mix.get(tag["category"], 0) + 1
        tagged.append({**message, **tag})

    # Stable sort on one flag: high-severity first, chat order kept underneath.
    # Sorting by timestamp as a tiebreak is deliberately avoided - a media-only
    # or unparseable row can carry a NULL timestamp, and comparing a datetime
    # against a placeholder is exactly the TypeError a live demo would hit.
    high_first = sorted(tagged, key=lambda m: m["severity"] != "high")

    return {
        "filename": file.filename,
        "default_ward_id": default_ward,
        "report": report,
        "category_mix": mix,
        "rule_version": nlp_rules.RULE_VERSION,
        "written": 0,
        "preview": high_first[:50],
        "note": "Preview only: nothing was inserted, so this is safe to re-run.",
    }


@app.post("/api/ingest/logs")
async def ingest_logs(file: UploadFile = File(...)) -> dict:
    """Validate a lab register (CSV/XLSX) and report per-row problems.

    Sample ids are allocated from the upload range so the preview shows the exact
    rows an accepted upload would insert, collisions included.
    """
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="empty upload")

    max_id = _scalar(
        "SELECT MAX(SAMPLE_ID) AS M FROM WARDQ.SAMPLE_LOG WHERE SAMPLE_ID >= ?",
        [UPLOAD_ID_BASE])
    id_base = (int(max_id) + 1) if max_id else UPLOAD_ID_BASE

    rows, report = load_tabular(file.filename or "register.csv", content, id_base=id_base)
    valid_wards = {wid for wid, _ in _wards()}
    unknown = sorted({r["WARD_ID"] for r in rows} - valid_wards)

    return {"rows": rows[:100], "report": report,
            "unknown_ward_ids": unknown, "written": 0,
            "note": "Validation preview; the register is not written by this endpoint."}


@app.post("/api/classify")
def classify(payload: dict = Body(...)) -> dict:
    """One sentence in, category + the rule that fired out.

    This is the live on-stage moment: a judge supplies the sentence, the answer
    is explainable because ``EVIDENCE`` is the phrase that matched.
    """
    text = str(payload.get("text") or "")
    result = nlp_rules.classify(text)
    return {"input": text[:500], **result}


# -- transparency -------------------------------------------------------------
@app.get("/api/sql/{step}")
def sql_source(step: str) -> dict:
    """Return the SQL that produced a number, for the click-through drawer."""
    name = SQL_WHITELIST.get(step)
    if name is None:
        raise HTTPException(status_code=404,
                            detail=f"unknown step; try one of {sorted(SQL_WHITELIST)}")
    path = DB_DIR / name
    if not path.is_file():
        raise HTTPException(status_code=404, detail=f"{name} is not present")
    return {"step": step, "file": f"db/{name}", "sql": path.read_text(encoding="utf-8")}


@app.get("/api/benchmark")
def benchmark(limit: int = Query(60, ge=1, le=200)) -> dict:
    """Measured timings, straight out of WARDQ.BENCHMARK_RESULTS.

    No number on the benchmark tab is allowed to originate anywhere else.
    """
    rows = _rows("""
        SELECT RUN_TS, SCENARIO, ENGINE, ROWS_TOUCHED, ELAPSED_MS, BYTES_SENT, NOTE
        FROM WARDQ.BENCHMARK_RESULTS
        ORDER BY RUN_TS DESC, SCENARIO, ENGINE
        LIMIT ?
    """, [limit])
    runs = sorted({str(r["RUN_TS"]) for r in rows}, reverse=True)
    latest = rows[0]["RUN_TS"] if runs else None
    paired = [r for r in rows if str(r["RUN_TS"]) == str(latest)] if latest else []
    return {"runs": len(runs), "latest_run_ts": latest,
            "scenarios": paired, "all": rows,
            "single_node_caveat": "Local Personal VM: 2 vCPU / 6 GB, one data node. "
                                  "No distribution clause is in the DDL at all (a "
                                  "single node makes it meaningless and this Personal "
                                  "build does not parse it); the wins reported are "
                                  "columnar scan, pushdown, pre-aggregation and the "
                                  "result cache."}


@app.get("/api/rules")
def rules() -> dict:
    """The rule table as data, so the PRD and the UI show the same thing."""
    return {"rule_version": nlp_rules.RULE_VERSION, "rules": nlp_rules.rules_as_table()}


# -- one origin, one port -----------------------------------------------------
# Mounted last so /api/* wins; serving the built SPA from the same process is
# what removes CORS from the failure list entirely.
if DIST_DIR.is_dir():
    app.mount("/", StaticFiles(directory=str(DIST_DIR), html=True), name="app")
else:  # pragma: no cover - developer convenience, not a demo path
    @app.get("/")
    def _no_build() -> dict:
        return {"detail": "frontend/dist is missing — run `make build` "
                          "(or use `make web` for the Vite dev server on :5173).",
                "api_docs": "/docs"}


def main() -> None:  # pragma: no cover - process entry point
    import uvicorn

    uvicorn.run("backend.app:app", host="127.0.0.1", port=8000, workers=1, log_level="info")


__all__ = ["app", "main", "MAX_TREND_POINTS"]
