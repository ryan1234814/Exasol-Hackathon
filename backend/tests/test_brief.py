"""Morning-brief tests — pure functions, no database.

What is actually being pinned here is the *product* rule: exactly three actions,
in a fixed priority order, and no sentence that the inputs cannot back up.
"""

from backend.brief import ACTION_KINDS, NO_SIGNAL, build_brief

RANKED = [
    {"WARD_ID": 12, "WARD_NAME": "Ward 4 - Dharavi", "RISK_SCORE": 86.5,
     "WORST_PARAM": "COLIFORM", "Z_COMPONENT": 0.97, "BREACH_COMPONENT": 0.92,
     "SLOPE_COMPONENT": 0.71, "COMPLAINT_COMP": 0.55,
     "N_COMPLAINTS": 42, "N_HIGH_SEV": 18, "RANK_IN_MONTH": 1},
    {"WARD_ID": 5, "WARD_NAME": "Ward 6 - Borivali West", "RISK_SCORE": 71.2,
     "WORST_PARAM": "CHLORINE", "Z_COMPONENT": 0.65, "BREACH_COMPONENT": 0.64,
     "SLOPE_COMPONENT": 0.42, "COMPLAINT_COMP": 0.38,
     "N_COMPLAINTS": 31, "N_HIGH_SEV": 9, "RANK_IN_MONTH": 2},
    {"WARD_ID": 9, "WARD_NAME": "Ward 3 - Powai", "RISK_SCORE": 64.0,
     "WORST_PARAM": "PH", "Z_COMPONENT": 0.55, "BREACH_COMPONENT": 0.51,
     "SLOPE_COMPONENT": 0.18, "COMPLAINT_COMP": 0.62,
     "N_COMPLAINTS": 28, "N_HIGH_SEV": 4, "RANK_IN_MONTH": 3},
    {"WARD_ID": 21, "WARD_NAME": "Ward 191 - Banashankari", "RISK_SCORE": 55.7,
     "WORST_PARAM": "TURBIDITY", "Z_COMPONENT": 0.35, "BREACH_COMPONENT": 0.33,
     "SLOPE_COMPONENT": 0.88, "COMPLAINT_COMP": 0.22,
     "N_COMPLAINTS": 12, "N_HIGH_SEV": 2, "RANK_IN_MONTH": 5},
]

FORECAST = [
    {"WARD_ID": 12, "WARD_NAME": "Ward 4 - Dharavi", "PARAM_CODE": "COLIFORM",
     "PARAM_NAME": "Total Coliform", "UNIT": "CFU/100ml", "STATUS": "over_limit",
     "DAYS_TO_BREACH": -3.0, "HEADLINE": "already above the 0 CFU/100ml limit",
     "CURRENT": 27.0, "SLOPE_PER_DAY": 0.0, "CONFIDENCE": "high", "RECENT_N": 31},
    {"WARD_ID": 12, "WARD_NAME": "Ward 4 - Dharavi", "PARAM_CODE": "TURBIDITY",
     "PARAM_NAME": "Turbidity", "UNIT": "NTU", "STATUS": "deteriorating",
     "DAYS_TO_BREACH": 10.0, "HEADLINE": "crosses 5 NTU in ~10 days (2026-10-31)",
     "CURRENT": 4.6, "SLOPE_PER_DAY": 0.04, "CONFIDENCE": "high", "RECENT_N": 30},
    {"WARD_ID": 5, "WARD_NAME": "Ward 6 - Borivali West", "PARAM_CODE": "CHLORINE",
     "PARAM_NAME": "Residual Chlorine", "UNIT": "mg/L", "STATUS": "deteriorating",
     "DAYS_TO_BREACH": 42.0, "HEADLINE": "crosses 0.2 mg/L in ~42 days (2026-12-02)",
     "CURRENT": 0.41, "SLOPE_PER_DAY": -0.005, "CONFIDENCE": "medium", "RECENT_N": 18},
]

DISAGREEMENTS = [
    {"SAMPLE_MONTH": "2026-10", "WARD_ID": 9, "WARD_NAME": "Ward 3 - Powai",
     "PARAM_CODE": "PH", "SENSOR_BREACHES": 101, "LAB_BREACHES": 0,
     "CITIZEN_COMPLAINTS_THAT_MONTH": 6, "VERDICT": "instrument_suspect"},
    {"SAMPLE_MONTH": "2026-10", "WARD_ID": 12, "WARD_NAME": "Ward 4 - Dharavi",
     "PARAM_CODE": "COLIFORM", "SENSOR_BREACHES": 27, "LAB_BREACHES": 19,
     "CITIZEN_COMPLAINTS_THAT_MONTH": 42, "VERDICT": "lab_confirmed"},
]

COUNTS = {"sample_rows": 288768, "complaint_rows": 15063, "wards": 24,
          "high_severity_complaints": 3421}
FRESHNESS = {"LAST_RUN_TS": "2026-10-23 20:15:04", "LOAD_SOURCE": "db/60_materialize.sql"}


def build(**overrides):
    kwargs = dict(month="2026-10", counts=COUNTS, ranked=RANKED,
                  forecast_items=FORECAST, disagreements=DISAGREEMENTS,
                  freshness=FRESHNESS)
    kwargs.update(overrides)
    return build_brief(**kwargs)


def test_always_exactly_three_numbered_actions():
    payload = build()
    assert len(payload["ACTIONS"]) == 3
    assert [a["N"] for a in payload["ACTIONS"]] == [1, 2, 3]
    assert payload["ACTIONS"][0]["KIND"] == "rank"


def test_the_rank_action_is_the_worst_ward_with_its_reasons():
    action = build()["ACTIONS"][0]
    assert action["WARD_ID"] == 12
    assert "Dharavi" in action["TITLE"]
    assert "COLIFORM" in action["DETAIL"]
    assert "42" in action["DETAIL"] and "18" in action["DETAIL"]


def test_the_crossing_action_skips_the_ward_already_being_visited():
    # ward 12 is sooner (10 days) but action 1 already sends someone there
    action = build()["ACTIONS"][1]
    assert action["KIND"] == "crossing"
    assert action["WARD_ID"] == 5
    assert action["DAYS_TO_BREACH"] == 42.0


def test_over_limit_is_not_treated_as_a_countdown():
    only_over = [i for i in FORECAST if i["STATUS"] == "over_limit"]
    # no deteriorating item left -> the third slot still fills, the second is skipped
    payload = build(forecast_items=only_over)
    kinds = [a["KIND"] for a in payload["ACTIONS"]]
    assert "crossing" not in kinds
    assert len(payload["ACTIONS"]) == 3


def test_instrument_suspicion_outranks_a_complaint_backlog():
    action = build()["ACTIONS"][2]
    assert action["KIND"] == "instrument"
    assert action["WARD_ID"] == 9
    assert "101" in action["DETAIL"]
    assert "maintenance ticket" in action["DETAIL"]


def test_complaint_queue_is_the_fallback_when_every_reading_agrees():
    agreeing = [d for d in DISAGREEMENTS if d["VERDICT"] != "instrument_suspect"]
    action = build(disagreements=agreeing)["ACTIONS"][2]
    assert action["KIND"] == "complaints"
    assert action["WARD_ID"] == 5  # 9 high-severity vs 4 for ward 9, 12 is excluded
    assert action["SQL_STEP"] == "complaint_category_mix"


def test_empty_input_still_produces_three_truthful_actions():
    payload = build(ranked=[], forecast_items=[], disagreements=[], counts={})
    assert len(payload["ACTIONS"]) == 3
    assert payload["ACTIONS"][2]["TITLE"] == NO_SIGNAL[0]
    assert payload["WATCHLIST"] == []
    assert "—" not in payload["HEADLINE"]  # no fabricated ward is printed


def test_markdown_contains_all_three_titles_and_the_data_caveat():
    payload = build()
    markdown = payload["MARKDOWN"]
    for action in payload["ACTIONS"]:
        assert action["TITLE"] in markdown
    assert payload["DATA_AS_OF"] in markdown
    assert "linear slope, not a model" in markdown
    assert markdown.startswith("# Morning brief — 2026-10")


def test_action_kinds_are_from_the_documented_vocabulary():
    kinds = {a["KIND"] for a in build()["ACTIONS"]}
    assert kinds <= set(ACTION_KINDS) | {"complaints", "none"}


def test_watchlist_follows_the_ranking_and_stops_at_three():
    watchlist = build()["WATCHLIST"]
    assert [w["WARD_ID"] for w in watchlist] == [5, 9, 21]
    assert watchlist[0]["RISK_SCORE"] == 71.2
