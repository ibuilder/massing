"""MEP-EQUIP (R16) — derive the **procurement equipment schedule** straight from the IFC. Where ASSET-REG
(`model_assets.py`) lists every serviceable asset one-per-GUID for the FM register, this **groups equipment
by (class, type)** into buyout line-items with a **quantity** and a few representative spec values pulled
from the model's Psets — the RFQ package a GC/PM sends out, built with **no doc-scanning because we own the
model**. Deterministic + pure over an opened model.

Phase-2 (SPEC-CONFLICT) will cross-validate each line's Pset values against a specified-requirement set via
`rule_library.py` — the "scheduled air-cooled vs. specified water-cooled" catch — reusing the same selector
spine. This module is just the schedule.
"""
from __future__ import annotations

from typing import Any

# Procurable MEP equipment superclasses — the units a GC actually buys and installs. ``by_type`` resolves
# every subtype. Excludes IfcFlowSegment / IfcFlowFitting (ducts/pipes/elbows — installed material, not a
# scheduled unit) and IfcDistributionControlElement (sensors/controllers — commissioned, not RFQ'd as gear).
_EQUIP_CLASSES = (
    "IfcEnergyConversionDevice", "IfcFlowMovingDevice", "IfcFlowStorageDevice",
    "IfcFlowTreatmentDevice", "IfcFlowController", "IfcFlowTerminal", "IfcTransportElement",
)
# Curated procurement-relevant property keys (case-insensitive substring match over the element's Psets) —
# what a buyer needs on the RFQ line. First match wins; missing → omitted.
_SPEC_KEYS = ("Manufacturer", "ModelLabel", "Model", "Reference", "NominalCapacity", "Capacity", "Power",
              "PowerConsumption", "FlowRate", "AirFlowRate", "Pressure", "Voltage")
_MAX_LINES = 4000


def _first_spec(psets: dict[str, dict]) -> dict[str, Any]:
    """Pull the curated spec values from an element's flattened Psets (first key that matches each label)."""
    flat: dict[str, Any] = {}
    for pset in psets.values():
        if isinstance(pset, dict):
            for k, v in pset.items():
                flat.setdefault(k.lower(), v)
    out: dict[str, Any] = {}
    for want in _SPEC_KEYS:
        wl = want.lower()
        hit = next((flat[k] for k in flat if wl in k), None)
        if hit not in (None, "") and want not in out:
            # normalize to the canonical label (Model/ModelLabel collapse, Capacity variants collapse)
            label = {"ModelLabel": "Model", "NominalCapacity": "Capacity", "PowerConsumption": "Power",
                     "AirFlowRate": "FlowRate"}.get(want, want)
            out.setdefault(label, hit)
    return out


def spec_conflicts(lines: list[dict], requirements: dict[str, dict]) -> dict[str, Any]:
    """SPEC-CONFLICT — cross-check the scheduled equipment against a **specified-requirement set**, the
    deterministic version of the "scheduled air-cooled unit vs. spec's water-cooled requirement" catch —
    no doc-scanning, we compare the model's own Pset values.

    ``requirements`` is ``{ifc_class: {spec_key: expected}}`` (e.g. ``{"IfcChiller": {"CondenserType":
    "WaterCooled"}}``); ``spec_key`` matches the canonical labels the schedule surfaces (Manufacturer /
    Model / Capacity / Power / FlowRate / Voltage / …). A conflict is a scheduled line whose spec carries
    that key with a value that doesn't match the requirement (case-insensitive for strings). A line missing
    the key entirely is reported as ``missing`` (specified but not modelled), not a hard conflict.
    """
    def _match(actual: Any, expected: Any) -> bool:
        if isinstance(expected, (list, tuple, set)):
            return any(_match(actual, e) for e in expected)
        if isinstance(actual, str) and isinstance(expected, str):
            return actual.strip().lower() == expected.strip().lower()
        return actual == expected

    conflicts: list[dict] = []
    missing: list[dict] = []
    for line in lines:
        reqs = requirements.get(line["ifc_class"])
        if not reqs:
            continue
        spec = line.get("spec") or {}
        for key, expected in reqs.items():
            actual = spec.get(key)
            row = {"ifc_class": line["ifc_class"], "type": line["type"], "count": line["count"],
                   "spec_key": key, "expected": expected, "actual": actual}
            if actual in (None, ""):
                missing.append(row)
            elif not _match(actual, expected):
                conflicts.append(row)
    return {"conflict_count": len(conflicts), "missing_count": len(missing),
            "units_in_conflict": sum(c["count"] for c in conflicts),
            "conflicts": conflicts, "missing": missing,
            "note": "Scheduled equipment cross-checked against the specified-requirement set: a conflict is "
                    "a modelled Pset value that disagrees with the spec; 'missing' is a specified property "
                    "the model doesn't carry. Deterministic — no spec-document scanning."}


def schedule(model) -> dict[str, Any]:
    """Group the model's procurable equipment by (ifc_class, type) → RFQ line-items with a quantity + a
    representative spec pulled from the first unit, plus by-discipline / by-class tallies."""
    from . import classification as cls

    try:
        import ifcopenshell.util.element as ue
    except Exception:                                    # noqa: BLE001 — no ifcopenshell: empty schedule
        ue = None

    groups: dict[tuple, dict] = {}
    seen: set[int] = set()
    for sc in _EQUIP_CLASSES:
        try:
            els = model.by_type(sc)
        except Exception:                                # noqa: BLE001 — class absent in this schema
            els = []
        for e in els:
            if e.id() in seen:
                continue
            seen.add(e.id())
            ic = e.is_a()
            type_name = None
            psets: dict = {}
            if ue is not None:
                try:
                    t = ue.get_type(e)
                    type_name = getattr(t, "Name", None) if t is not None else None
                    psets = ue.get_psets(e, psets_only=True) or {}
                except Exception:                        # noqa: BLE001 — opaque element: skip its metadata
                    pass
            key = (ic, type_name or "")
            g = groups.get(key)
            if g is None:
                disc = cls.discipline_name(cls.discipline_of_ifc_class(ic)) or "General"
                g = groups[key] = {"ifc_class": ic, "type": type_name or ic, "discipline": disc,
                                   "count": 0, "spec": _first_spec(psets), "guids": []}
            g["count"] += 1
            if len(g["guids"]) < 500:
                g["guids"].append(getattr(e, "GlobalId", None))

    lines = sorted(groups.values(), key=lambda r: (-r["count"], r["ifc_class"], r["type"]))[:_MAX_LINES]

    def _tally(key: str) -> list[dict]:
        agg: dict[str, int] = {}
        for r in lines:
            agg[r[key]] = agg.get(r[key], 0) + r["count"]
        return [{key: k, "count": v} for k, v in sorted(agg.items(), key=lambda kv: -kv[1])]

    return {
        "line_count": len(lines),
        "unit_count": sum(r["count"] for r in lines),
        "by_discipline": _tally("discipline"), "by_class": _tally("ifc_class"),
        "lines": lines,
        "note": "Procurement equipment schedule derived from the IFC: procurable units grouped by class + "
                "type into RFQ line-items with a quantity + representative spec (from the model's Psets). "
                "Ducts/pipes/fittings and controls are excluded. Feed this into a buyout package / RFQ.",
    }
