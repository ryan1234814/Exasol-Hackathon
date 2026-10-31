"""The morning brief: three actions, composed from numbers that already exist.

Why a template and not a language model: the brief is read out loud in front of
a judge and then acted on by a ward officer. Every clause here is a formatted
value from ``WARD_MONTH_RISK``, ``V_WARD_FORECAST`` or ``V_LAB_VS_SENSOR`` — it
runs offline, costs nothing, and cannot say something the database does not
support. The same reason ``nlp_rules.py`` is a regex table instead of a model.

The function is pure: no database, no clock, no I/O. ``app.py`` gathers rows and
hands them over, so ``test_brief.py`` can pin the wording without a VM.

Bilingual by template, not by framework. Every sentence lives in ``STRINGS``
under a language code, so Hindi is one more entry in a dict rather than a
translation layer: no dependency, no build step, and the numbers are still
formatted by the same helpers. ``en`` is the default and its output is
byte-identical to what shipped before the second language existed; an unknown
language falls back to ``en`` instead of failing a request.
"""

from __future__ import annotations

from typing import Any

# The order is the product opinion: a ward already ranked worst beats a trend,
# and an instrument artefact beats a complaint backlog, because it is the one
# action that stops the team from chasing water that is actually clean.
ACTION_KINDS = ("rank", "crossing", "instrument")

LANGS = ("en", "hi")
DEFAULT_LANG = "en"

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

NO_SIGNAL_HI = ("इस महीने तीसरा काम नहीं है",
                "इस महीने कोई सेंसर विसंगति और कोई उच्च-गंभीरता शिकायत नहीं — "
                "यह अच्छा महीना है, कोई कमी नहीं।")
NO_RANKING_HI = ("वार्ड रैंकिंग उपलब्ध नहीं है",
                 "WARD_MONTH_RISK में इस महीने की कोई पंक्ति नहीं है — "
                 "`60_materialize.sql` चलाएँ और यह पेज फिर खोलें।")
NO_COUNTDOWN_HI = ("इस महीने कोई उल्लंघन-गणना नहीं है",
                   "कोई भी पैरामीटर ऐसा नहीं है जो बिगड़ रहा हो और 90 दिन की "
                   "सीमा के भीतर हो।")

_STRINGS_EN = {
    "no_signal": NO_SIGNAL,
    "no_ranking": NO_RANKING,
    "no_countdown": NO_COUNTDOWN,
    "param_fallback": "water quality",
    "ward_fallback": "ward {id}",

    "title_rank": "Start with {ward}",
    "detail_rank": ("{param} sits {z} of its 0–1 anomaly component, with {breach} "
                    "of days in breach and {complaints} complaints ({high} high "
                    "severity)."),
    "title_crossing": "Plan for {ward} · {param}",
    "detail_crossing": ("{headline}. Currently {current} {unit}, trend {slope} per "
                        "day over the last 12 months ({confidence} confidence, "
                        "{n} samples)."),
    "title_instrument": "Check the probe in {ward}",
    "detail_instrument": ("{param}: {sensor} sensor-only breaches against {lab} "
                          "lab-confirmed ones, with {complaints} contamination "
                          "complaints. A reading only the instrument believes is a "
                          "maintenance ticket, not an outbreak — verify the probe "
                          "before flushing."),
    "title_complaints": "Clear the high-severity queue in {ward}",
    "detail_complaints": ("{high} of {total} complaints this month are high severity "
                          "(illness, no water for days, black water). The triage "
                          "queue is already severity-sorted."),

    "headline_scale": "{month}: {wards} wards ranked",
    "headline_worst": "worst is {ward} at {risk}",
    "headline_volume": "{readings} readings and {complaints} complaints analysed",
    "headline_asof": "data as of {as_of}",
    "clause_sep": "; ",
    "sentence_end": ".",

    "md_title": "# Morning brief — {month}",
    "md_actions": "## Do these three things today",
    "md_watchlist": "## Watchlist",
    "md_data": "## Data and limits",
    "md_table_head": "| Ward | Risk | Worst parameter | High-severity complaints |",
    "md_meta": "- Schema `WARDQ` · month `{month}` · data as of `{as_of}`",
    "md_counts": "- {readings} readings · {complaints} complaints · {wards} wards",
    "md_caveat": ("- Single-node local Exasol Personal VM (2 vCPU / 6 GB); "
                  "forecast is a 12-month linear slope, not a model."),
    "md_trace": ("- Every number above comes from the queries listed in the "
                 "dashboard's SQL drawer — nothing is generated prose."),
    "note": "Composed from SQL results by backend/brief.py — no model, no network.",
}

_STRINGS_HI = {
    "no_signal": NO_SIGNAL_HI,
    "no_ranking": NO_RANKING_HI,
    "no_countdown": NO_COUNTDOWN_HI,
    "param_fallback": "पानी की गुणवत्ता",
    "ward_fallback": "वार्ड {id}",

    "title_rank": "{ward} से शुरुआत करें",
    "detail_rank": ("{param} अपने 0–1 विसंगति घटक का {z} है, {breach} दिन सीमा से "
                    "बाहर और {complaints} शिकायतें ({high} उच्च-गंभीरता) दर्ज हैं।"),
    "title_crossing": "{ward} · {param} की योजना बनाएँ",
    "detail_crossing": ("{headline}। अभी {current} {unit}, पिछले 12 महीनों में "
                        "रुझान {slope} प्रति दिन ({confidence} भरोसा, {n} नमूने)।"),
    "title_instrument": "{ward} में सेंसर जाँचें",
    "detail_instrument": ("{param}: {sensor} केवल-सेंसर उल्लंघन, {lab} लैब-पुष्ट। "
                          "साथ में {complaints} संदूषण शिकायतें। जिस रीडिंग पर केवल "
                          "यंत्र भरोसा करता है वह रखरखाव का टिकट है, प्रकोप नहीं — "
                          "फ्लश से पहले जाँचें।"),
    "title_complaints": "{ward} की उच्च-गंभीरता शिकायतें निपटाएँ",
    "detail_complaints": ("इस महीने {total} में से {high} शिकायतें उच्च-गंभीरता की "
                          "हैं (बीमारी, कई दिन पानी नहीं, काला पानी)। शिकायत सूची "
                          "गंभीरता से क्रमबद्ध है।"),

    "headline_scale": "{month}: {wards} वार्ड रैंक",
    "headline_worst": "सबसे खराब {ward} ({risk})",
    "headline_volume": "{readings} रीडिंग और {complaints} शिकायतें जाँची गईं",
    "headline_asof": "डेटा {as_of} तक",
    "clause_sep": " · ",
    "sentence_end": "।",

    "md_title": "# सुबह की रिपोर्ट — {month}",
    "md_actions": "## आज ये तीन काम करें",
    "md_watchlist": "## निगरानी सूची",
    "md_data": "## डेटा और सीमाएँ",
    "md_table_head": "| वार्ड | जोखिम | सबसे खराब पैरामीटर | उच्च-गंभीरता शिकायतें |",
    "md_meta": "- स्कीमा `WARDQ` · महीना `{month}` · डेटा `{as_of}` तक",
    "md_counts": "- {readings} रीडिंग · {complaints} शिकायतें · {wards} वार्ड",
    "md_caveat": ("- सिंगल-नोड लोकल Exasol Personal VM (2 vCPU / 6 GB); पूर्वानुमान "
                  "12 महीने की रैखिक प्रवृत्ति है, कोई मॉडल नहीं।"),
    "md_trace": ("- ऊपर का हर आँकड़ा डैशबोर्ड के SQL ड्रॉअर में दी गई क्वेरी से आता है — "
                 "कोई भी वाक्य अनुमान से नहीं लिखा गया।"),
    "note": ("SQL परिणामों से backend/brief.py द्वारा बनाया गया — कोई मॉडल नहीं, "
             "कोई नेटवर्क नहीं।"),
}

STRINGS = {"en": _STRINGS_EN, "hi": _STRINGS_HI}


def strings_for(lang: str | None) -> dict:
    """Templates for ``lang``, falling back to English for anything unknown."""
    return STRINGS.get(str(lang or DEFAULT_LANG).lower(), _STRINGS_EN)


def resolve_lang(lang: str | None) -> str:
    code = str(lang or DEFAULT_LANG).lower()
    return code if code in STRINGS else DEFAULT_LANG


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


def _ward_name(row: dict, strings: dict) -> str:
    name = row.get("WARD_NAME")
    if name:
        return str(name)
    return strings["ward_fallback"].format(id=row.get("WARD_ID"))


def _rank_action(ranked: list[dict], strings: dict) -> dict | None:
    if not ranked:
        return None
    top = ranked[0]
    param = top.get("WORST_PARAM") or strings["param_fallback"]
    detail = strings["detail_rank"].format(
        param=param,
        z=_num(top.get("Z_COMPONENT"), 2),
        breach=_num(top.get("BREACH_COMPONENT"), 2),
        complaints=_num(top.get("N_COMPLAINTS"), 0),
        high=_num(top.get("N_HIGH_SEV"), 0),
    )
    return {
        "N": 1,
        "KIND": "rank",
        "WARD_ID": top.get("WARD_ID"),
        "WARD_NAME": _ward_name(top, strings),
        "TITLE": strings["title_rank"].format(ward=_ward_name(top, strings)),
        "DETAIL": detail,
        "SQL_STEP": "morning_brief",
        "SCORE": top.get("RISK_SCORE"),
    }


def _crossing_action(items: list[dict], exclude_ward: Any, strings: dict) -> dict | None:
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
    detail = strings["detail_crossing"].format(
        headline=item.get("HEADLINE"),
        current=_num(item.get("CURRENT"), 3),
        unit=item.get("UNIT") or "",
        slope=_signed(item.get("SLOPE_PER_DAY")),
        confidence=item.get("CONFIDENCE"),
        n=_num(item.get("RECENT_N"), 0),
    ).replace("  ", " ")
    ward_name = _ward_name(item, strings)
    return {
        "N": 2,
        "KIND": "crossing",
        "WARD_ID": item.get("WARD_ID"),
        "WARD_NAME": item.get("WARD_NAME"),
        "TITLE": strings["title_crossing"].format(ward=ward_name, param=param),
        "DETAIL": detail,
        "SQL_STEP": "forecast_eta",
        "DAYS_TO_BREACH": item.get("DAYS_TO_BREACH"),
    }


def _instrument_action(disagreements: list[dict], strings: dict) -> dict | None:
    suspects = [d for d in disagreements if d.get("VERDICT") == "instrument_suspect"]
    if not suspects:
        return None
    worst = max(suspects, key=lambda d: (float(d.get("SENSOR_BREACHES") or 0),
                                         str(d.get("WARD_ID"))))
    param = worst.get("PARAM_CODE") or "parameter"
    detail = strings["detail_instrument"].format(
        param=param,
        sensor=_num(worst.get("SENSOR_BREACHES"), 0),
        lab=_num(worst.get("LAB_BREACHES"), 0),
        complaints=_num(worst.get("CITIZEN_COMPLAINTS_THAT_MONTH"), 0),
    )
    ward_name = _ward_name(worst, strings)
    return {
        "N": 3,
        "KIND": "instrument",
        "WARD_ID": worst.get("WARD_ID"),
        "WARD_NAME": worst.get("WARD_NAME"),
        "TITLE": strings["title_instrument"].format(ward=ward_name),
        "DETAIL": detail,
        "SQL_STEP": "sensor_vs_lab",
    }


def _complaint_action(ranked: list[dict], exclude_ward: Any, strings: dict) -> dict | None:
    """Fallback for action three when no instrument disagreement was found."""
    rows = [r for r in ranked if r.get("N_HIGH_SEV")]
    if not rows:
        return None
    preferred = [r for r in rows if r.get("WARD_ID") != exclude_ward] or rows
    top = max(preferred, key=lambda r: (int(r.get("N_HIGH_SEV") or 0),
                                        -int(r.get("RANK_IN_MONTH") or 999)))
    detail = strings["detail_complaints"].format(
        high=_num(top.get("N_HIGH_SEV"), 0),
        total=_num(top.get("N_COMPLAINTS"), 0),
    )
    return {
        "N": 3,
        "KIND": "complaints",
        "WARD_ID": top.get("WARD_ID"),
        "WARD_NAME": _ward_name(top, strings),
        "TITLE": strings["title_complaints"].format(ward=_ward_name(top, strings)),
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


def _watchlist(ranked: list[dict], strings: dict, count: int = 3) -> list[dict]:
    out = []
    for row in ranked[1:1 + count]:
        out.append({
            "WARD_ID": row.get("WARD_ID"),
            "WARD_NAME": _ward_name(row, strings),
            "RISK_SCORE": row.get("RISK_SCORE"),
            "WORST_PARAM": row.get("WORST_PARAM"),
            "RANK_IN_MONTH": row.get("RANK_IN_MONTH"),
            "N_HIGH_SEV": row.get("N_HIGH_SEV"),
        })
    return out


def _headline(month: str, counts: dict, ranked: list[dict], freshness: dict,
              strings: dict) -> str:
    """One line of scale and freshness — clauses drop out when data is absent."""
    worst = ranked[0] if ranked else {}
    as_of = freshness.get("LAST_RUN_TS")
    wards = counts.get("wards")
    parts = []
    if wards:
        parts.append(strings["headline_scale"].format(month=month, wards=_num(wards, 0)))
    else:
        parts.append(str(month))
    if worst:
        parts.append(strings["headline_worst"].format(
            ward=_ward_name(worst, strings), risk=_num(worst.get("RISK_SCORE"))))
    readings, complaints = counts.get("sample_rows"), counts.get("complaint_rows")
    if readings or complaints:
        parts.append(strings["headline_volume"].format(
            readings=_num(readings, 0), complaints=_num(complaints, 0)))
    if as_of:
        parts.append(strings["headline_asof"].format(as_of=str(as_of)[:19]))
    return strings["clause_sep"].join(parts) + strings["sentence_end"]


def _markdown(payload: dict, strings: dict) -> str:
    """The same brief as a pasted report — the copy/download payload."""
    lines = [strings["md_title"].format(month=payload["MONTH"]), "",
             payload["HEADLINE"], ""]
    lines.append(strings["md_actions"])
    for action in payload["ACTIONS"]:
        lines.append(f"{action['N']}. **{action['TITLE']}** — {action['DETAIL']}")
    lines.append("")
    if payload["WATCHLIST"]:
        lines.append(strings["md_watchlist"])
        lines.append("")
        lines.append(strings["md_table_head"])
        lines.append("|---|---|---|---|")
        for row in payload["WATCHLIST"]:
            lines.append(f"| {row['WARD_NAME']} | {_num(row['RISK_SCORE'])} | "
                         f"{row['WORST_PARAM'] or '—'} | {_num(row['N_HIGH_SEV'], 0)} |")
        lines.append("")
    lines.append(strings["md_data"])
    lines.append("")
    lines.append(strings["md_meta"].format(
        month=payload["MONTH"], as_of=payload.get("DATA_AS_OF") or "unknown"))
    lines.append(strings["md_counts"].format(
        readings=_num(payload["COUNTS"].get("sample_rows"), 0),
        complaints=_num(payload["COUNTS"].get("complaint_rows"), 0),
        wards=_num(payload["COUNTS"].get("wards"), 0)))
    lines.append(strings["md_caveat"])
    lines.append(strings["md_trace"])
    return "\n".join(lines) + "\n"


def build_brief(*, month: str, counts: dict | None = None,
                ranked: list[dict] | None = None,
                forecast_items: list[dict] | None = None,
                disagreements: list[dict] | None = None,
                freshness: dict | None = None,
                lang: str | None = DEFAULT_LANG) -> dict:
    """Assemble the brief. Any missing input degrades to a truthful line.

    ``lang`` only selects a template table; the numbers, the ordering and the
    payload shape are identical in every language, which is what lets the UI
    switch language without invalidating anything it already rendered.
    """
    counts = counts or {}
    ranked = ranked or []
    forecast_items = forecast_items or []
    disagreements = disagreements or []
    freshness = freshness or {}
    code = resolve_lang(lang)
    strings = strings_for(code)

    actions: list[dict] = []
    first = _rank_action(ranked, strings)
    if first is None:
        first = _placeholder(1, "none", strings["no_ranking"], "morning_brief")
    actions.append(first)

    second = _crossing_action(forecast_items, first.get("WARD_ID"), strings)
    if second is None:
        second = _placeholder(2, "none", strings["no_countdown"], "forecast_eta")
    actions.append(second)

    third = (_instrument_action(disagreements, strings)
             or _complaint_action(ranked, first.get("WARD_ID"), strings))
    if third is None:
        third = _placeholder(3, "none", strings["no_signal"], "latest_risk")
    actions.append(third)

    # Numbers restart at 1..3 in display order, so the brief always reads as
    # three numbered tasks even when a slot is a placeholder.
    for index, action in enumerate(actions, start=1):
        action["N"] = index

    payload = {
        "MONTH": month,
        "LANG": code,
        "HEADLINE": _headline(month, counts, ranked, freshness, strings),
        "ACTIONS": actions[:3],
        "WATCHLIST": _watchlist(ranked, strings),
        "COUNTS": counts,
        "DATA_AS_OF": freshness.get("LAST_RUN_TS"),
        "DATA_SOURCE": freshness.get("LOAD_SOURCE"),
        # Section titles for the page, taken from the same table the markdown
        # headings come from. Without these the Hindi brief would arrive complete
        # but sit under English headings, which is the exact half-translation the
        # scope note on the Trust page promises not to ship. The '## ' is stripped
        # so one string serves both the markdown and the <h2>.
        "HEADINGS": {
            "ACTIONS": strings["md_actions"].removeprefix("## "),
            "WATCHLIST": strings["md_watchlist"].removeprefix("## "),
            "MARKDOWN": strings["md_data"].removeprefix("## "),
        },
        "NOTE": strings["note"],
    }
    payload["MARKDOWN"] = _markdown(payload, strings)
    return payload
