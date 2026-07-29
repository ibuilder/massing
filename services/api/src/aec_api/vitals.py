"""Project vitals — the six numbers that prove "one model" continuously.

**LOD · area · $/sf · float · IRR · health.**

The redesign audit's finding 13: ten 3D viewport controls (Fit, Grid, Section, Orbit, Snap, Units…)
are pinned to the bottom of every workspace, *including the four that have no viewport to orbit,
section or snap in*. Its prescription was to give that strip to these six instead — "the only
continuous proof of the one-model claim", and the one pillar of the prototype that never got built.

**Why this is one endpoint and not six client fetches.** The same audit's finding 03 is that the app
contradicts itself on screen — model health scored 24 in one workspace and 77 in another, the same
session. Assembling these in the browser from five engines would rebuild exactly that: five requests,
five failure modes, five chances to render a number that disagrees with the panel next to it. One
computed number per concept, one place it is defined.

Every value here is **read from the engine that already owns it** — `bim_kpi.scorecard`,
`schedule_cpm.compute`, `adjacency.summary`, the proforma returns, the cost rollup. Nothing is
recomputed locally, because a second implementation is a second answer.

`None` is a first-class result and means *"this project has not got there yet"* — no schedule, no
proforma, no spaces. It must render as an em-dash, never as `0`: a zero float reads as "critical" and
a zero IRR reads as "worthless", and both would be lies about a project that simply has not been
scheduled or underwritten. `note` carries the reason so the UI can say what it is waiting on, which
is the other half of finding 03 (never show an empty state adjacent to real data without saying what
it needs).
"""
from __future__ import annotations

from typing import Any

# Bands for the health traffic light. Shared with the scorecard rather than re-derived.
_HEALTH_GOOD = 80.0
_HEALTH_WARN = 60.0

#: LOD stages in ascending order of detail, matching `Pset_MassingLOD.Stage`.
_LOD_ORDER = ["100", "200", "300", "350", "400", "500"]

_SF_PER_M2 = 10.7639


def _safe(fn, *a, **kw):
    """Run an engine, or return None if this project has not got that far.

    A vitals strip must never take the page down with it. An engine that raises because a project
    has no schedule is answering the question — "no float yet" — not failing.
    """
    try:
        return fn(*a, **kw)
    except Exception:                                    # noqa: BLE001 - any engine gap means "not yet"
        return None


def _lod(lod_counts: dict[str, Any] | None) -> tuple[str | None, str | None]:
    """The project's LOD as a single label: the **lowest** stage that any element has reached.

    Lowest, not the average or the mode, and that is the load-bearing choice. A set is only as
    documented as its least-documented element — quoting LOD 400 because most walls are modelled to
    400 while the connections are still at 200 is how a "LOD 400 set" reaches a fabricator and stops
    being buildable. The weakest link is the honest number.
    """
    if not lod_counts:
        return None, "no model loaded"
    counts = lod_counts.get("counts") or {}
    total = int(lod_counts.get("total") or 0)
    if not total:
        return None, "no elements"
    unset = int(counts.get("UNSET") or 0)
    if unset:
        return None, f"{unset} of {total} elements have no LOD stage"
    present = [s for s in _LOD_ORDER if int(counts.get(s) or 0) > 0]
    if not present:
        return None, "no LOD stage recorded"
    return present[0], None


def _health(score: dict[str, Any] | None) -> tuple[float | None, str | None, str | None]:
    """Model health as one percentage plus its band — `scorecard()['summary']['health_pct']`.

    Read from the summary the scorecard already computes, never re-derived from the categories. The
    first draft of this looked for `score` / `overall` / `percent`, none of which exist, so the cell
    would have rendered an em-dash **forever** while looking like a working feature. A vital that can
    never populate is worse than a missing one; `test_vitals` now pins the real key.

    `scored == 0` (every category n/a) is genuinely unknown → `None`. A `health_pct` of **0.0** with
    categories scored is a real, alarming number and must render as 0, not as "no data" — the
    difference between "we measured, it is bad" and "we have not measured".
    """
    if not score:
        return None, None, "no model data"
    summary = score.get("summary") or {}
    if not summary.get("scored"):
        return None, None, "no KPI category has inputs yet"
    pct = summary.get("health_pct")
    if pct is None:
        return None, None, "scorecard summary has no health_pct"
    pct = round(float(pct), 1)
    band = "good" if pct >= _HEALTH_GOOD else ("warn" if pct >= _HEALTH_WARN else "poor")
    return pct, band, None


def _float_days(cpm: dict[str, Any] | None) -> tuple[float | None, str | None]:
    """Total float on the critical path, in days. Zero here is REAL and means zero slack."""
    if not cpm:
        return None, "no schedule"
    acts = cpm.get("activities") or cpm.get("tasks") or []
    if not acts:
        return None, "no activities scheduled"
    floats = [a.get("total_float") for a in acts if isinstance(a.get("total_float"), (int, float))]
    if not floats:
        return None, "schedule has no computed float"
    return round(min(floats), 1), None


def _area(space_summary: dict[str, Any] | None) -> tuple[float | None, str | None]:
    """Gross area in ft², from the space engine that already measures it."""
    if not space_summary:
        return None, "no spaces"
    sf = space_summary.get("total_area_sf")
    if sf is None:
        m2 = space_summary.get("total_area_m2")
        sf = (float(m2) * _SF_PER_M2) if m2 is not None else None
    if not sf:
        return None, "no space areas recorded"
    return round(float(sf), 0), None


def _cost_per_sf(budget: float | None, area_sf: float | None) -> tuple[float | None, str | None]:
    """$/ft² — the one derived figure here, and derived from the two above rather than stored.

    Storing it would create a third number that can disagree with its own inputs, which is the
    failure this module exists to prevent.
    """
    if budget is None:
        return None, "no budget"
    if not area_sf:
        return None, "no area to divide by"
    return round(float(budget) / float(area_sf), 2), None


def vitals(db, pid: str, *, lod_counts=None, scorecard=None, cpm=None,
           spaces=None, budget=None, irr=None) -> dict[str, Any]:
    """The six vitals for one project.

    Engine results are injected rather than imported so this stays a pure assembler: the router
    supplies each engine's own output, which keeps this module free of the import graph and makes it
    trivially testable without a database.
    """
    lod_val, lod_note = _lod(lod_counts)
    health_val, health_band, health_note = _health(scorecard)
    float_val, float_note = _float_days(cpm)
    area_val, area_note = _area(spaces)
    psf_val, psf_note = _cost_per_sf(budget, area_val)

    irr_val = round(float(irr) * 100, 1) if isinstance(irr, (int, float)) else None
    irr_note = None if irr_val is not None else "no solved scenario"

    return {
        "lod":    {"value": lod_val,    "unit": "LOD",   "note": lod_note},
        "area":   {"value": area_val,   "unit": "ft²",   "note": area_note},
        "cost_sf": {"value": psf_val,   "unit": "$/ft²", "note": psf_note},
        "float":  {"value": float_val,  "unit": "days",  "note": float_note},
        "irr":    {"value": irr_val,    "unit": "%",     "note": irr_note},
        "health": {"value": health_val, "unit": "%",     "note": health_note, "band": health_band},
        # The order the strip renders in: model → money → time → return → confidence, which is the
        # order somebody actually asks the questions.
        "order": ["lod", "area", "cost_sf", "float", "irr", "health"],
    }
