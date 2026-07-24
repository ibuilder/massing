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


def _norm(s: Any) -> str:
    return re.sub(r"[^a-z ]+", " ", str(s or "").lower())


def tier_of(source: Any) -> dict[str, Any]:
    """Classify one free-text source into a tier. Unrecognized text is the WEAKEST tier, never a
    middling guess — an unattributed number should not outrank an honest asking price."""
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


def statistic(comps: list[dict], field: str = "price_psf") -> dict[str, Any]:
    """A tier-aware statistic: the p25/median/p75 band **plus the weakest tier it rests on**, so a
    number carried by one asking price can never read like one carried by six recorded sales."""
    resolved = resolve_conflicts(comps)
    used = [(r[field], r) for r in resolved["comps"] if r.get(field) is not None]
    if not used:
        return {"field": field, "n": 0, "median": None, "worst_tier": None,
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
        "best_tier": best["tier"], "tier_counts": counts,
        "unattributed": counts.get(WEAKEST, 0),
        "conflicts_resolved": resolved["conflict_count"],
        "note": (f"Band rests on {len(values)} comp(s); the weakest contributing source is "
                 f"'{worst['label']}'. Strengthen that source before the number carries a decision."),
    }


def from_project(db, pid: str, field: str = "price_psf") -> dict[str, Any]:
    from . import modules as me
    comps = me.list_records(db, "comparable", pid, limit=100_000) if "comparable" in me.TABLES else []
    resolved = resolve_conflicts(comps)
    return {**resolved,
            "statistics": {f: statistic(comps, f)
                           for f in ("price_psf", "cap_rate", "rent_psf")},
            "requested": statistic(comps, field)}
