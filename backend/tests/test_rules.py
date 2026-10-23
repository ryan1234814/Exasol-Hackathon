"""Rule-engine tests. These run with no database and no third-party packages,
which is the point: the categorisation logic must be verifiable on a laptop with
the database switched off."""

from backend.nlp_rules import CATEGORIES, RULE_VERSION, classify, rules_as_table


def test_every_category_is_reachable():
    covered = {r["category"] for r in rules_as_table()}
    assert covered == set(CATEGORIES) - {"other"}


def test_contamination_beats_pressure_when_both_match():
    # A real message: low pressure AND black water. Health risk must win.
    result = classify("paani ka pressure bahut kam hai aur kala paani bhi aa raha hai")
    assert result["category"] == "contamination"


def test_illness_keywords_are_contamination_and_high_severity():
    result = classify("3 bachchon ko loose motion aur fever ho gaya hai")
    assert result["category"] == "contamination"
    assert result["severity"] == "high"


def test_pipe_burst_is_leakage():
    result = classify("Major pipe burst at the main road, water running for 6 hours")
    assert result["category"] == "leakage"
    assert result["severity"] == "high"  # "burst" and a duration are both escalation cues


def test_low_pressure_is_pressure():
    result = classify("Very low pressure since Monday, tank not filling")
    assert result["category"] == "pressure"


def test_billing_falls_through_to_other_with_zero_confidence():
    result = classify("Bill for this connection shows the wrong meter reading")
    assert result["category"] == "other"
    assert result["confidence"] == 0.0


def test_hinglish_and_romanised_indic_are_recognised():
    for text in (
        "paani mein se ganda smell aa rahi hai",
        "subah se kala paani aa raha hai",
        "pet kharab ho gaya hai paani peene ke baad",
        "drain ka paani hamari supply line mein mil raha hai",
    ):
        assert classify(text)["category"] == "contamination", text


def test_empty_and_none_input_is_safe():
    for text in (None, "", "   ", "\n"):
        result = classify(text)
        assert result["category"] == "other"
        assert result["confidence"] == 0.0
        assert result["evidence"] == ""


def test_always_returns_a_complete_record():
    result = classify("anything at all")
    assert set(result) == {"category", "severity", "confidence", "evidence", "rule_version"}
    assert result["category"] in CATEGORIES
    assert result["severity"] in {"high", "medium", "low"}
    assert 0.0 <= result["confidence"] <= 1.0
    assert result["rule_version"] == RULE_VERSION


def test_confidence_is_ordered_by_rule_strength():
    contamination = classify("black water with a foul smell and worms")["confidence"]
    leakage = classify("there is a leakage in the pipe")["confidence"]
    assert contamination > leakage


def test_evidence_records_the_phrase_that_fired():
    result = classify("black water coming from the tap")
    assert "black water" in result["evidence"].lower()


def test_oil_requires_a_word_boundary():
    # Regression: a bare "oil" pattern matched "spoiled" and "toilet".
    assert classify("the food was spoiled")["category"] != "contamination"
    assert classify("there is oil floating on the water")["category"] == "contamination"


def test_nal_requires_a_word_boundary():
    # Regression: "nal" matched inside "final" and "channel".
    assert classify("this is the final notice")["category"] != "leakage"
    assert classify("paani leak ho raha hai nal se")["category"] == "leakage"


def test_any_wording_of_illness_escalates_to_high():
    # Regression: "pet kharab" was tagged contamination but left at low
    # severity, so a ward officer's queue would not have surfaced it. The
    # Romanised forms citizens actually type must all escalate.
    for text in (
        "bacchon ko pet kharab ho raha hai",
        "paani peene ke baad ulti ho rahi hai",
        "three people are sick after the morning supply",
        "skin rash after bathing in this water",
        "area mein illness fail raha hai, log bimar hain",
    ):
        assert classify(text)["severity"] == "high", text


def test_illness_cues_do_not_fire_on_water_infrastructure_words():
    # "motion" and "ill" are dangerous substrings: promotion, billboard, the
    # billing counter. A cue must not escalate a non-health complaint.
    for text in (
        "the supply promotion notice was pasted on the board",
        "billboard near the tank fell into the pipe trench",
        "meter billing problem, wrong reading shown",
    ):
        assert classify(text)["severity"] != "high", text


def test_rules_as_table_is_serialisable_for_the_prd():
    table = rules_as_table()
    assert table
    for row in table:
        assert row["n_patterns"] == len(row["sample_patterns"]) or row["n_patterns"] >= 6
        assert isinstance(row["weight"], float)
