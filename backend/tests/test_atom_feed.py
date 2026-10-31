"""Atom-feed tests — pure functions, no database.

The feed is the one artefact a machine parses, so the assertions are structural:
the document has to load as XML, carry three entries, keep stable ids across
builds, and never emit a raw ``&`` from a ward name.
"""

import xml.etree.ElementTree as ET

from backend.atom_feed import build_atom, entry_count

ATOM = "{http://www.w3.org/2005/Atom}"

BRIEF = {
    "MONTH": "2026-10",
    "HEADLINE": "2026-10: 24 wards ranked; worst is Ward 4 - Dharavi at 86.5.",
    "DATA_AS_OF": "2026-10-23 20:15:04",
    "ACTIONS": [
        {"N": 1, "KIND": "rank", "WARD_ID": 12, "TITLE": "Start with Ward 4",
         "DETAIL": "COLIFORM sits 0.97 ...", "SQL_STEP": "morning_brief"},
        {"N": 2, "KIND": "crossing", "WARD_ID": 5, "TITLE": "Plan for Borivali",
         "DETAIL": "crosses 0.2 mg/L in ~42 days", "SQL_STEP": "forecast_eta"},
        {"N": 3, "KIND": "instrument", "WARD_ID": 9, "TITLE": "Check the probe",
         "DETAIL": "101 sensor-only breaches", "SQL_STEP": "sensor_vs_lab"},
    ],
}


def test_the_document_is_well_formed_xml():
    root = ET.fromstring(build_atom(BRIEF))
    assert root.tag == f"{ATOM}feed"
    assert root.findtext(f"{ATOM}title") == "WardQ morning brief"


def test_there_is_one_entry_per_action():
    root = ET.fromstring(build_atom(BRIEF))
    entries = root.findall(f"{ATOM}entry")
    assert len(entries) == 3
    assert entry_count(build_atom(BRIEF)) == 3


def test_entry_ids_are_stable_and_ordered():
    ids = [e.findtext(f"{ATOM}id") for e in ET.fromstring(build_atom(BRIEF)).findall(f"{ATOM}entry")]
    assert ids == ["urn:wardq:2026-10:action:1",
                   "urn:wardq:2026-10:action:2",
                   "urn:wardq:2026-10:action:3"]
    assert build_atom(BRIEF) == build_atom(BRIEF)


def test_updated_comes_from_the_data_as_of_timestamp():
    root = ET.fromstring(build_atom(BRIEF))
    assert root.findtext(f"{ATOM}updated") == "2026-10-23T20:15:04Z"


def test_updated_falls_back_to_the_month_when_freshness_is_unknown():
    brief = {**BRIEF, "DATA_AS_OF": None}
    assert ET.fromstring(build_atom(brief)).findtext(f"{ATOM}updated") == "2026-10-01T00:00:00Z"


def test_text_is_escaped_not_truncated():
    brief = {
        "MONTH": "2026-10",
        "HEADLINE": "Ward 4 - Dharavi & Sons <urgent>",
        "DATA_AS_OF": "2026-10-23 20:15:04",
        "ACTIONS": [{"N": 1, "TITLE": "A & B <probe>", "DETAIL": "5 < 6 & 7 > 3",
                     "SQL_STEP": "sensor_vs_lab"}],
    }
    body = build_atom(brief)
    assert "& Sons" not in body and "&amp; Sons" in body
    root = ET.fromstring(body)  # would raise if the escaping were wrong
    entry = root.find(f"{ATOM}entry")
    assert entry.findtext(f"{ATOM}title") == "A & B <probe>"


def test_no_actions_still_produces_a_valid_feed():
    root = ET.fromstring(build_atom({**BRIEF, "ACTIONS": []}))
    assert root.findall(f"{ATOM}entry") == []


def test_the_alternate_link_points_at_the_brief_tab():
    root = ET.fromstring(build_atom(BRIEF, base_url="http://example.test"))
    links = [l.get("href") for l in root.findall(f"{ATOM}link")]
    assert "http://example.test/#/brief" in links
    assert "http://example.test/feed/brief.xml" in links
