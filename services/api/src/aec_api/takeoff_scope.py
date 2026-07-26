"""R27-LAYOUT ② — a takeoff belongs to the view it was traced on.

`takeoff2d.quantify` takes traced regions and one `scale_units_per_px` for the whole sheet. That is
correct for a sheet holding a single drawing and quietly wrong for every other sheet: a plan at 1:100
and a detail at 1:20 sit side by side on the same page, and one scale applied to both prices the
detail five times over. Nothing checked that a traced polygon was even *on* a drawing rather than in
the titleblock.

`sheet_layout.sheet_regions` (v0.3.702) now reports each viewport's rectangle **and** the exact
page←world transform it was drawn with. This module joins the two: it decides which viewport a trace
belongs to, and — where the sheet was authored here — checks the operator's calibration against the
scale the sheet was actually drawn at.

**Pixels are not points, and pretending otherwise is the failure mode.** Traces come from a rendered
raster in **screen pixels**; viewport rectangles are in **PDF points**. Converting between them needs
the render factor, and it is the caller's — it depends on the zoom or DPI the sheet was rasterised at.
Without it nothing can be placed, so this refuses to scope rather than assuming 1:1, which would put
every trace in the top-left corner of the page and report it confidently.

**Three outcomes a trace can have, and only one of them is priceable.**

*Inside exactly one viewport* — scoped, and its scale is known.

*Outside every viewport* — the trace is on the titleblock, a legend, or the margin. It is reported as
`unscoped`, never quietly priced: a quantity measured off a legend is not a quantity.

*Straddling two viewports* — `ambiguous`. Two different drawing scales apply to one polygon, so there
is no single correct number, and picking either is a coin toss presented as a measurement.
"""
from __future__ import annotations

from typing import Any

#: Fraction of a trace's points that must fall inside a viewport for it to count as belonging there.
#: Not 1.0: a hand-traced polygon routinely nicks a viewport border by a pixel, and failing an
#: otherwise-clean trace on one stray vertex would make the check something operators route around.
INSIDE_RATIO = 0.9

#: Relative disagreement between the operator's calibration and the sheet's authored scale that is
#: worth reporting. Below this is measurement noise from clicking two points on a raster.
CALIBRATION_TOL = 0.02


def _rect_contains(rect: tuple[float, float, float, float], x: float, y: float) -> bool:
    rx, ry, rw, rh = rect
    return rx <= x <= rx + rw and ry <= y <= ry + rh


def _viewports(layout: dict[str, Any]) -> list[dict[str, Any]]:
    return [r for r in (layout.get("regions") or []) if r.get("kind") == "viewport"]


def scope(regions: list[dict[str, Any]], layout: dict[str, Any], *,
          px_per_point: float | None = None) -> dict[str, Any]:
    """Assign each traced region to the viewport it was drawn on.

    `regions` are `takeoff2d`-shaped (`{category, points:[[x,y],…]}`) in **screen pixels**; `layout` is
    a `sheet_layout.sheet_regions` result in **page points**. `px_per_point` is how many pixels one
    page point occupied when the sheet was rasterised — without it, the two coordinate spaces cannot
    be related and every trace is `unknown`.
    """
    vps = _viewports(layout)
    out: list[dict[str, Any]] = []

    if not px_per_point or px_per_point <= 0:
        for i, _ in enumerate(regions or []):
            out.append({"index": i, "scope": "unknown", "viewport": None, "scale_denom": None,
                        "detail": "no px_per_point supplied — traces are in screen pixels and "
                                  "viewports in page points, so nothing can be placed. Assuming 1:1 "
                                  "would put every trace in the page corner and report it "
                                  "confidently."})
        return _summarise(out, len(vps), scoped_possible=False)

    for i, reg in enumerate(regions or []):
        pts = reg.get("points") or []
        if not pts:
            out.append({"index": i, "scope": "unknown", "viewport": None, "scale_denom": None,
                        "detail": "the trace has no points"})
            continue
        # Count hits per viewport, converting each traced pixel back to page points.
        hits: list[tuple[int, int]] = []
        for v in vps:
            rect = tuple(float(c) for c in v["rect"])          # type: ignore[assignment]
            n = sum(1 for p in pts
                    if _rect_contains(rect, float(p[0]) / px_per_point, float(p[1]) / px_per_point))
            if n:
                hits.append((v.get("index", -1), n))
        total = len(pts)
        strong = [(vi, n) for vi, n in hits if n / total >= INSIDE_RATIO]
        if len(strong) == 1:
            vi = strong[0][0]
            v = next((x for x in vps if x.get("index") == vi), None)
            out.append({"index": i, "scope": "scoped", "viewport": vi,
                        "viewport_label": (v or {}).get("label"),
                        "scale_denom": (v or {}).get("scale_denom"),
                        "measurable": bool((v or {}).get("measurable")),
                        "detail": f"inside “{(v or {}).get('label')}”"})
        elif len(hits) > 1:
            # Two drawing scales apply to one polygon. There is no single correct number here, and
            # choosing one would be a coin toss presented as a measurement.
            out.append({"index": i, "scope": "ambiguous", "viewport": None, "scale_denom": None,
                        "candidates": sorted(vi for vi, _ in hits),
                        "detail": "the trace crosses more than one viewport, and each has its own "
                                  "scale — no single quantity is correct"})
        else:
            out.append({"index": i, "scope": "unscoped", "viewport": None, "scale_denom": None,
                        "detail": "the trace is not on any drawing — titleblock, legend or margin. "
                                  "A quantity measured off a legend is not a quantity."})
    return _summarise(out, len(vps), scoped_possible=True)


def _summarise(rows: list[dict[str, Any]], viewport_count: int, *, scoped_possible: bool) -> dict:
    kinds = {k: [r["index"] for r in rows if r["scope"] == k]
             for k in ("scoped", "unscoped", "ambiguous", "unknown")}
    return {
        "regions": rows,
        "viewport_count": viewport_count,
        "scoped": kinds["scoped"], "unscoped": kinds["unscoped"],
        "ambiguous": kinds["ambiguous"], "unknown": kinds["unknown"],
        # Only traces that land on exactly one drawing may be priced. Stated as a count so a caller
        # cannot mistake "nothing was scoped" for "everything was fine".
        "priceable": len(kinds["scoped"]),
        "all_scoped": bool(rows) and len(kinds["scoped"]) == len(rows),
        "note": ("Only `scoped` traces may be priced. `unscoped` means the trace is not on a drawing "
                 "at all; `ambiguous` means it crosses viewports with different scales, so no single "
                 "quantity is correct; `unknown` means the check could not run — none of the three is "
                 "a pass." + ("" if scoped_possible else
                              " This run supplied no px_per_point, so NOTHING was checked.")),
    }


def check_calibration(user_scale_units_per_px: float, scale_denom: int | None, *,
                      px_per_point: float | None = None) -> dict[str, Any]:
    """Compare an operator's two-click calibration against the scale the sheet was authored at.

    On a sheet this platform drew, the scale is not a thing to be measured — it is a thing we already
    know. A calibration that disagrees means the operator clicked the wrong two points, or is working
    on a different drawing than they think. Reporting the disagreement is the whole value; **the
    authored scale is not silently substituted**, because the operator may be right that the raster
    was scaled on the way in, and overriding their measurement without saying so would hide that.
    """
    if not scale_denom:
        return {"checked": False, "agrees": None,
                "detail": "the viewport has no fixed paper scale (fit-to-rect), so there is no "
                          "authored number to check against"}
    if not px_per_point or px_per_point <= 0:
        return {"checked": False, "agrees": None,
                "detail": "no px_per_point supplied — the operator's pixels and the sheet's points "
                          "cannot be related, so no comparison is possible"}
    # 1 page point = 0.352778 mm on paper; at 1:N that is 0.352778*N mm of world = /1000 m.
    expected_units_per_px = (0.352778 * float(scale_denom) / 1000.0) / float(px_per_point)
    got = float(user_scale_units_per_px)
    if expected_units_per_px <= 0:
        return {"checked": False, "agrees": None, "detail": "authored scale resolves to zero"}
    rel = abs(got - expected_units_per_px) / expected_units_per_px
    return {
        "checked": True,
        "agrees": rel <= CALIBRATION_TOL,
        "expected_units_per_px": round(expected_units_per_px, 9),
        "calibrated_units_per_px": round(got, 9),
        "relative_error": round(rel, 6),
        "detail": ("the calibration matches the scale this sheet was drawn at"
                   if rel <= CALIBRATION_TOL else
                   f"the calibration is off by {rel * 100:.1f}% from the sheet's authored 1:"
                   f"{scale_denom} — check which drawing was clicked. The authored scale is NOT "
                   "substituted automatically: the raster may genuinely have been rescaled on import, "
                   "and overriding a measurement without saying so would hide that."),
    }


def scope_annotations(annotations: list[dict[str, Any]], layout: dict[str, Any], *,
                      px_per_point: float | None = None) -> dict[str, Any]:
    """R27-LAYOUT ③ — attach each note, keynote or revision cloud to the view it governs.

    A general note that applies to the plan and a note that applies to the section sit centimetres
    apart on the same sheet, and page number is not enough to tell them apart. Anything anchored to a
    *sheet* rather than a *view* has to be re-read by a human to know what it is about, which is what
    keeps received drawings out of every downstream engine.

    **This is deliberately not a new engine.** An annotation and a traced polygon pose the identical
    question — which drawing is this on — so this maps annotations onto the same region shape and
    calls `scope`. A point annotation is a one-point region and falls out of the existing ratio test
    without a special case. Writing a second placement routine would give two answers to one question
    and guarantee they drift.

    Each annotation is ``{id?, kind?, x, y}`` or ``{id?, kind?, points:[[x,y],…]}`` (a cloud), in
    **screen pixels**. An annotation over the titleblock comes back `unscoped` — which is correct and
    common: a drawing-number stamp governs the sheet, not a view.
    """
    regions: list[dict[str, Any]] = []
    for a in (annotations or []):
        pts = a.get("points")
        if not pts and a.get("x") is not None and a.get("y") is not None:
            pts = [[a["x"], a["y"]]]
        regions.append({"category": a.get("kind") or "note", "points": pts or []})
    res = scope(regions, layout, px_per_point=px_per_point)
    for row, a in zip(res["regions"], annotations or [], strict=False):
        row["annotation_id"] = a.get("id")
        row["kind"] = a.get("kind") or "note"
    res["note"] = ("Each annotation is attached to the view it governs, not to the sheet. `unscoped` "
                   "is a legitimate answer, not a failure: a titleblock stamp or a sheet-wide note "
                   "governs the sheet rather than any one view. " + res["note"])
    return res
