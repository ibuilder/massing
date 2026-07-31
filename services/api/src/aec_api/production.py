"""R22-PRODUCTION — field-installed quantity reconciled against the **model** takeoff.

Both halves of this have existed for a long time and have never been joined:

* the **model** side — `aec_data.qto.takeoff()` returns per-element rows carrying `cost_code`, a
  `unit` naming a *dimension* (`area` / `volume` / `length` / `count`), and the measured quantities;
* the **field** side — the `production_quantity` module records what a crew actually installed, with
  its own `cost_code`, `quantity` and `unit`.

What did not exist is the join. `prod_actuals.analyze()` compares an installed *rate* against a
**planned rate the caller supplies in the request body** (`routers/research.py:59`), so "are we ahead
or behind" has always been answered against a number somebody typed, never against the model. And the
structural reason it stayed unbuilt is visible in the two modules: `production_quantity` carries
`cost_code` — the model's join key — and is read only by `pricing.py`, `carbon.py` and
`unit_rate_memory.py`; the module the production loop actually consumes, `progress_actual`, has **no
`cost_code` field at all**. The loop reads the module that cannot join, and the module that can join
is read only by cost consumers.

## What this refuses to do, and why each refusal is load-bearing

**A percent-complete is the most quotable number in construction**, which makes a wrong one expensive:
it drives a pay application. Every refusal below exists because the alternative is a plausible figure.

1. **Units are two different vocabularies and are never silently equated.** The model's `unit` is a
   *dimension* (`area`); the field's is a *trade unit* (`m²`, `SF`, `EA`). Dividing one by the other
   because both say "80" is the [[qto-measured-area]] mistake in a new place. A field unit is converted
   only through an explicit table, the factor is **reported**, and an unrecognised or wrong-dimension
   unit yields `unit_mismatch` with no percentage rather than a number.

2. **Over-installation is reported, never clamped.** >100% means over-installation, a bad join or a
   wrong model — all worth chasing, and `min(pct, 100)` hides all three behind a healthy-looking 100%.

3. **An unmapped takeoff is stated, not returned as an empty success.** `qto.takeoff()` sets
   `cost_code` to `None` for every element when no cost map is loaded. Reconciling that yields zero
   matched lines — which reads as "nothing to report" when it means "the model was never coded". That
   is the confident-empty this repo keeps finding, so `model_uncoded` counts it and `basis` says so.

4. **Field quantities against codes the model does not have are NAMED, not counted.** A count says
   *something* is unmatched; a name says *which*, and only the second can be fixed.

Pure arithmetic over rows the caller supplies — no model parsing here, so it is deterministic and
unit-testable. `aec_api` may import `aec_data`, never the reverse; this module imports neither and
takes the takeoff rows as data.
"""
from __future__ import annotations

from typing import Any

#: The dimensions `qto.takeoff()` can bill in — its `unit` field names one of these, not a trade unit.
DIMENSIONS = ("length", "area", "volume", "count", "weight")

#: Trade unit → (dimension, factor to the model's SI unit). `qto` meshes in **metres**, so area is m²
#: and volume m³. A unit absent from this table is refused rather than guessed: silently treating an
#: unknown symbol as 1.0 is how a 10.76× area error (SF read as m²) reaches a pay application.
UNIT_FACTORS: dict[str, tuple[str, float]] = {
    # length
    "m": ("length", 1.0), "lm": ("length", 1.0), "lf": ("length", 0.3048),
    "ft": ("length", 0.3048), "'": ("length", 0.3048), "in": ("length", 0.0254),
    "mm": ("length", 0.001), "cm": ("length", 0.01),
    # area
    "m2": ("area", 1.0), "m²": ("area", 1.0), "sm": ("area", 1.0), "sqm": ("area", 1.0),
    "sf": ("area", 0.09290304), "sqft": ("area", 0.09290304), "ft2": ("area", 0.09290304),
    "ft²": ("area", 0.09290304), "sy": ("area", 0.83612736),
    # volume
    "m3": ("volume", 1.0), "m³": ("volume", 1.0), "cm3": ("volume", 1.0), "cum": ("volume", 1.0),
    "cy": ("volume", 0.764554857984), "cf": ("volume", 0.028316846592),
    "ft3": ("volume", 0.028316846592), "ft³": ("volume", 0.028316846592),
    # count
    "ea": ("count", 1.0), "each": ("count", 1.0), "no": ("count", 1.0), "nr": ("count", 1.0),
    "pc": ("count", 1.0), "pcs": ("count", 1.0), "unit": ("count", 1.0),
    # weight
    "kg": ("weight", 1.0), "t": ("weight", 1000.0), "tonne": ("weight", 1000.0),
    "lb": ("weight", 0.45359237), "lbs": ("weight", 0.45359237), "ton": ("weight", 907.18474),
}

STATUS_OK = "reconciled"
STATUS_OVER = "over_installed"
STATUS_NOT_STARTED = "not_started"
STATUS_UNIT_MISMATCH = "unit_mismatch"
STATUS_UNMATCHED = "unmatched_in_model"

#: What each status asserts, carried in the payload so a reader does not have to infer it.
STATUS_MEANING = {
    STATUS_OK: "field quantity and model quantity are in the same dimension and comparable",
    STATUS_OVER: "more was installed than the model contains — over-installation, a bad join, or a "
                 "stale model. NOT clamped to 100%.",
    STATUS_NOT_STARTED: "the model carries this cost code and NO field quantity has been recorded "
                        "against it — absence of a record, not a measured zero",
    STATUS_UNIT_MISMATCH: "the field unit does not resolve to the dimension the model bills this "
                          "code in — no percentage is emitted, because any number here would be wrong",
    STATUS_UNMATCHED: "a field quantity was recorded against a cost code the model does not contain",
}


def _num(v: Any) -> float | None:
    """Strictly numeric. `bool` is rejected before `int` — `True` is not a quantity of 1, and
    `float("nan")`/`inf` are not measurements."""
    if isinstance(v, bool) or v in (None, ""):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):
        return None
    return f


def normalise_unit(unit: Any) -> tuple[str, float] | None:
    """A trade unit → (dimension, factor to SI), or None when it is not a unit we recognise.

    Returning None rather than a default is the point: an unrecognised unit means we do not know what
    was measured, and a reconciliation that assumes 1.0 produces a number indistinguishable from a
    correct one."""
    if not isinstance(unit, str):
        return None
    u = unit.strip().lower().replace(" ", "")
    u = u.rstrip(".")
    return UNIT_FACTORS.get(u)


def _model_quantity(row: dict) -> float | None:
    """The quantity a takeoff row contributes, read from the dimension its own `unit` names.

    `count` is the one that is not a measurement: an element billed per-each contributes exactly one
    element, never a measured extent."""
    dim = str(row.get("unit") or "").strip().lower()
    if dim == "count":
        return 1.0
    if dim in DIMENSIONS:
        return _num(row.get(dim))
    return None


def model_by_code(takeoff_rows: list[dict]) -> tuple[dict[str, dict], dict[str, Any]]:
    """Aggregate `qto.takeoff()` rows into per-cost-code modelled quantities.

    Also reports what could NOT be aggregated, because an uncoded or unquantified model is the
    difference between "nothing is installed" and "we never measured it"."""
    by: dict[str, dict] = {}
    uncoded = 0
    unquantified: list[str] = []
    for r in takeoff_rows or []:
        code = r.get("cost_code")
        if not code:
            uncoded += 1
            continue
        code = str(code)
        qty = _model_quantity(r)
        slot = by.setdefault(code, {"cost_code": code, "dimension": str(r.get("unit") or "").lower(),
                                    "modeled": 0.0, "elements": 0,
                                    "description": r.get("cost_description")})
        slot["elements"] += 1
        if qty is None:
            if len(unquantified) < 50:
                unquantified.append(str(r.get("guid") or "?"))
            continue
        slot["modeled"] += qty
    for slot in by.values():
        slot["modeled"] = round(slot["modeled"], 4)
    return by, {"uncoded_elements": uncoded, "unquantified_elements": len(unquantified),
                "unquantified_sample": unquantified[:10]}


def reconcile(takeoff_rows: list[dict], field_rows: list[dict]) -> dict[str, Any]:
    """Installed-vs-modelled per cost code.

    `takeoff_rows` are `aec_data.qto.takeoff()` output. `field_rows` are `production_quantity` records
    (`{cost_code, quantity, unit, description?}`) — the module that carries the model's join key."""
    model, model_notes = model_by_code(takeoff_rows)

    field: dict[str, dict] = {}
    unusable: list[dict] = []
    for r in field_rows or []:
        d = r.get("data") or r
        code = d.get("cost_code")
        qty = _num(d.get("quantity"))
        if not code or qty is None:
            unusable.append({"cost_code": str(code) if code else None,
                             "reason": "no cost code" if not code else "quantity is not a number"})
            continue
        field.setdefault(str(code), []).append({"qty": qty, "unit": d.get("unit")})

    lines: list[dict] = []
    for code in sorted(set(model) | set(field)):
        m = model.get(code)
        entries = field.get(code, [])

        if m is None:
            installed = sum(e["qty"] for e in entries)
            lines.append({"cost_code": code, "status": STATUS_UNMATCHED,
                          "installed_raw": round(installed, 4), "modeled": None,
                          "pct_complete": None, "remaining": None,
                          "units_seen": sorted({str(e["unit"]) for e in entries if e["unit"]})})
            continue

        dim = m["dimension"]
        installed = 0.0
        converted: list[dict] = []
        mismatched: list[str] = []
        for e in entries:
            got = normalise_unit(e["unit"])
            if got is None or got[0] != dim:
                mismatched.append(str(e["unit"]))
                continue
            installed += e["qty"] * got[1]
            converted.append({"unit": str(e["unit"]), "factor": got[1]})

        line = {"cost_code": code, "description": m["description"], "dimension": dim,
                "modeled": m["modeled"], "elements": m["elements"],
                "conversions": converted}

        if mismatched:
            # A partial answer here would be worse than none: some rows counted, some silently
            # dropped, and a percentage that looks complete. Refuse the whole line and name the units.
            line.update({"status": STATUS_UNIT_MISMATCH, "installed": None, "pct_complete": None,
                         "remaining": None, "unmatched_units": sorted(set(mismatched)),
                         "expected_dimension": dim})
            lines.append(line)
            continue

        if not entries:
            line.update({"status": STATUS_NOT_STARTED, "installed": None, "pct_complete": None,
                         "remaining": m["modeled"]})
            lines.append(line)
            continue

        installed = round(installed, 4)
        pct = round(100.0 * installed / m["modeled"], 2) if m["modeled"] else None
        line.update({"status": STATUS_OVER if pct is not None and pct > 100.0 else STATUS_OK,
                     "installed": installed, "pct_complete": pct,
                     "remaining": round(m["modeled"] - installed, 4)})
        lines.append(line)

    counts: dict[str, int] = {}
    for ln in lines:
        counts[ln["status"]] = counts.get(ln["status"], 0) + 1

    comparable = [ln for ln in lines if ln["status"] in (STATUS_OK, STATUS_OVER)]
    # Overall completion is weighted by MODELLED quantity, but only across lines that are actually
    # comparable — and `covered_pct` says how much of the model that is. A 97% complete computed over
    # 3% of the model is the number this pair of fields exists to stop anybody quoting.
    total_modeled = sum(ln["modeled"] for ln in comparable)
    total_installed = sum(ln["installed"] for ln in comparable)
    all_modeled = sum(m["modeled"] for m in model.values())

    return {
        "lines": lines,
        "by_status": counts,
        "status_meaning": STATUS_MEANING,
        "overall": {
            "pct_complete": round(100.0 * total_installed / total_modeled, 2) if total_modeled else None,
            "modeled": round(total_modeled, 4),
            "installed": round(total_installed, 4),
            "covered_pct": round(100.0 * total_modeled / all_modeled, 2) if all_modeled else 0.0,
            "note": "weighted by modelled quantity across COMPARABLE lines only; `covered_pct` is "
                    "how much of the coded model those lines represent",
        },
        "model": {"cost_codes": len(model), **model_notes},
        "unusable_field_rows": unusable,
        "basis": ("reconciled against the model takeoff by cost code"
                  if model else
                  "NO cost-coded model quantities — the takeoff carries no cost map, so nothing "
                  "could be reconciled. This is an absent basis, not 0% complete."),
    }
