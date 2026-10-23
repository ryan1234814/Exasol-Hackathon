"""Ingest tests: the tabular register path and the complaint corpus builder.

Both run with no database, which is how the loader is expected to be checked
before anyone types `make load`.
"""

from datetime import date, datetime
from pathlib import Path

from backend.ingest.load_complaints import (
    BULK_TARGET, COLUMNS, FIXTURE_DIR, build_all, build_ward_map, ward_from_filename,
    wards_from_seed_sql,
)
from backend.ingest.tabular import UPLOAD_ID_BASE, load_tabular
from backend.ingest.whatsapp_parser import infer_ward_id, parse_chat

DEMO_CSV = FIXTURE_DIR.parent / "sample_logs_demo.csv"

WARDS = wards_from_seed_sql()


def _upload_id_base(rows_count=0):
    return UPLOAD_ID_BASE + rows_count


# -- ward dimension -----------------------------------------------------------
def test_seed_file_ward_list_is_the_single_source_of_truth():
    assert len(WARDS) == 24
    assert len({wid for wid, _ in WARDS}) == 24
    assert (3, "Ward 4 - Dharavi") in WARDS


def test_ward_map_registers_locality_and_municipal_number():
    ward_map = build_ward_map(WARDS)
    assert ward_map["dharavi"] == 3
    # the municipal number in the name is not the surrogate id
    assert ward_map["ward 4"] == 3
    assert ward_map["ward 44"] == 13
    assert ward_map["electronic city"] == 19


def test_ward_map_excludes_directional_words():
    ward_map = build_ward_map(WARDS)
    for generic in ("east", "west", "north", "south", "ward"):
        assert generic not in ward_map, f"{generic!r} would attribute every message"


def test_export_filename_resolves_the_default_ward():
    ward_map = build_ward_map(WARDS)
    assert ward_from_filename("ward_4_dharavi", ward_map) == 3
    assert ward_from_filename("ward_44_koramangala", ward_map) == 13
    # a file that names no ward must resolve to None, not to a random ward
    assert ward_from_filename("messy_edge_cases", ward_map) is None


# -- the complaint corpus -----------------------------------------------------
def test_corpus_is_deterministic():
    first, _ = build_all(WARDS)
    second, _ = build_all(WARDS)
    assert first == second, "make load twice must give identical analytics"


def test_corpus_row_shape_matches_the_table():
    rows, summary = build_all(WARDS)
    assert summary["total_rows"] == len(rows) == summary["fixture_rows"] + summary["bulk_rows"]
    assert summary["bulk_rows"] == BULK_TARGET
    for row in rows:
        assert set(row) == set(COLUMNS)
        assert isinstance(row["RECEIVED_TS"], datetime)
        assert row["CATEGORY"] in {"contamination", "leakage", "pressure", "other"}
        assert row["RULE_VERSION"]
        assert 0.0 <= row["CONFIDENCE"] <= 1.0


def test_complaint_ids_are_unique_across_both_sources():
    rows, _ = build_all(WARDS)
    ids = [row["COMPLAINT_ID"] for row in rows]
    assert len(ids) == len(set(ids))


def test_only_the_nameless_export_leaves_wards_blank():
    ward_map = build_ward_map(WARDS)
    rows, summary = build_all(WARDS)
    fixture_rows = rows[:summary["fixture_rows"]]
    unattributed = [r for r in fixture_rows if r["WARD_ID"] is None]

    # The two ward-named exports must be attributed completely; every blank has
    # to be a message from the export that never names a ward.
    messy_raw = (FIXTURE_DIR / "messy_edge_cases_export.txt").read_text(encoding="utf-8")
    messy, _ = parse_chat(messy_raw, ward_map=ward_map)
    expected_blank = sum(1 for m in messy if m["ward_id"] is None)
    assert len(unattributed) == expected_blank > 0
    assert all(infer_ward_id(r["RAW_TEXT"], ward_map) is None for r in unattributed)
    assert any(r["WARD_ID"] == 3 for r in fixture_rows)
    assert any(r["WARD_ID"] == 13 for r in fixture_rows)


def test_bulk_corpus_skews_contamination_toward_the_signal_wards():
    rows, _ = build_all(WARDS)
    bulk = [r for r in rows if r["COMPLAINT_ID"] >= 1_000_000]

    def rate(ward_id):
        subset = [r for r in bulk if r["WARD_ID"] == ward_id]
        return sum(r["CATEGORY"] == "contamination" for r in subset) / max(len(subset), 1)

    # 12 carries the planted coliform outbreak, 2 the clean baseline
    assert rate(12) > rate(2)


# -- tabular register ingest --------------------------------------------------
def _load_demo():
    return load_tabular(DEMO_CSV.name, DEMO_CSV.read_bytes())


def test_demo_register_loads_every_good_row_and_reports_the_rest():
    rows, report = _load_demo()
    assert report["rows_read"] == 17
    assert report["rows_accepted"] == len(rows) == 15
    assert report["rows_rejected"] == 2      # 31/02/2025 and Conductivity
    assert report["warnings"] == 2           # empty cell, and "not detected"
    assert report["unmapped_headers"] == []


def test_parameter_spelling_variants_all_reach_a_code():
    # Regression: the alias table was keyed with underscores while the lookup
    # stripped them, so "Residual Free Chlorine" was silently rejected.
    _, report = _load_demo()
    assert not any("Residual Free Chlorine" in p["reason"] for p in report["problems"])
    rows, _ = _load_demo()
    chlorine_w4 = [r for r in rows if r["WARD_ID"] == 4 and r["PARAM_CODE"] == "CHLORINE"]
    assert [r["VALUE_DOUBLE"] for r in chlorine_w4] == [0.31]


def test_headers_are_matched_despite_units_and_clerk_spelling():
    _, report = _load_demo()
    assert report["header_mapping"]["Result (mg/L or NTU)"] == "VALUE_DOUBLE"
    assert report["header_mapping"]["Ward No"] == "WARD_ID"
    assert report["header_mapping"]["Lab Verified"] == "LAB_VERIFIED"


def test_values_are_coerced_from_typed_units():
    rows, _ = _load_demo()
    by_param = {(r["WARD_ID"], r["PARAM_CODE"], r["SAMPLE_DATE"]): r for r in rows}
    assert by_param[(3, "TURBIDITY", date(2025, 7, 4))]["VALUE_DOUBLE"] == 7.4
    assert by_param[(3, "CHLORINE", date(2025, 7, 4))]["VALUE_DOUBLE"] == 0.2  # "<0.2"
    assert by_param[(3, "COLIFORM", date(2025, 7, 4))]["VALUE_DOUBLE"] == 14.0
    assert by_param[(4, "CHLORINE", date(2025, 7, 6))]["VALUE_DOUBLE"] == 0.31


def test_parameter_names_are_normalised_to_codes():
    rows, _ = _load_demo()
    assert {r["PARAM_CODE"] for r in rows} == {"TURBIDITY", "CHLORINE", "COLIFORM", "PH"}


def test_dates_are_day_first_and_iso_both_parsed():
    rows, _ = _load_demo()
    ward_4_on_6_july = {r["PARAM_CODE"] for r in rows
                        if r["SAMPLE_DATE"] == date(2025, 7, 6) and r["WARD_ID"] == 4}
    # the ISO row and its day-first neighbour must both land on 6 July
    assert ward_4_on_6_july == {"COLIFORM", "CHLORINE"}
    assert any(r["SAMPLE_DATE"] == date(2025, 7, 4) for r in rows)


def test_missing_value_is_kept_as_null_not_dropped():
    rows, report = _load_demo()
    nulls = [r for r in rows if r["VALUE_DOUBLE"] is None]
    # one blank cell and one "not detected"; both rows still exist
    assert len(nulls) == 2
    assert {(r["WARD_ID"], r["PARAM_CODE"]) for r in nulls} == {(4, "COLIFORM"), (3, "TURBIDITY")}
    assert sum(1 for p in report["problems"]
               if "kept as NULL" in p["reason"]) == 2


def test_rejected_rows_are_named_with_their_line_number():
    _, report = _load_demo()
    reasons = {p["reason"] for p in report["problems"] if p.get("severity") != "warning"}
    assert any(reason.startswith("unknown parameter") for reason in reasons)
    assert "unparseable date" in reasons
    assert all(p["line"] >= 2 for p in report["problems"])


def test_lab_verified_flag_survives_and_sensors_stay_distinguishable():
    rows, _ = _load_demo()
    assert any(r["LAB_VERIFIED"] is False for r in rows)
    assert any(r["LAB_VERIFIED"] is True for r in rows)
    # a blank flag means a register row, treated as a lab result
    powai = [r for r in rows if r["WARD_ID"] == 9]
    assert all(r["LAB_VERIFIED"] is False for r in powai)


def test_uploaded_rows_get_their_own_sample_id_space():
    rows, report = _load_demo()
    assert report["id_base"] == UPLOAD_ID_BASE
    assert [r["SAMPLE_ID"] for r in rows] == list(range(UPLOAD_ID_BASE, UPLOAD_ID_BASE + len(rows)))
    # the seeded generator never reaches this high, so no PK collision is possible
    assert min(r["SAMPLE_ID"] for r in rows) > 300_800
    assert all(isinstance(r["SAMPLE_TS"], datetime) for r in rows)


def test_id_base_offset_is_honoured_for_a_second_upload():
    rows, _ = load_tabular(DEMO_CSV.name, DEMO_CSV.read_bytes(),
                           id_base=_upload_id_base(15))
    assert rows[0]["SAMPLE_ID"] == UPLOAD_ID_BASE + 15


def test_an_empty_file_is_cleanly_reported():
    rows, report = load_tabular("empty.csv", b"")
    assert rows == []
    assert report["rows_read"] == 0


def test_a_header_only_file_produces_no_rows_and_no_problems():
    _, report = load_tabular("h.csv", b"Ward No,Sampling Date,Parameter,Result\n")
    assert report["rows_read"] == 0
    assert report["rows_accepted"] == 0


def test_a_fully_unusable_file_rejects_every_row():
    _, report = load_tabular("junk.csv", b"ward,date,param,val\nX,not-a-date,Blah,abc\n")
    assert report["rows_accepted"] == 0
    assert report["rows_rejected"] == 1


def test_demo_csv_is_committed_because_the_upload_demo_needs_it():
    assert DEMO_CSV.is_file(), "the upload tab demonstrates with this file"
    assert Path("db/10_schema.sql").is_file()
