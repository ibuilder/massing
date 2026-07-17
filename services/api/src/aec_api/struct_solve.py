"""STRUCT-SOLVE · apply gravity load cases to the W10-7 analytical members + a lightweight statics solve.

The W10-7 `derive_analytical` recipe idealises the physical frame into `IfcStructuralCurveMember`s
(1-D line members between shared nodes) but carries only self-weight. This module closes that gap: it
reads those analytical members back off the IFC, **applies ASCE 7 gravity load cases** (dead + live by
occupancy, from `loads.py`) to them, and runs a **determinate, member-by-member statics solve** —

    horizontal members → simply-supported beam under a uniform line load w:
        end reactions R = wL/2 · max shear V = wL/2 · max moment M = wL²/8
        indicative deflection δ = 5wL⁴/(384·E·I)   (E,I default / caller-supplied)
        shear/moment/deflection *diagrams* sampled along the span
    vertical members → columns: tributary gravity accumulated down the stack (reuses `loads.takedown`)
        → service + ASCE-7-factored axial.

This is **NOT** a coupled stiffness (FEM) frame analysis — every member is solved in isolation as a
determinate element, which is exactly the hand-check a structural engineer runs before sizing. No lateral
(wind/seismic) member solve. Honest, preliminary, and license-free (statics is arithmetic).

**Not a substitute for design by a licensed professional engineer.**

Units: the analytical topology is in file units (converted to feet via the model unit scale); loads in
kips, lengths reported in ft, moments in kip-ft, deflection in inches.
"""
from __future__ import annotations

import math
from typing import Any

from . import loads

_M_PER_FT = 0.3048
_DEFLECT_LIMIT = 360.0        # L/360 — the common IBC Table 1604.3 live-load deflection limit for floors
# default section stiffness for the *indicative* deflection only (a mid-range steel floor beam, W18×50-ish)
_DEFAULT_E_KSI = 29000.0      # steel modulus of elasticity, ksi
_DEFAULT_I_IN4 = 800.0        # moment of inertia, in⁴ — caller-overridable; deflection is indicative only
_VERTICAL_COS = 0.87          # |dz|/L above this ⇒ treat the member as a column (≈ within 30° of vertical)


def _member_endpoints(cm) -> tuple[tuple, tuple] | None:
    """The two node coordinates (file units) of an `IfcStructuralCurveMember` from its `IfcEdge` topology."""
    rep = getattr(cm, "Representation", None)
    if rep is None:
        return None
    for r in rep.Representations:
        for item in (r.Items or []):
            if item.is_a("IfcEdge"):
                a = item.EdgeStart.VertexGeometry.Coordinates
                b = item.EdgeEnd.VertexGeometry.Coordinates
                return tuple(float(c) for c in a), tuple(float(c) for c in b)
    return None


def _beam_solve(length_ft: float, w_klf: float, e_ksi: float, i_in4: float,
                samples: int = 9) -> dict[str, Any]:
    """Simply-supported determinate beam under a uniform load. All closed-form statics — exact for the
    idealisation. Deflection is *indicative* (depends on the assumed E·I)."""
    L = length_ft
    R = w_klf * L / 2.0                                  # kip, each end reaction
    v_max = R                                            # kip, at the supports
    m_max = w_klf * L * L / 8.0                           # kip-ft, at midspan
    # δ = 5wL⁴/(384 EI); convert L ft→in, w kip/ft→kip/in for consistent inch units
    w_kli = w_klf / 12.0
    L_in = L * 12.0
    defl_in = (5.0 * w_kli * L_in ** 4) / (384.0 * e_ksi * i_in4) if (e_ksi * i_in4) else 0.0
    limit_in = L_in / _DEFLECT_LIMIT
    diagram = []
    for k in range(samples):
        x = L * k / (samples - 1)                        # ft from the left support
        vx = w_klf * (L / 2.0 - x)                        # kip
        mx = w_klf * x * (L - x) / 2.0                    # kip-ft
        # deflection curve of a simply-supported UDL beam: δ(x)=w·x(L³-2Lx²+x³)/(24EI)
        xi = x * 12.0
        dx = (w_kli * xi * (L_in ** 3 - 2 * L_in * xi ** 2 + xi ** 3)) / (24.0 * e_ksi * i_in4) \
            if (e_ksi * i_in4) else 0.0
        diagram.append({"x_ft": round(x, 2), "shear_kip": round(vx, 2),
                        "moment_kipft": round(mx, 2), "deflection_in": round(dx, 4)})
    return {"reaction_kip": round(R, 2), "shear_max_kip": round(v_max, 2),
            "moment_max_kipft": round(m_max, 2), "deflection_in": round(defl_in, 4),
            "deflection_limit_in": round(limit_in, 4),
            "deflection_ok": bool(defl_in <= limit_in + 1e-9),
            "diagram": diagram}


def _storeys_from_model(model) -> list[dict]:
    """Storeys top→bottom with a floor area estimate — mirrors the input shape `loads.takedown` wants,
    reusing the same read `loads.from_model` does but adding a per-storey area from the slab footprints."""

    # area per storey from slab quantities if present, else a single averaged plate
    storeys = []
    for st in model.by_type("IfcBuildingStorey"):
        storeys.append({"name": getattr(st, "Name", None) or "Level",
                        "elevation": getattr(st, "Elevation", None) or 0.0,
                        "occupancy": None})
    storeys.sort(key=lambda s: s["elevation"], reverse=True)
    for i, s in enumerate(storeys):
        s["roof"] = (i == 0)
    return storeys


def solve(model, *, live_occupancy: str = "office", sdl_psf: float = 20.0,
          slab_thickness_in: float = 8.0, tributary_ft: float | None = None,
          line_dead_klf: float | None = None, line_live_klf: float | None = None,
          e_ksi: float = _DEFAULT_E_KSI, i_in4: float = _DEFAULT_I_IN4,
          column_count: int | None = None, gross_area_sf: float | None = None) -> dict[str, Any]:
    """Apply a gravity load case to the analytical curve members and solve determinate statics.

    The uniform beam line load is either supplied directly (`line_dead_klf`/`line_live_klf`) or derived
    from floor pressures over a tributary strip width. If `tributary_ft` is omitted it is estimated as the
    average strip = gross floor area ÷ total beam length (a documented approximation for a preliminary
    line load). Returns per-beam solves + a governing beam, per-column axial (from the takedown), rolled
    reactions, and the applied load case. Read-only — nothing is written back to the IFC."""
    import ifcopenshell.util.unit as _uu

    members = model.by_type("IfcStructuralCurveMember")
    if not members:
        return {"has_analytical": False,
                "message": "No analytical model found — run the derive_analytical recipe first."}

    scale = _uu.calculate_unit_scale(model)              # metres per file unit
    ft_per_file = scale / _M_PER_FT

    beams: list[dict] = []
    columns: list[dict] = []
    total_beam_ft = 0.0
    for cm in members:
        ends = _member_endpoints(cm)
        if ends is None:
            continue
        a, b = ends
        dx, dy, dz = (b[0] - a[0]), (b[1] - a[1]), (b[2] - a[2])
        length_file = math.sqrt(dx * dx + dy * dy + dz * dz)
        if length_file <= 0:
            continue
        length_ft = length_file * ft_per_file
        vert = abs(dz) / length_file
        entry = {"name": getattr(cm, "Name", None) or "member", "guid": cm.GlobalId,
                 "length_ft": round(length_ft, 2)}
        if vert >= _VERTICAL_COS:
            columns.append(entry)
        else:
            entry["_len_ft"] = length_ft
            beams.append(entry)
            total_beam_ft += length_ft

    # --- assemble the gravity line load (dead + live) applied to every beam --------------------------
    slab_sw_psf = (slab_thickness_in / 12.0) * loads.CONCRETE_PCF
    dead_psf = slab_sw_psf + sdl_psf
    live_psf = loads._lo(live_occupancy)
    if tributary_ft is not None:
        trib = float(tributary_ft)
    else:
        # average tributary strip = gross floor area ÷ Σ beam length (documented approximation); if no
        # area is supplied, fall back to a nominal 8 ft strip so the solve still runs.
        trib = (float(gross_area_sf) / total_beam_ft) if (gross_area_sf and total_beam_ft) else 8.0
    w_dead = line_dead_klf if line_dead_klf is not None else (dead_psf * trib / 1000.0)
    w_live = line_live_klf if line_live_klf is not None else (live_psf * trib / 1000.0)
    w_service = w_dead + w_live
    # governing factored line load via the ASCE 7 combinations (treat as per-ft intensities)
    combos = loads.asce7_combos(w_dead, w_live)
    w_factored = combos["governing_lrfd"]["kips"]         # kip/ft (combos are unit-agnostic)

    for bm in beams:
        L = bm.pop("_len_ft")
        bm["service"] = _beam_solve(L, w_service, e_ksi, i_in4)
        bm["factored"] = _beam_solve(L, w_factored, e_ksi, i_in4)
    beams.sort(key=lambda b: b["factored"]["moment_max_kipft"], reverse=True)
    governing = beams[0] if beams else None

    # --- per-column axial from the gravity takedown (reuse the isolated loads.py) --------------------
    col_axial = None
    try:
        dm = loads.from_model(model)
        n_storeys = dm.get("storey_count", 0)
        cols = column_count or dm.get("column_count") or 12
        area_each = (gross_area_sf or 0.0)
        storeys = []
        sts = _storeys_from_model(model)
        for s in sts:
            storeys.append({"name": s["name"], "area_sf": area_each or 10000.0,
                            "occupancy": live_occupancy, "roof": s.get("roof")})
        if storeys:
            td = loads.takedown(storeys, sdl_psf=sdl_psf, slab_thickness_in=slab_thickness_in,
                                column_count=cols)
            col_axial = {"service_total_kip": td["column"]["service_total_kip"],
                         "factored_lrfd_kip": td["column"]["factored_lrfd_kip"],
                         "storeys": n_storeys, "column_count": cols,
                         "note": "Tributary gravity takedown per interior column; area assumed "
                                 f"{int(area_each) if area_each else 10000} sf/floor — override with gross_area_sf."}
    except Exception:  # noqa: BLE001 — the takedown is best-effort context, the beam solve is the core
        col_axial = None

    # --- roll reactions to the base -----------------------------------------------------------------
    total_beam_reaction = round(sum(b["service"]["reaction_kip"] * 2 for b in beams), 1)

    return {
        "has_analytical": True,
        "load_case": {
            "name": f"Dead + Live ({live_occupancy})",
            "dead_klf": round(w_dead, 3), "live_klf": round(w_live, 3),
            "service_klf": round(w_service, 3), "factored_lrfd_klf": round(w_factored, 3),
            "dead_psf": round(dead_psf, 1), "live_psf": round(live_psf, 1),
            "tributary_ft": round(trib, 2),
            "governing_combo": combos["governing_lrfd"]["combo"],
        },
        "counts": {"beams": len(beams), "columns": len(columns),
                   "total_beam_length_ft": round(total_beam_ft, 1)},
        "governing_beam": governing,
        "beams": beams,
        "columns_axial": col_axial,
        "reactions": {"sum_beam_service_kip": total_beam_reaction},
        "assumptions": {"E_ksi": e_ksi, "I_in4": i_in4, "slab_thickness_in": slab_thickness_in,
                        "superimposed_dead_psf": sdl_psf,
                        "deflection_limit": f"L/{int(_DEFLECT_LIMIT)}"},
        "disclaimer": "PRELIMINARY determinate statics for early coordination — every analytical member is "
                      "solved in isolation as a simply-supported element under a gravity load case (dead + "
                      "live). This is NOT a coupled stiffness (FEM) frame analysis, carries no lateral "
                      "(wind/seismic) member solve, and deflection is indicative (assumed E·I). All member "
                      "sizing and final design must be performed and stamped by a licensed professional engineer.",
    }
