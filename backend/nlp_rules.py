"""Explainable complaint categorisation.

Pure standard library, on purpose. Two reasons that matter more than accuracy
percentages here:

1. **Free forever.** No model download, no API key, no metered endpoint. A
   spaCy/transformer model is a few hundred MB on a ~350 KB/s link and a paid
   API would violate the hackathon's cost constraint outright.
2. **Explainable on stage.** When a judge asks "why is this tagged
   contamination", the answer is a matched phrase stored in
   ``COMPLAINT.RULE_EVIDENCE`` — a column you can query — not a latent vector.

The rule table is *data*, so it can be tuned live in front of an audience
without touching control flow.
"""

from __future__ import annotations

import re

RULE_VERSION = "2026.10"

# Categories the product actually routes on. ``other`` is the explicit
# fallback so a mis-tag is visible in the triage queue rather than hidden.
CATEGORIES = ("contamination", "leakage", "pressure", "other")

# Ordered by weight, but ties are broken by *specificity*: a message matching
# both "pressure" and "black water" is a contamination report, because the
# contamination rules carry the higher weight.
RULES: tuple[dict, ...] = (
    {
        "category": "contamination",
        "weight": 1.00,
        "note": "Health-affecting water quality: colour, odour, taste, pathogens, illness",
        "patterns": [
            # English
            r"black\s*water", r"brown\s*water", r"yellow\s*water", r"muddy\s*water",
            r"dirty\s*water", r"foul\s*(?:smell|odour|odor)", r"bad\s*(?:smell|odour|odor)",
            r"stink", r"smell", r"turbid", r"contaminat", r"sewage", r"\bdrain\b",
            r"drain\s*(?:water)?\s*mix",
            r"worm", r"insect", r"float", r"rust(?:y)?", r"\boil\b", r"kerosene", r"chemical",
            r"taste", r"bitter", r"salty", r"sweet", r"chlorine\s*(?:smell|heavy)",
            r"fever", r"loose\s*motion", r"diarrh(?:ea|oea)", r"vomit", r"sick",
            r"illness", r"hospital", r"skin\s*(?:rash|problem|allergy)", r"infection",
            r"coliform", r"pathogen", r"outbreak", r"epidemic", r"disease",
            # Hindi / Marathi / Kannada, romanised — how these are actually typed
            r"ka?ala?\s*paa?ni", r"kala\s*paani", r"ganda\s*paani", r" ganda",
            r"peela\s*paani", r"chipchip", r"chip\s*chip", r"meetha", r"kadwa",
            r"swaad?\b", r"badbu", r"vasna?\b", r"durgandh", r"paani\s*(?: ganda|kharab)",
            r"bimari", r"beemar", r"pet\s*(?:kharab|bigad)", r"ulti", r"bukh[ar]*\b",
            r"daivya", r"chamdi", r"rutka", r"twak",
        ],
    },
    {
        "category": "leakage",
        "weight": 0.70,
        "note": "Physical loss of water: bursts, leaks, running taps, wastage",
        "patterns": [
            r"leak(?:age|s|ing)?", r"pipe\s*burst", r"burst", r"phoot", r"phat",
            r"fuse[ds]?\b", r"chashma", r"tap\s*(?:running|not closing|khol)",
            r"valve", r"pipeline", r"pipe\s*line", r"\bpipe\b", r"\bnal\b", r"\bnala\b",
            r"beh\s*(?:raha|rahi|raha hai|waist)", r"water\s*wast", r"wastage",
            r"bumper", r"overflow", r"over\s*flow", r"tank\s*overflow", r"\bseep",
            r"drip", r"joint", r"connection\s*leak", r"raste\s*me",
        ],
    },
    {
        "category": "pressure",
        "weight": 0.60,
        "note": "Quantity and pressure: low pressure, no supply, irregular timing",
        "patterns": [
            r"pressure", r"low\s*flow", r"slow\s*(?:flow|supply)", r"dheema?",
            r"kam\s*(?:paani|pressure|dabaav|water)", r"paani\s*(?:nahi|nahi|kam|band)",
            r"no\s*water", r"water\s*(?:not\s*coming|supply\s*(?:issue|problem|irregular))",
            r"supply\s*(?:issue|irregular|problem|timing|band)", r"tanker",
            r"\bband\b", r"times?\s*(?:nahi|not)",
            r"morning\s*(?:nahi|not)", r"evening\s*(?:nahi|not)", r"bare\s*aate",
        ],
    },
)

# Severity is decided independently of category: a leak that has run for three
# days is more urgent than a faint smell. Cue words are weighted, highest wins.
SEVERITY_CUES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "high",
        (
            r"black", r"blood", r"fever", r"vomit", r"diarr", r"loose\s*motion",
            # An illness report is the whole point of the system, so every common
            # way of saying "people are sick" has to escalate, including the
            # romanised Hindi/Marathi/Kannada forms citizens actually type.
            r"pet\s*kharab", r"pait\s*kharab", r"\bulti\b", r"\bbimar\b",
            r"gastric",
            r"stomach", r"\bill\b|illness|sick", r"nausea|vomit|\bmotion\b",
            r"\bdizzy|giddi", r"\brash|\bsore\b",
            r"child|kids?\b|bachch?|bacca|kudcha|maga|pilla", r"hospital",
            r"outbreak|epidemic", r"contaminat", r"sewage", r"worm", r"infect",
            r"no\s*water\s*for", r"\b\d+\s*(?:days?|weeks?)\b", r"burst",
            r"old\s*pipe", r"school", r"clinic|hospital\s*(?:near|area)",
        ),
    ),
    (
        "medium",
        (
            r"smell", r"badbu", r"taste", r"swad", r"muddy", r"turbid",
            r"leak", r"pressure", r"dheema", r"kam", r"supply", r"overflow",
            r"wast", r"rust", r"chlorine", r"tank",
        ),
    ),
)

_MAX_CATEGORY_WEIGHT = max(r["weight"] for r in RULES)

_COMPILED = tuple(
    (rule["category"], rule["weight"],
     [re.compile(p, re.IGNORECASE) for p in rule["patterns"]])
    for rule in RULES
)
_COMPILED_SEVERITY = tuple(
    (level, [re.compile(p, re.IGNORECASE) for p in patterns])
    for level, patterns in SEVERITY_CUES
)


def classify(text: str | None) -> dict:
    """Return the category, severity, confidence and *evidence* for one message.

    ``evidence`` is the list of phrases that fired, joined for storage in
    ``COMPLAINT.RULE_EVIDENCE`` and shown as the triage-queue tooltip.
    """
    if not text or not text.strip():
        return {
            "category": "other",
            "severity": "low",
            "confidence": 0.0,
            "evidence": "",
            "rule_version": RULE_VERSION,
        }

    best_category = "other"
    best_score = 0.0
    best_hits: list[str] = []

    for category, weight, patterns in _COMPILED:
        hits = [m.group(0).strip() for p in patterns if (m := p.search(text))]
        if not hits:
            continue
        # Specificity beats volume: the weight dominates, matched-phrase count
        # only breaks ties between two equally weighted categories.
        score = weight + min(len(hits), 4) * 0.01
        if score > best_score:
            best_score, best_category, best_hits = score, category, hits

    severity = "low"
    for level, patterns in _COMPILED_SEVERITY:
        if any(p.search(text) for p in patterns):
            severity = level
            break

    # Confidence is the winning rule's weight relative to the strongest rule,
    # nudged up when several distinct phrases matched. A bare "other" therefore
    # reports 0.0 rather than pretending to be a low-confidence real tag.
    if best_category == "other":
        confidence = 0.0
    else:
        confidence = (best_score - 0.0) / (_MAX_CATEGORY_WEIGHT + 0.04)
        confidence = round(min(max(confidence, 0.0), 1.0), 3)

    return {
        "category": best_category,
        "severity": severity,
        "confidence": confidence,
        "evidence": "; ".join(dict.fromkeys(h.lower() for h in best_hits))[:400],
        "rule_version": RULE_VERSION,
    }


def rules_as_table() -> list[dict]:
    """The rule set in tabular form — this is the source for docs/prd.md, so the
    PRD's rules table cannot drift from the code that actually runs."""
    return [
        {
            "category": r["category"],
            "weight": r["weight"],
            "note": r["note"],
            "n_patterns": len(r["patterns"]),
            "sample_patterns": r["patterns"][:6],
        }
        for r in RULES
    ]
