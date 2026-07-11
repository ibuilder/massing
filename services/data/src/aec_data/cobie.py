"""Phase 5 — COBie handover data (facility/space/asset) for owner/FM deliverables.

A pragmatic subset of the COBie worksheets (Contact, Facility, Floor, Space, Zone, Type, Component,
System, Attribute).
Full COBie has more sheets; this covers the spine most owners ask for, now with the asset fields FM
teams actually use — space areas, manufacturer/warranty/expected-life on Types, serial/tag/asset-id
on Components — plus the **Attribute** sheet that flattens every remaining property set so no
model data is lost in handover (C2 field-enrichment)."""
from __future__ import annotations

from typing import Any

import ifcopenshell
import ifcopenshell.util.element as ue

from .ifc_loader import open_model, physical_elements, storey_name


def _psets(el) -> dict[str, dict[str, Any]]:
    try:
        return ue.get_psets(el)
    except Exception:                        # noqa: BLE001 — defensive: never let one element break export
        return {}


def _first(psets: dict, candidates: list[tuple[str, str]], default: Any = None) -> Any:
    """First present value across (pset_name, prop_name) candidates — COBie fields live under
    different psets depending on the authoring tool, so we search a few well-known homes."""
    for pset_name, prop in candidates:
        ps = psets.get(pset_name)
        if ps and ps.get(prop) not in (None, ""):
            return ps.get(prop)
    return default


# COBie Type asset fields → the psets they typically live in (IFC4 + common Revit exports)
_TYPE_FIELDS = {
    "Manufacturer": [("Pset_ManufacturerTypeInformation", "Manufacturer")],
    "ModelNumber": [("Pset_ManufacturerTypeInformation", "ModelLabel"),
                    ("Pset_ManufacturerTypeInformation", "ModelReference")],
    "WarrantyGuarantorParts": [("Pset_Warranty", "WarrantyIdentifier")],
    "WarrantyDurationParts": [("Pset_Warranty", "WarrantyPeriod"), ("Pset_Warranty", "DurationOfWarranty")],
    "ExpectedLife": [("Pset_ServiceLife", "ServiceLifeDuration"), ("Pset_Warranty", "ServiceLifeDuration")],
    "ReplacementCost": [("Pset_EconomicImpactValues", "ReplacementCost"), ("Pset_Asset", "OriginalValue")],
    "Color": [("Pset_ManufacturerTypeInformation", "Color"), ("Pset_ColourTypeInformation", "Colour")],
    "Material": [("Pset_MaterialCommon", "Name")],
    "Finish": [("Pset_DoorCommon", "Finish"), ("Pset_WindowCommon", "Finish")],
}
# COBie Component (occurrence) fields
_COMPONENT_FIELDS = {
    "SerialNumber": [("Pset_ManufacturerOccurrence", "SerialNumber")],
    "InstallationDate": [("Pset_ManufacturerOccurrence", "AssemblyPlace"), ("Pset_Asset", "AcquisitionDate")],
    "WarrantyStartDate": [("Pset_Warranty", "WarrantyStartDate")],
    "TagNumber": [("Pset_ManufacturerOccurrence", "BarCode"), ("Pset_Asset", "AssetAccountingType")],
    "AssetIdentifier": [("Pset_Asset", "AssetIdentifier")],
}


def _email_of(actor) -> str | None:
    """Best-effort email for an IfcPerson/IfcOrganization from its telecom addresses (COBie keys a
    Contact by email). Returns None when the model carries no email for that party."""
    try:
        for addr in getattr(actor, "Addresses", None) or []:
            if addr.is_a("IfcTelecomAddress"):
                emails = getattr(addr, "ElectronicMailAddresses", None) or []
                if emails and emails[0]:
                    return emails[0]
    except Exception:
        pass
    return None


def _grouped_names(group) -> list[str]:
    """Names of the objects a group (IfcZone/IfcSystem) assigns, via IfcRelAssignsToGroup."""
    out: list[str] = []
    try:
        for rel in getattr(group, "IsGroupedBy", None) or []:
            for obj in getattr(rel, "RelatedObjects", None) or []:
                out.append(getattr(obj, "Name", None) or getattr(obj, "GlobalId", ""))
    except Exception:
        pass
    return [n for n in out if n]


def _contact_sheet(model: ifcopenshell.file) -> list[dict[str, Any]]:
    """COBie Contact sheet — the people/organizations behind the model (keyed by email), pulled from
    IfcPersonAndOrganization / IfcPerson / IfcOrganization. Deduped by email (or name when no email)."""
    rows: dict[str, dict[str, Any]] = {}

    def add(email, company, given, family, category):
        key = (email or f"{given or ''} {family or ''} @ {company or ''}").strip().lower()
        if key and key not in rows:
            rows[key] = {"Email": email, "Company": company, "GivenName": given,
                         "FamilyName": family, "Category": category or "Contact"}

    for po in model.by_type("IfcPersonAndOrganization"):
        person, org = getattr(po, "ThePerson", None), getattr(po, "TheOrganization", None)
        add(_email_of(person) or _email_of(org),
            getattr(org, "Name", None) if org else None,
            getattr(person, "GivenName", None) if person else None,
            getattr(person, "FamilyName", None) if person else None, "Person")
    for person in model.by_type("IfcPerson"):
        add(_email_of(person), None, getattr(person, "GivenName", None),
            getattr(person, "FamilyName", None), "Person")
    for org in model.by_type("IfcOrganization"):
        add(_email_of(org), getattr(org, "Name", None), None, None, "Organization")
    return list(rows.values())


def cobie_sheets(model: ifcopenshell.file) -> dict[str, list[dict[str, Any]]]:
    project = (model.by_type("IfcProject") or [None])[0]
    sites = model.by_type("IfcSite")
    buildings = model.by_type("IfcBuilding")

    facility = [{
        "Name": getattr(b, "Name", None),
        "Project": getattr(project, "Name", None) if project else None,
        "Site": getattr(sites[0], "Name", None) if sites else None,
        "Category": "Building",
    } for b in buildings] or [{"Name": None, "Project": getattr(project, "Name", None) if project else None}]

    floor = [{
        "Name": getattr(s, "Name", None),
        "Category": "Floor",
        "Elevation": getattr(s, "Elevation", None),
    } for s in model.by_type("IfcBuildingStorey")]

    # Space — now with the areas/height FM teams expect (from Qto_SpaceBaseQuantities)
    attribute: list[dict[str, Any]] = []
    space: list[dict[str, Any]] = []
    for sp in model.by_type("IfcSpace"):
        ps = _psets(sp)
        row_name = getattr(sp, "Name", None) or sp.GlobalId
        space.append({
            "Name": getattr(sp, "Name", None),
            "Floor": storey_name(sp),
            "Description": getattr(sp, "LongName", None),
            "Category": _first(ps, [("Pset_SpaceCommon", "Reference")], "Space"),
            "NetArea": _first(ps, [("Qto_SpaceBaseQuantities", "NetFloorArea")]),
            "GrossArea": _first(ps, [("Qto_SpaceBaseQuantities", "GrossFloorArea")]),
            "UsableHeight": _first(ps, [("Qto_SpaceBaseQuantities", "Height")]),
        })
        _flatten_attributes(attribute, ps, "Space", row_name)

    # Type and Component sheets — keyed by GUID, with asset/warranty fields + Attribute spillover
    types: dict[str, dict[str, Any]] = {}
    component: list[dict[str, Any]] = []
    for el in physical_elements(model):
        if el.is_a("IfcOpeningElement"):
            continue
        el_type = ue.get_type(el)
        type_name = getattr(el_type, "Name", None) if el_type else None
        if el_type and type_name and type_name not in types:
            tps = _psets(el_type)
            row = {"Name": type_name, "Category": el_type.is_a(), "AssetType": "Fixed"}
            for field, cands in _TYPE_FIELDS.items():
                row[field] = _first(tps, cands)
            types[type_name] = row
            _flatten_attributes(attribute, tps, "Type", type_name)
        cps = _psets(el)
        crow = {
            "Name": getattr(el, "Name", None),
            "TypeName": type_name,
            "Space": storey_name(el),
            "Category": el.is_a(),
            "ExtIdentifier": el.GlobalId,
        }
        for field, cands in _COMPONENT_FIELDS.items():
            crow[field] = _first(cps, cands)
        component.append(crow)
        _flatten_attributes(attribute, cps, "Component", getattr(el, "Name", None) or el.GlobalId)

    # Zone — spatial groupings of spaces (IfcZone); System — functional groupings of components
    # (IfcSystem / IfcDistributionSystem). Both list their members so FM can navigate space↔zone and
    # component↔system, which is the whole point of these COBie tabs.
    zone = [{
        "Name": getattr(z, "Name", None) or z.GlobalId,
        "Category": getattr(z, "LongName", None) or "Zone",
        "SpaceNames": ", ".join(_grouped_names(z)),
    } for z in model.by_type("IfcZone")]
    system = [{
        "Name": getattr(sy, "Name", None) or sy.GlobalId,
        "Category": (getattr(sy, "PredefinedType", None) or getattr(sy, "LongName", None) or "System"),
        "ComponentNames": ", ".join(_grouped_names(sy)),
    } for sy in model.by_type("IfcSystem")]

    return {
        "Contact": _contact_sheet(model),
        "Facility": facility,
        "Floor": floor,
        "Space": space,
        "Zone": zone,
        "Type": list(types.values()),
        "Component": component,
        "System": system,
        "Attribute": attribute,
    }


# Psets already surfaced as first-class columns — don't duplicate them onto the Attribute sheet.
_PROMOTED = {"Qto_SpaceBaseQuantities", "Pset_SpaceCommon", "Pset_ManufacturerTypeInformation",
             "Pset_Warranty", "Pset_ServiceLife", "Pset_ManufacturerOccurrence", "Pset_Asset"}


def _flatten_attributes(out: list, psets: dict, sheet: str, row_name: Any) -> None:
    """COBie Attribute sheet: every remaining property as Name/Value/SheetName/RowName, so arbitrary
    model data round-trips through handover rather than being dropped."""
    for pset_name, props in psets.items():
        if pset_name in _PROMOTED:
            continue
        for prop, val in props.items():
            if prop == "id" or val in (None, ""):
                continue
            out.append({"Name": prop, "Value": val, "SheetName": sheet,
                        "RowName": row_name, "Category": pset_name})


def cobie_file(ifc_path: str) -> dict[str, list[dict[str, Any]]]:
    return cobie_sheets(open_model(ifc_path))
