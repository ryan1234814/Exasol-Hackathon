"""The morning brief: three actions, composed from numbers that already exist.

Why a template and not a language model: the brief is read out loud in front of
a judge and then acted on by a ward officer. Every clause here is a formatted
value from ``WARD_MONTH_RISK``, ``V_WARD_FORECAST`` or ``V_LAB_VS_SENSOR`` — it
runs offline, costs nothing, and cannot say something the database does not
support. The same reason ``nlp_rules.py`` is a regex table instead of a model.

The function is pure: no database, no clock, no I/O. ``app.py`` gathers rows and
hands them over, so ``test_brief.py`` can pin the wording without a VM.
"""

from __future__ import annotations

from typing import Any

# The order is the product opinion: a ward already ranked worst beats a trend,
# and an instrument artefact beats a complaint backlog, because it is the one
# action that stops the team from chasing water that is actually clean.
ACTION_KINDS = ("rank", "crossing", "instrument")

NO_SIGNAL = ("No third action this month",
             "No instrument disagreement and no high-severity complaint in the "
             "latest month — that is a good month, not a missing feature.")

# Placeholders keep the brief a three-item list even when an input is missing:
# a numbered gap reads as a bug, an explicit "nothing here" reads as a finding.
NO_RANKING = ("No ward ranking available",
              "WARD_MONTH_RISK has no rows for this month — run `60_materialize.sql` "
              "then reload this page.")
NO_COUNTDOWN = ("No breach countdown this month",
                "No parameter is both deteriorating and inside the 90-day horizon.")


def _num(value: Any, digits: int = 1) -> str:
    """Format a number for prose; unknown values become an em dash, never 0."""
    if value is None or value == "":
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    text = f"{number:,.{digits}f}"
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _signed(value: Any, digits: int = 4) -> str:
    if value is None or value == "":
        return "—"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{number:+.{digits}f}"


def _ward_name(row: dict) -> str:
    return str(row.get("WARD_NAME") or f"ward {row.get('WARD_ID')}")


def _rank_action(ranked: list[dict]) -> dict | None:
    if not ranked:
        return None
    top = ranked[0]
    param = top.get("WORST_PARAM") or "water quality"
    detail = (
        f"{param} sits {_num(top.get('Z_COMPONENT'), 2)} of its 0–1 anomaly "
        f"component, with {_num(top.get('BREACH_COMPONENT'), 2)} of days in "
        f"breach and {_num(top.get('N_COMPLAINTS'), 0)} complaints "
        f"({_num(top.get('N_HIGH_SEV'), 0)} high severity)."
    )
    return {
        "N": 1,
        "KIND": "rank",
        "WARD_ID": top.get("WARD_ID"),
        "WARD_NAME": _ward_name(top),
        "TITLE": f"Start with {_ward_name(top)}",
        "DETAIL": detail,
        "SQL_STEP": "morning_brief",
        "SCORE": top.get("RISK_SCORE"),
    }


def _crossing_action(items: list[dict], exclude_ward: Any) -> dict | None:
    """Soonest genuine countdown to a limit, skipping the ward above.

    "Already over the limit" is excluded on purpose: that is an incident, not a
    forecast, and it belongs in the rank action instead.
    """
    candidates = [i for i in items
                  if i.get("STATUS") == "deteriorating" and i.get("DAYS_TO_BREACH") is not None]
    if not candidates:
        return None
    preferred = [i for i in candidates if i.get("WARD_ID") != exclude_ward] or candidates
    item = min(preferred, key=lambda i: (i["DAYS_TO_BREACH"], str(i.get("WARD_ID"))))
    param = item.get("PARAM_NAME") or item.get("PARAM_CODE")
    detail = (
        f"{item.get('HEADLINE')}. Currently {_num(item.get('CURRENT'), 3)} "
        f"{item.get('UNIT') or ''}, trend {_signed(item.get('SLOPE_PER_DAY'))} "
        f"per day over the last 12 months "
        f"({item.get('CONFIDENCE')} confidence, "
        f"{_num(item.get('RECENT_N'), 0)} samples)."
    ).replace("  ", " ")
    return {
        "N": 2,
        "KIND": "crossing",
        "WARD_ID": item.get("WARD_ID"),
        "WARD_NAME": item.get("WARD_NAME"),
        "TITLE": f"Plan for {item.get('WARD_NAME')} · {param}",
        "DETAIL": detail,
        "SQL_STEP": "forecast_eta",
        "DAYS_TO_BREACH": item.get("DAYS_TO_BREACH"),
    }


def _instrument_action(disagreements: list[dict]) -> dict | None:
    suspects = [d for d in disagreements if d.get("VERDICT") == "instrument_suspect"]
    if not suspects:
        return None
    worst = max(suspects, key=lambda d: (float(d.get("SENSOR_BREACHES") or 0),
                                         str(d.get("WARD_ID"))))
    param = worst.get("PARAM_CODE") or "parameter"
    detail = (
        f"{param}: {_num(worst.get('SENSOR_BREACHES'), 0)} sensor-only breaches "
        f"against {_num(worst.get('LAB_BREACHES'), 0)} lab-confirmed ones, with "
        f"{_num(worst.get('CITIZEN_COMPLAINTS_THAT_MONTH'), 0)} contamination "
        "complaints. A reading only the instrument believes is a maintenance "
        "ticket, not an outbreak — verify the probe before flushing."
    )
    return {
        "N": 3,
        "KIND": "instrument",
        "WARD_ID": worst.get("WARD_ID"),
        "WARD_NAME": worst.get("WARD_NAME"),
        "TITLE": f"Check the probe in {worst.get('WARD_NAME') or 'ward ' + str(worst.get('WARD_ID'))}",
        "DETAIL": detail,
        "SQL_STEP": "sensor_vs_lab",
    }


def _complaint_action(ranked: list[dict], exclude_ward: Any) -> dict | None:
    """Fallback for action three when no instrument disagreement was found."""
    rows = [r for r in ranked if r.get("N_HIGH_SEV")]
    if not rows:
        return None
    preferred = [r for r in rows if r.get("WARD_ID") != exclude_ward] or rows
    top = max(preferred, key=lambda r: (int(r.get("N_HIGH_SEV") or 0),
                                        -int(r.get("RANK_IN_MONTH") or 999)))
    detail = (
        f"{_num(top.get('N_HIGH_SEV'), 0)} of {_num(top.get('N_COMPLAINTS'), 0)} "
        "complaints this month are high severity (illness, no water for days, "
        "black water). The triage queue is already severity-sorted."
    )
    return {
        "N": 3,
        "KIND": "complaints",
        "WARD_ID": top.get("WARD_ID"),
        "WARD_NAME": _ward_name(top),
        "TITLE": f"Clear the high-severity queue in {_ward_name(top)}",
        "DETAIL": detail,
        "SQL_STEP": "complaint_category_mix",
    }


def _placeholder(n: int, kind: str, text: tuple[str, str], sql_step: str) -> dict:
    return {
        "N": n,
        "KIND": kind,
        "WARD_ID": None,
        "WARD_NAME": None,
        "TITLE": text[0],
        "DETAIL": text[1],
        "SQL_STEP": sql_step,
    }


def _watchlist(ranked: list[dict], count: int = 3) -> list[dict]:
    out = []
    for row in ranked[1:1 + count]:
        out.append({
            "WARD_ID": row.get("WARD_ID"),
            "WARD_NAME": _ward_name(row),
            "RISK_SCORE": row.get("RISK_SCORE"),
            "WORST_PARAM": row.get("WORST_PARAM"),
            "RANK_IN_MONTH": row.get("RANK_IN_MONTH"),
            "N_HIGH_SEV": row.get("N_HIGH_SEV"),
        })
    return out


def _headline(month: str, counts: dict, ranked: list[dict], freshness: dict) -> str:
    """One line of scale and freshness — clauses drop out when data is absent."""
    worst = ranked[0] if ranked else {}
    as_of = freshness.get("LAST_RUN_TS")
    wards = counts.get("wards")
    parts = [f"{month}: {_num(wards, 0)} wards ranked" if wards else str(month)]
    if worst:
        parts.append(f"worst is {_ward_name(worst)} at {_num(worst.get('RISK_SCORE'))}")
    readings, complaints = counts.get("sample_rows"), counts.get("complaint_rows")
    if readings or complaints:
        parts.append(f"{_num(readings, 0)} readings and "
                     f"{_num(complaints, 0)} complaints analysed")
    if as_of:
        parts.append(f"data as of {str(as_of)[:19]}")
    return "; ".join(parts) + "."


def _markdown(payload: dict) -> str:
    """The same brief as a pasted report — the copy/download payload."""
    lines = [f"# Morning brief — {payload['MONTH']}", "",
             payload["HEADLINE"], ""]
    lines.append("## Do these three things today")
    for action in payload["ACTIONS"]:
        lines.append(f"{action['N']}. **{action['TITLE']}** — {action['DETAIL']}")
    lines.append("")
    if payload["WATCHLIST"]:
        lines.append("## Watchlist")
        lines.append("")
        lines.append("| Ward | Risk | Worst parameter | High-severity complaints |")
        lines.append("|---|---|---|---|")
        for row in payload["WATCHLIST"]:
            lines.append(f"| {row['WARD_NAME']} | {_num(row['RISK_SCORE'])} | "
                         f"{row['WORST_PARAM'] or '—'} | {_num(row['N_HIGH_SEV'], 0)} |")
        lines.append("")
    lines.append("## Data and limits")
    lines.append("")
    lines.append(f"- Schema `WARDQ` · month `{payload['MONTH']}` · "
                 f"data as of `{payload.get('DATA_AS_OF') or 'unknown'}`")
    lines.append(f"- {_num(payload['COUNTS'].get('sample_rows'), 0)} readings · "
                 f"{_num(payload['COUNTS'].get('complaint_rows'), 0)} complaints · "
                 f"{_num(payload['COUNTS'].get('wards'), 0)} wards")
    lines.append("- Single-node local Exasol Personal VM (2 vCPU / 6 GB); "
                 "forecast is a 12-month linear slope, not a model.")
    lines.append("- Every number above comes from the queries listed in the "
                 "dashboard's SQL drawer — nothing is generated prose.")
    return "\n".join(lines) + "\n"


def build_brief(*, month: str, counts: dict | None = None,
                ranked: list[dict] | None = None,
                forecast_items: list[dict] | None = None,
                disagreements: list[dict] | None = None,
                freshness: dict | None = None) -> dict:
    """Assemble the brief. Any missing input degrades to a truthful line."""
    counts = counts or {}
    ranked = ranked or []
    forecast_items = forecast_items or []
    disagreements = disagreements or []
    freshness = freshness or {}

    actions: list[dict] = []
    first = _rank_action(ranked)
    if first is None:
        first = _placeholder(1, "none", NO_RANKING, "morning_brief")
    actions.append(first)

    second = _crossing_action(forecast_items, first.get("WARD_ID"))
    if second is None:
        second = _placeholder(2, "none", NO_COUNTDOWN, "forecast_eta")
    actions.append(second)

    third = (_instrument_action(disagreements)
             or _complaint_action(ranked, first.get("WARD_ID")))
    if third is None:
        third = _placeholder(3, "none", NO_SIGNAL, "latest_risk")
    actions.append(third)

    # Numbers restart at 1..3 in display order, so the brief always reads as
    # three numbered tasks even when a slot is a placeholder.
    for index, action in enumerate(actions, start=1):
        action["N"] = index

    payload = {
        "MONTH": month,
        "HEADLINE": _headline(month, counts, ranked, freshness),
        "ACTIONS": actions[:3],
        "WATCHLIST": _watchlist(ranked),
        "COUNTS": counts,
        "DATA_AS_OF": freshness.get("LAST_RUN_TS"),
        "DATA_SOURCE": freshness.get("LOAD_SOURCE"),
        "NOTE": "Composed from SQL results by backend/brief.py — no model, no network.",
    }
    payload["MARKDOWN"] = _markdown(payload)
    return payload
