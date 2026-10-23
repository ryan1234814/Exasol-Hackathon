"""Tabular sample-log ingestion: CSV and Excel lab registers.

Municipal registers arrive with whatever header the clerk used, so this module
owns the alias map and the unit coercion, and — critically — returns a
per-row validation report rather than dropping bad rows silently. A dropped row
in a water-quality system is a sample that never happened.

Reading uses only the standard library ``csv`` plus ``openpyxl`` for .xlsx — no
pandas anywhere, so the ingest path adds one small dependency and the API's
request path adds none.
"""

from __future__ import annotations

import io
import math
import re
from datetime import datetime, date, time

# Uploads live in their own SAMPLE_ID range: 30_generate_readings.sql numbers
# every seeded row by arithmetic that tops out at 300,799, so nothing can ever
# collide.
UPLOAD_ID_BASE = 10_000_000_000

# Header -> canonical column. Keys are compared case- and whitespace-insensitive
# because real registers use "Turbidity (NTU)", "turbidity_ntu", "TURBIDITY".
COLUMN_ALIASES: dict[str, str] = {
    "ward": "WARD_ID", "wardid": "WARD_ID", "ward_id": "WARD_ID",
    "wardno": "WARD_ID", "ward_no": "WARD_ID", "wardnumber": "WARD_ID",
    "date": "SAMPLE_DATE", "sampledate": "SAMPLE_DATE", "sample_date": "SAMPLE_DATE",
    "samplingdate": "SAMPLE_DATE", "collectiondate": "SAMPLE_DATE",
    "parameter": "PARAM_CODE", "param": "PARAM_CODE", "parametercode": "PARAM_CODE",
    "paramcode": "PARAM_CODE", "parameter_code": "PARAM_CODE", "test": "PARAM_CODE",
    "value": "VALUE_DOUBLE", "result": "VALUE_DOUBLE", "reading": "VALUE_DOUBLE",
    "value_double": "VALUE_DOUBLE", "observedvalue": "VALUE_DOUBLE",
    "station": "STATION_ID", "stationid": "STATION_ID", "station_id": "STATION_ID",
    "samplingstation": "SOURCE_STATION", "sourcestation": "SOURCE_STATION",
    "source_station": "SOURCE_STATION", "location": "SOURCE_STATION",
    "lab": "LAB_VERIFIED", "labverified": "LAB_VERIFIED", "lab_verified": "LAB_VERIFIED",
}

# Parameter names as clerks type them -> PARAM_CODE.
PARAM_ALIASES: dict[str, str] = {
    "turbidity": "TURBIDITY", "ntu": "TURBIDITY", "turbidityntu": "TURBIDITY",
    "chlorine": "CHLORINE", "residualchlorine": "CHLORINE", "residual_free_chlorine": "CHLORINE",
    "freechlorine": "CHLORINE", "cl2": "CHLORINE",
    "coliform": "COLIFORM", "totalcoliform": "COLIFORM", "totalcoliformcfu": "COLIFORM",
    "ecoli": "COLIFORM", "mpn": "COLIFORM",
    "ph": "PH",
}

_TRUE = {"true", "t", "yes", "y", "1", "lab", "verified"}
_FALSE = {"false", "f", "no", "n", "0", "sensor", "field"}

_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
                 "%m/%d/%Y", "%d/%m/%y", "%Y/%m/%d", "%d %b %Y", "%d-%b-%Y")


def _norm(text) -> str:
    """Fold a header or cell to a comparable key: lowercase, no spacing.

    "Residual Free Chlorine", "residual_free_chlorine" and "RESIDUAL-FREE-CHLORINE"
    are the same measurement written three ways, so both the alias tables and
    the incoming text are normalised the same way before they meet.
    """
    return re.sub(r"[^a-z0-9]", "", str(text).lower().strip())


# Built from PARAM_ALIASES through _norm so a key can never be written in a
# form that the lookup is unable to reach.
_PARAM_LOOKUP = {_norm(alias): code for alias, code in PARAM_ALIASES.items()}


def _canon(header: str) -> str | None:
    text = str(header).lower().strip()
    # A register header often carries the unit in parentheses: "Result (mg/L)",
    # "Turbidity (NTU)", "Lab Verified (Y/N)". The unit belongs on the value,
    # not in the column name, so drop the parenthetical before matching.
    text = re.sub(r"\([^)]*\)", " ", text)
    key = re.sub(r"[^a-z0-9_]", "", text)
    return COLUMN_ALIASES.get(key) or COLUMN_ALIASES.get(key.replace("_", ""))


def _parse_date(value) -> date | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value).strip()
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(text).date()
    except ValueError:
        return None


def _parse_bool(value) -> bool:
    text = str(value).strip().lower()
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    return True  # a register row with no flag is treated as a lab result


def _parse_number(value) -> float | None:
    if value is None:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    text = str(value).strip().replace(",", "")
    if text == "" or text.lower() in {"na", "n/a", "nil", "none", "-", "--", "absent"}:
        return None
    # Strip a trailing unit the clerk typed into the cell: "3.4 NTU", "<0.5", "ND"
    if re.fullmatch(r"(?i)\s*(nd|not\s+detected|below\s+detect)\s*", text):
        return None
    text = re.sub(r"(?i)\s*(ntu|mg/l|cfu/100ml|cfu/100\s*ml|mpn/100ml|ph|ppm)\s*$", "", text)
    text = re.sub(r"^\s*[<>]=?\s*", "", text)
    try:
        return float(text)
    except ValueError:
        return None


def load_tabular(filename: str, content: bytes,
                 id_base: int = UPLOAD_ID_BASE) -> tuple[list[dict], dict]:
    """Parse CSV or Excel bytes into ``SAMPLE_LOG`` rows plus a validation report.

    Returns ``(rows, report)``. ``rows`` are dicts with the canonical uppercase
    keys; ``report.problems`` lists every rejected row with a reason and the
    original line, so the UI can show "3 of 120 rows need a human".

    SAMPLE_LOG declares SAMPLE_ID and SAMPLE_TS as NOT NULL, so uploaded rows
    cannot be returned without them. They are numbered from ``id_base``, a range
    the seeded generator never touches (its highest id is 300,799), so
    an upload can never collide with a generated row; the caller picks the exact
    offset by asking the database for the current high-water mark.
    """
    lower = (filename or "").lower()
    if lower.endswith((".xlsx", ".xls")):
        columns, records = _read_excel(content)
    else:
        columns, records = _read_csv(content)

    rows: list[dict] = []
    problems: list[dict] = []
    mapping: dict[str, str | None] = {}

    for header in columns:
        mapping[str(header)] = _canon(str(header))

    unmapped = [h for h, canon in mapping.items() if canon is None]

    for idx, raw in enumerate(records, start=2):
        canon: dict[str, object] = {}
        for header, value in raw.items():
            target = mapping.get(str(header))
            if target:
                canon[target] = value

        ward_id = canon.get("WARD_ID")
        sample_date = _parse_date(canon.get("SAMPLE_DATE"))
        param_raw = canon.get("PARAM_CODE")
        param_code = _PARAM_LOOKUP.get(_norm(param_raw))
        value = _parse_number(canon.get("VALUE_DOUBLE"))

        if ward_id is None or str(ward_id).strip() == "":
            problems.append({"line": idx, "reason": "missing WARD_ID", "raw": raw})
            continue
        try:
            ward_id = int(float(str(ward_id).strip()))
        except ValueError:
            problems.append({"line": idx, "reason": f"non-numeric ward: {ward_id!r}", "raw": raw})
            continue
        if sample_date is None:
            problems.append({"line": idx, "reason": "unparseable date", "raw": raw})
            continue
        if param_code is None:
            problems.append({"line": idx,
                             "reason": f"unknown parameter: {param_raw!r}", "raw": raw})
            continue
        if value is None:
            # Kept as a row with a NULL value: the sample happened, the result
            # did not. Dropping it would silently erase the gap from the trend.
            problems.append({"line": idx, "reason": "value missing/unparseable (kept as NULL)",
                             "raw": raw, "severity": "warning"})

        station_raw = canon.get("STATION_ID")
        try:
            station_id = int(float(str(station_raw).strip())) if station_raw not in (None, "") else 1
        except ValueError:
            station_id = 1

        rows.append({
            "SAMPLE_ID": id_base + len(rows),
            "WARD_ID": ward_id,
            "PARAM_CODE": param_code,
            "SAMPLE_DATE": sample_date,
            "SAMPLE_TS": datetime.combine(sample_date, time(0, 0)),
            "VALUE_DOUBLE": value,
            "STATION_ID": station_id,
            "SOURCE_STATION": str(canon.get("SOURCE_STATION") or f"Ward {ward_id} register"),
            "LAB_VERIFIED": _parse_bool(canon.get("LAB_VERIFIED")),
        })

    report = {
        "filename": filename,
        "id_base": id_base,
        "rows_read": len(records),
        "rows_accepted": len(rows),
        "rows_rejected": len([p for p in problems if p.get("severity") != "warning"]),
        "warnings": len([p for p in problems if p.get("severity") == "warning"]),
        "unmapped_headers": unmapped,
        "header_mapping": {h: c for h, c in mapping.items() if c},
        "problems": problems[:200],
    }
    return rows, report


def _read_csv(content: bytes) -> tuple[list[str], list[dict]]:
    """CSV via the standard library — no pandas, so the serving dependency list
    stays at what the starter kit already provides."""
    import csv

    text = content.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))
    try:
        header = [h.strip() for h in next(reader)]
    except StopIteration:
        return [], []
    records = [dict(zip(header, row)) for row in reader if any(c.strip() for c in row)]
    return header, records


def _read_excel(content: bytes) -> tuple[list[str], list[dict]]:
    """First worksheet of an .xlsx via openpyxl (MIT). .xls is not supported;
    the UI says so rather than failing obscurely."""
    import openpyxl

    workbook = openpyxl.load_workbook(io.BytesIO(content), read_only=True, data_only=True)
    sheet = workbook.worksheets[0]
    iterator = sheet.iter_rows(values_only=True)
    header = [str(h).strip() if h is not None else "" for h in next(iterator)]
    records = []
    for row in iterator:
        if row is None or not any(c not in (None, "") for c in row):
            continue
        records.append(dict(zip(header, row)))
    workbook.close()
    return header, records
