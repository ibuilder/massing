"""R22-OPTION-OBJECT — the option as ONE comparable record, and the axes it admits it lacks.

"Make option the primary object: geometry + unit mix + cost + carbon + IRR as one comparable record,
**so no massing is ever evaluated without its returns.**"

Premise-checked: all four engines exist and are good — `design_options.compare` (geometry, unit mix,
area), `option_carbon.compare_carbon`, `option_economics.compare_economics`, and `option_takeoff` for
cost. **Nothing joins them.** They are three separate routes, so a reader compares options by opening
three screens and reconciling them by eye — which is exactly how a massing gets evaluated without its
returns, one screen at a time.

This re-derives nothing. Each engine is called through the entry point that already owns its number,
so this cannot disagree with the screen a user might open beside it.

Two refusals, and the first is the object-level form of a bug already fixed one layer down:

1. **a missing axis is `absent`, never a zero and never a default.** `option_score` once coerced a
   missing `cost_per_sf` to 0.0 and, on a lower-is-better axis, that scored 100 — the best possible
   mark awarded for having no data. The record here states per option which of the five axes it
   actually has, so an option cannot look complete by being empty;
2. **this does not rank.** Ranking is `option_score`'s job and it has the machinery to do it
   honestly (missing criteria excluded from the pool, weights renormalised, partially-scored options
   ranked but never recommended). A second ordering computed here would be a rival answer to the same
   question, and the one thing worse than no ranking is two.

`comparable_count` is the number the ring is really about: how many options can be compared on ALL
five axes. If it is lower than the option count, some massing is being evaluated without its returns
and the record says which.
"""
from __future__ import annotations

from typing import Any

#: The five axes the ring names. Order is the order a developer reads them in.
AXES = ("geometry", "unit_mix", "cost", "carbon", "returns")

STATUS_PRESENT = "present"
STATUS_ABSENT = "absent"


def _num(v: Any) -> float | None:
    if v is None or isinstance(v, bool) or v == "":
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f or f in (float("inf"), float("-inf")) else f


def _first(*vals: float | None) -> float | None:
    """First value that is actually a number. 0.0 is a value — only None falls through."""
    for v in vals:
        if v is not None:
            return v
    return None


def _by_id(payload: dict | None, key: str = "options") -> dict[str, dict]:
    rows = (payload or {}).get(key) or []
    out = {}
    for r in rows:
        if isinstance(r, dict) and r.get("id"):
            out[str(r["id"])] = r
    return out


def join(geometry: dict | None, carbon: dict | None, economics: dict | None) -> dict[str, Any]:
    """One record per option across the five axes — pure, so it is testable without a database."""
    geo, car, eco = _by_id(geometry), _by_id(carbon), _by_id(economics)
    ids = list(geo) + [i for i in list(car) + list(eco) if i not in geo]

    rows: list[dict[str, Any]] = []
    for oid in ids:
        g, c, e = geo.get(oid, {}), car.get(oid, {}), eco.get(oid, {})
        # Every key below is the one the owning engine actually emits — verified against
        # `design_options.compare`, `option_carbon.compare_carbon` and `option_economics
        # .compare_economics`, not assumed. The first draft of this dict read `total_cost`,
        # `equity_irr` and `carbon_intensity_kgco2e_m2`; NONE of the three exists, so it reported
        # all five axes absent for a fully-populated project while its unit test — written against
        # a fixture invented alongside it — stayed green. A join is defined by the field names on
        # both sides of it, so those names are the part that must be checked against the real thing.
        axes = {
            "geometry": _num(g.get("gross_area_sf")),
            "unit_mix": _num(g.get("unit_count")),
            # economics owns cost when it has one (it carries a basis); the option card otherwise.
            "cost": _first(_num(e.get("hard_cost")), _num(g.get("hard_cost"))),
            # intensity preferred over the absolute, so options of different sizes compare.
            "carbon": _first(_num(c.get("kgco2e_per_m2")), _num(c.get("embodied_kgco2e"))),
            "returns": _num(e.get("irr_pct")),
        }
        missing = [a for a in AXES if axes[a] is None]
        rows.append({
            "id": oid, "name": g.get("name") or c.get("name") or e.get("name") or oid,
            "state": g.get("state"),
            "axes": axes,
            # Each engine labels how it got its number (declared / benchmark / derived / unlinked /
            # unavailable). Dropping that in the join would turn a benchmarked carbon figure and a
            # measured one into the same number, which is the provenance loss this record exists to
            # prevent one level up.
            "carbon_basis": c.get("basis"),
            "economics_basis": e.get("basis"),
            "axis_status": {a: (STATUS_ABSENT if axes[a] is None else STATUS_PRESENT) for a in AXES},
            "missing_axes": missing,
            "comparable": not missing,
            "note": ("" if not missing else
                     f"missing {', '.join(missing)} — this option cannot be compared with the others "
                     "on those axes. It is NOT zero on them, and nothing here substitutes a default: "
                     "a missing axis coerced to a number is how an empty option comes to look like a "
                     "good one"),
        })

    comparable = [r for r in rows if r["comparable"]]
    return {
        "options": rows, "option_count": len(rows),
        "comparable_count": len(comparable),
        "incomparable": [{"id": r["id"], "name": r["name"], "missing_axes": r["missing_axes"]}
                         for r in rows if not r["comparable"]],
        "axes": list(AXES),
        "note": ("one record per option across geometry · unit mix · cost · carbon · returns. This "
                 "does NOT rank — `option_score` owns ranking and does it honestly (missing criteria "
                 "excluded from the pool, weights renormalised, partially-scored options ranked but "
                 "never recommended). A second ordering computed here would be a rival answer to the "
                 "same question, and the one thing worse than no ranking is two."),
    }


def for_project(db, project_id: str) -> dict[str, Any]:
    """The comparable record for a project's design options, joined from the engines that own each axis."""
    from . import design_options, option_carbon, option_economics

    def _safe(fn):
        try:
            return fn(db, project_id)
        except Exception:                        # noqa: BLE001 — one absent engine must not deny the rest
            return None

    out = join(_safe(design_options.compare),
               _safe(option_carbon.compare_carbon),
               _safe(option_economics.compare_economics))
    out["project_id"] = project_id
    return out
