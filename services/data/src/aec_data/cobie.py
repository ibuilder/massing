"""Phase 5 — COBie handover data (facility/space/asset) for owner/FM deliverables.

A pragmatic subset of the COBie worksheets (Facility, Floor, Space, Type, Component).
Full COBie has more sheets/attributes; this covers the spine most owners ask for."""
from __future__ import annotations

from typing import Any

import ifcopenshell
import ifcopenshell.util.element as ue

from .ifc_loader import open_model, physical_elements, storey_name


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

    space = [{
        "Name": getattr(sp, "Name", None),
        "Floor": storey_name(sp),
        "Description": getattr(sp, "LongName", None),
        "Category": "Space",
    } for sp in model.by_type("IfcSpace")]

    # Type and Component sheets — keyed by GUID
    types: dict[str, dict[str, Any]] = {}
    component: list[dict[str, Any]] = []
    for el in physical_elements(model):
        if el.is_a("IfcOpeningElement"):
            continue
        el_type = ue.get_type(el)
        type_name = getattr(el_type, "Name", None) if el_type else None
        if el_type and type_name and type_name not in types:
            types[type_name] = {
                "Name": type_name,
                "Category": el_type.is_a(),
                "AssetType": "Fixed",
            }
        component.append({
            "Name": getattr(el, "Name", None),
            "TypeName": type_name,
            "Space": storey_name(el),
            "Category": el.is_a(),
            "ExtIdentifier": el.GlobalId,
        })

    return {
        "Facility": facility,
        "Floor": floor,
        "Space": space,
        "Type": list(types.values()),
        "Component": component,
    }


def cobie_file(ifc_path: str) -> dict[str, list[dict[str, Any]]]:
    return cobie_sheets(open_model(ifc_path))
