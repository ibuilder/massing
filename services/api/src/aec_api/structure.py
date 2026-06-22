"""Structural-system advisor (R3) — choose a plausible structural system by height and span, with
rough member sizing and a load-path read. Grounded in structural rules of thumb (Salvadori, *Why
Buildings Stand Up*): systems are selected by scale and load path, not one-size-fits-all. Pure
functions; feeds the generative model so the frame is sensible for the building's height instead of
a fixed section."""
from __future__ import annotations

from typing import Any


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
    return {
        "system": system, "lateral_system": lateral, "rationale": rationale,
        "height_m": round(height_m, 1), "floors": floors, "span_m": span_m, "slenderness": slenderness,
        "members_mm": {"slab": slab_mm, "beam_depth": beam_depth_mm, "column": col_mm,
                       "uses_beams": not flat_plate},
        "load_path": load_path, "flags": flags,
    }
