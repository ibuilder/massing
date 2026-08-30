"""R22-OPTION-OBJECT — an option's economics come from the proforma, or they say they didn't.

`design_options.compare()` ranks schemes on `hard_cost`, `cost_per_sf` and `irr_pct`. Every one of
those is a plain `number` field somebody typed into a form, and the `design_option` schema carried
**zero** references to a deal or a scenario. Meanwhile the platform holds a complete underwriting
engine — `proforma/solve.py` sizes the debt, `returns.py` computes the levered IRR, `waterfall.py`
splits the promote — and none of it reached the card where a scheme is actually chosen.

The ring entry asks for "no massing evaluated without its returns". The failure it names is not a
missing number; it is a number **whose provenance is invisible**. A typed 19.7% and a solved 19.7%
render identically, and the typed one is the one that is six weeks stale, or aspirational, or copied
from the option above it.

So this is a seam, not a second underwriting model. Every figure states its `basis`:

- ``derived``     — the option names a proforma scenario; `solve()` was run and this is its output.
- ``declared``    — a figure recorded on the option itself. Used as given and **labelled**, because
                    a hand-entered number is a legitimate early-stage input, not an error.
- ``unlinked``    — the project HAS scenarios but this option names none. Reported with the
                    candidates, and **deliberately not resolved**: attaching the project's deal to a
                    massing that never claimed it would manufacture provenance, which is worse than
                    having none. The whole point of the field is to record which deal a scheme was
                    priced under.
- ``unavailable`` — nothing to derive from and nothing recorded.

**A `declared` figure is never silently upgraded to `derived`, and a `derived` one never overwrites
what a user typed** — both are reported, and `agrees_with_declared` says whether they match. A
scheme whose typed IRR is 400 bps above what its own scenario solves to is the single most useful
thing this module can surface, and it can only be surfaced by keeping both.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from . import modules as me
from .models import Scenario

BASIS_DERIVED = "derived"
BASIS_DECLARED = "declared"
BASIS_UNLINKED = "unlinked"
BASIS_UNAVAILABLE = "unavailable"

_WHY = {
    BASIS_DERIVED: "solved from the proforma scenario this option names",
    BASIS_DECLARED: "recorded on the option by hand — a stated input, not a computed result",
    BASIS_UNLINKED: ("the project has proforma scenarios but this option names none, so its returns "
                     "cannot be attributed to any deal"),
    BASIS_UNAVAILABLE: "no scenario to solve and no figure recorded",
}

#: A derived and a declared IRR within this many percentage points are treated as agreeing. Wider
#: than float noise on purpose: a typed figure is rounded by whoever typed it, and flagging 19.7
#: against 19.74 as a disagreement would train readers to ignore the flag.
IRR_AGREE_PCT = 0.5


def _num(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return None


def _solved(scenario: Scenario) -> dict[str, Any] | None:
    """The scenario's result, solved on demand if it has not been cached.

    Mirrors `routers/proforma.py`'s `s.result or solve(s.assumptions)` rather than requiring a cached
    result — an option linked to a never-opened scenario should still price.
    """
    if scenario is None:
        return None
    if scenario.result:
        return scenario.result
    try:
        from .proforma.solve import solve
        return solve(scenario.assumptions)
    except Exception:
        # A scenario whose assumptions no longer solve is a real state (fields renamed, a required
        # key dropped). It must read as "could not derive", never as a zero-cost, zero-return option.
        return None


def option_economics(rec: dict[str, Any], scenario: Scenario | None,
                     project_scenarios: list[tuple[str, str]] | None = None) -> dict[str, Any]:
    """Economics for ONE design option, with the basis each figure rests on.

    `scenario` is the Scenario this option names (or None). `project_scenarios` is [(id, name)] of
    what the project has, used only to distinguish `unlinked` from `unavailable`.
    """
    d = rec.get("data") or rec
    area = _num(d.get("gross_area_sf"))
    dec_cost, dec_irr = _num(d.get("hard_cost")), _num(d.get("irr_pct"))
    solved = _solved(scenario)

    row: dict[str, Any] = {
        "id": rec.get("id"), "name": d.get("name", ""), "state": rec.get("workflow_state", ""),
        "gross_area_sf": area,
        "scenario_id": scenario.id if scenario is not None else None,
        "scenario_name": scenario.name if scenario is not None else None,
        "declared_hard_cost": dec_cost, "declared_irr_pct": dec_irr,
    }

    if solved:
        su, ret = solved.get("sources_uses") or {}, solved.get("returns") or {}
        cost = _num(su.get("total_uses"))
        irr = _num(ret.get("equity_irr"))
        irr_pct = round(irr * 100, 2) if irr is not None else None
        row.update({
            "basis": BASIS_DERIVED, "hard_cost": round(cost, 2) if cost is not None else None,
            "irr_pct": irr_pct,
            "equity": round(_num(su.get("equity")) or 0.0, 2),
            "loan_amount": round(_num(su.get("loan_amount")) or 0.0, 2),
            "equity_multiple": _num(ret.get("equity_multiple")),
            "yield_on_cost": _num(ret.get("yield_on_cost")),
            "cost_per_sf": round(cost / area, 2) if cost and area else None,
            # Both figures survive. The disagreement is the finding, so it cannot be computed if the
            # derived value has overwritten the declared one.
            "agrees_with_declared": (None if dec_irr is None or irr_pct is None
                                     else abs(irr_pct - dec_irr) <= IRR_AGREE_PCT),
            "declared_vs_derived_irr_pct": (None if dec_irr is None or irr_pct is None
                                            else round(dec_irr - irr_pct, 2)),
            "note": None,
        })
    elif dec_cost is not None or dec_irr is not None:
        row.update({
            "basis": BASIS_DECLARED, "hard_cost": dec_cost, "irr_pct": dec_irr,
            "cost_per_sf": round(dec_cost / area, 2) if dec_cost and area else None,
            "equity": None, "loan_amount": None, "equity_multiple": None, "yield_on_cost": None,
            "agrees_with_declared": None, "declared_vs_derived_irr_pct": None,
            "note": ("figures were entered by hand; link a proforma scenario to derive them"
                     if scenario is None else
                     "the linked scenario could not be solved, so the recorded figures are shown"),
        })
    else:
        unlinked = bool(project_scenarios) and scenario is None
        row.update({
            "basis": BASIS_UNLINKED if unlinked else BASIS_UNAVAILABLE,
            "hard_cost": None, "irr_pct": None, "cost_per_sf": None,
            "equity": None, "loan_amount": None, "equity_multiple": None, "yield_on_cost": None,
            "agrees_with_declared": None, "declared_vs_derived_irr_pct": None,
            "note": (f"this project has {len(project_scenarios)} proforma scenario(s) "
                     f"({', '.join(n for _, n in (project_scenarios or [])[:3])}) but this option "
                     f"names none — set `scenario` to price it"
                     if unlinked else
                     "no proforma scenario and no recorded figures — nothing to evaluate this "
                     "massing against"),
        })
    row["basis_note"] = _WHY[row["basis"]]
    return row


def compare_economics(db: Session, pid: str) -> dict[str, Any]:
    """Every design option's economics, ranked, with the unpriced ones named rather than dropped."""
    rows = me.list_records(db, "design_option", pid, limit=100_000) \
        if "design_option" in me.TABLES else []
    scenarios = db.query(Scenario).filter(Scenario.project_id == pid).all()
    by_id = {s.id: s for s in scenarios}
    by_name = {(s.name or "").strip().lower(): s for s in scenarios}
    candidates = [(s.id, s.name) for s in scenarios]

    opts = []
    for r in rows:
        d = r.get("data") or r
        if not d.get("name"):
            continue
        ref = str(d.get("scenario") or "").strip()
        sc = by_id.get(ref) or by_name.get(ref.lower()) if ref else None
        opts.append(option_economics(r, sc, candidates))

    # Same separation this module already makes between listed and ranked, for a second reason:
    # `best_irr` must not name a scheme the team rejected. `derived` / `disagree` deliberately keep
    # reading EVERY option, rejected included — "your declared IRR disagrees with your proforma" is
    # a data-quality finding about a record, and it stays true whether or not the scheme is in play.
    from .design_options import DESIGN_OPTION_NOT_IN_CONTENTION
    contenders = [o for o in opts if o["state"] not in DESIGN_OPTION_NOT_IN_CONTENTION]
    priced = [o for o in contenders if o["irr_pct"] is not None]
    ranked = sorted(priced, key=lambda o: -o["irr_pct"])
    derived = [o for o in opts if o["basis"] == BASIS_DERIVED]
    disagree = [o for o in derived if o["agrees_with_declared"] is False]

    return {
        # `count` is everything LISTED; the pricing counts describe the RANKED population, so they
        # are taken against `contenders`. Deriving `unpriced_count` from `opts` instead reported a
        # rejected option that HAS an IRR as unpriced — measured: unpriced_count 1 while zero
        # options lacked a figure. The exclusion and the count that describes it must run over the
        # same population, or the response contradicts itself; `in_contention_count` is returned so
        # a reader can reconcile `count` rather than having to infer the difference.
        #
        # THIRD TIME THIS SHAPE HAS APPEARED (v0.3.1122 `billed_to_date` vs `invoice_count`, then
        # `priced` vs `unpriced_count`, then carbon's `measured`+`unavailable` not summing): filter a
        # computation, leave a count over the unfiltered set. Whenever a filter is added here, every
        # count derived from that set moves with it.
        "count": len(opts), "in_contention_count": len(contenders),
        "priced_count": len(priced), "derived_count": len(derived),
        "unpriced_count": len(contenders) - len(priced),
        "options": opts,
        "best_irr": ranked[0]["name"] if ranked else None,
        "scenarios": [{"id": i, "name": n} for i, n in candidates],
        # The headline finding this module exists to surface.
        "declared_disagrees_with_derived": [
            {"name": o["name"], "declared_irr_pct": o["declared_irr_pct"],
             "derived_irr_pct": o["irr_pct"],
             "delta_pct": o["declared_vs_derived_irr_pct"]} for o in disagree],
        "basis_meanings": _WHY,
        "not_in_contention": [o["name"] for o in opts
                              if o["state"] in DESIGN_OPTION_NOT_IN_CONTENTION],
        "note": ("An option is ranked only on a figure that exists, and only if it is still in "
                 "contention — a REJECTED option is listed but never named `best_irr`. A `declared` "
                 "figure is shown and labelled, never promoted to `derived`; an `unlinked` option is "
                 "never priced from another scheme's deal."),
        "message": (None if priced else
                    "No option can be priced yet. Link a proforma scenario to an option (set its "
                    "`scenario` field), or record hard_cost / irr_pct directly."),
    }
