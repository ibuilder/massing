"""5D — carry cost in the IFC itself, using the schema's own relationships.

The takeoff has always produced good rows and left them **outside** the model. That is the thing that
stops it being 5D: a cost that lives in a sidecar cannot travel with the file, cannot be read by
another tool, and drifts the moment the model is re-exported. Our first non-negotiable is that IFC is
the source of truth, and a cost sitting beside the IFC is not in it.

IFC already has the relationships for this, so nothing bespoke is needed:

* **`IfcCostItem`** — one priced line. Its `CostValues` carry the rate; its `CostQuantities` carry the
  measured quantity the rate applies to.
* **`IfcRelAssignsToControl`** — binds the elements a cost item prices. This is the actual 5D link:
  element → cost, by GlobalId, in the model.
* **`IfcCostSchedule`** — groups the items into an estimate, so a file can carry several (bid, GMP,
  as-built) without them merging.

The equivalent 4D link is `IfcRelAssignsToProcess` (products → `IfcTask`), which `schedule.from_ifc`
already reads. Writing cost the same way makes both dimensions the same kind of fact rather than two
different sidecars.

**A quantity must state its basis.** "120 m²" is not a measurement — *"120 m², wall net side area,
from Qto_WallBaseQuantities.NetSideArea"* is. Two estimators measuring the same wall gross and net
disagree by the openings, and a number with no stated basis gives nobody a way to find out which
happened. So every quantity written here carries the name it was measured under.
"""
from __future__ import annotations

from typing import Any

import ifcopenshell
import ifcopenshell.guid

# Which IfcQuantity subtype and unit label each basis uses. The `meaning` is written into the model
# as the quantity's Description, so the basis survives export rather than living in our docs.
QUANTITY_KINDS: dict[str, dict[str, str]] = {
    "length": {"entity": "IfcQuantityLength", "attr": "LengthValue", "unit": "m",
               "meaning": "Length along the element's run"},
    "area": {"entity": "IfcQuantityArea", "attr": "AreaValue", "unit": "m2",
             "meaning": "Net surface area, openings deducted"},
    "volume": {"entity": "IfcQuantityVolume", "attr": "VolumeValue", "unit": "m3",
               "meaning": "Net solid volume, openings deducted"},
    "weight": {"entity": "IfcQuantityWeight", "attr": "WeightValue", "unit": "kg",
               "meaning": "Net weight"},
    "count": {"entity": "IfcQuantityCount", "attr": "CountValue", "unit": "each",
              "meaning": "Number of occurrences"},
}

MAX_COST_ITEMS = 20_000


def _owner(model):
    hist = model.by_type("IfcOwnerHistory")
    return hist[0] if hist else None


def _quantity(model, basis: str, value: float, name: str):
    kind = QUANTITY_KINDS[basis]
    q = model.create_entity(kind["entity"], Name=name, Description=kind["meaning"])
    setattr(q, kind["attr"], float(value))
    return q


def write_cost_schedule(model: ifcopenshell.file, lines: list[dict[str, Any]],
                        name: str = "Estimate", predefined_type: str = "BUDGET"):
    """Write an `IfcCostSchedule` of `IfcCostItem`s, each bound to the elements it prices.

    `lines` are dicts of ``{code, description, unit_cost, basis, quantity, guids}``. A line whose
    GlobalIds are not in the model is written **without** an assignment rather than skipped — the cost
    is still real, and silently dropping it would make an estimate quietly cheaper than the project.
    Unmatched GlobalIds are returned so the caller can report them instead of discovering the gap in a
    bid.
    """
    owner = _owner(model)
    by_guid = {}
    for e in model.by_type("IfcProduct"):
        gid = getattr(e, "GlobalId", None)
        if gid:
            by_guid[gid] = e

    schedule = model.create_entity(
        "IfcCostSchedule", GlobalId=ifcopenshell.guid.new(), OwnerHistory=owner,
        Name=name, PredefinedType=predefined_type)

    items, missing = [], []
    for ln in lines[:MAX_COST_ITEMS]:
        # An ABSENT basis defaults to `count` — a lump-sum line genuinely is "one of these". An
        # EMPTY basis does not: that is a caller who tried to state one and failed, and letting it
        # become `count` would silently turn 57.6 m² into a count of 57.6.
        raw_basis = ln.get("basis")
        basis = "count" if raw_basis is None else str(raw_basis).strip().lower()
        if basis not in QUANTITY_KINDS:
            raise ValueError(f"basis must be one of {sorted(QUANTITY_KINDS)}, got {basis!r}")
        item = model.create_entity(
            "IfcCostItem", GlobalId=ifcopenshell.guid.new(), OwnerHistory=owner,
            Name=str(ln.get("description") or ln.get("code") or "Cost item"),
            Identification=str(ln.get("code") or ""))
        rate = ln.get("unit_cost")
        if rate is not None:
            # AppliedValue is an IfcAppliedValueSelect, so the rate must be a WRAPPED measure rather
            # than a bare float — IfcMonetaryMeasure is the one that says "this number is money"
            item.CostValues = [model.create_entity(
                "IfcCostValue", Name="Unit rate",
                AppliedValue=model.create_entity("IfcMonetaryMeasure", float(rate)))]
        qty = ln.get("quantity")
        if qty is not None:
            item.CostQuantities = [_quantity(model, basis, qty,
                                             str(ln.get("code") or "quantity"))]
        items.append(item)

        guids = list(ln.get("guids") or [])
        found = [by_guid[g] for g in guids if g in by_guid]
        missing.extend(g for g in guids if g not in by_guid)
        if found:
            # THE 5D LINK: element → cost item, by GlobalId, inside the model
            model.create_entity(
                "IfcRelAssignsToControl", GlobalId=ifcopenshell.guid.new(), OwnerHistory=owner,
                RelatedObjects=found, RelatingControl=item)

    if items:
        model.create_entity(
            "IfcRelAssignsToControl", GlobalId=ifcopenshell.guid.new(), OwnerHistory=owner,
            RelatedObjects=items, RelatingControl=schedule)

    return {"schedule": schedule, "items": items,
            "written": len(items), "missing_guids": sorted(set(missing))}


def read_cost_schedule(model: ifcopenshell.file) -> list[dict[str, Any]]:
    """Read cost items back out, with the elements each one prices and the basis it was measured on.

    The round trip is the point. A cost written into the model that cannot be read back is a sidecar
    with extra steps.
    """
    # cost items assigned to a schedule are the estimate; anything else is left alone
    out: list[dict[str, Any]] = []
    for item in model.by_type("IfcCostItem"):
        guids: list[str] = []
        for rel in model.by_type("IfcRelAssignsToControl"):
            if rel.RelatingControl == item:
                guids.extend(getattr(o, "GlobalId", None) for o in (rel.RelatedObjects or []))
        rate = None
        for cv in (item.CostValues or []):
            applied = getattr(cv, "AppliedValue", None)
            if applied is None:
                continue
            # AppliedValue is a SELECT: the rate arrives as a WRAPPED measure (IfcMonetaryMeasure),
            # so the number lives on `.wrappedValue`. Reading the wrapper itself as a float is what
            # made this silently return None — a rate that reads as "no rate" is worse than an error.
            raw = getattr(applied, "wrappedValue", applied)
            try:
                rate = float(raw)
            except (TypeError, ValueError):
                rate = None
            break
        qty, basis, meaning = None, None, None
        for q in (item.CostQuantities or []):
            for b, kind in QUANTITY_KINDS.items():
                if q.is_a(kind["entity"]):
                    qty = getattr(q, kind["attr"], None)
                    basis, meaning = b, q.Description or kind["meaning"]
                    break
            if basis:
                break
        out.append({"code": item.Identification or "", "description": item.Name or "",
                    "unit_cost": rate, "quantity": qty, "basis": basis,
                    "basis_meaning": meaning,
                    "guids": sorted(g for g in guids if g)})
    return out
