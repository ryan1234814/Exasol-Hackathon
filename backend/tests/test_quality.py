"""Data-quality grading tests — pure functions, no database.

The point of these is the same as ``test_brief.py``: the scorecard is allowed to
be opinionated, but it is not allowed to invent a number. Every assertion below
pins either the arithmetic or the "unknown stays unknown" rule.
"""

from backend.quality import GOOD, WATCH, band_for, summarise


def row(**overrides):
    base = {
        "SAMPLE_MONTH": "2026-10", "WARD_ID": 12, "WARD_NAME": "Ward 4 - Dharavi",
        "PARAM_CODE": "TURBIDITY", "UNIT": "NTU",
        "N_READINGS": 100, "N_MISSING": 3, "N_LAB_VERIFIED": 60,
        "N_SENSOR_ONLY": 37, "N_IMPLAUSIBLE": 0,
        "FIRST_DATE": "2026-10-01", "LAST_DATE": "2026-10-30",
    }
    base.update(overrides)
    return base


def test_completeness_is_counted_not_estimated():
    payload = summarise([row(N_READINGS=200, N_MISSING=10, N_LAB_VERIFIED=100,
                             N_SENSOR_ONLY=90)])
    overall = payload["OVERALL"]
    assert overall["READINGS"] == 200
    assert overall["MISSING"] == 10
    assert overall["USABLE"] == 190
    assert overall["COMPLETE_PCT"] == 95.0
    assert overall["UNUSABLE_PCT"] == 5.0
    assert overall["LAB_PCT"] == round(100 * 100 / 190, 2)


def test_bands_flip_exactly_at_the_documented_boundaries():
    assert band_for(GOOD) == "good"
    assert band_for(GOOD - 0.0001) == "watch"
    assert band_for(WATCH) == "watch"
    assert band_for(WATCH - 0.0001) == "poor"
    assert band_for(None) == "unknown"


def test_missing_is_good_on_this_dataset_but_never_rounded_up():
    # 3 of 100 missing is 97% complete: inside the watch band, not "good".
    payload = summarise([row()])
    assert payload["OVERALL"]["COMPLETE_PCT"] == 97.0
    assert payload["BY_PARAM"][0]["BAND"] == "watch"


def test_every_finding_quotes_a_number_from_its_inputs():
    payload = summarise([row(N_READINGS=100, N_MISSING=10, N_LAB_VERIFIED=5,
                             N_SENSOR_ONLY=85)])
    assert payload["FINDINGS"], "a 90% complete parameter must produce a finding"
    for finding in payload["FINDINGS"]:
        assert any(ch.isdigit() for ch in finding["DETAIL"]), \
            f"finding has no number to back it up: {finding['TITLE']}"
    titles = " ".join(f["TITLE"] for f in payload["FINDINGS"])
    assert "90" in titles  # 90 of 100 usable, stated as a percentage


def test_zero_implausible_rows_is_reported_as_a_positive_finding():
    findings = summarise([row()])["FINDINGS"]
    good = [f for f in findings if f["SEVERITY"] == "good"]
    assert good and "implausible" in good[0]["TITLE"]
    assert "0 of 100" in good[0]["DETAIL"]


def test_an_implausible_row_makes_the_finding_real():
    findings = summarise([row(N_IMPLAUSIBLE=4)])["FINDINGS"]
    bad = [f for f in findings if f["SEVERITY"] == "poor"]
    assert bad and "4" in bad[0]["TITLE"]


def test_empty_input_reports_no_data_instead_of_a_grade():
    payload = summarise([])
    assert payload["OVERALL"]["BAND"] == "unknown"
    assert payload["OVERALL"]["COMPLETE_PCT"] is None
    assert payload["BY_PARAM"] == []
    assert len(payload["FINDINGS"]) == 1
    assert "no data quality rows" in payload["FINDINGS"][0]["TITLE"]


def test_worst_cells_lead_with_the_biggest_gap():
    rows = [
        row(WARD_ID=12, N_MISSING=20),
        row(WARD_ID=5, PARAM_CODE="CHLORINE", N_MISSING=40),
        row(WARD_ID=9, N_MISSING=0),
    ]
    cells = summarise(rows)["WORST_CELLS"]
    assert [c["WARD_ID"] for c in cells] == [5, 12]
    assert cells[0]["N_MISSING"] == 40


def test_staleness_is_passed_in_so_this_module_never_reads_a_clock():
    payload = summarise([row()], staleness_days=12)
    assert payload["OVERALL"]["STALENESS_DAYS"] == 12
    assert payload["OVERALL"]["LAST_DATE"] == "2026-10-30"
    assert summarise([row()])["OVERALL"]["STALENESS_DAYS"] is None


def test_lab_coverage_is_measured_against_usable_readings():
    # 60 lab-verified of 97 usable, not of 100 received.
    payload = summarise([row()])
    param = payload["BY_PARAM"][0]
    assert param["LAB_PCT"] == round(100 * 60 / 97, 2)
    assert param["READINGS"] == 100 and param["CELLS"] == 1
