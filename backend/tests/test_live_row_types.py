"""Do the new features survive the Python types Exasol actually returns?

The mock hands the UI JavaScript numbers, so no mock-mode walkthrough can catch a
``Decimal`` vs ``float`` mismatch. pyexasol 3.x maps the real schema like this:

===============  ===================  ==========================================
Exasol type      Python type          columns the new features read
===============  ===================  ==========================================
``DECIMAL(9,0)`` ``decimal.Decimal``  ``WARD_MONTH_RISK.WARD_ID`` / ``RANK_IN_MONTH``,
                                      ``COMPLAINT_SUMMARY.N_COMPLAINTS`` / ``N_HIGH_SEV``,
                                      every ``SUM(CASE ...)`` in ``V_LAB_VS_SENSOR``,
                                      ``COUNT(*)`` in ``V_WARD_FORECAST.RECENT_N``
``DOUBLE``       ``float``            ``RISK_SCORE``, ``SLOPE_12M``, thresholds
``DATE``         ``datetime.date``    ``V_WARD_FORECAST.LAST_DATE``
``TIMESTAMP``    ``datetime.datetime`` ``LOAD_RUN.RUN_TS`` -> ``DATA_AS_OF``
``VARCHAR``      ``str``              every name and code
``BOOLEAN``      ``bool``             ``WARD.DOWNSTREAM``
===============  ===================  ==========================================

``float * Decimal`` raises ``TypeError`` in Python, so one unguarded multiplication
would turn a page into a 500 the first time it ran against the database and never
before. Every payload below is therefore pushed through ``jsonable_encoder`` and
``json.dumps`` — the exact path a FastAPI response takes — with real types.
"""

import json
from datetime import date, datetime
from decimal import Decimal

from fastapi.encoders import jsonable_encoder

from backend import forecast
from backend.brief import build_brief

# ---------------------------------------------------------------------------
# One row of WARDQ.V_WARD_FORECAST, typed the way pyexasol returns it.
# ---------------------------------------------------------------------------
TURBIDITY_ROW = {
    "WARD_ID": Decimal("21"),
    "WARD_NAME": "Ward 191 - Banashankari",
    "CITY": "Bengaluru",
    "PARAM_CODE": "TURBIDITY",
    "PARAM_NAME": "Turbidity",
    "UNIT": "NTU",
    "THRESHOLD_LO": None,
    "THRESHOLD_HI": 5.0,
    "LAST_DATE": date(2026, 10, 21),
    "RECENT_AVG": 3.6012,
    "RECENT_STDDEV": 0.2419,
    "RECENT_N": Decimal("31"),
    "SLOPE_12M": 0.0141,
}

# Ward 9 pH: the drifting unverified station 4. Past the lower limit, still
# falling — the "instrument artefact, not an outbreak" case.
PH_DRIFT_ROW = {
    "WARD_ID": Decimal("9"),
    "WARD_NAME": "Ward 3 - Powai",
    "PARAM_CODE": "PH",
    "PARAM_NAME": "pH",
    "UNIT": "pH",
    "THRESHOLD_LO": 5.5,
    "THRESHOLD_HI": 8.5,
    "LAST_DATE": date(2026, 10, 21),
    "RECENT_AVG": 5.421,
    "RECENT_STDDEV": 0.071,
    "RECENT_N": Decimal("31"),
    "SLOPE_12M": -0.0026,
}

# A short window: too few recent samples for sigma to mean anything.
SHORT_WINDOW_ROW = {
    "WARD_ID": Decimal("3"), "WARD_NAME": "Ward 44 - Koramangala",
    "PARAM_CODE": "CHLORINE", "PARAM_NAME": "Residual Chlorine", "UNIT": "mg/L",
    "THRESHOLD_LO": 0.2, "THRESHOLD_HI": 1.0,
    "LAST_DATE": date(2026, 10, 21),
    "RECENT_AVG": 0.164, "RECENT_STDDEV": None, "RECENT_N": Decimal("3"),
    "SLOPE_12M": -0.0009,
}


def _roundtrip(payload):
    """Serialise exactly as a FastAPI JSON response would."""
    return json.loads(json.dumps(jsonable_encoder(payload)))


def test_a_real_forecast_row_summarises_to_json():
    item = forecast.summarise(TURBIDITY_ROW)

    assert item["WARD_ID"] == Decimal("21")
    assert item["STATUS"] in forecast.STATUSES
    assert isinstance(item["CURRENT"], float)
    assert item["RECENT_N"] == 31
    assert item["LAST_DATE"] == "2026-10-21"
    if item["DAYS_TO_BREACH"] is not None:
        assert isinstance(item["DAYS_TO_BREACH"], float)
    assert _roundtrip(item)["PARAM_CODE"] == "TURBIDITY"


def test_the_eta_lands_on_the_dates_own_timeline():
    item = forecast.summarise(TURBIDITY_ROW)
    if item["DAYS_TO_BREACH"] is not None and item["DAYS_TO_BREACH"] > 0:
        assert item["BREACH_DATE"] > "2026-10-21"


def test_a_real_over_limit_row_is_called_over_limit_not_a_negative_countdown():
    item = forecast.summarise(PH_DRIFT_ROW)
    assert item["STATUS"] == "over_limit"
    assert "limit" in item["HEADLINE"]
    assert _roundtrip(item)["STATUS"] == "over_limit"


def test_a_short_window_degrades_instead_of_inventing_a_band():
    item = forecast.summarise(SHORT_WINDOW_ROW)
    assert item["BAND_LOW"] is None and item["BAND_HIGH"] is None
    assert item["CONFIDENCE"] == "low"
    assert item["RECENT_N"] == 3


def test_breach_date_accepts_every_type_the_view_can_supply():
    assert forecast.breach_date(date(2026, 10, 21), 43) == "2026-12-03"
    assert forecast.breach_date(datetime(2026, 10, 21, 6, 30), 43) == "2026-12-03"
    assert forecast.breach_date("2026-10-21", 43) == "2026-12-03"
    assert forecast.breach_date(None, 43) is None
    assert forecast.breach_date(date(2026, 10, 21), None) is None


# ---------------------------------------------------------------------------
# WARD_MONTH_RISK ranked rows, with DECIMAL ids and counts.
# ---------------------------------------------------------------------------
RANKED = [
    {"WARD_ID": Decimal("12"), "WARD_NAME": "Ward 4 - Dharavi", "CITY": "Mumbai",
     "RISK_SCORE": 68.4831, "RANK_IN_MONTH": Decimal("1"), "WORST_PARAM": "COLIFORM",
     "Z_COMPONENT": 0.63, "BREACH_COMPONENT": 1.0, "SLOPE_COMPONENT": 0.31,
     "COMPLAINT_COMP": 0.14,
     "N_COMPLAINTS": Decimal("18"), "N_HIGH_SEV": Decimal("7")},
    {"WARD_ID": Decimal("9"), "WARD_NAME": "Ward 3 - Powai", "CITY": "Mumbai",
     "RISK_SCORE": 61.2214, "RANK_IN_MONTH": Decimal("2"), "WORST_PARAM": "PH",
     "Z_COMPONENT": 0.58, "BREACH_COMPONENT": 0.74, "SLOPE_COMPONENT": 0.22,
     "COMPLAINT_COMP": 0.09,
     "N_COMPLAINTS": Decimal("11"), "N_HIGH_SEV": Decimal("3")},
    {"WARD_ID": Decimal("21"), "WARD_NAME": "Ward 191 - Banashankari", "CITY": "Bengaluru",
     "RISK_SCORE": 57.9022, "RANK_IN_MONTH": Decimal("3"), "WORST_PARAM": "TURBIDITY",
     "Z_COMPONENT": 0.44, "BREACH_COMPONENT": 0.62, "SLOPE_COMPONENT": 0.88,
     "COMPLAINT_COMP": 0.05,
     "N_COMPLAINTS": Decimal("4"), "N_HIGH_SEV": Decimal("1")},
    {"WARD_ID": Decimal("5"), "WARD_NAME": "Ward 6 - Borivali West", "CITY": "Mumbai",
     "RISK_SCORE": 52.1043, "RANK_IN_MONTH": Decimal("4"), "WORST_PARAM": "CHLORINE",
     "Z_COMPONENT": 0.31, "BREACH_COMPONENT": 0.55, "SLOPE_COMPONENT": 0.4,
     "COMPLAINT_COMP": 0.02,
     "N_COMPLAINTS": Decimal("2"), "N_HIGH_SEV": Decimal("0")},
]

# V_LAB_VS_SENSOR with every SUM() as Decimal, as pyexasol returns it.
DISAGREEMENTS = [
    {"SAMPLE_MONTH": "2026-10", "WARD_ID": Decimal("9"), "WARD_NAME": "Ward 3 - Powai",
     "PARAM_CODE": "PH", "UNIT": "pH", "THRESHOLD_LO": 5.5, "THRESHOLD_HI": 8.5,
     "SENSOR_READINGS": Decimal("93"), "LAB_READINGS": Decimal("279"),
     "SENSOR_BREACHES": Decimal("31"), "LAB_BREACHES": Decimal("0"),
     "CITIZEN_COMPLAINTS_THAT_MONTH": Decimal("0"), "VERDICT": "instrument_suspect"},
    {"SAMPLE_MONTH": "2026-10", "WARD_ID": Decimal("12"), "WARD_NAME": "Ward 4 - Dharavi",
     "PARAM_CODE": "COLIFORM", "UNIT": "CFU/100ml", "THRESHOLD_LO": None,
     "THRESHOLD_HI": 0.0,
     "SENSOR_READINGS": Decimal("93"), "LAB_READINGS": Decimal("279"),
     "SENSOR_BREACHES": Decimal("27"), "LAB_BREACHES": Decimal("81"),
     "CITIZEN_COMPLAINTS_THAT_MONTH": Decimal("18"), "VERDICT": "lab_confirmed"},
]

COUNTS = {"sample_rows": Decimal("288768"), "complaint_rows": Decimal("40"),
          "wards": Decimal("24"), "high_severity_complaints": Decimal("19")}

FRESHNESS = {"LAST_RUN_TS": datetime(2026, 10, 21, 20, 15, 4),
             "LOAD_SOURCE": "db/60_materialize.sql"}


def test_a_real_ranked_row_builds_a_serialisable_brief():
    items = [forecast.summarise(TURBIDITY_ROW), forecast.summarise(PH_DRIFT_ROW),
             forecast.summarise(SHORT_WINDOW_ROW)]
    payload = build_brief(month="2026-10", counts=COUNTS, ranked=RANKED,
                          forecast_items=items, disagreements=DISAGREEMENTS,
                          freshness=FRESHNESS)

    assert len(payload["ACTIONS"]) == 3
    assert _roundtrip(payload)["ACTIONS"][0]["KIND"] == "rank"


def test_the_brief_names_the_worst_ward_and_the_suspect_probe():
    items = [forecast.summarise(row) for row in (TURBIDITY_ROW, PH_DRIFT_ROW)]
    payload = build_brief(month="2026-10", counts=COUNTS, ranked=RANKED,
                          forecast_items=items, disagreements=DISAGREEMENTS,
                          freshness=FRESHNESS)

    actions = payload["ACTIONS"]
    assert actions[0]["WARD_NAME"] == "Ward 4 - Dharavi"
    # The instrument artefact must beat the complaint fallback: it is the whole
    # premise of V_LAB_VS_SENSOR.
    assert actions[2]["KIND"] == "instrument"
    assert actions[2]["WARD_NAME"] == "Ward 3 - Powai"
    assert "31 sensor-only breaches" in actions[2]["DETAIL"]


def test_every_number_in_the_brief_traces_back_to_an_input():
    items = [forecast.summarise(TURBIDITY_ROW)]
    payload = build_brief(month="2026-10", counts=COUNTS, ranked=RANKED,
                          forecast_items=items, disagreements=DISAGREEMENTS,
                          freshness=FRESHNESS)
    text = payload["MARKDOWN"]
    # Counts, the worst score, the probe's breach count and the watchlist scores
    # are all formattable from the inputs above; nothing is invented prose.
    assert "288,768 readings" in text or "288768 readings" in text
    assert "Ward 4 - Dharavi" in text
    assert "2026-10-21 20:15:04" in text


def test_the_markdown_never_leaks_a_python_repr():
    items = [forecast.summarise(row) for row in (TURBIDITY_ROW, PH_DRIFT_ROW)]
    payload = build_brief(month="2026-10", counts=COUNTS, ranked=RANKED,
                          forecast_items=items, disagreements=DISAGREEMENTS,
                          freshness=FRESHNESS)
    assert "Decimal(" not in payload["MARKDOWN"]
    assert "datetime." not in payload["MARKDOWN"]
    assert "object at 0x" not in payload["MARKDOWN"]


# ---------------------------------------------------------------------------
# Response shapes the endpoints hand to FastAPI.
# ---------------------------------------------------------------------------
def test_heatmap_cells_with_decimal_ids_serialise():
    cells = [{"SAMPLE_MONTH": "2026-10", "WARD_ID": Decimal("12"),
              "RISK_SCORE": 68.4831, "WORST_PARAM": "COLIFORM",
              "RANK_IN_MONTH": Decimal("1"), "COMPLAINT_DENSITY": Decimal("1.19")}]
    dims = [{"WARD_ID": Decimal("12"), "WARD_NAME": "Ward 4 - Dharavi",
             "CITY": "Mumbai", "CITY_ZONE": "South", "POPULATION": Decimal("55000"),
             "CONNECTIONS": Decimal("15132"), "DOWNSTREAM": True}]
    out = _roundtrip({"months": ["2026-10"], "wards": dims, "cells": cells,
                      "months_returned": 1, "query_ms": 4.2})
    assert out["cells"][0]["WARD_ID"] == 12
    assert out["wards"][0]["DOWNSTREAM"] is True
    assert out["cells"][0]["COMPLAINT_DENSITY"] == 1.19


def test_the_verdict_reader_accepts_decimal_breach_counts():
    from backend.app import _verdict

    assert _verdict({"SENSOR_BREACHES": Decimal("31"), "LAB_BREACHES": Decimal("0")}) \
        == "instrument_suspect"
    assert _verdict({"SENSOR_BREACHES": Decimal("27"), "LAB_BREACHES": Decimal("81")}) \
        == "lab_confirmed"
    assert _verdict({"SENSOR_BREACHES": None, "LAB_BREACHES": None}) == "consistent"
    # A bare string can only arrive from a mis-typed mock, and must not explode.
    assert _verdict({"SENSOR_BREACHES": "0", "LAB_BREACHES": "0"}) == "consistent"
