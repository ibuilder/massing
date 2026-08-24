"""R41-MODEL-ALIGN — fit a yaw-only alignment to a model's footprint.

A federated model often arrives with wrong, missing or unit-mismatched georeferencing: it renders in
the right shape and the wrong orientation, so clash finds nothing and a plan is drawn askew. This
fits the rotation that puts the building back on its own axes, **without touching the source file** —
the result is a proposal, and applying it is a stored transform, never an edit to the IFC.

WHY THERE IS AN ACCEPTANCE THRESHOLD, AND WHY IT IS THE VALUABLE PART
---------------------------------------------------------------------
The geometry is one shapely call. The judgement is not.

A *true* minimum-area rectangle is not what a drafter means by "aligned". Measured on a real building
the smallest rectangle sat **37° off the building's own walls to buy 14% of area** — arithmetically
optimal and visibly broken, because the walls are what a person sees. So a fit is accepted only when
it saves at least `MIN_AREA_SAVING` of the axis-aligned area. That threshold does not buy the
*smallest* rectangle; it buys a **wall-parallel** one, by refusing the marginal cases where the two
disagree.

A building that is genuinely askew is not marginal. The case this exists for measures 54 × 78 m
against a 90.1 × 94.8 m axis-aligned box — **2.03× the true area**, a 50.7% saving, nowhere near the
threshold. The rule separates "this model is rotated" from "this model has a slightly ragged
footprint", and only the first is worth proposing to a user.

WHY YAW ONLY
------------
Roll and pitch on a building model are almost always a unit or axis-convention error rather than a
real rotation, and a fit that could express them would happily explain a Z-up/Y-up mix-up as a 90°
pitch. Refusing to represent it means such a model reports a poor yaw fit and is rejected, which
sends someone to look at the georeferencing — the actual problem — instead of accepting a plausible
correction that hides it.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

#: A fit must save at least this fraction of the axis-aligned area to be proposed. See the docstring:
#: this is the difference between "smallest" and "wall-parallel".
MIN_AREA_SAVING = 0.20

#: Fewer than this many DISTINCT plan points cannot bound an area, so there is nothing to fit.
#:
#: Four, not more. The first draft said eight, on the reasoning that a handful of points makes a shape
#: too crude to trust — and a probe against a real generated model showed the commonest case of all,
#: a simple extruded massing block, has **exactly four** unique plan vertices. The threshold would
#: have rejected the shape the feature exists to align, and would have done it silently by returning
#: None. A floor set by intuition about "enough points" was measuring the wrong thing: what matters is
#: whether the points enclose an area, and four do.
MIN_POINTS = 4


@dataclass(frozen=True)
class AlignmentFit:
    """A proposed yaw correction, and every number behind the decision."""
    yaw_deg: float
    """Rotation to APPLY to bring the model onto its own axes: the negative of the fitted angle."""
    fitted_deg: float
    """The angle the building's long axis currently sits at, in (-45, 45]."""
    obb_area: float
    aabb_area: float
    saving: float
    """Fraction of the axis-aligned area the oriented box saves, 0..1."""
    extent: tuple[float, float]
    """The building's true plan extent (long, short), metres."""
    accepted: bool
    reason: str


def _normalise(deg: float) -> float:
    """Fold an angle into (-45, 45].

    A rectangle is symmetric under 90° rotation, so 37°, 127° and -53° describe the same box. Without
    this a model at 88° would be reported as needing an 88° turn when it needs -2°, and a user shown
    that number would reasonably refuse it.
    """
    a = ((deg + 45.0) % 90.0) - 45.0
    # `% 90` maps exactly -45 to -45; the interval is closed at +45 by convention, so lift it.
    return 45.0 if math.isclose(a, -45.0, abs_tol=1e-9) else a


def fit_yaw(points, min_saving: float = MIN_AREA_SAVING) -> AlignmentFit | None:
    """Fit a yaw-only oriented box to plan `points`. None when there is nothing to fit.

    Returns a fit even when it is REJECTED, with `accepted=False` and the numbers that decided it —
    an alignment tool that answers "no" without saying how close it came is one nobody can calibrate.
    """
    from shapely.geometry import MultiPoint

    pts = np.asarray(points, dtype=float).reshape(-1, 2)
    pts = pts[np.isfinite(pts).all(axis=1)]
    if len(np.unique(pts, axis=0)) < MIN_POINTS:
        return None

    hull = MultiPoint([tuple(p) for p in pts]).convex_hull
    mrr = hull.minimum_rotated_rectangle
    coords = np.asarray(mrr.exterior.coords)[:4] if hasattr(mrr, "exterior") else None
    if coords is None or len(coords) < 4:
        return None

    edges = np.diff(np.vstack([coords, coords[:1]]), axis=0)
    lengths = np.hypot(edges[:, 0], edges[:, 1])
    long_i = int(np.argmax(lengths))
    fitted = _normalise(math.degrees(math.atan2(edges[long_i, 1], edges[long_i, 0])))

    obb_area = float(mrr.area)
    aabb_area = float((pts[:, 0].max() - pts[:, 0].min()) * (pts[:, 1].max() - pts[:, 1].min()))
    # A degenerate footprint (a line, a single column) has no axis-aligned area to save.
    if aabb_area <= 0 or obb_area <= 0:
        return None
    saving = 1.0 - (obb_area / aabb_area)

    accepted = saving >= min_saving
    reason = (f"the oriented box is {saving:.0%} smaller than the axis-aligned one, so the model is "
              f"rotated rather than ragged" if accepted else
              f"only {saving:.0%} smaller than the axis-aligned box (needs {min_saving:.0%}) — at this "
              f"margin the smallest rectangle and a wall-parallel one disagree, and the smallest one "
              f"is the wrong answer")
    return AlignmentFit(
        yaw_deg=-fitted, fitted_deg=fitted, obb_area=obb_area, aabb_area=aabb_area,
        saving=saving, extent=(float(lengths[long_i]), float(lengths[(long_i + 1) % 4])),
        accepted=accepted, reason=reason,
    )
