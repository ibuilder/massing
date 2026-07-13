"""Structural-system advisor (R3) — choose a plausible structural system by height and span, with
rough member sizing and a load-path read. Grounded in structural rules of thumb (Salvadori, *Why
Buildings Stand Up*): systems are selected by scale and load path, not one-size-fits-all. Pure
functions; feeds the generative model so the frame is sensible for the building's height instead of
a fixed section."""
from __future__ import annotations

import math
from typing import Any


def column_schedule(floors: int, base_col_mm: float, span_m: float = 7.5) -> list[dict[str, Any]]:
    """Per-floor column taper. A column at level i carries (floors − i) floors of tributary load;
    axial load ∝ floors carried and column area ∝ load, so the **side ∝ √(floors carried)**. The
    ground column (carries everything) is `base_col_mm`; upper columns shrink with √load, floored at
    400 mm and rounded to 50 mm so adjacent levels share a section (real buildings taper in zones)."""
    floors = max(1, int(floors))
    out: list[dict[str, Any]] = []
    for i in range(floors):
        carried = floors - i                       # this level supports itself + everything above
        side = base_col_mm * math.sqrt(carried / floors)
        side_mm = round(max(400.0, side) / 50) * 50
        out.append({"floor": i, "floors_carried": carried, "side_mm": side_mm})
    return out


def lateral_core(height_m: float, floors: int, plate_w_m: float, plate_d_m: float,
                 lateral: str) -> dict[str, Any]:
    """A central reinforced-concrete lateral core sized to the building. Provided when the system uses
    a core/shear-wall lateral (mid-rise and up). Core plan ≈ 20% of the floorplate (rule of thumb for a
    stiff enough core), min ~6 m; wall thickness grows with height (drift). Positioned at the plan
    centre (0,0). Returns geometry the generator can extrude the full height for real lateral stiffness."""
    uses_core = "core" in lateral.lower()          # a *central* core, not distributed shear walls
    plate_area = max(1.0, plate_w_m * plate_d_m)
    core_area = 0.20 * plate_area                  # ~20% of the plate for a code-plausible core
    side = max(6.0, math.sqrt(core_area))          # ~square core, ≥6 m so stairs+lifts fit
    core_w = round(min(side, plate_w_m * 0.6), 1)
    core_d = round(min(side, plate_d_m * 0.6), 1)
    wall_mm = round(min(900, max(250, 200 + height_m * 4)) / 50) * 50   # thicker as it gets taller
    return {
        "provided": uses_core, "plan_w_m": core_w, "plan_d_m": core_d, "wall_mm": wall_mm,
        "position": {"x": 0.0, "y": 0.0}, "full_height": True,
        "note": (f"Central {core_w:g}×{core_d:g} m core, {wall_mm} mm walls, extruded the full "
                 f"{floors}-storey height — carries wind/seismic to the foundation."
                 if uses_core else "Lateral resisted by distributed shear walls / braced bays; "
                 "no single central core at this scale."),
    }


def _system(height_m: float, floors: int) -> tuple[str, str, str]:
    """(system, lateral system, one-line rationale) by height — the classic tiers."""
    if height_m <= 15:
        return ("Concrete flat-plate", "Shear walls / braced bays",
                "Low-rise: a flat-plate slab on columns is fast and economical; gravity dominates.")
    if height_m <= 45:
        return ("Concrete flat-plate + shear walls", "Reinforced-concrete shear walls",
                "Mid-rise: flat-plate gravity frame with shear walls to carry wind/seismic.")
    if height_m <= 150:
        return ("Shear-core + perimeter frame", "Central reinforced-concrete shear core",
                "High-rise: a stiff central core resists lateral load; the frame carries gravity.")
    return ("Outrigger & belt-truss core (or framed tube)", "Core + outriggers to perimeter columns",
            "Supertall: outriggers tie the core to perimeter columns to control drift and overturning.")


def recommend(height_m: float, floors: int, span_m: float = 7.5,
              use: str = "residential") -> dict[str, Any]:
    """Recommend a structural system + rough member sizes (mm) for the given scale. Sizing uses
    span/height rules of thumb (slab ≈ span/30, beam ≈ span/16, columns grow with tributary load)."""
    height_m = max(3.0, float(height_m)); span_m = max(3.0, float(span_m)); floors = max(1, int(floors))
    system, lateral, rationale = _system(height_m, floors)

    slab_mm = round(max(150, span_m * 1000 / 30) / 10) * 10
    beam_depth_mm = round(max(300, span_m * 1000 / 16) / 50) * 50
    # column side grows with floors carried (axial) and span (tributary area)
    col_mm = round(min(1200, max(400, 300 + floors * 25 + span_m * 12)) / 50) * 50

    flags: list[str] = []
    flat_plate = "flat-plate" in system
    if flat_plate and span_m > 9:
        flags.append(f"Long span ({span_m:g} m) for a flat-plate — add beams/girders or post-tensioning.")
    if span_m > 12:
        flags.append(f"Span {span_m:g} m is long — post-tensioned or steel framing is more efficient.")
    if height_m > 60 and "core" not in system.lower() and "shear" not in system.lower():
        flags.append("Tall building without a dedicated lateral core — verify drift.")
    slenderness = round(height_m / max(span_m, 1), 1)
    if slenderness > 7:
        flags.append(f"Slender (H/width ≈ {slenderness}) — overturning/drift likely governs; consider outriggers.")

    load_path = (f"Gravity: slab → {'beams → ' if not flat_plate else ''}columns → foundation. "
                 f"Lateral: wind/seismic → {lateral.lower()} → foundation.")

    # Per-floor taper + lateral core so the *generated geometry* follows the load path, not a
    # fixed section. Plate size for the core is unknown here, so pass a span-derived nominal plate;
    # the generator overrides it with the real footprint when it calls lateral_core() itself.
    schedule = column_schedule(floors, col_mm, span_m)
    nominal_plate = span_m * 5                      # ~5 bays if the caller gives us no footprint
    core = lateral_core(height_m, floors, nominal_plate, nominal_plate, lateral)
    return {
        "system": system, "lateral_system": lateral, "rationale": rationale,
        "height_m": round(height_m, 1), "floors": floors, "span_m": span_m, "slenderness": slenderness,
        "members_mm": {"slab": slab_mm, "beam_depth": beam_depth_mm, "column": col_mm,
                       "uses_beams": not flat_plate},
        "column_schedule": schedule, "base_column_mm": col_mm,
        "top_column_mm": schedule[-1]["side_mm"], "lateral_core": core,
        "load_path": load_path, "flags": flags,
    }
