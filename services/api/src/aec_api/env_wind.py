"""ENV-1 — pedestrian wind-comfort SCREEN at massing stage (approximate, offline, deterministic).

Early massing decisions (height, slenderness, podium, gaps) drive most pedestrian-level wind
problems, but CFD comes far too late to steer them. This screen applies the published rule-of-thumb
mechanisms — **corner acceleration**, **downwash** (tall façades redirecting gradient wind to grade),
and **channelling** between buildings — to the massing numbers, grades each zone on the **Lawson
comfort categories** (A sitting < 4 m/s · B standing < 6 · C strolling < 8 · D walking < 10 ·
E uncomfortable ≥ 10 · unsafe > 15), and suggests the standard mitigations (podium, canopy, porous
screens, corner chamfers). A screening heuristic to steer massing — NOT CFD and NOT a wind-tunnel
study; verify with a wind consultant for any tall or exposed site.
"""
from __future__ import annotations

from typing import Any

# Lawson comfort categories by mean wind speed at pedestrian level (m/s)
_LAWSON = [(4.0, "A", "sitting"), (6.0, "B", "standing"), (8.0, "C", "strolling"),
           (10.0, "D", "brisk walking"), (15.0, "E", "uncomfortable")]


def _lawson(v: float) -> tuple[str, str]:
    for thr, cls, label in _LAWSON:
        if v < thr:
            return cls, label
    return "S", "unsafe — exceeds the 15 m/s safety criterion"


def screen(height_m: float, width_m: float, depth_m: float,
           wind_ms: float = 5.0, gap_m: float | None = None,
           podium_height_m: float = 0.0) -> dict[str, Any]:
    """Screen one building mass. `wind_ms` = the site's mean pedestrian-level wind (unobstructed);
    `gap_m` = the clear distance to the nearest comparable building (enables the channelling check);
    `podium_height_m` = a wider podium interrupting downwash (the classic mitigation)."""
    h = max(0.0, float(height_m))
    w = max(0.1, float(width_m))
    v0 = max(0.1, float(wind_ms))
    zones: list[dict[str, Any]] = []
    mitigations: list[str] = []

    # corner acceleration — grows with height (flow wrapping a bluff body); ~1.2 low-rise → ~1.6 tall
    corner_f = 1.2 + 0.4 * min(1.0, h / 100.0)
    vc = round(v0 * corner_f, 1)
    c_cls, c_label = _lawson(vc)
    zones.append({"zone": "corners", "factor": round(corner_f, 2), "speed_ms": vc,
                  "lawson": c_cls, "comfort": c_label})
    if c_cls in ("D", "E", "S"):
        mitigations.append("chamfer/round the windward corners or add corner canopies")

    # downwash — façades taller than ~25 m redirect faster gradient wind to grade; a podium ≥ ~20% of
    # the height intercepts it
    if h > 25.0:
        dw_f = 1.1 + 0.5 * min(1.0, (h - 25.0) / 125.0)
        if podium_height_m >= 0.2 * h:
            dw_f = max(1.0, dw_f - 0.35)
            mitigations.append("podium present — downwash largely intercepted (keep its roof landscaped)")
        vd = round(v0 * dw_f, 1)
        d_cls, d_label = _lawson(vd)
        zones.append({"zone": "base (downwash)", "factor": round(dw_f, 2), "speed_ms": vd,
                      "lawson": d_cls, "comfort": d_label})
        if d_cls in ("D", "E", "S") and podium_height_m < 0.2 * h:
            mitigations.append(f"add a podium (≥ {round(0.2 * h)} m) or an entrance canopy to intercept downwash")

    # channelling — a gap narrower than the flanking height funnels the flow (venturi)
    if gap_m is not None and gap_m > 0 and h > 10.0 and gap_m < h / 2.0:
        ch_f = 1.15 + 0.45 * min(1.0, (h / 2.0 - gap_m) / (h / 2.0))
        vch = round(v0 * ch_f, 1)
        g_cls, g_label = _lawson(vch)
        zones.append({"zone": f"passage ({gap_m:g} m gap)", "factor": round(ch_f, 2), "speed_ms": vch,
                      "lawson": g_cls, "comfort": g_label})
        if g_cls in ("D", "E", "S"):
            mitigations.append("widen the gap, stagger the masses, or add porous screens/planting in the passage")

    open_cls, open_label = _lawson(v0)
    zones.insert(0, {"zone": "open site (baseline)", "factor": 1.0, "speed_ms": round(v0, 1),
                     "lawson": open_cls, "comfort": open_label})
    worst = max(zones, key=lambda z: z["speed_ms"])
    return {
        "inputs": {"height_m": h, "width_m": w, "depth_m": float(depth_m), "wind_ms": v0,
                   "gap_m": gap_m, "podium_height_m": podium_height_m},
        "zones": zones, "worst": {"zone": worst["zone"], "lawson": worst["lawson"],
                                  "speed_ms": worst["speed_ms"]},
        "acceptable_for_entrances": worst["lawson"] in ("A", "B", "C"),
        "mitigations": mitigations,
        "disclaimer": "Approximate massing-stage screen (Lawson comfort categories via published "
                      "corner/downwash/channelling rules of thumb) — NOT CFD or a wind-tunnel study. "
                      "Verify tall or exposed sites with a wind consultant.",
    }
