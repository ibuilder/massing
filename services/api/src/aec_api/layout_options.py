"""MASSING-OPT (R16 Tier-1, Finch) — the layout/massing **optioneer**: deterministically enumerate
envelope levers over a fixed zoning envelope, score each option for developer yield, and rank + build a
Pareto frontier — the same shape as ``schedule_options.optimize`` but for the *massing* stage instead of
the schedule.

Given one site (``lot`` + zoning: FAR, coverage, setbacks, height limit) and acquisition assumptions
(land + hard $/sf + rent + cap rate), sweep the levers a developer actually turns early —
**floor-to-floor**, **core efficiency**, **unit size / mix**, **coverage strategy** (podium vs. tower) —
run each combination through ``massing.compute_massing`` (the deterministic zoning→program engine), and
compute a lightweight yield-on-cost proforma per option. Pure and offline: no IFC is written here (that
is the phase-2 recipe-chain emission); this ranks the *program* so the user picks a massing to author.

Everything is reused: the envelope math is ``compute_massing``; the score is transparent arithmetic; the
frontier is a plain Pareto filter. Zero new dependencies.
"""
from __future__ import annotations

import itertools
from typing import Any

_M2_TO_SF = 10.763910417

# The most a lever-sweep may enumerate — guards a combinatorial blow-up from wide custom lever lists.
_MAX_SCENARIOS = 240


def _yield(m: dict, base: dict, use_type: str) -> dict[str, Any]:
    """A transparent yield-on-cost proforma over one computed program. Not the full underwriting engine —
    a deterministic first-cut score so options are ranked by the developer metric, not just raw GFA."""
    gfa_sf = float(m.get("buildable_gfa_sf") or 0.0)
    net_sellable_sf = float(m.get("net_sellable_m2") or 0.0) * _M2_TO_SF
    units = int(m.get("units") or 0)

    land = float(base.get("land_cost", 0) or 0)
    hard = gfa_sf * float(base.get("hard_cost_psf", 0) or 0)
    soft = hard * float(base.get("soft_cost_pct", 0) or 0)
    contingency = hard * float(base.get("contingency_pct", 0) or 0)
    total_cost = land + hard + soft + contingency

    if use_type == "commercial":
        egi = net_sellable_sf * float(base.get("rent_psf_year", 0) or 0)
    else:
        egi = units * float(base.get("rent_per_unit_month", 0) or 0) * 12.0
    noi = egi * (1.0 - float(base.get("opex_ratio", 0) or 0))
    exit_cap = float(base.get("exit_cap", 0.05) or 0.05)
    value = noi / exit_cap if exit_cap > 0 else 0.0
    yoc = (noi / total_cost) if total_cost > 0 else 0.0     # yield-on-cost — the primary ranking metric
    return {"total_cost": round(total_cost), "noi": round(noi), "stabilized_value": round(value),
            "profit": round(value - total_cost), "yield_on_cost": round(yoc, 4),
            "profit_margin": round((value - total_cost) / total_cost, 4) if total_cost > 0 else 0.0}


def _levers(base: dict) -> dict[str, list]:
    """The default lever grid — sensible spreads around the base assumptions. A caller may override any
    key with its own list (``layers`` in the request); an empty/absent key falls back to the base value."""
    f2f0 = float(base.get("floor_to_floor", 3.5) or 3.5)
    eff0 = float(base.get("efficiency", 0.82) or 0.82)
    cov0 = float(base.get("coverage_max", 0.6) or 0.6)
    au0 = float(base.get("avg_unit_m2", 75.0) or 75.0)
    return {
        # tighter floor-to-floor packs more floors under a height cap; taller ceilings sell better
        "floor_to_floor": sorted({round(max(2.7, f2f0 - 0.3), 2), round(f2f0, 2), round(f2f0 + 0.5, 2)}),
        # core/circulation efficiency strategy (single-loaded vs point-access vs double-loaded)
        "efficiency": sorted({round(min(0.9, eff0 + 0.03), 3), round(eff0, 3), round(max(0.7, eff0 - 0.04), 3)}),
        # podium (fat footprint) vs tower (slender) — only meaningful when coverage binds
        "coverage_max": sorted({round(min(1.0, cov0), 3), round(max(0.2, cov0 - 0.15), 3)}),
        # unit-size mix: studio-heavy (more units) vs family (fewer, larger)
        "avg_unit_m2": sorted({round(max(30.0, au0 - 20), 1), round(au0, 1), round(au0 + 25, 1)}),
    }


def _pareto(scenarios: list[dict]) -> list[str]:
    """The non-dominated set on (maximize profit, minimize total_cost) — the classic developer frontier:
    an option is on the frontier if no other option is both cheaper AND more profitable."""
    front: list[str] = []
    for a in scenarios:
        dominated = any(
            b is not a
            and b["proforma"]["total_cost"] <= a["proforma"]["total_cost"]
            and b["proforma"]["profit"] >= a["proforma"]["profit"]
            and (b["proforma"]["total_cost"] < a["proforma"]["total_cost"]
                 or b["proforma"]["profit"] > a["proforma"]["profit"])
            for b in scenarios
        )
        if not dominated:
            front.append(a["id"])
    return front


def optioneer(base: dict, levers: dict[str, list] | None = None, *, objective: str = "yield_on_cost",
              limit: int = 24) -> dict[str, Any]:
    """Enumerate the lever grid over the envelope → scored, ranked massing options + a Pareto frontier.

    ``base`` is the MassingIn-shaped envelope + econ dict. ``levers`` overrides any default lever list.
    ``objective`` ∈ {yield_on_cost, profit, units, net_sellable} picks the ranking key. Returns the top
    ``limit`` scenarios (each carrying the lever values, the computed program, and the proforma), the
    frontier ids, and the winning option.
    """
    from aec_data.massing import compute_massing  # type: ignore

    compute_massing(base)                                   # validate the envelope up front — a bad lot
    #                                                         (no area) raises ValueError → 422, not a
    #                                                         silently-empty result
    use_type = str(base.get("use_type", "residential"))
    grid = {**_levers(base), **{k: v for k, v in (levers or {}).items() if v}}
    keys = list(grid)
    combos = list(itertools.product(*(grid[k] for k in keys)))
    if len(combos) > _MAX_SCENARIOS:
        combos = combos[:_MAX_SCENARIOS]

    scenarios: list[dict] = []
    seen: set[tuple] = set()
    for combo in combos:
        overrides = dict(zip(keys, combo))
        params = {**base, **overrides}
        try:
            m = compute_massing(params)
        except ValueError:
            continue                                        # infeasible envelope for this combo — skip
        # collapse duplicate PROGRAMS (different levers can yield the same floors/gfa/units)
        sig = (m["floors"], m["buildable_gfa_m2"], m["units"], overrides["efficiency"])
        if sig in seen:
            continue
        seen.add(sig)
        pf = _yield(m, base, use_type)
        scenarios.append({
            "id": f"opt-{len(scenarios) + 1}",
            "levers": overrides,
            "floors": m["floors"], "height_m": m["building_height_m"],
            "gfa_m2": m["buildable_gfa_m2"], "gfa_sf": m["buildable_gfa_sf"],
            "net_sellable_m2": m["net_sellable_m2"], "units": m["units"],
            "far_achieved": m["far_achieved"], "binding_constraint": m["binding_constraint"],
            "proforma": pf,
        })

    if not scenarios:
        return {"scenarios": [], "frontier": [], "best": None, "objective": objective,
                "note": "no feasible massing options for this envelope"}

    def _key(s: dict) -> float:
        pf = s["proforma"]
        return {"yield_on_cost": pf["yield_on_cost"], "profit": pf["profit"],
                "units": s["units"], "net_sellable": s["net_sellable_m2"]}.get(objective, pf["yield_on_cost"])

    frontier = _pareto(scenarios)
    for s in scenarios:
        s["on_frontier"] = s["id"] in frontier
    scenarios.sort(key=_key, reverse=True)
    ranked = scenarios[: max(1, limit)]
    return {
        "scenarios": ranked, "frontier": frontier, "best": ranked[0]["id"],
        "objective": objective, "count": len(scenarios), "shown": len(ranked),
        "levers_swept": {k: grid[k] for k in keys},
        "note": "Deterministic massing options over the zoning envelope — floor-to-floor, core efficiency, "
                "coverage strategy and unit size swept through the program engine, ranked by "
                f"{objective}. Author the winner via the blank-IFC → levels/grid → walls/slabs recipe chain.",
    }
