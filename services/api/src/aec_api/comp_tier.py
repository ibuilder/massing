"""CRE-COMP-TIER (R20) — **a comp is not a fact until you know where it came from.**

The `comparable` module has always carried a free-text `source`. That is enough to display and not
enough to decide with: when two comps disagree about the same property, something has to break the
tie, and "whichever row sorted first" is not a method.

This leaf ranks sources into an explicit hierarchy — a recorded sale outranks a party-verified
number, which outranks a vendor-confirmed one, which outranks a vendor *estimate*, which outranks
an asking price, which outranks a marketing package — and then does two things with it:

* **Deduplicate by conflict, not by row.** Comps describing the same subject are grouped; the
  best-tier member wins and the losers are kept beside it as `outranked`, so the disagreement is
  visible instead of averaged away.
* **Carry the worst tier forward.** Every derived statistic (median $/SF, a cap-rate band) reports
  the **weakest tier it depended on**. A median resting on one asking price is not the same number
  as a median resting on six recorded sales, and the output says so — the CITED-ANSWER contract
  applied to market data.

Tier assignment is pure string normalization over what users already type; anything unrecognized
lands in `unknown` (the weakest tier) rather than being optimistically promoted.
"""
from __future__ import annotations

import re
from typing import Any

# rank 1 is strongest. label + the phrases that map to it (matched against a normalized source)
TIERS: dict[str, dict[str, Any]] = {
    "recorded_sale": {"rank": 1, "label": "Recorded sale",
                      "match": ("recorded", "deed", "county", "registry", "public record", "closed sale")},
    "verified": {"rank": 2, "label": "Party-verified",
                 "match": ("verified", "confirmed with", "principal", "buyer", "seller", "our deal",
                           "closed by us", "in-house")},
    "confirmed": {"rank": 3, "label": "Vendor-confirmed",
                  "match": ("confirmed", "researched", "comp service", "verified vendor")},
    "estimate": {"rank": 4, "label": "Vendor estimate",
                 "match": ("estimate", "estimated", "model", "avm", "automated", "algorithm")},
    "listing": {"rank": 5, "label": "Listing / asking",
                "match": ("listing", "asking", "on market", "for sale", "mls", "advertised", "quoted")},
    "broker": {"rank": 6, "label": "Broker package",
               "match": ("broker", "om", "offering memorandum", "teaser", "flyer", "marketing")},
    "unknown": {"rank": 7, "label": "Unattributed", "match": ()},
}
_BY_RANK = sorted(TIERS.items(), key=lambda kv: kv[1]["rank"])
WEAKEST = "unknown"

#: **The register's own vocabulary, mapped exactly — and this table is the whole point of
#: COMPTIER-DARK.** The phrases above were written for a free-text `source`, and `source` is not
#: free text: `services/api/modules/comparable/module.json` declares it a `select` with seven
#: options, and `modules._validate_values` refuses anything outside them (plus a project's own
#: custom enum values). So the guaranteed population of this function is seven strings, and
#: **four of the seven matched no phrase at all** — measured, not reasoned:
#:
#:     Broker        -> broker (6)          CoStar     -> unknown (7)   <- a comp service
#:     MLS           -> listing (5)         Appraisal  -> unknown (7)   <- a researched opinion
#:     Public record -> recorded_sale (1)   Owner      -> unknown (7)   <- a principal
#:                                          Other      -> unknown (7)   <- correct
#:
#: Three of those four are DEMOTIONS, and the demotion is the expensive direction for this engine
#: specifically: `statistic()` reports the weakest tier its band rests on and appends *"Strengthen
#: that source before the number carries a decision."* A band of owner-confirmed and appraisal
#: comps therefore carried that sentence on every render — **so the one qualifier this leaf exists
#: to publish fired on the most ordinary sources an analyst picks, and a qualifier that fires on
#: everything is one nobody reads.** It was defeated by being always-on, not by being absent.
#:
#: Matched EXACTLY (normalised, whitespace-collapsed) and consulted BEFORE the substring pass, which
#: is load-bearing in both directions. Adding `"owner"` to the `verified` phrase list would have
#: promoted *"listing agent for the owner"* to party-verified, and adding `"appraisal"` to
#: `confirmed` would have promoted *"broker OM quoting an appraisal"*; an exact table cannot reach
#: either, because neither is a declared option. The substring pass still handles everything a user
#: types into a custom enum value.
#:
#: `"other"` is IN the table rather than left to fall through, so the gate that reads this against
#: `module.json` needs no exemption list — *an exemption list is where the next instance hides*. It
#: maps to the weakest tier deliberately: the register's own option asserts there is no attribution.
#: That also sharpens `matched`, which now means **the source was recognised** rather than "a phrase
#: hit": a recognised `Other` is unattributed because somebody said so, which is not the same fact
#: as a source string nobody could read.
#:
#: Pinned against the register by `services/api/test_comp_tier_sources.py`, which DERIVES the
#: population from `module.json` instead of restating it. The two are edited by different people
#: for different reasons — one is a market-data judgement, the other is a form — and nothing
#: connected them, so the disagreement above produced no failing test, no 500 and no changed
#: number: only a sentence that was already there, firing on four more sources than it should.
#: *(How long it had been wrong is deliberately NOT stated. The checkout this was found in is
#: shallow — `test -f .git/shallow` — so `git log` on either file cannot reach the commit that
#: introduced the `select`, and the first draft of this line claimed "a year" from nothing.
#: `test_gap_records` paid for the same lesson when its replay used `git show`: a figure that
#: depends on the depth of somebody's clone is not a measurement, and one that decays toward the
#: conclusion it supports is the hardest kind to notice.)*
REGISTER_SOURCES: dict[str, str] = {
    "public record": "recorded_sale",
    # A principal to the transaction. The `verified` phrase list already names "buyer", "seller" and
    # "principal"; the register spells the same fact "Owner".
    "owner": "verified",
    # A vendor comp service — `confirmed`'s phrase list literally contains "comp service", written
    # for somebody typing those words rather than the product name. A JUDGEMENT, not a derivation:
    # some CoStar figures are their own analytics, which would be `estimate`, and the register
    # cannot tell the two apart. Tier 3 is the honest reading of "a researcher's record", and
    # tier 4 would demote every recorded sale that happens to arrive through a vendor.
    "costar": "confirmed",
    # A licensed professional researched and confirmed it, and is not a party to the deal — which is
    # exactly the line between `verified` (2) and `confirmed` (3).
    "appraisal": "confirmed",
    "mls": "listing",
    "broker": "broker",
    "other": WEAKEST,
}


def _norm(s: Any) -> str:
    return re.sub(r"[^a-z ]+", " ", str(s or "").lower())


def _exact(s: Any) -> str:
    """`_norm` with runs of space collapsed — `"Public record"` and `"PUBLIC  RECORD"` are one key.

    Separate from `_norm` rather than folded into it: the substring pass below matches multi-word
    phrases like `"public record"` against text that may legitimately carry a doubled space, and
    changing `_norm` would change every one of those comparisons at once.
    """
    return " ".join(_norm(s).split())


def tier_of(source: Any) -> dict[str, Any]:
    """Classify one source into a tier.

    A declared register option (see `REGISTER_SOURCES`) is matched exactly first; anything else
    falls to the free-text phrase pass. Unrecognized text is the WEAKEST tier, never a middling
    guess — an unattributed number should not outrank an honest asking price.
    """
    key = REGISTER_SOURCES.get(_exact(source))
    if key is not None:
        spec = TIERS[key]
        return {"tier": key, "rank": spec["rank"], "label": spec["label"], "matched": True}
    text = _norm(source)
    for key, spec in _BY_RANK:
        if any(phrase in text for phrase in spec["match"]):
            return {"tier": key, "rank": spec["rank"], "label": spec["label"], "matched": True}
    return {"tier": WEAKEST, "rank": TIERS[WEAKEST]["rank"], "label": TIERS[WEAKEST]["label"],
            "matched": False}


def _num(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace("$", "").replace(",", "").replace("%", "").strip())
    except (TypeError, ValueError):
        return None


def _subject_key(data: dict) -> str:
    """What makes two comps 'the same property' — normalized address, else the record's own id."""
    addr = re.sub(r"[^a-z0-9]+", "", str(data.get("address") or "").lower())
    return addr or f"__row_{id(data)}"


def rank_comps(comps: list[dict]) -> list[dict[str, Any]]:
    """Each comp with its tier, strongest first (then by most recent sale date)."""
    out = []
    for c in comps or []:
        d = c.get("data") or c
        t = tier_of(d.get("source"))
        out.append({**t, "address": d.get("address"), "source": d.get("source"),
                    "sale_date": d.get("sale_date"), "price": _num(d.get("price")),
                    "price_psf": _num(d.get("price_psf")), "cap_rate": _num(d.get("cap_rate")),
                    "rent_psf": _num(d.get("rent_psf")), "ref": c.get("ref"),
                    "_key": _subject_key(d)})
    out.sort(key=lambda r: (r["rank"], str(r.get("sale_date") or ""), str(r.get("address") or "")))
    return out


def resolve_conflicts(comps: list[dict]) -> dict[str, Any]:
    """Group comps by subject; the best tier wins and the outranked rows ride along so a reviewer
    can see WHAT was overruled and by how much."""
    ranked = rank_comps(comps)
    groups: dict[str, list[dict]] = {}
    for r in ranked:
        groups.setdefault(r["_key"], []).append(r)
    winners, conflicts = [], []
    for rows in groups.values():
        rows.sort(key=lambda r: r["rank"])
        best, rest = rows[0], rows[1:]
        winners.append(best)
        if rest and any(r["rank"] > best["rank"] for r in rest):
            deltas = []
            for r in rest:
                for field in ("price", "price_psf", "cap_rate", "rent_psf"):
                    a, b = best.get(field), r.get(field)
                    if a is not None and b is not None and abs(a - b) > 1e-9:
                        deltas.append({"field": field, "kept": a, "outranked": b,
                                       "kept_tier": best["tier"], "outranked_tier": r["tier"]})
            conflicts.append({"address": best.get("address"), "kept_tier": best["tier"],
                              "outranked": [{"tier": r["tier"], "source": r.get("source")} for r in rest],
                              "value_deltas": deltas})
    winners.sort(key=lambda r: (r["rank"], str(r.get("address") or "")))
    for w in winners:
        w.pop("_key", None)
    return {"comps": winners, "comp_count": len(winners),
            "conflicts": conflicts, "conflict_count": len(conflicts),
            "note": ("Comps describing the same address are resolved by source tier — the stronger "
                     "source wins and the overruled values are kept beside it, never averaged in.")}


def _pct(values: list[float], p: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    if len(s) == 1:
        return s[0]
    i = (len(s) - 1) * p
    lo, hi = int(i), min(int(i) + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (i - lo)


#: How many comps a band may name as carrying no value for its field before the list is a page. The
#: COUNT is always exact; only the naming is capped, and `without_value.truncated` says so — the
#: `CLASH-TRUNC` rule, which is that a consumer handed a page and told it is a total will treat it
#: as one.
_NAME_LIMIT = 20


def statistic(comps: list[dict], field: str = "price_psf") -> dict[str, Any]:
    """A tier-aware statistic: the p25/median/p75 band **plus the weakest tier it rests on**, so a
    number carried by one asking price can never read like one carried by six recorded sales.

    **The band is a SUBSET and now says so.** `n` was the only size reported, so a band over three
    of five comps and a band over all three of three were the same payload — and the two comps
    missing a `price_psf` were not absent from the market, they were absent from the form. `of_comps`
    is the resolved population the band was drawn from and `without_value` NAMES the shortfall, the
    same rule `from_project` already applies one level up to the appraiser's exclusions: *a sample
    that shrank without saying so reads as a thinner market rather than as a gap in the data entry.*
    Carried HERE rather than left to the caller, because `statistic()` is also called standalone and
    a coverage figure a caller has to reassemble is one some caller will not.

    **`conflicts_resolved` is field-scoped, and was not.** It reported `resolve_conflicts`' whole
    count, which is a property of the comp SET sitting among keys that are all properties of the
    BAND. Measured: a `rent_psf` band of one comp reported `conflicts_resolved: 1` for a
    disagreement about `price_psf` at a different address — so the single rent figure read as the
    survivor of a tie-break it was never in. The set-wide figure is still published, as
    `conflicts_in_set`, because it is the honest answer to a different question and dropping it
    would trade one wrong number for a missing one.
    """
    resolved = resolve_conflicts(comps)
    used = [(r[field], r) for r in resolved["comps"] if r.get(field) is not None]
    blank = [r for r in resolved["comps"] if r.get(field) is None]
    # A conflict counts for THIS band only if the tie-break moved THIS field. `value_deltas` is
    # already per-field, so the scoping is a read of what the engine recorded rather than a new
    # derivation.
    field_conflicts = [c for c in resolved["conflicts"]
                       if any(d["field"] == field for d in c["value_deltas"])]
    coverage = {
        "of_comps": resolved["comp_count"],
        "without_value": {
            "count": len(blank),
            "comps": [{"address": r.get("address"), "source": r.get("source"), "tier": r["tier"]}
                      for r in blank[:_NAME_LIMIT]],
            "truncated": len(blank) > _NAME_LIMIT,
        },
        "conflicts_resolved": len(field_conflicts),
        "conflicts_in_set": resolved["conflict_count"],
    }
    if not used:
        # The empty band carries its coverage too. Without it the caller cannot tell "nobody has
        # entered a cap rate on any of eleven comps" from "there are no comps", and those are a data
        # -entry task and an empty register respectively.
        return {"field": field, "n": 0, "median": None, "worst_tier": None, **coverage,
                "reason": f"no comp carries a {field} value"}
    values = [v for v, _ in used]
    worst = max((r for _, r in used), key=lambda r: r["rank"])
    best = min((r for _, r in used), key=lambda r: r["rank"])
    counts: dict[str, int] = {}
    for _, r in used:
        counts[r["tier"]] = counts.get(r["tier"], 0) + 1
    return {
        "field": field, "n": len(values),
        "p25": round(_pct(values, 0.25), 4), "median": round(_pct(values, 0.5), 4),
        "p75": round(_pct(values, 0.75), 4),
        "min": round(min(values), 4), "max": round(max(values), 4),
        "worst_tier": worst["tier"], "worst_tier_label": worst["label"],
        # The RANKS, not only the keys. A consumer handed `{"worst_tier": "listing"}` cannot tell
        # whether that is strong or weak without restating this ladder on its own side, and a
        # re-spelled ladder is a second copy that drifts — the `noRespelledShapes` argument applied
        # to an ordering rather than to a shape.
        "worst_rank": worst["rank"], "best_rank": best["rank"],
        "best_tier": best["tier"], "tier_counts": counts,
        "unattributed": counts.get(WEAKEST, 0),
        **coverage,
        "note": (f"Band rests on {len(values)} of {resolved['comp_count']} comp(s); the weakest "
                 f"contributing source is '{worst['label']}'. Strengthen that source before the "
                 f"number carries a decision."),
    }


def from_project(db, pid: str, field: str = "price_psf") -> dict[str, Any]:
    from . import modules as me
    # AN EXCLUDED COMPARABLE HAS BEEN EXCLUDED. The `comparable` workflow's transition INTO this
    # state is the action `exclude`, with `reinstate` to undo it — so the state is not metadata, it
    # is the appraiser's stated decision about this comp. Reading every record ignored it: a comp
    # marked excluded at $900/sf still moved the price_psf median from 305 to 310 and the sample
    # from n=2 to n=3.
    #
    # `recorded` is NOT filtered. It is the initial state and an unverified comp is still a comp;
    # only `excluded` is an explicit removal. Same rule as the `margin` sub-invoice fix — exclude
    # what the workflow says was rejected, leave the genuinely ambiguous state alone.
    all_comps = me.list_records(db, "comparable", pid, limit=100_000) if "comparable" in me.TABLES else []
    comps = [c for c in all_comps if c.get("workflow_state") != "excluded"]
    excluded = [{"id": c.get("id"), "ref": c.get("ref"), "reason": "excluded by the appraiser"}
                for c in all_comps if c.get("workflow_state") == "excluded"]
    resolved = resolve_conflicts(comps)
    return {**resolved,
            # The ladder itself, strongest first. `tier_counts` is a dict and a reader has no order
            # to render it in; the alternative is every client hard-coding this sequence, which is
            # exactly how the register's own `source` options and this ladder came to disagree for a
            # year. Published once per response rather than per band.
            "ladder": [{"tier": k, "label": spec["label"], "rank": spec["rank"]}
                       for k, spec in _BY_RANK],
            "statistics": {f: statistic(comps, f)
                           for f in ("price_psf", "cap_rate", "rent_psf")},
            "requested": statistic(comps, field),
            # NAMED, not silently dropped: a sample that shrank without saying so reads as a
            # thinner market rather than as a decision somebody made.
            "excluded_comparables": excluded}
