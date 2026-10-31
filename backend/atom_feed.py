"""The morning brief as an Atom feed.

Same reason as the calendar file: a ward office already has a feed reader, and
pulling is free while pushing (SMS, WhatsApp, email) costs money or credentials.
The feed is generated from the payload ``/api/brief`` already returns, so the
page and the feed cannot disagree — a property worth more than the ~80 lines
this module costs.

XML is assembled with ``xml.sax.saxutils.escape`` rather than f-strings: ward
names are data, and one unescaped ``&`` makes the whole feed unreadable.
"""

from __future__ import annotations

from typing import Any
from xml.sax.saxutils import escape

DEFAULT_BASE_URL = "http://127.0.0.1:8000"
FEED_TITLE = "WardQ morning brief"
AUTHOR = "WardQ rule engine"
MAX_ENTRIES = 3


def _updated(brief: dict) -> str:
    """RFC 3339 timestamp from the payload, with a deterministic fallback."""
    raw = brief.get("DATA_AS_OF")
    if raw:
        text = str(raw).replace("T", " ")[:19]
        day, _, clock = text.partition(" ")
        if len(day) == 10 and len(clock) == 8:
            return f"{day}T{clock}Z"
        if len(day) == 10:
            return f"{day}T00:00:00Z"
    month = str(brief.get("MONTH") or "1970-01")
    return f"{month}-01T00:00:00Z"


def _entry(action: dict, month: str, stamp: str, base_url: str) -> str:
    # Assembled line by line: a nested f-string that reuses its parent's quote
    # character is a syntax error before Python 3.12, and this venv is 3.11.
    title = str(action.get("TITLE") or "")
    detail = str(action.get("DETAIL") or "")
    sql_step = str(action.get("SQL_STEP") or "")
    ward = action.get("WARD_ID")

    body = ["<p>" + escape(title) + "</p>", "<p>" + escape(detail) + "</p>"]
    if ward is not None:
        body.append("<p>Ward #" + escape(str(ward)) + "</p>")
    body.append("<p>SQL: " + escape(sql_step) + "</p>")

    return "\n".join([
        "  <entry>",
        "    <id>urn:wardq:%s:action:%s</id>" % (escape(month), action.get("N")),
        "    <title>%s</title>" % escape(title),
        "    <updated>%s</updated>" % stamp,
        '    <link rel="alternate" href="%s/#/brief"/>' % escape(base_url),
        '    <content type="html">%s</content>' % escape("".join(body)),
        "  </entry>",
    ])


def build_atom(brief: dict, *, base_url: str = DEFAULT_BASE_URL) -> str:
    """Render one brief payload as an Atom 1.0 document."""
    brief = brief or {}
    month = str(brief.get("MONTH") or "unknown")
    stamp = _updated(brief)
    actions = [a for a in (brief.get("ACTIONS") or []) if a.get("N")][:MAX_ENTRIES]

    entries = "\n".join(_entry(a, month, stamp, base_url) for a in actions)
    headline = escape(str(brief.get("HEADLINE") or ""))

    return "\n".join([
        '<?xml version="1.0" encoding="utf-8"?>',
        '<feed xmlns="http://www.w3.org/2005/Atom">',
        f"  <title>{escape(FEED_TITLE)}</title>",
        f"  <subtitle>{headline}</subtitle>",
        f"  <id>urn:wardq:month:{escape(month)}</id>",
        f"  <updated>{stamp}</updated>",
        f'  <link rel="alternate" href="{escape(base_url)}/#/brief"/>',
        f'  <link rel="self" href="{escape(base_url)}/feed/brief.xml"/>',
        "  <author>",
        f"    <name>{escape(AUTHOR)}</name>",
        "  </author>",
        entries,
        "</feed>",
    ]).replace("\n\n", "\n") + "\n"


def entry_count(feed_xml: str) -> int:
    """Cheap count used by the tests and by the Trust page's own assertion."""
    return feed_xml.count("<entry>")
