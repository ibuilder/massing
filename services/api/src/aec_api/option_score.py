"""GEN-SCORE — generative design-option scoring: massing variants ranked by cost · carbon · yield · code.

The frontier-bet payoff of the engines already built: `compute_massing` turns a zoning envelope into a
program, the conceptual estimator prices it, a whole-building carbon benchmark rates it, and the zoning
checks gate it — so N candidate options score in one deterministic pass and the developer sees WHICH
massing to take into design, with the trade-offs (cheapest vs greenest vs highest-yield) explicit rather
than argued from spreadsheets. Offline, deterministic, no LLM: the "generative" part is a systematic
variant grid around a base envelope, the scoring is the platform's own engines.

Scoring model (per option, normalized 0–100 across the option set, weighted composite):
  · cost      — conceptual $/SF (lower is better)
  · carbon    — embodied kgCO₂e/m² GFA benchmark by building type (lower is better)
  · yield     — net sellable/leasable area (higher is better)
  · compliance— zoning checks (FAR achieved ≤ allowed, height ≤ limit): a violation flags the option
                non-compliant, caps its composite, and excludes it from `recommended`.
"""
from __future__ import annotations

from typing import Any

from . import conceptual_estimate as ce

# Whole-building embodied-carbon benchmarks, kgCO₂e/m² GFA (A1–A3 structure+envelope typicals from
# published whole-building LCA studies; editable defaults, same spirit as ce.COST_PER_SF). Types align
# with the conceptual estimator's catalog so one building_type drives both cost and carbon.
CARBON_KGCO2E_M2: dict[str, float] = {
    "office": 500.0, "office_highrise": 600.0, "multifamily": 400.0, "multifamily_highrise": 500.0,
    "retail": 350.0, "industrial": 320.0, "warehouse": 280.0, "hotel": 480.0, "hospital": 650.0,
    "school": 420.0, "parking_structure": 300.0, "mixed_use": 460.0, "data_center": 800.0,
    "senior_living": 430.0, "lab": 700.0,
}
_DEFAULT_CARBON = 450.0                      # unknown type → mid-range placeholder, flagged in the row

DEFAULT_WEIGHTS = {"cost": 0.35, "carbon": 0.25, "yield": 0.25, "compliance": 0.15}
M2_TO_SF = 10.7639


def generate_options(base: dict, far_steps: list[float] | None = None,
                     types: list[str] | None = None) -> list[dict]:
    """The generative grid: massing variants around a `base` envelope (the compute_massing params).

    Varies FAR utilisation (default 60/80/100% of the base FAR) × building type (default: keep the
    base's). Deterministic — the same base always yields the same option set. Each option is a full
    params dict ready for `score_options`, labelled for the scoreboard."""
    far = float(base.get("far", 1.0))
    steps = far_steps or [0.6, 0.8, 1.0]
    tlist = types or [base.get("building_type") or "multifamily"]
    out: list[dict] = []
    for t in tlist:
        for s in steps:
            opt = dict(base)
            opt["far"] = round(far * s, 3)
            opt["building_type"] = t
            opt["label"] = f"{t} @ FAR {opt['far']:g}" + ("" if s == 1.0 else f" ({s:.0%} of max)")
            out.append(opt)
    return out


def _norm(vals: list[float], value: float, higher_better: bool) -> float:
    """Min-max normalize `value` against the option set → 0–100. A flat set (all equal) scores 100 —
    the criterion doesn't differentiate, so it shouldn't penalize anyone."""
    lo, hi = min(vals), max(vals)
    if hi - lo < 1e-9:
        return 100.0
    x = (value - lo) / (hi - lo)
    return round((x if higher_better else 1.0 - x) * 100.0, 1)


def _evaluate(opt: dict) -> dict[str, Any]:
    """One option through the engines: massing → program, conceptual $/SF → cost, carbon benchmark,
    zoning checks. Raw (un-normalized) figures; `score_options` normalizes across the set."""
    from aec_data import massing as mg  # type: ignore  # deferred heavy import

    m = mg.compute_massing(opt)
    gfa_m2 = float(m.get("buildable_gfa_m2") or 0.0)
    gfa_sf = float(m.get("buildable_gfa_sf") or gfa_m2 * M2_TO_SF)
    btype = (opt.get("building_type") or "multifamily").lower()
    est = ce.estimate({"building_type": btype, "gfa_sf": gfa_sf, "region": opt.get("region"),
                       "year": opt.get("year"), "stories": m.get("floors"),
                       "units": m.get("units"), "soft_cost_pct": opt.get("soft_cost_pct")})
    carbon_int = CARBON_KGCO2E_M2.get(btype, _DEFAULT_CARBON)
    carbon_t = round(gfa_m2 * carbon_int / 1000.0, 1)          # tCO₂e total

    # zoning compliance off the massing result: FAR + height. compute_massing already binds the
    # program to the envelope, so violations here mean the INPUT asked past the envelope.
    violations: list[str] = []
    far_allowed = float(opt.get("far", 0) or 0)
    if far_allowed and float(m.get("far_achieved") or 0) > far_allowed + 1e-6:
        violations.append(f"FAR {m['far_achieved']} exceeds allowed {far_allowed}")
    hl = opt.get("height_limit")
    if hl is not None and float(m.get("building_height_m") or 0) > float(hl) + 1e-6:
        violations.append(f"height {m['building_height_m']}m exceeds limit {hl}m")

    return {
        "label": opt.get("label") or f"{btype} FAR {far_allowed:g}",
        "building_type": btype,
        "massing": {k: m.get(k) for k in ("floors", "building_height_m", "buildable_gfa_m2",
                                          "buildable_gfa_sf", "net_sellable_m2", "units",
                                          "far_achieved", "binding_constraint")},
        "cost_total": est["total_cost"], "cost_per_sf": (est.get("metrics") or {}).get("cost_per_sf"),
        "carbon_intensity_kgco2e_m2": carbon_int, "carbon_total_tco2e": carbon_t,
        "carbon_benchmark_matched": btype in CARBON_KGCO2E_M2,
        "yield_net_sellable_m2": float(m.get("net_sellable_m2") or 0.0),
        "compliant": not violations, "violations": violations,
    }


def score_options(options: list[dict], weights: dict[str, float] | None = None) -> dict[str, Any]:
    """Score N candidate options and rank them. Composite = Σ(weightᵢ × normalized criterionᵢ); a
    non-compliant option's composite is capped at 49 (never above any compliant one's floor) and it is
    excluded from `recommended`. Raises ValueError on an empty set."""
    if not options:
        raise ValueError("no options to score — pass at least one massing-params dict")
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    total_w = sum(w.values()) or 1.0
    rows = [_evaluate(o) for o in options]

    psf = [float(r["cost_per_sf"] or 0.0) for r in rows]
    cint = [r["carbon_intensity_kgco2e_m2"] for r in rows]
    sell = [r["yield_net_sellable_m2"] for r in rows]
    for r in rows:
        scores = {
            "cost": _norm(psf, float(r["cost_per_sf"] or 0.0), higher_better=False),
            "carbon": _norm(cint, r["carbon_intensity_kgco2e_m2"], higher_better=False),
            "yield": _norm(sell, r["yield_net_sellable_m2"], higher_better=True),
            "compliance": 100.0 if r["compliant"] else 0.0,
        }
        composite = round(sum(w[k] * v for k, v in scores.items()) / total_w, 1)
        if not r["compliant"]:
            composite = min(composite, 49.0)           # a violating option never outranks a compliant one
        r["scores"] = scores
        r["composite"] = composite
    rows.sort(key=lambda r: -r["composite"])
    compliant = [r for r in rows if r["compliant"]]
    return {
        "options": rows, "weights": w,
        "recommended": (compliant[0]["label"] if compliant else None),
        "note": ("Deterministic scoring through the platform's own engines: conceptual $/SF (cost), "
                 "whole-building embodied-carbon benchmarks (carbon), net sellable area (yield), and "
                 "zoning FAR/height checks (compliance). Normalized within THIS option set — scores "
                 "compare options to each other, not to an absolute standard. Editable defaults; refine "
                 "with a detailed takeoff + EPDs as the design develops."),
    }
