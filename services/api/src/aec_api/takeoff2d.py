"""TAKEOFF-2D · quantity takeoff from a 2D drawing (PDF page / scan).

The drawings-only case the model takeoff misses: a GC or estimator has a PDF/scan, not a BIM model, and
needs quantities off it. The browser traces regions on the drawing (manual polygon or one-click flood
fill) and calibrates a scale (two points at a known real distance → real units per pixel). This module is
the server-side quantify step: it turns those pixel-space regions + the scale into **real areas / lengths
and priced quantities**, grouped by assembly, feeding the same 5D estimate the model takeoff feeds.

Pure geometry (shoelace area, polyline length) + a small assembly rate table; no model, no network. The
tracer/flood-fill lives in the browser; this is the deterministic, testable measurement + pricing core.
"""
from __future__ import annotations

import math
from typing import Any

# 2D-takeoff assemblies: category → (measure, $/unit, label). `area` bills the polygon area, `length`
# bills the polyline length. Rates are all-in installed benchmarks, overridable per call (project vintage).
TAKEOFF_ASSEMBLIES: dict[str, tuple[str, float, str]] = {
    "floor_slab": ("area", 130.0, "Floor slab (in place)"),
    "roofing": ("area", 210.0, "Roofing assembly"),
    "ceiling": ("area", 55.0, "Ceiling / covering"),
    "partition": ("area", 160.0, "Interior partition (by wall face area)"),
    "exterior_wall": ("area", 320.0, "Exterior wall assembly (by face area)"),
    "curtain_wall": ("area", 600.0, "Curtain wall"),
    "paving": ("area", 90.0, "Site paving"),
    "generic_area": ("area", 100.0, "Generic area"),
    "wall_linear": ("length", 210.0, "Wall run (linear)"),
    "footing_linear": ("length", 240.0, "Strip footing (linear)"),
    "generic_linear": ("length", 50.0, "Generic linear"),
    # R34-TAKEOFF-COUNT — the platform had no count measure at all. Every assembly was `area` or
    # `length`, so a door, a fixture, a receptacle or a sprinkler head — the thing an estimator counts
    # most often — could not be taken off a drawing. Rates are per EACH, not per unit of geometry.
    "door": ("count", 850.0, "Doors"),
    "window": ("count", 650.0, "Windows"),
    "plumbing_fixture": ("count", 1200.0, "Plumbing fixtures"),
    "receptacle": ("count", 145.0, "Receptacles"),
    "light_fixture": ("count", 320.0, "Light fixtures"),
    "sprinkler_head": ("count", 185.0, "Sprinkler heads"),
    "generic_count": ("count", 100.0, "Generic count"),
}
_UNIT_LABEL = {"area": "m²", "length": "m", "count": "ea"}


def _count_of(reg: dict) -> float:
    """How many items a count region stands for. One marker is one item unless it says otherwise.

    A region may carry an explicit `count` for a marker that represents several ("12 receptacles on
    this run"). It must be a positive whole number: a fractional count is not a quantity anyone can
    order, and a string that survives `float()` is the type-confusion `valid_scale` already refuses
    one field over. Anything else falls back to 1 — the marker exists, so the count is at least one;
    what is unknown is the multiplicity, not the presence.
    """
    v = reg.get("count")
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return 1.0
    if not math.isfinite(v) or v <= 0 or float(v) != int(v):
        return 1.0
    return float(int(v))


def polygon_area_px2(points: list) -> float:
    """Shoelace area of a polygon given as [[x, y], …] in pixels (absolute value, auto-closes)."""
    n = len(points)
    if n < 3:
        return 0.0
    s = 0.0
    for i in range(n):
        x0, y0 = float(points[i][0]), float(points[i][1])
        x1, y1 = float(points[(i + 1) % n][0]), float(points[(i + 1) % n][1])
        s += x0 * y1 - x1 * y0
    return abs(s) / 2.0


def polyline_length_px(points: list) -> float:
    """Total length of a polyline [[x, y], …] in pixels (open — does not close back to the start)."""
    total = 0.0
    for i in range(len(points) - 1):
        dx = float(points[i + 1][0]) - float(points[i][0])
        dy = float(points[i + 1][1]) - float(points[i][1])
        total += (dx * dx + dy * dy) ** 0.5
    return total


#: How a measurement was produced. `unrecorded` is a real answer and the DEFAULT one — a region that
#: does not say how it was made is not assumed to have been carefully traced. Recording the number
#: while inventing its method is the failure this exists to prevent.
MEASURE_METHODS = ("one_click", "traced", "imported", "unrecorded")

#: Who produced it. Same rule: absent means `unrecorded`, not `person`. An agent-generated takeoff and
#: a hand-traced one carry different weight in a claim, and only one of them is defensible without a
#: witness — so the distinction has to survive into the row rather than being reconstructed later.
MEASURE_AUTHORS = ("person", "agent", "unrecorded")


#: Upper bound on units-per-pixel. Generous by three orders of magnitude for any real drawing (1e6
#: would be 1,000 km per pixel) and low enough that squaring it for an area cannot overflow.
MAX_SCALE_UNITS_PER_PX = 1e6


def valid_scale(v: Any) -> float | None:
    """A real, finite, sane units-per-pixel value — or None, which callers read as "not stated".

    **Type-based, not `float()`-based, and that is the whole point.** `float()` accepts `True` (JSON
    `true` → 1.0) and numeric strings, so a client type-confusion used to arrive as a perfectly
    plausible scale: a region carrying `"scale_units_per_px": true` was measured at 1.0 units/px
    instead of 0.01 — a **10,000x** error once the area path squares it — and the row then reported
    `scale_source: "region"`, asserting that the region had deliberately recorded a scale when the
    value was a boolean. That is precisely the claim this module exists to refuse.

    Non-finite and absurd magnitudes go the same way. `1e300` is finite and positive, so it passed
    the old `rs > 0` test, then overflowed to `inf` when squared; FastAPI encodes `inf` as `null`, so
    ONE bad region silently returned `total_cost: null` for the whole takeoff under an HTTP 200.
    A number that cannot be measured with is not a scale.
    """
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    f = float(v)
    if not math.isfinite(f) or f <= 0 or f > MAX_SCALE_UNITS_PER_PX:
        return None
    return f


def _provenance(reg: dict, scale: float) -> dict:
    """What a region records about HOW it was measured, normalised. Never guesses."""
    m = str(reg.get("method") or "").strip().lower().replace("-", "_").replace(" ", "_")
    a = str(reg.get("measured_by") or reg.get("by") or "").strip().lower()
    # A region may carry its own scale (different sheets are scaled differently); when it does not,
    # the call's scale is what was applied, and either way the row records the one actually used.
    # An unusable region scale falls back to the call's and is reported as `scale_source: "call"`, so
    # the row never claims a provenance the input did not actually carry.
    rs = valid_scale(reg.get("scale_units_per_px"))
    return {"method": m if m in MEASURE_METHODS else "unrecorded",
            "measured_by": a if a in MEASURE_AUTHORS else "unrecorded",
            "scale_applied": rs if rs else scale,
            "scale_source": "region" if rs else "call"}


def quantify(regions: list[dict], scale_units_per_px: float, *,
             unit: str = "m", overrides: dict[str, float] | None = None) -> dict[str, Any]:
    """Measure + price traced regions. `scale_units_per_px` converts pixels → real units (`unit`, from the
    calibration: known real distance ÷ its pixel distance). Each region is
    ``{category, points:[[x,y],…], label?}``; an `area` assembly bills the polygon area, a `length`
    assembly the polyline length. Returns per-region rows, per-assembly subtotals, and the grand total."""
    overrides = overrides or {}
    # The same validation as a region's. The route guards `<= 0`, which `inf` passes — and an `inf`
    # sheet scale nulls every quantity and the grand total while still returning 200. Refusing is the
    # honest outcome: a takeoff whose scale cannot be measured with has no answer to give.
    s = valid_scale(scale_units_per_px)
    if s is None:
        raise ValueError("scale_units_per_px must be a finite positive number "
                         f"(0 < scale <= {MAX_SCALE_UNITS_PER_PX:g})")
    area_unit = f"{unit}²"
    rows: list[dict] = []
    for i, reg in enumerate(regions or []):
        cat = str(reg.get("category") or "generic_area")
        spec = TAKEOFF_ASSEMBLIES.get(cat) or TAKEOFF_ASSEMBLIES["generic_area"]
        measure, default_rate, label = spec
        rate = float(overrides.get(cat, default_rate))
        pts = reg.get("points") or []
        prov = _provenance(reg, s)
        rs = prov["scale_applied"]
        if measure == "count":
            # A COUNT IS NOT SCALED. This is the whole reason it is a third measure rather than a
            # third unit: area goes as scale², length as scale¹, and a count as scale⁰ — six doors are
            # six doors whether the sheet is 1/8"=1' or 1/2"=1'. Multiplying a count by a scale would
            # produce a plausible non-integer ("7.3 doors") that prices cleanly and is wrong, and the
            # mis-scaled-plan defect this ring already fixed shows exactly how such a number travels.
            qty = _count_of(reg)
            qunit = _UNIT_LABEL["count"]
        elif measure == "length":
            qty = polyline_length_px(pts) * rs
            qunit = unit
        else:
            qty = polygon_area_px2(pts) * rs * rs
            qunit = area_unit
        cost = qty * rate
        rows.append({"index": i, "category": cat, "assembly": label, "measure": measure,
                     "label": reg.get("label"), "quantity": round(qty, 2), "unit": qunit,
                     "rate": round(rate, 2), "cost": round(cost, 2),
                     # R34-MEASURE-PROVENANCE: the number alone cannot be defended in a claim.
                     **prov})

    by_assembly: dict[str, dict] = {}
    for r in rows:
        agg = by_assembly.setdefault(r["category"], {"category": r["category"], "assembly": r["assembly"],
                                                     "measure": r["measure"], "unit": r["unit"],
                                                     "quantity": 0.0, "cost": 0.0, "count": 0})
        agg["quantity"] = round(agg["quantity"] + r["quantity"], 2)
        agg["cost"] = round(agg["cost"] + r["cost"], 2)
        agg["count"] += 1

    total = round(sum(r["cost"] for r in rows), 2)
    by_method = {m: sum(1 for r in rows if r["method"] == m) for m in MEASURE_METHODS}
    by_author = {a: sum(1 for r in rows if r["measured_by"] == a) for a in MEASURE_AUTHORS}
    unrecorded = [r["index"] for r in rows
                  if r["method"] == "unrecorded" or r["measured_by"] == "unrecorded"]
    scales_used = sorted({r["scale_applied"] for r in rows})
    return {
        "scale_units_per_px": s, "unit": unit,
        "provenance": {
            "by_method": by_method, "by_author": by_author,
            # Named, not just counted — an index list can be chased; a percentage cannot.
            "unrecorded_regions": unrecorded,
            "recorded_pct": (round(100 * (len(rows) - len(unrecorded)) / len(rows), 1)
                             if rows else 0.0),
            "scales_used": scales_used,
            # More than one scale in a single takeoff is not an error — real plan sets mix them — but
            # it is the thing a reviewer must see, because a wrong scale is a plausible number.
            "mixed_scales": len(scales_used) > 1,
            "note": ("a region that does not state its method or author is `unrecorded`, never "
                     "assumed traced-by-a-person; the number is recorded either way but its "
                     "defensibility is not"),
        },
        "region_count": len(rows), "total_cost": total,
        "regions": rows,
        "by_assembly": sorted(by_assembly.values(), key=lambda a: -a["cost"]),
        "assemblies": [{"category": k, "measure": v[0], "rate": v[1], "label": v[2],
                        "unit": _UNIT_LABEL.get(v[0])} for k, v in TAKEOFF_ASSEMBLIES.items()],
        "disclaimer": "PRELIMINARY 2D takeoff — quantities are measured off a traced drawing at the supplied "
                      "calibration and priced at benchmark assembly rates. Accuracy depends on the trace + "
                      "scale; verify against the model takeoff where a model exists.",
    }


def calibration_scale(p1: list, p2: list, real_distance: float) -> float:
    """Real units per pixel from a calibration: two clicked points + the real distance between them."""
    dx = float(p2[0]) - float(p1[0])
    dy = float(p2[1]) - float(p1[1])
    px = (dx * dx + dy * dy) ** 0.5
    if px <= 0:
        return 0.0
    return float(real_distance) / px
