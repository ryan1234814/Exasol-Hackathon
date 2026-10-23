"""Parser tests, driven by the committed fixtures plus targeted inline cases.

The inline cases exist so a failure names the exact shape that broke, rather
than just "the fixture count changed".
"""

from datetime import datetime
from pathlib import Path

from backend.ingest.load_complaints import FIXTURE_DIR
from backend.ingest.whatsapp_parser import infer_ward_id, parse_chat

WARD_MAP = {"dharavi": 3, "koramangala": 13, "ward 12": 1, "powai": 9}


def _texts(messages):
    return [m["text"] for m in messages]


# -- the two real timestamp shapes ------------------------------------------
def test_bracketed_format_with_seconds():
    messages, _ = parse_chat("[14/07/2025, 07:12:45] Rahul Sharma: black water again")
    assert len(messages) == 1
    assert messages[0]["sender_handle"] == "Rahul Sharma"
    assert messages[0]["received_ts"] == datetime(2025, 7, 14, 7, 12, 45)


def test_android_dash_format():
    messages, _ = parse_chat("14/07/2025, 7:13:02 AM - Prakash A: muddy water today")
    assert len(messages) == 1
    assert messages[0]["sender_handle"] == "Prakash A"
    assert messages[0]["received_ts"] == datetime(2025, 7, 14, 7, 13, 2)


def test_12_hour_clock_pm_is_converted():
    messages, _ = parse_chat("25/07/2025, 6:12:44 PM - Nagaraj H: supply timing changed")
    assert messages[0]["received_ts"].hour == 18


def test_two_digit_year_is_interpreted():
    messages, _ = parse_chat("[14/07/25, 7:13 PM] Asha: short form")
    assert messages[0]["received_ts"].year == 2025


def test_dates_are_day_first_not_month_first():
    # 04/07/2025 must be 4 July (Indian locale), not 4 April.
    messages, _ = parse_chat("[04/07/2025, 08:00:00] A: smell today")
    assert messages[0]["received_ts"].month == 7
    assert messages[0]["received_ts"].day == 4


def test_message_text_containing_a_colon_survives():
    messages, _ = parse_chat("[15/07/2025, 07:15:00] Rohit: ward: 12 and time: 7am")
    assert "ward: 12" in messages[0]["text"]


# -- system noise and media --------------------------------------------------
def test_system_lines_are_not_messages():
    raw = "\n".join([
        "Messages and calls are end-to-end encrypted. No one outside of this chat can read them.",
        "Created group",
        "You created group",
        "Missed voice call with +91 98XXX XX12",
        "You deleted this message",
        "Searching for messages",
        "[15/07/2025, 08:00:00] Real Person: actual complaint about smell",
    ])
    messages, report = parse_chat(raw)
    assert len(messages) == 1
    assert messages[0]["sender_handle"] == "Real Person"
    assert report["lines_system"] == 6


def test_media_only_message_produces_no_row():
    messages, report = parse_chat(
        "[14/07/2025, 07:13:02] Rahul Sharma: <attached: 00000032-PHOTO-2025-07-14.jpg>")
    assert messages == []
    assert report["messages_with_media"] == 1


def test_media_marker_is_stripped_but_text_kept():
    messages, _ = parse_chat(
        "[14/07/2025, 07:13:02] Rahul: black water <attached: photo.jpg> please check")
    assert "<attached" not in messages[0]["text"]
    assert "black water" in messages[0]["text"]
    assert "please check" in messages[0]["text"]


# -- multi-line messages -----------------------------------------------------
def test_continuation_lines_merge_into_the_previous_message():
    raw = "\n".join([
        "[16/07/2025, 08:01:00] Meera: multi-line complaint starts here",
        "the leak has been running since morning",
        "near the school",
        "[16/07/2025, 08:05:00] Other: second message",
    ])
    messages, report = parse_chat(raw)
    assert len(messages) == 2
    assert "running since morning" in messages[0]["text"]
    assert "near the school" in messages[0]["text"]
    assert report["lines_continuation"] == 2


def test_orphan_text_before_any_message_is_counted_unparsed():
    messages, report = parse_chat("This is a preamble header line\nwith no timestamp")
    assert messages == []
    assert report["lines_unparsed"] == 2


def test_report_line_counts_account_for_every_line():
    raw = (
        "preamble line\n"
        "[14/07/2025, 07:12:45] A: black water\n"
        "continuation text\n"
        "Created group\n"
        "[14/07/2025, 07:13:45] B: low pressure\n"
    )
    messages, report = parse_chat(raw)
    accounted = (report["lines_parsed"] + report["lines_system"]
                 + report["lines_continuation"] + report["lines_unparsed"])
    assert accounted == report["lines_total"]
    assert len(messages) == 2


# -- ward attribution --------------------------------------------------------
def test_ward_is_inferred_from_text():
    assert infer_ward_id("problem in dharavi lane 6", WARD_MAP) == 3
    assert infer_ward_id("Koramangala 5th block", WARD_MAP) == 13
    assert infer_ward_id("nothing relevant here", WARD_MAP) is None


def test_longest_keyword_wins():
    # "ward 12" and "powai" both present in the map; the more specific match wins
    assert infer_ward_id("ward 12 area", WARD_MAP) == 1


def test_ward_named_only_in_a_continuation_line_is_still_found():
    # Regression: attribution used to run on the first line only, so the ward
    # in "near the school, Ward 12 lane 3" was thrown away.
    raw = "\n".join([
        "[16/07/2025, 08:01:00] Meera: multi-line complaint starts here",
        "near the school, Ward 12 lane 3",
    ])
    messages, _ = parse_chat(raw, ward_map=WARD_MAP)
    assert len(messages) == 1
    assert messages[0]["ward_id"] == 1


def test_default_ward_applies_when_text_is_silent():
    messages, _ = parse_chat(
        "[14/07/2025, 07:12:45] A: black water", ward_map=WARD_MAP, default_ward_id=13)
    assert messages[0]["ward_id"] == 13


def test_unresolved_ward_stays_none_rather_than_guessing():
    messages, report = parse_chat("[14/07/2025, 07:12:45] A: black water", ward_map=WARD_MAP)
    assert messages[0]["ward_id"] is None
    assert report["ward_unresolved"] == 1


def test_first_and_last_timestamps_are_reported():
    raw = ("[01/07/2025, 07:00:00] A: smell\n[09/08/2025, 09:00:00] B: leak")
    _, report = parse_chat(raw)
    assert report["first_ts"] == datetime(2025, 7, 1, 7, 0, 0)
    assert report["last_ts"] == datetime(2025, 8, 9, 9, 0, 0)


def test_empty_input_is_safe():
    messages, report = parse_chat("")
    assert messages == []
    assert report["lines_total"] == 0


def test_bidi_marks_are_stripped():
    messages, _ = parse_chat("\u200e[14/07/2025, 07:12:45]\u200e Rahul: kala paani")
    assert len(messages) == 1
    assert messages[0]["sender_handle"] == "Rahul"


# -- the committed fixtures ---------------------------------------------------
def test_all_committed_fixtures_parse():
    fixtures = sorted(FIXTURE_DIR.glob("*.txt"))
    assert len(fixtures) >= 3, "the demo depends on committed exports existing"
    for path in fixtures:
        messages, report = parse_chat(
            path.read_text(encoding="utf-8", errors="replace"), ward_map=WARD_MAP)
        assert messages, f"{path.name} produced no messages"
        assert report["messages_returned"] == len(messages)


def test_dharavi_fixture_captures_the_outbreak_story():
    path = FIXTURE_DIR / "ward_4_dharavi_export.txt"
    messages, _ = parse_chat(path.read_text(encoding="utf-8"), ward_map=WARD_MAP)
    texts = _texts(messages)
    assert any("black" in t.lower() for t in texts)
    assert any("loose motion" in t.lower() for t in texts)
    # the July 2025 cluster must be present, since that is what the demo points at
    july_2025 = [m for m in messages
                 if m["received_ts"] and m["received_ts"].year == 2025
                 and m["received_ts"].month == 7]
    assert len(july_2025) >= 8


def test_koramangala_fixture_uses_the_dash_format_throughout():
    path = FIXTURE_DIR / "ward_44_koramangala_export.txt"
    messages, report = parse_chat(path.read_text(encoding="utf-8"), ward_map=WARD_MAP)
    assert report["lines_parsed"] >= 20
    assert all(m["sender_handle"] for m in messages)


def test_messy_fixture_does_not_crash_and_is_honest_about_loss():
    path = FIXTURE_DIR / "messy_edge_cases_export.txt"
    messages, report = parse_chat(path.read_text(encoding="utf-8"), ward_map=WARD_MAP)
    assert messages
    # The preamble lines are genuinely unattributable and must be reported,
    # not silently dropped.
    assert report["lines_unparsed"] >= 1
