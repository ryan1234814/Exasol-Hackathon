"""Breach forecast arithmetic, deliberately separated from the database.

The warehouse can tell us two numbers per ward x parameter — a 30-day mean and
a trailing 12-month slope (``WARDQ.V_WARD_FORECAST``). Turning those two numbers
into "crosses 5 NTU in ~43 days, ±1.4" is a policy decision with four branches,
and each branch is a different sentence on stage:

* chlorine drifting DOWN toward 0.2 mg/L is deteriorating,
* turbidity drifting UP toward 5 NTU is deteriorating,
* pH above 8.5 with a negative slope is *improving*,
* coliform's limit is 0, so it is almost always "already over" rather than a
  countdown.

Keeping that logic here means it is unit-testable with no database and no
FastAPI, exactly like ``nlp_rules.py``. Nothing in this module imports the DB.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta
from typing import Any

# How far ahead the UI is willing to claim. A 12-month slope extended further
# than a quarter is numerology, not a forecast.
HORIZON_DAYS = 90

# The band widens as a random walk: sigma grows with the square root of time.
# Seven days is the sampling cadence the daily aggregate already implies.
BAND_STEP_DAYS = 7.0
BAND_Z = 1.96

# Below this many recent samples a standard deviation is not a measurement.
MIN_BAND_SAMPLES = 7

# A slope this shallow is flat at the precision the dashboard displays, and
# without this guard it produces headlines like "breaches in 9,412 days".
FLAT_SLOPE = 1e-9

STATUSES = ("over_limit", "deteriorating", "improving", "stable", "unknown")


def _as_float(value: Any) -> float | None:
    """pyexasol hands back Decimal for DECIMAL columns; normalise once, here."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _fmt(value: float | None, digits: int = 2) -> str:
    if value is None:
        return "—"
    return f"{value:.{digits}f}".rstrip("0").rstrip(".")


def _limit_in_play(slope: float, lo: float | None, hi: float | None):
    """Which bound the current trend is walking toward.

    Returns ``(limit, rising)`` or ``(None, rising)`` when the trend is moving
    away from the only bound that exists (a rising series with no upper limit
    cannot breach, so there is nothing to count down to).
    """
    rising = slope > 0
    if rising and hi is not None:
        return hi, True
    if not rising and lo is not None:
        return lo, False
    return None, rising


def is_over_limit(current: float | None, lo: float | None, hi: float | None) -> bool:
    if current is None:
        return False
    if hi is not None and current > hi:
        return True
    if lo is not None and current < lo:
        return True
    return False


def days_to_breach(current: float | None, slope: float | None,
                   lo: float | None, hi: float | None) -> float | None:
    """Days until the trend reaches a limit; negative means already past it.

    ``None`` means "no countdown is meaningful": no history, a flat slope, or a
    trend heading away from the only limit.
    """
    current = _as_float(current)
    slope = _as_float(slope)
    lo, hi = _as_float(lo), _as_float(hi)
    if current is None or slope is None or abs(slope) < FLAT_SLOPE:
        return None
    limit, rising = _limit_in_play(slope, lo, hi)
    if limit is None:
        return None
    distance = (limit - current) if rising else (current - limit)
    return round(distance / abs(slope), 1)


def status_for(current: float | None, slope: float | None, lo: float | None,
               hi: float | None, horizon_days: int = HORIZON_DAYS) -> str:
    """One of ``STATUSES`` — the label the UI colours and the brief quotes."""
    current = _as_float(current)
    slope = _as_float(slope)
    lo, hi = _as_float(lo), _as_float(hi)
    if current is None:
        return "unknown"
    if is_over_limit(current, lo, hi):
        return "over_limit"
    if slope is None:
        return "unknown"
    if abs(slope) < FLAT_SLOPE:
        return "stable"

    limit, _rising = _limit_in_play(slope, lo, hi)
    if limit is None:
        # Drifting away from the only bound that exists.
        return "improving"

    eta = days_to_breach(current, slope, lo, hi)
    if eta is None:
        return "unknown"
    if eta <= 0:
        return "over_limit"
    if eta <= horizon_days:
        return "deteriorating"
    # Real trend, but too slow to call inside the promised horizon.
    return "stable"


def project(current: float | None, slope: float | None, days: int) -> float | None:
    """Linear projection, floored at zero (no negative NTU or CFU exists)."""
    current = _as_float(current)
    slope = _as_float(slope)
    if current is None or slope is None:
        return None
    return round(max(0.0, current + slope * days), 3)


def band(current: float | None, stddev: float | None, days: int,
         n: int | None) -> tuple[float, float] | None:
    """±1.96 sigma at ``days`` ahead, widening as sqrt(days / 7).

    ``None`` when there is not enough recent history for sigma to mean
    anything — a fake-narrow band is worse than no band.
    """
    current = _as_float(current)
    stddev = _as_float(stddev)
    if current is None or stddev is None or n is None or n < MIN_BAND_SAMPLES:
        return None
    width = BAND_Z * stddev * (max(days, 0) / BAND_STEP_DAYS) ** 0.5
    return (round(max(0.0, current - width), 3), round(current + width, 3))


def confidence(n: int | None, stddev: float | None) -> str:
    """A statement about sample size only — never about model skill."""
    n = _as_float(n)
    if n is None or n < MIN_BAND_SAMPLES or _as_float(stddev) is None:
        return "low"
    if n >= 25:
        return "high"
    if n >= 14:
        return "medium"
    return "low"


def breach_date(last_date: Any, eta_days: float | None) -> str | None:
    """ISO date of the projected crossing, or ``None`` for no countdown."""
    eta = _as_float(eta_days)
    if last_date is None or eta is None or eta < 0:
        return None
    if isinstance(last_date, datetime):
        anchor = last_date.date()
    elif isinstance(last_date, date):
        anchor = last_date
    else:
        text = str(last_date)[:10]
        try:
            anchor = datetime.strptime(text, "%Y-%m-%d").date()
        except ValueError:
            return None
    return (anchor + timedelta(days=int(round(eta)))).isoformat()


def headline(item: dict) -> str:
    """One sentence a ward officer can read out loud."""
    name = item.get("PARAM_NAME") or item.get("PARAM_CODE") or "parameter"
    unit = item.get("UNIT") or ""
    lo, hi = item.get("THRESHOLD_LO"), item.get("THRESHOLD_HI")
    status = item.get("STATUS")

    def with_unit(value):
        text = _fmt(value)
        return f"{text} {unit}".strip()

    if status == "unknown":
        return f"not enough recent history to forecast {name}"
    if status == "over_limit":
        if hi is not None and (lo is None or (item.get("CURRENT") or 0) > hi):
            return f"already above the {with_unit(hi)} limit"
        if lo is not None:
            return f"already below the {with_unit(lo)} limit"
        return "already outside its limit"
    if status == "deteriorating":
        limit = hi if (item.get("SLOPE_PER_DAY") or 0) > 0 else lo
        eta = item.get("DAYS_TO_BREACH")
        when = item.get("BREACH_DATE")
        tail = f" ({when})" if when else ""
        return f"crosses {with_unit(limit)} in ~{_fmt(eta, 0)} days{tail}"
    if status == "improving":
        limit = lo if (item.get("SLOPE_PER_DAY") or 0) > 0 else hi
        return f"moving away from the {with_unit(limit)} limit"
    return f"no breach expected within {int(item.get('HORIZON_DAYS') or HORIZON_DAYS)} days"


def summarise(row: dict, horizon_days: int = HORIZON_DAYS) -> dict:
    """Turn one ``V_WARD_FORECAST`` row into the shape the UI renders.

    Unknown inputs stay ``None`` all the way to the JSON — the UI prints an em
    dash. Inventing a zero here would be the one thing that makes the forecast
    untrustworthy on stage.
    """
    current = _as_float(row.get("RECENT_AVG"))
    slope = _as_float(row.get("SLOPE_12M"))
    stddev = _as_float(row.get("RECENT_STDDEV"))
    n = _as_float(row.get("RECENT_N"))
    lo, hi = row.get("THRESHOLD_LO"), row.get("THRESHOLD_HI")

    status = status_for(current, slope, lo, hi, horizon_days)
    eta = days_to_breach(current, slope, lo, hi)
    span = band(current, stddev, horizon_days, None if n is None else int(n))

    item = {
        "WARD_ID": row.get("WARD_ID"),
        "WARD_NAME": row.get("WARD_NAME"),
        "PARAM_CODE": row.get("PARAM_CODE"),
        "PARAM_NAME": row.get("PARAM_NAME"),
        "UNIT": row.get("UNIT"),
        "THRESHOLD_LO": _as_float(lo),
        "THRESHOLD_HI": _as_float(hi),
        "CURRENT": None if current is None else round(current, 3),
        "SLOPE_PER_DAY": None if slope is None else round(slope, 6),
        "RECENT_STDDEV": None if stddev is None else round(stddev, 4),
        "RECENT_N": None if n is None else int(n),
        "LAST_DATE": str(row.get("LAST_DATE"))[:10] if row.get("LAST_DATE") else None,
        "STATUS": status,
        "DAYS_TO_BREACH": eta,
        "BREACH_DATE": breach_date(row.get("LAST_DATE"), eta),
        "PROJECTED_30D": project(current, slope, 30),
        "PROJECTED_90D": project(current, slope, 90),
        "BAND_LOW": span[0] if span else None,
        "BAND_HIGH": span[1] if span else None,
        "CONFIDENCE": confidence(None if n is None else int(n), stddev),
        "HORIZON_DAYS": horizon_days,
    }
    item["HEADLINE"] = headline(item)
    return item
