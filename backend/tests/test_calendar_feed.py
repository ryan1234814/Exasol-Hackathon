"""Calendar-feed tests — pure functions, no database.

A `.ics` file is unforgiving: one bare LF or one 76-octet line and a calendar
client silently drops the event, which on stage looks like "the feature does not
work". These assertions are the format contract.
"""

from backend.calendar_feed import build_ics, escape_text, fold_line, select_events

ITEM = {
    "WARD_ID": 12, "WARD_NAME": "Ward 4 - Dharavi", "PARAM_CODE": "TURBIDITY",
    "PARAM_NAME": "Turbidity", "UNIT": "NTU", "CURRENT": 4.6,
    "SLOPE_PER_DAY": 0.04, "CONFIDENCE": "high", "RECENT_N": 30,
    "STATUS": "deteriorating", "DAYS_TO_BREACH": 10.0, "BREACH_DATE": "2026-11-09",
    "LAST_DATE": "2026-10-30",
    "HEADLINE": "crosses 5 NTU in ~10 days (2026-11-09)",
}
OVER_LIMIT = {**ITEM, "WARD_ID": 5, "PARAM_CODE": "COLIFORM", "STATUS": "over_limit",
              "DAYS_TO_BREACH": -3.0, "BREACH_DATE": None}
STABLE = {**ITEM, "WARD_ID": 9, "PARAM_CODE": "PH", "STATUS": "stable",
          "DAYS_TO_BREACH": 400.0, "BREACH_DATE": "2027-12-01"}


def physical_lines(text):
    assert text.endswith("\r\n")
    return text[:-2].split("\r\n")


def test_output_is_crlf_only():
    body = build_ics([ITEM])
    assert "\n" not in body.replace("\r\n", "")


def test_every_physical_line_fits_seventy_five_octets():
    body = build_ics([ITEM])
    for line in physical_lines(body):
        assert len(line.encode("utf-8")) <= 75, f"line overflows: {line!r}"


def test_folding_counts_octets_not_characters():
    # Devanagari is 3 bytes per character: 30 characters is already 90 octets.
    folded = fold_line("SUMMARY:" + "पानी" * 10)
    assert "\r\n" in folded
    for line in folded.split("\r\n"):
        assert len(line.encode("utf-8")) <= 75


def test_only_deteriorating_items_become_events():
    picked = select_events([ITEM, OVER_LIMIT, STABLE])
    assert [i["WARD_ID"] for i in picked] == [12]
    body = build_ics([ITEM, OVER_LIMIT, STABLE])
    assert body.count("BEGIN:VEVENT") == 1


def test_an_incident_is_not_put_on_next_months_calendar():
    body = build_ics([OVER_LIMIT])
    assert "BEGIN:VEVENT" not in body
    assert body.startswith("BEGIN:VCALENDAR")
    assert body.rstrip().endswith("END:VCALENDAR")


def test_uid_is_stable_so_a_reimport_updates_instead_of_duplicating():
    first = build_ics([ITEM])
    second = build_ics([ITEM])
    assert first == second
    assert "UID:wardq-w12-turbidity@wardq.local" in first


def test_event_dates_come_from_the_data_not_the_clock():
    body = build_ics([ITEM])
    assert "DTSTART;VALUE=DATE:20261109" in body
    assert "DTSTAMP:20261030T000000Z" in body


def test_the_alarm_precedes_the_event_by_the_requested_days():
    assert "TRIGGER:-P7D" in build_ics([ITEM])
    assert "TRIGGER:-P3D" in build_ics([ITEM], alarm_days=3)


def test_status_and_transparency_are_declared():
    body = build_ics([ITEM])
    assert "STATUS:CONFIRMED" in body
    assert "BEGIN:VALARM" in body and "END:VALARM" in body


def test_text_values_are_escaped():
    assert escape_text("a,b;c\\d") == "a\\,b\\;c\\\\d"
    assert escape_text("line1\nline2") == "line1\\nline2"
    body = build_ics([{**ITEM, "HEADLINE": "crosses 5 NTU, soon; probably"}])
    descriptions = "".join(l for l in physical_lines(body) if l.startswith("DESCRIPTION:"))
    assert descriptions, "an event must carry its reasoning"
    assert "\\, soon" in descriptions and "\\; probably" in descriptions


def test_no_events_is_still_a_valid_calendar():
    body = build_ics([])
    assert "BEGIN:VCALENDAR" in body and "END:VCALENDAR" in body
    assert "BEGIN:VEVENT" not in body
