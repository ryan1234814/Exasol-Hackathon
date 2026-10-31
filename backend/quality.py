"""Data-quality grading, deliberately separated from the database.

``WARDQ.V_DATA_QUALITY`` supplies counts; this module decides what counts as a
problem. That split matters for the same reason ``forecast`` and ``brief`` keep
their arithmetic out of SQL: the bands below are a policy opinion, they will be
argued about, and they must be testable without a VM.

Three rules shape the output:

* an unknown input stays unknown — a missing measurement never becomes 100%;
* an empty result set produces a finding that says so, rather than a grade;
* every sentence quotes a number that came from the rows, so the Trust page can
  never say something the view does not support.
"""

from __future__ import annotations

from typing import Any

# Completeness bands, inclusive upper bound. A reading that was taken but whose
# result was never recorded is unusable, and 2% is the point where a monthly
# mean starts to be worth re-measuring.
GOOD = 0.98
WATCH = 0.95

# How much of the usable data a laboratory confirmed. Below a quarter, every
# breach in that parameter rests on an unverified probe — which is exactly the
# story the Disagreements tab tells per ward, stated here per parameter.
LAB_WATCH = 0.25

BAND_LABELS = ("good", "watch", "poor", "unknown")


def band_for(ratio: float | None) -> str:
    """Map a 0..1 completeness ratio onto a display band."""
    if ratio is None:
        return "unknown"
    if ratio >= GOOD:
        return "good"
    if ratio >= WATCH:
        return "watch"
    return "poor"


def _num(value: Any) -> float | None:
    """pyexasol returns Decimal for DECIMAL columns; normalise once, here."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _int(value: Any) -> int:
    number = _num(value)
    return 0 if number is None else int(number)


def _pct(part: float, whole: float) -> float | None:
    if not whole:
        return None
    return round(100.0 * part / whole, 2)


def _fmt(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}".rstrip("0").rstrip(".")


def _totals(rows: list[dict]) -> dict:
    readings = sum(_int(r.get("N_READINGS")) for r in rows)
    missing = sum(_int(r.get("N_MISSING")) for r in rows)
    lab = sum(_int(r.get("N_LAB_VERIFIED")) for r in rows)
    sensor = sum(_int(r.get("N_SENSOR_ONLY")) for r in rows)
    implausible = sum(_int(r.get("N_IMPLAUSIBLE")) for r in rows)
    usable = readings - missing
    return {
        "READINGS": readings,
        "MISSING": missing,
        "USABLE": usable,
        "LAB_VERIFIED": lab,
        "SENSOR_ONLY": sensor,
        "IMPLAUSIBLE": implausible,
        "COMPLETE_PCT": _pct(usable, readings),
        "USABLE_PCT": _pct(usable, readings),
        "UNUSABLE_PCT": _pct(missing, readings),
        "LAB_PCT": _pct(lab, usable),
        "BAND": band_for(None if not readings else usable / readings),
    }


def _by_param(rows: list[dict]) -> list[dict]:
    """Aggregate to one row per parameter — the level a decision is made at."""
    buckets: dict[str, dict] = {}
    for row in rows:
        code = str(row.get("PARAM_CODE") or "UNKNOWN")
        bucket = buckets.setdefault(code, {
            "PARAM_CODE": code,
            "UNIT": row.get("UNIT"),
            "READINGS": 0, "MISSING": 0, "LAB_VERIFIED": 0,
            "SENSOR_ONLY": 0, "IMPLAUSIBLE": 0,
            "LAST_DATE": None, "CELLS": 0,
        })
        bucket["READINGS"] += _int(row.get("N_READINGS"))
        bucket["MISSING"] += _int(row.get("N_MISSING"))
        bucket["LAB_VERIFIED"] += _int(row.get("N_LAB_VERIFIED"))
        bucket["SENSOR_ONLY"] += _int(row.get("N_SENSOR_ONLY"))
        bucket["IMPLAUSIBLE"] += _int(row.get("N_IMPLAUSIBLE"))
        bucket["CELLS"] += 1
        last = str(row.get("LAST_DATE"))[:10] if row.get("LAST_DATE") else None
        if last and (bucket["LAST_DATE"] is None or last > bucket["LAST_DATE"]):
            bucket["LAST_DATE"] = last

    out = []
    for code in sorted(buckets):
        bucket = buckets[code]
        usable = bucket["READINGS"] - bucket["MISSING"]
        ratio = (usable / bucket["READINGS"]) if bucket["READINGS"] else None
        lab_ratio = (bucket["LAB_VERIFIED"] / usable) if usable else None
        bucket["COMPLETE_PCT"] = _pct(usable, bucket["READINGS"])
        bucket["UNUSABLE_PCT"] = _pct(bucket["MISSING"], bucket["READINGS"])
        bucket["LAB_PCT"] = _pct(bucket["LAB_VERIFIED"], usable)
        bucket["BAND"] = band_for(ratio)
        bucket["LAB_BAND"] = band_for(lab_ratio)
        out.append(bucket)
    return out


def _worst_cells(rows: list[dict], limit: int = 5) -> list[dict]:
    """The ward x parameter cells with the most unusable readings."""
    scored = []
    for row in rows:
        missing = _int(row.get("N_MISSING"))
        if missing <= 0:
            continue
        readings = _int(row.get("N_READINGS"))
        scored.append({
            "SAMPLE_MONTH": row.get("SAMPLE_MONTH"),
            "WARD_ID": row.get("WARD_ID"),
            "WARD_NAME": row.get("WARD_NAME"),
            "PARAM_CODE": row.get("PARAM_CODE"),
            "N_READINGS": readings,
            "N_MISSING": missing,
            "COMPLETE_PCT": _pct(readings - missing, readings),
        })
    scored.sort(key=lambda r: (-r["N_MISSING"], str(r["WARD_ID"]), str(r["PARAM_CODE"])))
    return scored[:limit]


def _findings(rows: list[dict], by_param: list[dict], totals: dict) -> list[dict]:
    """Plain sentences, each quoting a count that exists in the inputs."""
    findings: list[dict] = []

    for param in by_param:
        if param["BAND"] in ("poor", "watch"):
            findings.append({
                "SEVERITY": param["BAND"],
                "TITLE": f"{param['PARAM_CODE']} completeness is {_fmt(param['COMPLETE_PCT'])}%",
                "DETAIL": (f"{param['MISSING']} of {param['READINGS']} readings have no "
                           f"recorded result, leaving {_fmt(param['COMPLETE_PCT'])}% usable. "
                           f"Monthly means include the surviving readings only."),
                "WARD_ID": None,
                "PARAM_CODE": param["PARAM_CODE"],
            })
        lab_ratio = None if param["LAB_PCT"] is None else param["LAB_PCT"] / 100.0
        if lab_ratio is not None and lab_ratio < LAB_WATCH:
            findings.append({
                "SEVERITY": "watch",
                "TITLE": f"only {_fmt(param['LAB_PCT'])}% of {param['PARAM_CODE']} is lab-verified",
                "DETAIL": (f"{param['LAB_VERIFIED']} of {param['READINGS'] - param['MISSING']} "
                           f"usable readings were confirmed by a laboratory; the remaining "
                           f"{param['SENSOR_ONLY']} rest on an unverified probe. A breach "
                           "here needs a confirmation sample before it is escalated."),
                "WARD_ID": None,
                "PARAM_CODE": param["PARAM_CODE"],
            })

    if totals["IMPLAUSIBLE"]:
        findings.append({
            "SEVERITY": "poor",
            "TITLE": f"{totals['IMPLAUSIBLE']} implausible values",
            "DETAIL": (f"{totals['IMPLAUSIBLE']} readings are negative, which no concentration "
                       "can be — a unit or parse defect rather than water quality."),
            "WARD_ID": None,
            "PARAM_CODE": None,
        })
    else:
        findings.append({
            "SEVERITY": "good",
            "TITLE": "no implausible values",
            "DETAIL": (f"0 of {totals['READINGS']} readings are outside the physically "
                       "possible range, so nothing on this page is a parsing artefact."),
            "WARD_ID": None,
            "PARAM_CODE": None,
        })

    if not rows:
        findings = [{
            "SEVERITY": "unknown",
            "TITLE": "no data quality rows",
            "DETAIL": ("V_DATA_QUALITY returned nothing for this month — run "
                       "db/46_data_quality_view.sql after the readings are loaded."),
            "WARD_ID": None,
            "PARAM_CODE": None,
        }]
    return findings


def summarise(rows: list[dict], staleness_days: int | None = None) -> dict:
    """Grade the quality rows.

    ``staleness_days`` is supplied by the caller so this module never reads a
    clock — the same reason ``brief.py`` takes freshness as an argument.
    """
    rows = list(rows or [])
    totals = _totals(rows)
    by_param = _by_param(rows)
    totals["CELLS"] = len(rows)
    totals["PARAMS"] = len(by_param)
    totals["LAST_DATE"] = max(
        (str(r.get("LAST_DATE"))[:10] for r in rows if r.get("LAST_DATE")),
        default=None,
    )
    totals["STALENESS_DAYS"] = staleness_days

    return {
        "OVERALL": totals,
        "BY_PARAM": by_param,
        "WORST_CELLS": _worst_cells(rows),
        "FINDINGS": _findings(rows, by_param, totals),
        "BANDS": {"GOOD": GOOD, "WATCH": WATCH, "LAB_WATCH": LAB_WATCH},
        "NOTE": ("Completeness and lab coverage are counted in SQL "
                 "(V_DATA_QUALITY); the bands and the sentences are decided in "
                 "backend/quality.py so they can be tested without a database."),
    }
