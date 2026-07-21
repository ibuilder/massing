"""ASSET-REG (R16) — derive the **maintainable-asset register straight from the IFC**, so the FM handover
register isn't hand-entered (bimassetpro's "model → full control in days", done deterministically because
IFC is our source of truth). Selects the serviceable equipment / terminals / controls / transport by IFC
class (subtype-resolved), GUID-keyed, tagged with discipline + storey + type — ready to seed the shipped
`asset_register` module and hang preventive-maintenance (`pm_schedule`) off. Pure over an opened model.
"""
from __future__ import annotations

from typing import Any

# The serviceable-asset superclasses — ``by_type`` resolves every subtype (AHUs, pumps, fans, boilers,
# chillers, valves, dampers, air terminals, sensors, elevators…). Deliberately EXCLUDES IfcFlowSegment /
# IfcFlowFitting (ducts/pipes/elbows) — you maintain the unit, not each duct run.
_ASSET_CLASSES = (
    "IfcEnergyConversionDevice", "IfcFlowMovingDevice", "IfcFlowController", "IfcFlowTerminal",
    "IfcFlowStorageDevice", "IfcFlowTreatmentDevice", "IfcDistributionControlElement", "IfcTransportElement",
)
# which superclass an element matched → a coarse maintainable category for the summary
_CATEGORY = {
    "IfcEnergyConversionDevice": "equipment", "IfcFlowMovingDevice": "equipment",
    "IfcFlowStorageDevice": "equipment", "IfcFlowTreatmentDevice": "equipment",
    "IfcFlowController": "control", "IfcDistributionControlElement": "control",
    "IfcFlowTerminal": "terminal", "IfcTransportElement": "transport",
}
_MAX_ASSETS = 5000


def _storey_map(model) -> dict[int, str]:
    """element id → containing storey name, via IfcRelContainedInSpatialStructure."""
    out: dict[int, str] = {}
    for rel in model.by_type("IfcRelContainedInSpatialStructure"):
        st = getattr(rel, "RelatingStructure", None)
        name = getattr(st, "Name", None) if st is not None else None
        for e in (rel.RelatedElements or []):
            out[e.id()] = name
    return out


def _type_name(model, e) -> str | None:
    try:
        import ifcopenshell.util.element as _ue
        t = _ue.get_type(e)
        return getattr(t, "Name", None) if t is not None else None
    except Exception:                                    # noqa: BLE001 — no/opaque type: skip
        return None


def assets(model) -> dict[str, Any]:
    """Derive the maintainable-asset register from the model → ``{count, by_discipline, by_category,
    by_class, assets:[…]}``. Each asset: guid · name · ifc_class · type · discipline · category · storey."""
    from . import classification as cls

    storeys = _storey_map(model)
    seen: set[int] = set()
    out: list[dict] = []
    for sc in _ASSET_CLASSES:
        try:
            els = model.by_type(sc)
        except Exception:                                # noqa: BLE001 — class absent in this schema
            els = []
        cat = _CATEGORY.get(sc, "equipment")
        for e in els:
            if e.id() in seen:
                continue
            seen.add(e.id())
            ic = e.is_a()
            disc = cls.discipline_name(cls.discipline_of_ifc_class(ic)) or "General"
            out.append({"guid": getattr(e, "GlobalId", None), "name": (getattr(e, "Name", None) or ic),
                        "ifc_class": ic, "type": _type_name(model, e), "discipline": disc,
                        "category": cat, "storey": storeys.get(e.id())})

    out.sort(key=lambda a: (a["discipline"], a["ifc_class"], a["name"]))

    def _tally(key: str) -> list[dict]:
        agg: dict[str, int] = {}
        for a in out:
            agg[a[key] or "—"] = agg.get(a[key] or "—", 0) + 1
        return [{key: k, "count": v} for k, v in sorted(agg.items(), key=lambda kv: -kv[1])]

    return {"count": len(out), "by_discipline": _tally("discipline"), "by_category": _tally("category"),
            "by_class": _tally("ifc_class"), "assets": out[:_MAX_ASSETS],
            "note": "Maintainable assets derived from the IFC (serviceable equipment / terminals / controls "
                    "/ transport, subtype-resolved; ducts/pipes/fittings excluded). GUID-keyed — seed the "
                    "asset_register module from this, then hang preventive maintenance (pm_schedule) off it."}


def seed(db, pid: str, derived: list[dict], actor: str | None = None) -> dict[str, Any]:
    """Create `asset_register` records from the derived assets, idempotent by **tag** (`{ifc_class}-{guid8}`),
    so re-seeding after a model change only adds what's new."""
    from . import modules as me

    existing = {(r.get("data") or {}).get("tag", "") for r in me.list_records(db, "asset_register", pid, limit=100_000)}
    created, skipped = [], 0
    for a in derived[:_MAX_ASSETS]:
        guid = a.get("guid") or ""
        tag = f"{a['ifc_class']}-{guid[:8]}"
        if tag in existing:
            skipped += 1
            continue
        rec = me.create_record(db, "asset_register", pid, {"data": {
            "name": a.get("name") or a["ifc_class"], "tag": tag,
            "location": a.get("storey") or "", "model": a.get("type") or ""}}, actor, None)
        existing.add(tag)
        created.append(rec.get("ref"))
    return {"created": len(created), "skipped": skipped, "created_refs": created,
            "note": "Seeded the asset_register from the model (idempotent by tag). Attach pm_schedule "
                    "preventive-maintenance tasks + warranty/serial per asset from here."}
