"""IFC-QA · export round-trip fidelity — does writing the model out and reopening it preserve the model?

The #1 openBIM complaint is silent loss on export: entities dropped, GlobalIds churned, property sets
lost when a model is serialized (edit-write) or pushed through a cross-format bridge. This compares two
opened models — or a model against its own write→reopen — on the invariants that must survive an openBIM
exchange: IFC schema, project units, the semantic entity counts by class, the GlobalId set, the storey
list, and the element property/quantity count. Pure + guarded; a malformed model degrades to a reported
skip rather than a 500.

Two verdicts are returned: `identical` (an exact match — the target for a plain re-serialization) and
`lossless` (nothing was *dropped*: the "after" is a superset — the bar a legitimate transform must clear).
"""
from __future__ import annotations

import os
import tempfile
from collections import Counter
from typing import Any


def _units(model) -> list[str]:
    """Human-readable project units from the IfcUnitAssignment (order-insensitive; sorted for comparison)."""
    out: list[str] = []
    try:
        for ua in model.by_type("IfcUnitAssignment"):
            for u in (getattr(ua, "Units", None) or []):
                name = getattr(u, "Name", None) or getattr(u, "UnitType", None) or u.is_a()
                prefix = getattr(u, "Prefix", None)
                out.append(f"{prefix or ''}{name}")
    except Exception:       # noqa: BLE001 — a malformed unit assignment shouldn't sink the whole scan
        return []
    return sorted(out)


def _property_count(model) -> int:
    """Total individual properties across all IfcPropertySet / IfcElementQuantity — the data payload that a
    lossy export tends to shed. Counts single properties and quantities, not the sets themselves."""
    n = 0
    try:
        for ps in model.by_type("IfcPropertySet"):
            n += len(getattr(ps, "HasProperties", None) or [])
        for q in model.by_type("IfcElementQuantity"):
            n += len(getattr(q, "Quantities", None) or [])
    except Exception:       # noqa: BLE001
        pass
    return n


def fingerprint(model) -> dict[str, Any]:
    """A comparable summary of the model's semantic content. `by_class` covers IfcProduct (physical +
    spatial elements); `guids` is the full IfcRoot GlobalId set; plus schema, units, storey names, the
    total entity count (incl. geometry), and the property/quantity payload size."""
    try:
        guids = sorted(g for g in (getattr(e, "GlobalId", None) for e in model.by_type("IfcRoot")) if g)
        by_class = Counter(e.is_a() for e in model.by_type("IfcProduct"))
        storeys = sorted((getattr(s, "Name", None) or "") for s in model.by_type("IfcBuildingStorey"))
        total = sum(1 for _ in model)
        return {"schema": getattr(model, "schema", None), "units": _units(model),
                "total_entities": total, "guid_count": len(guids), "guids": guids,
                "by_class": dict(by_class), "storeys": storeys, "property_count": _property_count(model),
                "ok": True}
    except Exception as e:  # noqa: BLE001 — report the failure instead of raising into the request path
        return {"ok": False, "error": type(e).__name__}


def compare(before, after) -> dict[str, Any]:
    """Diff two opened models on the export-fidelity invariants. Returns per-dimension deltas plus the two
    verdicts: `identical` (exact) and `lossless` (nothing dropped — `after` ⊇ `before`)."""
    a = fingerprint(before)
    b = fingerprint(after)
    if not (a.get("ok") and b.get("ok")):
        return {"comparable": False, "before_ok": a.get("ok", False), "after_ok": b.get("ok", False),
                "note": "one or both models could not be fingerprinted"}

    ga, gb = set(a["guids"]), set(b["guids"])
    guids_removed = sorted(ga - gb)
    guids_added = sorted(gb - ga)

    class_deltas: dict[str, dict[str, int]] = {}
    dropped_classes = False
    for cls in sorted(set(a["by_class"]) | set(b["by_class"])):
        na, nb = a["by_class"].get(cls, 0), b["by_class"].get(cls, 0)
        if na != nb:
            class_deltas[cls] = {"before": na, "after": nb, "delta": nb - na}
            if nb < na:
                dropped_classes = True

    storeys_preserved = set(a["storeys"]) <= set(b["storeys"])
    schema_same = a["schema"] == b["schema"]
    units_same = a["units"] == b["units"]
    prop_delta = b["property_count"] - a["property_count"]

    lossless = (not guids_removed and not dropped_classes and storeys_preserved
                and schema_same and prop_delta >= 0)
    identical = (lossless and not guids_added and not class_deltas and units_same
                 and a["storeys"] == b["storeys"] and prop_delta == 0
                 and a["total_entities"] == b["total_entities"])

    return {
        "comparable": True, "identical": identical, "lossless": lossless,
        "schema": {"before": a["schema"], "after": b["schema"], "same": schema_same},
        "units": {"before": a["units"], "after": b["units"], "same": units_same},
        "entities": {"before": a["total_entities"], "after": b["total_entities"]},
        "guids": {"before": a["guid_count"], "after": b["guid_count"],
                  "removed": len(guids_removed), "added": len(guids_added),
                  "removed_sample": guids_removed[:20], "added_sample": guids_added[:20]},
        "by_class": class_deltas, "dropped_classes": dropped_classes,
        "storeys": {"before": a["storeys"], "after": b["storeys"], "preserved": storeys_preserved},
        "properties": {"before": a["property_count"], "after": b["property_count"], "delta": prop_delta},
        "note": ("exact match — the export re-serializes the model with no change" if identical else
                 "no data dropped on export (superset preserved)" if lossless else
                 "EXPORT LOSS — entities, GlobalIds, storeys or properties were dropped; see the deltas"),
    }


def roundtrip(model) -> dict[str, Any]:
    """Write the model out to a temp .ifc and reopen it, then compare — a pure serialization-fidelity check
    of the write path (the same `model.write()` the edit recipes use to republish). A clean IFC write is
    expected to be `identical`; a drift here means the serializer is shedding data."""
    import ifcopenshell

    fd, path = tempfile.mkstemp(suffix=".ifc")
    os.close(fd)
    try:
        model.write(path)
        reopened = ifcopenshell.open(path)
        report = compare(model, reopened)
    except Exception as e:  # noqa: BLE001 — a write/reopen failure is itself a fidelity failure to report
        report = {"comparable": False, "identical": False, "lossless": False,
                  "error": type(e).__name__, "note": "write→reopen failed — the export path is broken"}
    finally:
        try:
            os.remove(path)
        except OSError:
            pass
    return {"method": "write→reopen serialization round-trip", **report}
