"""R27-CLAIM-TYPE — what *kind* of statement is this?

The platform is good at recording facts about an element and poor at saying what sort of fact each one
is. "This wall is fire-rated" can mean *the specification requires it*, *the model asserts it*, *an
inspector looked at it*, or *a rule worked it out from the wall type* — four different claims that
render identically today. An estimator, an inspector and a lawyer each need a different one of them,
and none of them can currently tell which they are holding.

The distinction comes from systems-engineering practice on durable technical representation, and it
is four-way:

* **intent** — what was *specified*. A schedule, a spec section, a design requirement. Authoritative
  about what *should* happen; says nothing about what did.
* **embodiment** — what was *built*, as asserted by the artifact itself. An IFC property, a stamp
  written into the model.
* **evidence** — what was *observed*. A field record, an inspection, a scan measurement. Somebody
  went and looked.
* **inference** — what was *derived*. A rule ran and produced a conclusion nobody stated directly.

**Claim type is a property of the SOURCE, not of the fact.** This is the whole design, and
`element_facts.verified` is the proof: verification backed by an IFC stamp is an *embodiment* claim,
and the same verification backed by a field record is *evidence*. A table keyed on fact name would
have to pick one and would be wrong half the time.

**These are deliberately NOT ranked.** It is tempting to order them — evidence beats embodiment beats
inference beats intent — and it is wrong. For *"what should this be"* the specification is the
authority and an observation is beside the point; for *"what is it"* the observation wins and the
spec is a wish. Ranking them here would bake one question's answer into a layer that does not know
which question is being asked. The caller knows; this does not.

**An unrecognised source is `unknown`, never a default.** Guessing that an unlabelled fact is an
inference would quietly manufacture the weakest possible claim; guessing evidence would manufacture
the strongest. Both are worse than saying so.
"""
from __future__ import annotations

from typing import Any

#: The four kinds of statement. Order is definitional, NOT a ranking — see the module docstring.
CLAIM_TYPES = ("intent", "embodiment", "evidence", "inference")

#: What each kind asserts, in words a UI can show without inventing its own explanation.
MEANS: dict[str, str] = {
    "intent": "specified — what should be, not a report of what is",
    "embodiment": "asserted by the artifact itself — the model or the file says so",
    "evidence": "observed — somebody went and looked, or measured",
    "inference": "derived — a rule concluded this; nobody stated it directly",
}

#: Source label → claim type. Sources are the strings the fact engines already emit
#: (`element_facts`, `fived`, `qto`), so this is a translation layer rather than a new vocabulary.
BY_SOURCE: dict[str, str] = {
    # element_facts
    "model": "embodiment",      # an IFC stamp / property written into the file
    "field": "evidence",        # a field record — somebody was there
    "schedule": "intent",       # planned work: what is meant to happen
    "rule": "inference",        # matched by a selector rather than bound in the model
    # qto / fived quantity provenance (v0.3.697, v0.3.699)
    "declared": "embodiment",   # the model's own Qto pset asserts the quantity
    "measured": "inference",    # we computed it from geometry — derived, not asserted
    "override": "intent",       # a human supplied it, overriding the model: a stated position
    "quoted": "intent",         # a price somebody committed to
    "vintage": "inference",     # a rate derived from a dated cost database
}


def claim_type(source: str | None) -> str | None:
    """The kind of claim a fact from `source` makes, or None when the source is unrecognised.

    None is a real answer. A fact whose provenance we do not recognise has an **unknown** claim type,
    and defaulting it would manufacture a claim nobody made — weak or strong, both are fabrications.
    """
    if not source:
        return None
    return BY_SOURCE.get(str(source).strip().lower())


def _one(kind: str, fact: Any) -> dict[str, Any]:
    """Classify a single fact from `element_facts.gather`."""
    if fact is None:
        return {"fact": kind, "present": False, "claim": None, "source": None,
                "detail": "not recorded — no claim of any kind is being made"}
    src = fact.get("source") if isinstance(fact, dict) else None
    # A fact can carry provenance for its two halves (a price has a quantity source AND a rate
    # source). Where they disagree the claim is `mixed`, for the same reason `fived` collapses to
    # `mixed`: one measured element among fifty does not make the line declared.
    if isinstance(fact, dict) and fact.get("quantity_source") and fact.get("rate_source"):
        a, b = claim_type(fact["quantity_source"]), claim_type(fact["rate_source"])
        claim = a if a == b else ("mixed" if a and b else None)
        return {"fact": kind, "present": True, "claim": claim,
                "source": f"{fact['quantity_source']}+{fact['rate_source']}",
                "detail": (MEANS.get(claim or "", "")
                           or "the quantity and the rate make different kinds of claim")}
    c = claim_type(src)
    return {"fact": kind, "present": True, "claim": c, "source": src,
            "detail": MEANS.get(c or "", f"unrecognised source {src!r} — the kind of claim this makes "
                                         "is unknown, and guessing would invent one")}


def classify(facts: dict[str, Any]) -> dict[str, Any]:
    """Tag every fact in an `element_facts.gather` result with the kind of claim it makes.

    Returns the per-fact rows plus `by_claim` (which facts make which kind of claim) and `unknown`
    (facts present whose provenance was not recognised). `unknown` is listed rather than folded into
    a bucket, because a fact of unknown kind is a gap in the record, not a fifth kind.
    """
    rows = [_one(k, v) for k, v in (facts or {}).items()]
    present = [r for r in rows if r["present"]]
    by_claim: dict[str, list[str]] = {c: [] for c in CLAIM_TYPES}
    for r in present:
        if r["claim"] in by_claim:
            by_claim[r["claim"]].append(r["fact"])
    return {
        "facts": rows,
        "by_claim": by_claim,
        "unknown": [r["fact"] for r in present if r["claim"] is None],
        "mixed": [r["fact"] for r in present if r["claim"] == "mixed"],
        "present_count": len(present),
        # Whether anybody actually went and looked. The single most useful thing this classification
        # buys: a wall that is specified, modelled, priced and scheduled but never observed is a wall
        # nobody has seen, and that was previously indistinguishable from a fully-evidenced one.
        "has_evidence": bool(by_claim["evidence"]),
        "note": ("Claim types are NOT ranked. For 'what should this be' the specification (intent) is "
                 "the authority and an observation is beside the point; for 'what is it' the "
                 "observation (evidence) wins and the specification is a wish. Which question is "
                 "being asked is the caller's to know. A fact with an unrecognised source is "
                 "`unknown` — never defaulted, because a default manufactures a claim nobody made."),
    }
