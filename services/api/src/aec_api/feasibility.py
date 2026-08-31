"""Site feasibility / zoning envelope — the "Massing" feasibility study.

Given the project's `zoning` record (site area + zoning controls: FAR, height, lot coverage,
setbacks, open space, parking, unit size), compute the **maximum buildable envelope**: allowed
GFA as the binding minimum of the FAR cap vs. the physical envelope (footprint x floors), then
unit yield, parking demand and required open space. Reconciles the allowed GFA against the
**model's actual gross floor area** (when a source IFC exists) to show FAR used and headroom.

Pure functions — no I/O except a thin reader for the zoning record + an optional model GFA the
caller passes in (so this is testable without an IFC). Mirrors the analytics-engine pattern used
across the codebase (precon.py, specs.py)."""
from __future__ import annotations

import math
from typing import Any

SF_PER_ACRE = 43_560.0


def _num(v: Any) -> float | None:
    try:
        if v is None or v == "":
            return None
        return float(v)
    except (TypeError, ValueError):
        return None


def _d(r: dict) -> dict:
    return r.get("data") or r


def _buildable_footprint(z: dict, site_area: float) -> tuple[float | None, str]:
    """Footprint area from lot-coverage and/or setback geometry, whichever is the tighter limit."""
    cov = _num(z.get("lot_coverage_pct"))
    cov_fp = site_area * cov / 100.0 if cov else None
    w, dep = _num(z.get("lot_width_ft")), _num(z.get("lot_depth_ft"))
    fs, ss, rs = _num(z.get("front_setback_ft")), _num(z.get("side_setback_ft")), _num(z.get("rear_setback_ft"))
    set_fp = None
    if w and dep:
        bw = max(0.0, w - 2 * (ss or 0.0))
        bd = max(0.0, dep - (fs or 0.0) - (rs or 0.0))
        set_fp = bw * bd
    candidates = [(c, lbl) for c, lbl in ((cov_fp, "lot coverage"), (set_fp, "setbacks")) if c]
    if not candidates:
        return None, ""
    fp, lbl = min(candidates, key=lambda t: t[0])
    return round(fp, 1), lbl


def compute(zoning: dict, actual_gfa_sf: float | None = None) -> dict[str, Any]:
    """Core feasibility math. `zoning` is a flat field map (the module record's `data`)."""
    z = _d(zoning)
    warnings: list[str] = []
    site_area = _num(z.get("site_area_sf"))
    if not site_area:
        return {"error": "site_area_sf is required", "warnings": ["No site area set."]}

    far = _num(z.get("far"))
    height = _num(z.get("height_limit_ft"))
    f2f = _num(z.get("floor_to_floor_ft")) or 12.0
    max_floors_cap = _num(z.get("max_floors"))
    eff = _num(z.get("efficiency_pct")) or 85.0
    avg_unit = _num(z.get("avg_unit_sf"))
    parking_ratio = _num(z.get("parking_ratio"))
    open_pct = _num(z.get("open_space_pct"))

    # FAR cap
    far_gfa = round(site_area * far, 1) if far else None
    if not far:
        warnings.append("No FAR set - allowed GFA falls back to the physical envelope only.")

    # physical envelope: footprint x floors
    footprint, fp_basis = _buildable_footprint(z, site_area)
    floors_by_height = math.floor(height / f2f) if height else None
    floors = None
    floor_basis = []
    if floors_by_height is not None:
        floors, floor_basis = floors_by_height, [f"height {height:g}ft / {f2f:g}ft floors"]
    if max_floors_cap is not None:
        floors = int(max_floors_cap) if floors is None else min(floors, int(max_floors_cap))
        floor_basis.append(f"cap {int(max_floors_cap)}")
    envelope_gfa = round(footprint * floors, 1) if (footprint and floors) else None

    # binding constraint = the tighter of FAR vs envelope
    options = [(g, lbl) for g, lbl in ((far_gfa, "FAR"), (envelope_gfa, "physical envelope")) if g is not None]
    if options:
        allowed_gfa, binding = min(options, key=lambda t: t[0])
    else:
        allowed_gfa, binding = None, None
        warnings.append("Not enough zoning inputs to size an envelope (need FAR, or coverage/height).")

    net_area = round(allowed_gfa * eff / 100.0, 1) if allowed_gfa is not None else None
    unit_yield = math.floor(net_area / avg_unit) if (net_area is not None and avg_unit) else None
    if allowed_gfa is not None and not avg_unit:
        warnings.append("No avg unit size - unit yield not computed.")
    parking_required = math.ceil(unit_yield * parking_ratio) if (unit_yield is not None and parking_ratio) else None
    open_space_required = round(site_area * open_pct / 100.0, 1) if open_pct else None

    # reconcile against the model's actual GFA, if provided
    model = None
    if actual_gfa_sf and allowed_gfa:
        far_used = round(actual_gfa_sf / site_area, 3)
        pct = round(100.0 * actual_gfa_sf / allowed_gfa, 1)
        headroom = round(allowed_gfa - actual_gfa_sf, 1)
        model = {
            "actual_gfa_sf": round(actual_gfa_sf, 1),
            "far_used": far_used,
            "pct_of_allowed": pct,
            "headroom_gfa_sf": headroom,
            "status": "over" if headroom < -1 else ("at-capacity" if pct >= 98 else "under"),
        }

    # a constraint table so the UI/report can show what binds
    constraints = []
    if far_gfa is not None:
        constraints.append({"constraint": "FAR cap", "limit_gfa_sf": far_gfa,
                            "basis": f"{site_area:,.0f} SF x FAR {far:g}"})
    if envelope_gfa is not None:
        constraints.append({"constraint": "Physical envelope", "limit_gfa_sf": envelope_gfa,
                            "basis": f"{footprint:,.0f} SF footprint ({fp_basis}) x {floors} floors ({', '.join(floor_basis)})"})

    return {
        "site": z.get("site"), "jurisdiction": z.get("jurisdiction"), "use_type": z.get("use_type"),
        "site_area_sf": round(site_area, 1), "site_area_acres": round(site_area / SF_PER_ACRE, 3),
        "inputs": {"far": far, "height_limit_ft": height, "floor_to_floor_ft": f2f,
                   "max_floors": max_floors_cap, "lot_coverage_pct": _num(z.get("lot_coverage_pct")),
                   "efficiency_pct": eff, "avg_unit_sf": avg_unit, "parking_ratio": parking_ratio,
                   "open_space_pct": open_pct},
        "buildable_footprint_sf": footprint, "footprint_basis": fp_basis,
        "max_floors": floors,
        "far_gfa_sf": far_gfa, "envelope_gfa_sf": envelope_gfa,
        "allowed_gfa_sf": allowed_gfa, "binding_constraint": binding,
        "net_buildable_sf": net_area, "unit_yield": unit_yield,
        "parking_required": parking_required, "open_space_required_sf": open_space_required,
        "constraints": constraints,
        "model": model,
        "warnings": warnings,
    }


def compare(db, pid: str, actual_gfa_sf: float | None = None) -> dict[str, Any]:
    """Scenario comparison — run the envelope math for every `zoning` record (each is a scheme) and
    rank them so a developer can test FAR / height / coverage trade-offs side by side, Giraffe-style.
    Ranked by unit yield, then allowed GFA. Deltas are vs. the top scheme."""
    from . import modules as me
    if "zoning" not in me.TABLES:
        return {"error": "zoning module not installed", "scenarios": []}
    recs = me.list_records(db, "zoning", pid, limit=100000)
    if not recs:
        return {"scenarios": [], "count": 0, "warnings": ["Add Zoning & Site records (one per scheme) to compare."]}
    # A SUPERSEDED scheme is not a candidate. `supersede` is the explicit act of replacing a zoning
    # record (with `reopen` back to draft), so ranking one can make the winner — and therefore the
    # BASELINE every other scheme's deltas are measured against — a scheme that no longer applies.
    # Measured before this: a superseded FAR-12 scheme ranked first at 240,000 GFA against a live
    # FAR-4 scheme's 80,000, so the live scheme was reported as a 160,000 SF shortfall against an
    # envelope nobody can build.
    #
    # `draft` stays: an unapproved scheme is a real thing to test, which is what this comparison is
    # FOR. Only the explicit replacement is excluded. The sibling `feasibility()` thirty lines below
    # already reads this state to prefer an approved record — one function in the file honoured it
    # and this one did not.
    #
    # `workflow_state` is now carried on every row. It was dropped before the caller could see it,
    # so the UI had no way to mark a scheme as superseded even if it wanted to — the same shape as
    # the appraisal defect, where the state was discarded before any filter could apply.
    superseded = [r for r in recs if r.get("workflow_state") == "superseded"]
    live = [r for r in recs if r.get("workflow_state") != "superseded"]
    scen = []
    for rec in live:
        f = compute(rec, actual_gfa_sf=actual_gfa_sf)
        if f.get("error"):
            continue
        scen.append({
            "ref": rec.get("ref"), "zoning_id": rec.get("id"),
            "workflow_state": rec.get("workflow_state"),
            "site": f.get("site"), "use_type": f.get("use_type"),
            "far": (f.get("inputs") or {}).get("far"),
            "max_floors": f.get("max_floors"),
            "allowed_gfa_sf": f.get("allowed_gfa_sf"), "binding_constraint": f.get("binding_constraint"),
            "net_buildable_sf": f.get("net_buildable_sf"), "unit_yield": f.get("unit_yield"),
            "parking_required": f.get("parking_required"),
        })
    scen.sort(key=lambda s: ((s["unit_yield"] or 0), (s["allowed_gfa_sf"] or 0)), reverse=True)
    best = scen[0] if scen else None
    for s in scen:                                          # deltas vs. the top scheme
        if best:
            s["delta_units"] = (s["unit_yield"] or 0) - (best["unit_yield"] or 0)
            s["delta_gfa_sf"] = round((s["allowed_gfa_sf"] or 0) - (best["allowed_gfa_sf"] or 0), 1)
    return {"scenarios": scen, "count": len(scen), "best_ref": best["ref"] if best else None,
            # Named rather than silently dropped: a comparison whose field shrank without saying so
            # reads as a thinner set of options rather than as a decision somebody recorded.
            "superseded_excluded": [{"ref": r.get("ref"), "zoning_id": r.get("id")}
                                    for r in superseded],
            "note": ("Schemes ranked by unit yield, then allowed GFA; deltas are vs. the top scheme. "
                     "SUPERSEDED records are excluded from the ranking and named in "
                     "`superseded_excluded` — a replaced scheme cannot be the baseline the live ones "
                     "are measured against. Drafts ARE ranked: an unapproved scheme is a real option "
                     "to test.")}


def feasibility(db, pid: str, actual_gfa_sf: float | None = None, zoning_id: str | None = None) -> dict[str, Any]:
    """Resolve the project's zoning record (the given id, else the most recently modified approved/
    draft one) and run the envelope math, reconciled against the model GFA when available."""
    from . import modules as me
    if "zoning" not in me.TABLES:
        return {"error": "zoning module not installed", "warnings": []}
    recs = me.list_records(db, "zoning", pid, limit=100000)
    if not recs:
        return {"error": "no zoning record", "warnings": ["Add a Zoning & Site record to run a feasibility study."]}
    rec = next((r for r in recs if r.get("id") == zoning_id), None) if zoning_id else None
    if rec is None:
        # prefer approved, then most recent
        rec = next((r for r in recs if r.get("workflow_state") == "approved"), recs[0])
    out = compute(rec, actual_gfa_sf=actual_gfa_sf)
    out["ref"] = rec.get("ref")
    out["zoning_id"] = rec.get("id")
    return out
