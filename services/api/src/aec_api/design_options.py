"""Design options / variants (B1): a project carries N schemes; compare them apples-to-apples and
promote one to the selected design.

Each option is a lightweight snapshot of the metrics that decide a scheme — program (area, units,
efficiency), economics (hard cost, cost/sf, energy EUI, IRR) and **embodied carbon** — entered by hand
or copied from the test-fit / proforma. Carbon is A1-A3 embodied and is NOT `energy_eui`, which is
operational: different lifecycle stage, different units, and picking a scheme on one while believing
it is the other is the mistake the separate `carbon_basis` field exists to prevent.

`compare()` normalizes them, names the best-in-class per metric and the deltas vs the selected option,
so switching direction is a decision, not a spreadsheet.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from . import modules as me


def _d(r: dict) -> dict:
    return r.get("data") or r


def _num(v: Any) -> float | None:
    if v in (None, ""):
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _option(r: dict) -> dict[str, Any]:
    d = _d(r)
    area, cost = _num(d.get("gross_area_sf")), _num(d.get("hard_cost"))
    # Embodied carbon comes from `option_carbon`, not from a second copy of the rules here. It carries
    # its own `carbon_basis` because the figure is sometimes declared, sometimes benchmarked and
    # sometimes absent, and a card that shows the number without the basis invites comparing a real
    # LCA against an area × intensity estimate as though they were the same claim.
    from . import option_carbon
    oc = option_carbon.option_carbon(r)
    return {
        "id": r.get("id"), "name": d.get("name", ""), "state": r.get("workflow_state", ""),
        "drawing_set": d.get("drawing_set"),
        "gross_area_sf": area, "unit_count": _num(d.get("unit_count")),
        "efficiency_pct": _num(d.get("efficiency_pct")),
        "hard_cost": cost, "cost_per_sf": round(cost / area, 2) if area and cost else None,
        "energy_eui": _num(d.get("energy_eui")), "irr_pct": _num(d.get("irr_pct")),
        "building_type": oc["building_type"],
        "embodied_kgco2e": oc["embodied_kgco2e"], "kgco2e_per_sf": oc["kgco2e_per_sf"],
        "carbon_basis": oc["basis"], "carbon_note": oc["note"],
    }


# metric key -> (label, lower-is-better)
# `_leader` skips options whose value is None, so an option with no carbon basis is never named
# best-in-class — which is the whole reason `option_carbon` returns None instead of a placeholder.
_METRICS = {
    "cost_per_sf": ("Lowest cost / sf", True),
    "energy_eui": ("Lowest energy EUI", True),
    "kgco2e_per_sf": ("Lowest embodied carbon / sf", True),
    "irr_pct": ("Highest IRR", False),
    "gross_area_sf": ("Largest area", False),
    "efficiency_pct": ("Highest efficiency", False),
}


def compare(db: Session, pid: str) -> dict[str, Any]:
    rows = me.list_records(db, "design_option", pid, limit=100000) if "design_option" in me.TABLES else []
    opts = [_option(r) for r in rows if _d(r).get("name")]

    # Provenance for the money columns, added ALONGSIDE them and never over them. `hard_cost` and
    # `irr_pct` keep meaning exactly what they meant — the figures recorded on the option — so no
    # existing reader changes behaviour. What is new is that the card can now say whether anyone
    # solved them: `economics_basis` is `derived` only when the option names a proforma scenario that
    # actually solves. A typed IRR and a solved IRR render identically otherwise, and the typed one
    # is the one that goes stale. See `option_economics` for why an unlinked option is not priced
    # from the project's other scenario.
    try:
        from . import option_economics
        econ = {e["id"]: e for e in option_economics.compare_economics(db, pid)["options"]}
    except Exception:
        econ = {}
    for o in opts:
        e = econ.get(o["id"])
        o["economics_basis"] = e["basis"] if e else None
        o["derived_irr_pct"] = e["irr_pct"] if e and e["basis"] == "derived" else None
        o["derived_hard_cost"] = e["hard_cost"] if e and e["basis"] == "derived" else None
        o["irr_agrees_with_proforma"] = e["agrees_with_declared"] if e else None

    def _leader(key: str, lower: bool) -> str | None:
        vals = [(o[key], o["name"]) for o in opts if o.get(key) is not None]
        if not vals:
            return None
        return (min if lower else max)(vals, key=lambda t: t[0])[1]

    leaders = {key: {"label": label, "option": _leader(key, lower)}
               for key, (label, lower) in _METRICS.items()}
    selected = next((o for o in opts if o["state"] == "selected"), None)

    # deltas vs the selected option (so "what do we give up / gain by switching" is explicit)
    if selected:
        for o in opts:
            o["delta_vs_selected"] = {
                k: (round(o[k] - selected[k], 2) if o.get(k) is not None and selected.get(k) is not None else None)
                for k in ("cost_per_sf", "irr_pct", "energy_eui", "gross_area_sf",
                          "kgco2e_per_sf")}

    return {
        "count": len(opts), "options": opts, "leaders": leaders,
        "selected": selected["name"] if selected else None,
        "by_state": {s: sum(1 for o in opts if o["state"] == s)
                     for s in ("proposed", "shortlisted", "selected", "rejected")},
        "note": "Options compared on program, economics and embodied carbon; best-in-class named per "
                "metric. An option whose carbon_basis is 'unavailable' carries no figure and is never "
                "named best-in-class. Promote one to 'selected' to set the project's design direction "
                "(its drawing set becomes current).",
    }
