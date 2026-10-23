"""Build the COMPLAINT table: parse the real-shaped fixtures, then scale.

Two sources, deliberately:

1. ``data/raw/whatsapp_ward_exports/*.txt`` — hand-written exports in exactly
   the messy shape a real group chat has. These are what the parser tests run
   against and what the live ingest demo uploads, so the "we parsed an actual
   WhatsApp export" claim is demonstrated, not asserted.
2. A deterministic synthetic corpus on top, to give the ward x month rollups
   enough volume that a trend is statistically meaningful rather than one
   person complaining loudly.

Seeded, so ``make load`` twice produces identical analytics and the benchmark
numbers quoted in the PRD stay true.
"""

from __future__ import annotations

import random
import re
from datetime import datetime, timedelta
from pathlib import Path

from backend.ingest.whatsapp_parser import infer_ward_id, parse_chat
from backend.nlp_rules import classify

# this file lives at <repo>/backend/ingest/, so the repo root is three levels up.
REPO_ROOT = Path(__file__).resolve().parents[2]
FIXTURE_DIR = REPO_ROOT / "data" / "raw" / "whatsapp_ward_exports"

BULK_TARGET = 15_000
SEED = 20261023
SPINE_START = datetime(2024, 10, 1)
SPINE_DAYS = 752

# Message templates per category. ``{ward}`` is interpolated so the parser's
# ward-inference path is exercised by the bulk corpus too, not just the fixtures.
TEMPLATES: dict[str, list[tuple[str, int]]] = {
    # (template, weight) — weight biases the mix toward what a real register looks like
    "contamination": [
        ("Water from {ward} tap is black colour, cannot use for cooking", 6),
        ("{ward} area paani mein se bohot buri smell aa rahi hai", 5),
        ("Since 3 days muddy water in {ward}. Children have loose motion and fever", 4),
        ("Paani ka swad kharab hai {ward} mein, chlorine ki bahut tez smell", 4),
        ("White powder settling after boiling in {ward}. Is water safe?", 3),
        ("{ward} supply has yellow water and a chemical taste, hospital case nearby", 3),
        ("Worms found in overhead tank of {ward} building. Please test immediately", 2),
        ("{ward} ke paani se ganda smell aa rahi hai, pet kharab ho gaya", 3),
        ("Skin rash after bathing, {ward} lane number 4", 2),
        ("Drain water mixing into supply line at {ward}. Very contaminated", 2),
    ],
    "leakage": [
        ("Major pipe burst at {ward} main road, water running for 6 hours", 6),
        ("Leakage from the joint near {ward} school, huge wastage", 5),
        ("{ward} nala ke paas pipe se paani beh raha hai subah se", 4),
        ("Overhead tank of {ward} overflowing, nobody to close the valve", 3),
        ("New connection leaking at {ward} house no 22", 3),
        ("{ward} pipeline repair pending since last week", 2),
    ],
    "pressure": [
        ("Very low pressure in {ward} since Monday, tank not filling", 6),
        ("{ward} mein subah paani aata hi nahi, supply band hai", 5),
        ("No water supply in {ward} for 2 days. Need tanker urgently", 4),
        ("Water comes only 10 minutes in {ward}, pressure bahut kam hai", 4),
        ("Evening supply irregular in {ward} all this month", 3),
        ("{ward} upper floors get no water at all", 2),
    ],
    "other": [
        ("Bill for {ward} connection shows wrong meter reading", 3),
        ("Request for new connection, {ward} lane 7", 2),
        ("Meter replacement needed in {ward}", 2),
        ("When will the {ward} pipeline work finish?", 1),
    ],
}

_SENDERS = [
    "Rahul Sharma", "A. Prakash", "Sunita Devi", "Imran Q.", "Meena Kulkarni",
    "Vijay R.", "Fatima Shaikh", "Ganesh Bhat", "Priya N.", "Rakesh Patil",
    "Lakshmi Iyer", "S. Yusuf", "Anita Deshmukh", "Kiran R.", "Deepa M.",
    "unknown", "+91 98XXX XX12", "+91 90XXX XX77",
]


def _flatten(templates: dict[str, list[tuple[str, int]]]):
    pool: list[tuple[str, str, int]] = []
    for category, items in templates.items():
        for text, weight in items:
            pool.append((category, text, weight))
    return pool


def generate_bulk(wards: list[tuple[int, str]], n: int = BULK_TARGET,
                  seed: int = SEED) -> list[dict]:
    """Deterministically build ``n`` complaint rows across the ward spine.

    Contamination volume is deliberately correlated with the planted water
    signals (the outbreak ward and the monsoon wards), so the
    "citizens noticed before the lab did" story is real in the data rather than
    claimed in the slides.
    """
    rng = random.Random(seed)
    pool = _flatten(TEMPLATES)
    weights = [w for _, _, w in pool]

    # Contamination-only sub-pool with its own aligned weights, used wherever a
    # signal should make citizens complain about quality specifically.
    contam_pool = [p for p in pool if p[0] == "contamination"]
    contam_weights = [w for _, _, w in contam_pool]

    # Ward ids whose readings were planted to be bad; these get extra traffic.
    hot = {12: 3.0, 5: 2.2, 21: 1.8, 3: 1.6, 7: 1.6, 19: 1.6, 24: 1.5, 6: 1.5, 18: 1.4}

    rows: list[dict] = []
    for i in range(n):
        ward_id, ward_name = rng.choice(wards)
        category, template, _ = rng.choices(pool, weights=weights, k=1)[0]

        boost = hot.get(ward_id, 1.0)
        # A hot ward is more likely to be a quality complaint than a billing one.
        if rng.random() < min(0.85, 0.30 * boost):
            category, template, _ = rng.choices(contam_pool, weights=contam_weights, k=1)[0]

        day = rng.randrange(SPINE_DAYS)
        ts = SPINE_START + timedelta(
            days=day, hours=rng.randint(5, 22), minutes=rng.randint(0, 59))

        # Monsoon months carry more complaints, matching the turbidity signal.
        if ts.month in (7, 8, 9) and rng.random() < 0.30:
            category, template, _ = rng.choices(contam_pool, weights=contam_weights, k=1)[0]

        text = template.format(ward=ward_name.split(" - ")[-1])
        tag = classify(text)
        rows.append({
            "COMPLAINT_ID": 1_000_000 + i,
            "WARD_ID": ward_id,
            "RECEIVED_TS": ts,
            "SENDER_HANDLE": rng.choice(_SENDERS),
            "RAW_TEXT": text[:2000],
            "CATEGORY": tag["category"],
            "SEVERITY": tag["severity"],
            "CONFIDENCE": tag["confidence"],
            "RULE_VERSION": tag["rule_version"],
            "RULE_EVIDENCE": tag["evidence"][:400],
            "CHANNEL": "whatsapp",
        })
    return rows


WARDS_SQL = REPO_ROOT / "db" / "20_seed_dims.sql"


def wards_from_seed_sql(text: str | None = None) -> list[tuple[int, str]]:
    """Read the (WARD_ID, WARD_NAME) list straight out of the seed file.

    The loader normally takes this from the database, but the parsers and tests
    must run with the database switched off, and reading the seed keeps one
    source of truth instead of a duplicated Python ward list that can drift.
    Only the WARD INSERT block is looked at, so parameter rows are not mixed in.
    """
    if text is None:
        text = WARDS_SQL.read_text(encoding="utf-8")
    block = text.split("INSERT INTO WARDQ.WARD", 1)[-1].split(";", 1)[0]
    return [(int(ward_id), name)
            for ward_id, name in re.findall(r"\(\s*(\d+),\s*'([^']+)'", block)]


def build_ward_map(wards: list[tuple[int, str]]) -> dict[str, int]:
    """Derive the lowercase-keyword -> WARD_ID map used for text attribution.

    WARD_NAME carries the *municipal* ward number, which is not the surrogate
    WARD_ID (e.g. id 3 is named 'Ward 4 - Dharavi'). Both are registered so a
    citizen writing either one resolves. Directional/shape words are dropped
    because "east" appearing in a message must not nominate a ward.
    """
    generic = {"ward", "east", "west", "north", "south", "central", "nagar",
               "layout", "area", "city", "street", "st", "the"}
    ward_map: dict[str, int] = {}

    for ward_id, name in wards:
        keys: list[str] = []
        locality = name.split("-")[-1].strip().lower()
        if locality:
            keys.append(locality)                      # "andheri east"
            keys.extend(t for t in re.split(r"[^a-z0-9]+", locality) if len(t) > 3)
        number = re.search(r"ward\s*(\d+)", name, re.IGNORECASE)
        if number:
            keys.append(f"ward {number.group(1)}")     # "ward 198"
        for key in keys:
            if key not in generic and key not in ward_map:
                ward_map[key] = ward_id
    return ward_map


def ward_from_filename(stem: str, ward_map: dict[str, int]) -> int | None:
    """Resolve the export's default ward from names like ward_4_dharavi_export."""
    return infer_ward_id(stem.replace("_", " ").replace("-", " "), ward_map)


def load_fixtures(ward_map: dict[str, int],
                  wards: list[tuple[int, str]]) -> tuple[list[dict], list[dict]]:
    """Parse every committed export. Returns (rows, reports)."""
    rows: list[dict] = []
    reports: list[dict] = []
    next_id = 10_000

    for path in sorted(FIXTURE_DIR.glob("*.txt")):
        default_ward = ward_from_filename(path.stem.replace("_export", ""), ward_map)
        messages, report = parse_chat(
            path.read_text(encoding="utf-8", errors="replace"),
            ward_map=ward_map, default_ward_id=default_ward, channel="whatsapp")
        report["filename"] = path.name
        reports.append(report)

        for message in messages:
            tag = classify(message["text"])
            rows.append({
                "COMPLAINT_ID": next_id,
                "WARD_ID": message["ward_id"],
                "RECEIVED_TS": message["received_ts"],
                "SENDER_HANDLE": message["sender_handle"],
                "RAW_TEXT": message["text"],
                "CATEGORY": tag["category"],
                "SEVERITY": tag["severity"],
                "CONFIDENCE": tag["confidence"],
                "RULE_VERSION": tag["rule_version"],
                "RULE_EVIDENCE": tag["evidence"][:400],
                "CHANNEL": message["channel"],
            })
            next_id += 1
    return rows, reports


COLUMNS = ("COMPLAINT_ID", "WARD_ID", "RECEIVED_TS", "SENDER_HANDLE", "RAW_TEXT",
           "CATEGORY", "SEVERITY", "CONFIDENCE", "RULE_VERSION", "RULE_EVIDENCE",
           "CHANNEL")


def build_all(wards: list[tuple[int, str]],
              ward_map: dict[str, int] | None = None) -> tuple[list[dict], dict]:
    """Everything the loader needs: fixture rows + bulk rows, and a summary."""
    ward_map = ward_map if ward_map is not None else build_ward_map(wards)
    fixture_rows, reports = load_fixtures(ward_map, wards)
    bulk_rows = generate_bulk(wards, n=BULK_TARGET)
    all_rows = fixture_rows + bulk_rows

    by_category: dict[str, int] = {}
    for row in all_rows:
        by_category[row["CATEGORY"]] = by_category.get(row["CATEGORY"], 0) + 1

    summary = {
        "fixture_rows": len(fixture_rows),
        "bulk_rows": len(bulk_rows),
        "total_rows": len(all_rows),
        "by_category": by_category,
        "fixture_reports": reports,
    }
    return all_rows, summary
