"""R27-CLAIM-TYPE — what kind of statement is this?

"This wall is fire-rated" can mean the spec requires it, the model asserts it, an inspector looked at
it, or a rule worked it out. Four different claims that render identically today, and an estimator,
an inspector and a lawyer each need a different one.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_claim_type.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_claim_type.db"
os.environ["STORAGE_DIR"] = "./test_storage_claim_type"
if os.path.exists("./test_claim_type.db"):
    os.remove("./test_claim_type.db")

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_api import claim_type as ct  # noqa: E402


# --- the design: claim type follows the SOURCE, not the fact ------------------------------------------
def test_the_SAME_fact_makes_different_claims_depending_on_where_it_came_from():
    # `element_facts.verified` is the proof of the whole design. A table keyed on fact NAME would
    # have to pick one of these and would be wrong half the time.
    from_model = ct.classify({"verified": {"verified": True, "source": "model"}})
    from_field = ct.classify({"verified": {"verified": True, "source": "field"}})
    assert from_model["facts"][0]["claim"] == "embodiment", from_model["facts"]
    assert from_field["facts"][0]["claim"] == "evidence", from_field["facts"]

def test_each_source_maps_to_the_kind_of_statement_it_actually_makes():
    assert ct.claim_type("schedule") == "intent"       # planned work: what SHOULD happen
    assert ct.claim_type("model") == "embodiment"      # the file itself asserts it
    assert ct.claim_type("field") == "evidence"        # somebody went and looked
    assert ct.claim_type("rule") == "inference"        # a selector matched; nobody stated it
    assert ct.claim_type("declared") == "embodiment"   # the model's own Qto pset
    assert ct.claim_type("measured") == "inference"    # we computed it from geometry
    assert ct.claim_type("override") == "intent"       # a human's stated position over the model

def test_source_matching_is_forgiving_of_case_and_padding_but_not_of_meaning():
    assert ct.claim_type("  FIELD ") == "evidence"
    assert ct.claim_type("fieldwork") is None, "a near-miss is not a match"


# --- an unrecognised source is UNKNOWN, never a default -------------------------------------------------
def test_an_unknown_source_makes_an_unknown_claim():
    # Defaulting to `inference` would manufacture the weakest possible claim; defaulting to
    # `evidence` the strongest. Both are fabrications.
    r = ct.classify({"installed": {"installed": True, "source": "carrier-pigeon"}})
    assert r["facts"][0]["claim"] is None, r["facts"]
    assert r["unknown"] == ["installed"], r["unknown"]
    assert "guessing would invent one" in r["facts"][0]["detail"]

def test_a_fact_with_no_source_at_all_is_unknown_too():
    assert ct.claim_type(None) is None and ct.claim_type("") is None
    r = ct.classify({"checked": {"ok": True}})
    assert r["facts"][0]["claim"] is None and r["unknown"] == ["checked"]

def test_unknown_is_listed_separately_rather_than_folded_into_a_bucket():
    # A fact of unknown kind is a GAP in the record, not a fifth kind of claim.
    r = ct.classify({"installed": {"source": "???"}, "verified": {"source": "field"}})
    assert r["unknown"] == ["installed"], r["unknown"]
    assert r["by_claim"]["evidence"] == ["verified"], r["by_claim"]
    assert "installed" not in sum(r["by_claim"].values(), []), r["by_claim"]


# --- absence is not a claim -------------------------------------------------------------------------------
def test_a_fact_that_is_not_recorded_makes_no_claim_at_all():
    r = ct.classify({"installed": None, "verified": None})
    assert all(not f["present"] for f in r["facts"]), r["facts"]
    assert r["present_count"] == 0 and r["unknown"] == [], r
    assert "no claim of any kind" in r["facts"][0]["detail"]

def test_absent_is_distinguished_from_unrecognised():
    # "Nobody recorded this" and "somebody recorded it and we cannot tell what kind" are different
    # states, and collapsing them loses the one that is actionable.
    r = ct.classify({"installed": None, "verified": {"source": "mystery"}})
    assert r["facts"][0]["present"] is False and r["facts"][0]["claim"] is None
    assert r["facts"][1]["present"] is True and r["facts"][1]["claim"] is None
    assert r["unknown"] == ["verified"], "only the RECORDED one is a gap in provenance"


# --- a two-part fact can make two kinds of claim ------------------------------------------------------------
def test_a_price_whose_halves_disagree_is_MIXED():
    # A price is a rate times a quantity. A quoted rate is a stated position; a measured quantity is
    # derived. One number, two kinds of claim — so the honest answer is neither of them.
    r = ct.classify({"priced": {"quantity_source": "measured", "rate_source": "quoted"}})
    assert r["facts"][0]["claim"] == "mixed", r["facts"]
    assert r["mixed"] == ["priced"], r["mixed"]

def test_a_price_whose_halves_agree_takes_that_claim():
    r = ct.classify({"priced": {"quantity_source": "declared", "rate_source": "declared"}})
    assert r["facts"][0]["claim"] == "embodiment", r["facts"]

def test_a_price_with_an_unrecognised_half_is_unknown_not_mixed():
    r = ct.classify({"priced": {"quantity_source": "measured", "rate_source": "vibes"}})
    assert r["facts"][0]["claim"] is None, r["facts"]


# --- the payoff -----------------------------------------------------------------------------------------------
def test_has_evidence_answers_the_question_nobody_could_ask_before():
    # A wall specified, modelled, priced and scheduled but never observed is a wall NOBODY HAS SEEN,
    # and that was previously indistinguishable from a fully-evidenced one.
    paper = ct.classify({"checked": {"source": "rule"}, "scheduled": {"source": "schedule"},
                         "verified": {"source": "model"}})
    assert paper["present_count"] == 3 and paper["has_evidence"] is False, paper
    seen = ct.classify({"installed": {"source": "field"}})
    assert seen["has_evidence"] is True, seen

def test_the_kinds_are_NOT_ranked_and_the_result_says_so():
    # For "what should this be" the spec is the authority and an observation is beside the point; for
    # "what is it" the observation wins. Which question is being asked is the caller's to know.
    r = ct.classify({"verified": {"source": "field"}})
    assert "NOT ranked" in r["note"], r["note"]
    assert list(ct.CLAIM_TYPES) == ["intent", "embodiment", "evidence", "inference"]
    for c in ct.CLAIM_TYPES:
        assert len(ct.MEANS[c]) > 20, c        # every kind explains itself; no UI need invent it

def test_degenerate_input_is_an_answer():
    r = ct.classify({})
    assert r["facts"] == [] and r["present_count"] == 0 and r["has_evidence"] is False
    assert ct.classify(None)["present_count"] == 0


for name, fn in sorted(globals().items()):
    if name.startswith("test_") and callable(fn):
        fn()

print("R27-CLAIM-TYPE OK - every fact now says what KIND of statement it is. 'This wall is "
      "fire-rated' can mean the spec requires it (INTENT), the model asserts it (EMBODIMENT), an "
      "inspector looked at it (EVIDENCE), or a rule worked it out (INFERENCE) - four different "
      "claims that rendered identically, and an estimator, an inspector and a lawyer each need a "
      "different one. CLAIM TYPE FOLLOWS THE SOURCE, NOT THE FACT, and element_facts.verified is the "
      "proof: backed by an IFC stamp it is embodiment, backed by a field record it is evidence, and a "
      "table keyed on fact NAME would have to pick one and be wrong half the time. THE KINDS ARE NOT "
      "RANKED - for 'what should this be' the specification is the authority and an observation is "
      "beside the point; for 'what is it' the observation wins and the spec is a wish - so ranking "
      "them here would bake one question's answer into a layer that does not know which question is "
      "being asked. An unrecognised source is UNKNOWN and listed separately, never defaulted, since "
      "defaulting to inference manufactures the weakest claim and defaulting to evidence the "
      "strongest; and 'nobody recorded this' stays distinct from 'recorded, kind unclear', because "
      "collapsing them loses the one that is actionable. A price whose rate is quoted and whose "
      "quantity is measured is MIXED - one number, two kinds of claim. The payoff is `has_evidence`: "
      "a wall specified, modelled, priced and scheduled but never observed is a wall NOBODY HAS SEEN, "
      "and until now that was indistinguishable from a fully-evidenced one.")
