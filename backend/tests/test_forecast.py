"""Forecast arithmetic tests — no database, no third-party packages.

Same contract as ``test_rules.py``: the reasoning that decides whether a ward is
deteriorating has to be verifiable with the database switched off, because that
is exactly the state a reviewer's checkout is in.
"""

from backend.forecast import (
    HORIZON_DAYS,
    band,
    breach_date,
    confidence,
    days_to_breach,
    project,
    status_for,
    summarise,
)

TURBIDITY = {"lo": None, "hi": 5.0}
CHLORINE = {"lo": 0.2, "hi": 1.0}
COLIFORM = {"lo": None, "hi": 0.0}


def test_rising_turbidity_counts_down_to_the_upper_limit():
    eta = days_to_breach(3.2, 0.04, **TURBIDITY)
    assert eta == 45.0
    assert status_for(3.2, 0.04, **TURBIDITY) == "deteriorating"


def test_falling_chlorine_counts_down_to_the_lower_limit():
    # 0.45 -> 0.2 at 0.005 mg/L per day
    assert days_to_breach(0.45, -0.005, **CHLORINE) == 50.0
    assert status_for(0.45, -0.005, **CHLORINE) == "deteriorating"


def test_slow_drift_beyond_the_horizon_is_stable_not_a_cry_wolf():
    # 110 days to a 90-day horizon
    assert days_to_breach(0.45, 0.005, **CHLORINE) == 110.0
    assert status_for(0.45, 0.005, **CHLORINE) == "stable"


def test_value_already_outside_its_limit_is_over_limit():
    assert status_for(8.6, 0.001, 5.5, 8.5) == "over_limit"
    # coliform's limit is 0, so any positive reading is already over
    assert status_for(12.0, None, **COLIFORM) == "over_limit"


def test_missing_or_flat_slope_never_invents_a_countdown():
    assert days_to_breach(3.2, None, **TURBIDITY) is None
    assert status_for(3.2, None, **TURBIDITY) == "unknown"
    assert days_to_breach(3.2, 0.0, **TURBIDITY) is None
    assert status_for(3.2, 0.0, **TURBIDITY) == "stable"


def test_drifting_away_from_the_only_bound_is_improving():
    # turbidity has no lower limit, so a falling series cannot breach
    assert status_for(3.0, -0.02, **TURBIDITY) == "improving"
    assert days_to_breach(3.0, -0.02, **TURBIDITY) is None


def test_unknown_current_beats_every_other_branch():
    assert status_for(None, 0.04, **TURBIDITY) == "unknown"
    assert days_to_breach(None, 0.04, **TURBIDITY) is None


def test_projection_is_linear_and_floored_at_zero():
    assert project(3.0, 0.5, 30) == 18.0
    assert project(0.4, -0.1, 30) == 0.0  # no negative NTU / CFU exists
    assert project(None, 0.5, 30) is None


def test_band_is_absent_without_enough_samples_and_widens_with_time():
    assert band(3.0, 0.4, 90, 6) is None
    assert band(3.0, None, 90, 30) is None

    near = band(3.0, 0.4, 30, 30)
    far = band(3.0, 0.4, 90, 30)
    assert near and far
    assert far[1] - far[0] > near[1] - near[0]
    assert near[0] >= 0


def test_confidence_is_a_sample_size_statement():
    assert confidence(5, 0.4) == "low"
    assert confidence(30, None) == "low"
    assert confidence(14, 0.4) == "medium"
    assert confidence(30, 0.4) == "high"


def test_breach_date_is_iso_and_refuses_negative_offsets():
    assert breach_date("2026-10-21", 45) == "2026-12-05"   # crosses two month ends
    assert breach_date("2026-10-21", -3) is None
    assert breach_date("2026-10-21", None) is None
    assert breach_date(None, 45) is None
    assert breach_date("not-a-date", 45) is None


def test_summarise_keeps_unknowns_unknown_and_never_writes_a_zero():
    row = {
        "WARD_ID": 12, "WARD_NAME": "Ward 4 - Dharavi", "PARAM_CODE": "TURBIDITY",
        "PARAM_NAME": "Turbidity", "UNIT": "NTU", "THRESHOLD_LO": None,
        "THRESHOLD_HI": 5.0, "LAST_DATE": "2026-10-21", "RECENT_AVG": None,
        "RECENT_STDDEV": None, "RECENT_N": 0, "SLOPE_12M": None,
    }
    item = summarise(row, horizon_days=HORIZON_DAYS)
    assert item["STATUS"] == "unknown"
    assert item["CURRENT"] is None
    assert item["DAYS_TO_BREACH"] is None
    assert item["PROJECTED_90D"] is None
    assert item["BAND_LOW"] is None
    assert item["CONFIDENCE"] == "low"


def test_summarise_carries_the_numbers_into_the_headline():
    row = {
        "WARD_ID": 21, "WARD_NAME": "Ward 191 - Banashankari", "PARAM_CODE": "TURBIDITY",
        "PARAM_NAME": "Turbidity", "UNIT": "NTU", "THRESHOLD_LO": None,
        "THRESHOLD_HI": 5.0, "LAST_DATE": "2026-10-21", "RECENT_AVG": 3.2,
        "RECENT_STDDEV": 0.25, "RECENT_N": 30, "SLOPE_12M": 0.04,
    }
    item = summarise(row)
    assert item["STATUS"] == "deteriorating"
    assert item["DAYS_TO_BREACH"] == 45.0
    assert item["BREACH_DATE"] == breach_date("2026-10-21", 45)
    assert item["CONFIDENCE"] == "high"
    assert item["BAND_LOW"] is not None and item["BAND_HIGH"] > item["BAND_LOW"]
    assert "45" in item["HEADLINE"]
    assert "5 NTU" in item["HEADLINE"]
