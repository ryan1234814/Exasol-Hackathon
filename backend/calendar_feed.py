"""The breach forecast as a calendar file.

A ward officer does not open a dashboard every morning; they open a calendar.
This module turns the same 96 forecast rows the case file already renders into
one all-day event per parameter that is actually going to cross its limit, with
a seven-day alarm in front of it. Nothing is delivered — the file is built on
request and the officer imports or subscribes to it, which is what keeps this
free forever, unlike an SMS or WhatsApp gateway.

Two properties are deliberate and tested:

* **No clock.** The event date is ``LAST_DATE`` + ``DAYS_TO_BREACH`` from the
  view, so the same data always produces the same file. A forecast that changed
  because it was generated on a different day could not be diffed or trusted.
* **Stable UID.** Re-importing an updated file updates the existing events
  instead of duplicating them.

Format details that are easy to get wrong and are therefore pinned here:
RFC 5545 wants CRLF line endings, lines folded at 75 **octets** (not
characters — this file can carry Devanagari ward names), and ``,`` / ``;`` /
``\\`` escaped inside TEXT values.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

PRODID = "-//WardQ//Ward Water Quality Triage//EN"
UID_DOMAIN = "wardq.local"
DEFAULT_CALENDAR_NAME = "WardQ breach forecast"
LINE_OCTETS = 75


def escape_text(value: Any) -> str:
    """Escape one RFC 5545 TEXT value."""
    text = "" if value is None else str(value)
    return (text.replace("\\", "\\\\")
                .replace(";", "\\;")
                .replace(",", "\\,")
                .replace("\r\n", "\\n")
                .replace("\r", "\\n")
                .replace("\n", "\\n"))


def fold_line(line: str, limit: int = LINE_OCTETS) -> str:
    """Fold a content line to ``limit`` UTF-8 octets per physical line.

    Continuation lines begin with a single space, and that space counts toward
    the limit — counting characters instead of octets overflows the line for
    every non-ASCII ward name and makes strict parsers reject the file.
    """
    if len(line.encode("utf-8")) <= limit:
        return line
    parts: list[str] = []
    current = ""
    size = 0
    for char in line:
        width = len(char.encode("utf-8"))
        if size + width > limit:
            parts.append(current)
            current = " "  # the fold marker is part of the continuation line
            size = 1
        current += char
        size += width
    parts.append(current)
    return "\r\n".join(parts)


def _date(value: Any) -> str | None:
    """``2026-11-15`` (or a timestamp) to the ``YYYYMMDD`` an all-day event wants."""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.strftime("%Y%m%d")
    if hasattr(value, "strftime"):
        return value.strftime("%Y%m%d")
    text = str(value)[:10].replace("-", "")
    return text if len(text) == 8 and text.isdigit() else None


def _stamp(value: Any) -> str:
    """DTSTAMP derived from the data, never from ``datetime.now()``."""
    day = _date(value) or "19700101"
    return f"{day}T000000Z"


def _event(item: dict, alarm_days: int) -> list[str]:
    ward_id = item.get("WARD_ID")
    param = str(item.get("PARAM_CODE") or "PARAM").upper()
    unit = item.get("UNIT") or ""
    current = item.get("CURRENT")
    slope = item.get("SLOPE_PER_DAY")

    summary = (f"Ward {ward_id} — {param} breach expected")
    detail = (
        f"{item.get('HEADLINE') or 'projected to cross its limit'}. "
        f"Current {current if current is not None else '—'} {unit}".rstrip() + ". "
        f"Trend {slope if slope is not None else '—'} per day over the last 12 months, "
        f"{item.get('CONFIDENCE') or 'low'} confidence, "
        f"{item.get('RECENT_N') if item.get('RECENT_N') is not None else '—'} recent samples. "
        f"Reproduce with db/sql/forecast_eta.sql in schema WARDQ."
    )

    lines = [
        "BEGIN:VEVENT",
        f"UID:wardq-w{ward_id}-{param.lower()}@{UID_DOMAIN}",
        f"DTSTAMP:{_stamp(item.get('LAST_DATE'))}",
        f"DTSTART;VALUE=DATE:{(item.get('BREACH_DATE') or '').replace('-', '')[:8]}",
        "DURATION:P1D",
        f"SUMMARY:{escape_text(summary)}",
        f"DESCRIPTION:{escape_text(detail)}",
        "STATUS:CONFIRMED",
        "TRANSP:TRANSPARENT",
        "CATEGORIES:Water quality",
        "BEGIN:VALARM",
        f"TRIGGER:-P{int(alarm_days)}D",
        "ACTION:DISPLAY",
        f"DESCRIPTION:{escape_text(summary)}",
        "END:VALARM",
        "END:VEVENT",
    ]
    return lines


def select_events(items: list[dict]) -> list[dict]:
    """Only genuine countdowns: a real date and a trend toward a limit.

    ``over_limit`` is excluded on purpose — that is an incident for today's
    brief, not something to put on next month's calendar.
    """
    picked = []
    for item in items or []:
        if item.get("STATUS") != "deteriorating":
            continue
        if item.get("DAYS_TO_BREACH") is None or not item.get("BREACH_DATE"):
            continue
        if _date(item.get("BREACH_DATE")) is None:
            continue
        picked.append(item)
    picked.sort(key=lambda i: (str(i.get("BREACH_DATE")), int(i.get("WARD_ID") or 0),
                              str(i.get("PARAM_CODE"))))
    return picked


def build_ics(items: list[dict], *, calendar_name: str = DEFAULT_CALENDAR_NAME,
              alarm_days: int = 7) -> str:
    """Render the forecast as an importable VCALENDAR document."""
    events = select_events(items)
    description = (f"{len(events)} parameter(s) projected to cross a BIS 10500 limit "
                   "within the forecast horizon. Dates are the trailing 12-month "
                   "slope extended linearly, not a model.")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        f"PRODID:{PRODID}",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape_text(calendar_name)}",
        f"X-WR-CALDESC:{escape_text(description)}",
    ]
    for item in events:
        lines.extend(_event(item, alarm_days))
    lines.append("END:VCALENDAR")

    return "\r\n".join(fold_line(line) for line in lines) + "\r\n"
