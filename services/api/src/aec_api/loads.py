"""Preliminary gravity load takedown + ASCE 7 load combinations (Wave 8 ④).

A defensible, *non-FEA* gravity check a BIM platform can compute for early coordination — the
tributary-area "load takedown" every structural engineer runs by hand before sizing columns:

    dead (slab self-weight + superimposed) + live (ASCE 7 by occupancy, with §4.7 reduction)
      → tributary area per column → accumulate storey-by-storey down to the footing
      → ASCE 7 load combinations (LRFD §2.3 + ASD §2.4) → governing factored axial load.

No stiffness matrix, no lateral (wind/seismic) — that needs a licensed engineer and a real analysis.
This yields per-column and per-footing service + factored axial loads for preliminary sizing and
sanity-checking a scheme. **Not a substitute for design by a licensed professional engineer.**

Pure arithmetic (coefficients are facts from ASCE 7-22); `from_model()` reads storey/column counts off
the IFC. Units: loads in kips, areas in ft², pressures in psf.
"""
from __future__ import annotations

import math
from typing import Any

# ASCE 7-22 Table 4.3-1 (representative uniform live loads, psf) — pick the closest occupancy.
LIVE_PSF: dict[str, float] = {
    "office": 50, "residential": 40, "apartment": 40, "hotel": 40, "retail": 75, "mercantile": 75,
    "assembly": 100, "lobby": 100, "corridor": 80, "stair": 100, "school": 40, "classroom": 40,
    "parking": 40, "garage": 40, "warehouse_light": 125, "warehouse_heavy": 250, "storage": 125,
    "roof": 20, "mechanical": 150, "library_stack": 150,
}
CONCRETE_PCF = 150.0        # normal-weight reinforced concrete
_KLL_INTERIOR = 4           # ASCE 7 §4.7.2 live-load element factor (interior column)
_RED_FLOOR_MIN = 0.40       # members supporting ≥2 floors: reduction capped at 40 %


def live_load_reduction(lo_psf: float, tributary_sf: float, k_ll: int = _KLL_INTERIOR,
                        min_factor: float = _RED_FLOOR_MIN) -> float:
    """ASCE 7 §4.7: L = Lo·(0.25 + 15/√(K_LL·A_T)), for K_LL·A_T ≥ 400 ft², floored per code."""
    infl = k_ll * tributary_sf
    if infl < 400:
        return lo_psf
    reduced = lo_psf * (0.25 + 15.0 / math.sqrt(infl))
    return max(reduced, min_factor * lo_psf)


def asce7_combos(D: float, L: float = 0.0, Lr: float = 0.0, S: float = 0.0, R: float = 0.0,
                 W: float = 0.0, E: float = 0.0) -> dict[str, Any]:
    """Governing ASCE 7 combinations for a gravity load set (any unit — here kips)."""
    lr_s_r = max(Lr, S, R)
    lrfd = {
        "1.4D": 1.4 * D,
        "1.2D+1.6L+0.5(Lr/S/R)": 1.2 * D + 1.6 * L + 0.5 * lr_s_r,
        "1.2D+1.6(Lr/S/R)+0.5L": 1.2 * D + 1.6 * lr_s_r + 0.5 * L,
        "1.2D+1.0W+1.0L+0.5(Lr/S/R)": 1.2 * D + 1.0 * W + 1.0 * L + 0.5 * lr_s_r,
        "1.2D+1.0E+1.0L+0.2S": 1.2 * D + 1.0 * E + 1.0 * L + 0.2 * S,
    }
    asd = {
        "D": D, "D+L": D + L, "D+(Lr/S/R)": D + lr_s_r,
        "D+0.75L+0.75(Lr/S/R)": D + 0.75 * L + 0.75 * lr_s_r,
        "D+0.6W": D + 0.6 * W, "D+0.7E": D + 0.7 * E,
    }
    gl = max(lrfd, key=lambda k: lrfd[k])
    ga = max(asd, key=lambda k: asd[k])
    return {"lrfd": {k: round(v, 1) for k, v in lrfd.items()},
            "asd": {k: round(v, 1) for k, v in asd.items()},
            "governing_lrfd": {"combo": gl, "kips": round(lrfd[gl], 1)},
            "governing_asd": {"combo": ga, "kips": round(asd[ga], 1)}}


def _lo(occ: str | None) -> float:
    return LIVE_PSF.get((occ or "office").lower().strip(), 50.0)


def takedown(storeys: list[dict], sdl_psf: float = 20.0, slab_thickness_in: float = 8.0,
             concrete_pcf: float = CONCRETE_PCF, column_count: int = 12,
             k_ll: int = _KLL_INTERIOR) -> dict[str, Any]:
    """Gravity takedown for a typical interior column. `storeys` top→bottom, each
    ``{name, area_sf, occupancy, roof?}``. Returns per-storey rows + the accumulated base column /
    footing service & factored axial loads."""
    column_count = max(1, int(column_count))
    slab_dead_psf = (slab_thickness_in / 12.0) * concrete_pcf     # self-weight of the slab
    d_psf = slab_dead_psf + sdl_psf
    rows = []
    cum_d_lb = 0.0                        # per-column dead, accumulated down
    cum_live_unred_lb = 0.0               # per-column live (unreduced), summed
    cum_trib_sf = 0.0
    roof_lr_lb = 0.0                      # roof live carried straight (its own reduction rules)
    for s in storeys:
        area = float(s.get("area_sf", 0) or 0)
        trib = area / column_count
        is_roof = bool(s.get("roof"))
        lo = _lo("roof" if is_roof else s.get("occupancy"))
        d_lb = d_psf * trib
        cum_d_lb += d_lb
        if is_roof:
            roof_lr_lb += lo * trib
            live_lb = lo * trib
        else:
            cum_live_unred_lb += lo * trib
            cum_trib_sf += trib
            live_lb = lo * trib
        rows.append({"name": s.get("name") or f"Level {len(rows) + 1}",
                     "occupancy": "roof" if is_roof else (s.get("occupancy") or "office"),
                     "area_sf": round(area, 1), "tributary_sf": round(trib, 1),
                     "dead_psf": round(d_psf, 1), "live_psf": round(lo, 1),
                     "col_dead_kip": round(d_lb / 1000, 2), "col_live_kip": round(live_lb / 1000, 2)})
    # one reduction factor on the summed floor live (approximation, documented), + roof live unreduced
    factor = 1.0
    if cum_trib_sf and (k_ll * cum_trib_sf) >= 400:
        eff_lo = cum_live_unred_lb / cum_trib_sf
        factor = live_load_reduction(eff_lo, cum_trib_sf, k_ll) / eff_lo if eff_lo else 1.0
    live_lb = cum_live_unred_lb * factor + roof_lr_lb
    D = cum_d_lb / 1000.0
    L = (cum_live_unred_lb * factor) / 1000.0
    Lr = roof_lr_lb / 1000.0
    combos = asce7_combos(D, L, Lr)
    return {
        "assumptions": {"slab_thickness_in": slab_thickness_in, "slab_self_weight_psf": round(slab_dead_psf, 1),
                        "superimposed_dead_psf": sdl_psf, "dead_psf": round(d_psf, 1),
                        "concrete_pcf": concrete_pcf, "column_count": column_count, "k_ll": k_ll,
                        "live_reduction_factor": round(factor, 3), "storeys": len(storeys)},
        "storeys": rows,
        "column": {"service_dead_kip": round(D, 1), "service_live_kip": round(L + Lr, 1),
                   "service_total_kip": round(D + L + Lr, 1),
                   "factored_lrfd_kip": combos["governing_lrfd"]["kips"],
                   "factored_asd_kip": combos["governing_asd"]["kips"]},
        "footing": {"service_total_kip": round(D + L + Lr, 1),
                    "factored_lrfd_kip": combos["governing_lrfd"]["kips"]},
        "combinations": combos,
        "disclaimer": "PRELIMINARY gravity estimate for early coordination only — a tributary-area load "
                      "takedown with ASCE 7 combinations, NOT a structural analysis. Lateral (wind/seismic) "
                      "is out of scope. All member sizing and final design must be performed and stamped by "
                      "a licensed professional engineer.",
    }


def from_model(model) -> dict[str, Any]:
    """Read storey names + interior-column count off the IFC to pre-fill the takedown (best-effort)."""
    storeys = []
    for st in model.by_type("IfcBuildingStorey"):
        storeys.append({"name": getattr(st, "Name", None) or "Level",
                        "elevation": getattr(st, "Elevation", None)})
    storeys.sort(key=lambda s: (s.get("elevation") if s.get("elevation") is not None else 0), reverse=True)
    cols = len(model.by_type("IfcColumn"))
    return {"storey_names": [s["name"] for s in storeys], "storey_count": len(storeys),
            "column_count": cols}
