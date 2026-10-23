"""Parse a WhatsApp group chat export into complaint rows.

The brief's pain point is literally "complaint data lives in WhatsApp groups",
so this is the ingestion path that makes the demo credible. Real exports are
messy in specific, well-known ways, and every branch below exists because a
real export does it:

* two timestamp shapes — ``[DD/MM/YYYY, HH:MM:SS] Name: msg`` (older iOS /
  bracketed) and ``DD/MM/YYYY, HH:MM - Name: msg`` (current Android, en-dash);
* 12-hour clocks with ``AM``/``PM``, and day-first vs month-first dates;
* U+200E / U+200F left-to-right marks that WhatsApp injects invisibly;
* multi-line messages, where continuation lines carry no timestamp at all;
* system noise — "Created group", "Missed voice call with X", "You deleted
  this message", join/leave lines, the E2E encryption banner;
* attachments — ``<attached: 00000012-PHOTO-2025-09-14-at-7.41.32AM.jpg>``
  and ``Media omitted``.

Parsing never writes to the database; it returns rows plus an honest report of
what it could not parse, which the UI shows. Silent data loss in a civic
health tool is the worst possible failure mode.
"""

from __future__ import annotations

import re
from datetime import datetime

# WhatsApp injects these directional marks; they break naive start-of-line
# matching, so they are stripped before anything else happens.
_BIDI_RE = re.compile(r"[\u200e\u200f\u202a-\u202e]")

_MESSAGE_RE = re.compile(
    r"^\[?\s*"
    r"(?P<date>\d{1,2}[./-]\d{1,2}[./-]\d{2,4})"
    r",?\s+"
    r"(?P<time>\d{1,2}:\d{2}(?::\d{2})?\s*(?:[AaPp]\.?[Mm]\.?)?)"
    r"\s*\]?\s*"
    r"(?:[-\u2013\u2014]\s*)?"          # Android dash form
    r"(?P<sender>[^:\n]{0,80}?):\s?"
    r"(?P<text>.*)$"
)

# Lines that are structural or system-generated, not complaints.
_SYSTEM_RES = (
    re.compile(r"^Messages and calls are end-to-end encrypted", re.I),
    re.compile(r"^\s*[-\u2013\u2014]+\s*$"),
    re.compile(r"^(?:You )?(?:created|Changed the subject)", re.I),
    re.compile(r"^(?:\S.{0,60}?) (?:joined using|left|was added|was removed)", re.I),
    re.compile(r"^(?:You )?[Mm]issed (?:voice|video|group) call", re.I),
    re.compile(r"^Missed (?:voice|video) call with", re.I),
    re.compile(r"^(?:You |.{1,60}? )?(?:deleted this message|cleared this chat)", re.I),
    re.compile(r"^This message was deleted", re.I),
    re.compile(r"^\d+ missed calls?", re.I),
    re.compile(r"^(?:You )?(?:pinned|unpinned) a message", re.I),
    re.compile(r"^Searching for messages", re.I),
)

_ATTACHED_RE = re.compile(r"<attached:[^>]*>", re.I)
_MEDIA_OMITTED_RE = re.compile(r"\bMedia omitted\b|\bimage omitted\b|\bsticker omitted\b", re.I)

# Date formats are tried day-first (Indian locale, which is what these exports
# are produced in) and only then month-first, so 04/07/2025 means 4 July.
_DATE_FORMATS = (
    "%d/%m/%Y", "%d/%m/%y", "%d.%m.%Y", "%d-%m-%Y", "%d.%m.%y", "%d-%m-%y",
    "%m/%d/%Y", "%m/%d/%y",
)
_TIME_FORMATS = ("%H:%M:%S", "%H:%M", "%I:%M:%S %p", "%I:%M %p",
                 "%I:%M:%S %p.", "%I:%M %p.", "%H:%M:%S.", "%H:%M.")


def _parse_ts(date_str: str, time_str: str) -> datetime | None:
    time_str = time_str.strip().replace(".", "")
    for df in _DATE_FORMATS:
        try:
            d = datetime.strptime(date_str.strip(), df)
        except ValueError:
            continue
        for tf in _TIME_FORMATS:
            try:
                t = datetime.strptime(time_str, tf)
                return d.replace(hour=t.hour, minute=t.minute, second=t.second)
            except ValueError:
                continue
        # A date that parsed but no time format matched is still a usable day.
        return d
    return None


def _is_system_line(line: str) -> bool:
    stripped = line.strip()
    if not stripped:
        return True
    return any(r.match(stripped) for r in _SYSTEM_RES)


def infer_ward_id(text: str, ward_map: dict[str, int]) -> int | None:
    """Best-effort ward attribution from message text.

    ``ward_map`` maps a lowercase area keyword to a WARD_ID. Explicit mention
    wins; otherwise the caller decides (an override, or NULL). Returning None
    is *better* than guessing, because a complaint attributed to the wrong ward
    pollutes that ward's trend line.
    """
    haystack = text.lower()
    best_id = None
    best_len = 0
    for keyword, ward_id in ward_map.items():
        if keyword in haystack and len(keyword) > best_len:
            best_id, best_len = ward_id, len(keyword)
    return best_id


def parse_chat(
    raw: str,
    ward_map: dict[str, int] | None = None,
    default_ward_id: int | None = None,
    channel: str = "whatsapp",
) -> tuple[list[dict], dict]:
    """Return ``(messages, report)``.

    ``messages`` are dicts ready for :class:`WARDQ.COMPLAINT` insertion minus
    the category fields, which the caller fills in via ``nlp_rules.classify``.
    """
    ward_map = ward_map or {}
    raw = _BIDI_RE.sub("", raw or "")
    lines = raw.splitlines()

    messages: list[dict] = []
    report = {
        "lines_total": len(lines),
        "lines_parsed": 0,
        "lines_system": 0,
        "lines_continuation": 0,
        "lines_unparsed": 0,
        "messages_with_media": 0,
        "messages_without_timestamp": 0,
        "ward_inferred": 0,
        "ward_unresolved": 0,
        "senders": set(),
        "first_ts": None,
        "last_ts": None,
    }

    current: dict | None = None

    def flush() -> None:
        if current is None:
            return
        body = "\n".join(current.pop("_parts")).strip()
        body = _ATTACHED_RE.sub(" ", body)
        body = re.sub(r"\s{2,}", " ", body).strip()
        if not body:
            # Media-only message: nothing a ward officer can triage.
            return
        current["text"] = body[:2000]
        # Ward attribution happens here, on the *merged* body, not at the line
        # that opened the message: "near the school, Ward 12 lane 3" is a real
        # continuation line and the ward named there is the whole point.
        inferred = infer_ward_id(body, ward_map)
        # An explicit mention anywhere in the message wins; otherwise fall back
        # to the caller's default (the group's own ward), else NULL.
        current["ward_id"] = inferred if inferred is not None else default_ward_id
        messages.append(current)
        ts = current.get("received_ts")
        if ts:
            report["first_ts"] = min(report["first_ts"], ts) if report["first_ts"] else ts
            report["last_ts"] = max(report["last_ts"], ts) if report["last_ts"] else ts
        if current.get("ward_id") is not None:
            report["ward_inferred"] += 1
        else:
            report["ward_unresolved"] += 1

    for line in lines:
        match = _MESSAGE_RE.match(line.strip())
        if match:
            flush()
            sender = (match.group("sender") or "").strip() or "unknown"
            text = match.group("text").strip()
            ts = _parse_ts(match.group("date"), match.group("time"))
            if ts is None:
                report["messages_without_timestamp"] += 1

            has_media = bool(_ATTACHED_RE.search(text) or _MEDIA_OMITTED_RE.search(text))
            if has_media:
                report["messages_with_media"] += 1

            report["lines_parsed"] += 1
            report["senders"].add(sender)
            current = {
                "received_ts": ts,
                "sender_handle": sender[:120],
                "channel": channel,
                "ward_id": None,          # decided in flush(), once the body is whole
                "_parts": [text],
            }
            continue

        stripped = line.strip()
        if _is_system_line(stripped):
            report["lines_system"] += 1
            continue

        if current is not None:
            # A continuation of the previous sender's multi-line message.
            current["_parts"].append(stripped)
            report["lines_continuation"] += 1
        else:
            report["lines_unparsed"] += 1

    flush()

    report["senders"] = sorted(report["senders"])
    report["messages_returned"] = len(messages)
    return messages, report
