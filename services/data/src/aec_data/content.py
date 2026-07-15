"""CONTENT-1 — a curated **content catalog** that classifies real-world parts into the *right* IFC place.

The point isn't random shapes — it's that a crane, a porta-john, a tree, and an office desk each belong in a
specific IFC class, on a specific storey, in a specific project phase, with a specific classification code, so
they behave correctly downstream (the crane time-phases on the 4D logistics slider; the tree exports as
landscape; the desk feeds FF&E takeoff). This module holds that mapping; `edit.place_content` authors an
element (from an imported mesh or a sized placeholder) using it.

Content is imported/authored per-asset with **license vetting** — the catalog records the intended license
tier (CC0/CC-BY preferred); the geometry itself is supplied by the caller (an imported glTF/OBJ/SketchUp
asset) or a procedural placeholder box, never bundled unvetted.
"""
from __future__ import annotations

from typing import Any

# category -> how it maps into IFC. `ifc_class` is the authored class; `phase` (or None) sets
# Massing_Phasing.Status; `group` is the site/discipline bucket; `classification` is (system, code, title);
# `dims` is a default placeholder box size (metres, L×W×H) when no mesh is supplied.
_C: dict[str, dict[str, Any]] = {
    # ── Site logistics (temporary — time-phases on the 4D logistics slider) ──────────────────────────
    "tower_crane":  {"ifc_class": "IfcBuildingElementProxy", "phase": "temporary", "group": "Site Logistics",
                     "classification": ("Uniclass2015", "Pr_40_70_15", "Cranes"), "dims": [4.0, 4.0, 40.0]},
    "mobile_crane": {"ifc_class": "IfcBuildingElementProxy", "phase": "temporary", "group": "Site Logistics",
                     "classification": ("Uniclass2015", "Pr_40_70_15", "Cranes"), "dims": [12.0, 3.0, 4.0]},
    "hoist":        {"ifc_class": "IfcBuildingElementProxy", "phase": "temporary", "group": "Site Logistics",
                     "classification": ("Uniclass2015", "Pr_40_70", "Lifting equipment"), "dims": [2.5, 2.5, 20.0]},
    "site_fence":   {"ifc_class": "IfcBuildingElementProxy", "phase": "temporary", "group": "Site Logistics",
                     "classification": ("Uniclass2015", "Pr_25_71_02", "Temporary fencing"), "dims": [3.5, 0.1, 2.0]},
    "sanitary_unit": {"ifc_class": "IfcSanitaryTerminal", "phase": "temporary", "group": "Site Logistics",
                      "classification": ("Uniclass2015", "Pr_40_50", "Sanitary equipment"), "dims": [1.2, 1.2, 2.3]},
    "site_office":  {"ifc_class": "IfcBuildingElementProxy", "phase": "temporary", "group": "Site Logistics",
                     "classification": ("Uniclass2015", "Pr_15_31", "Site accommodation"), "dims": [9.0, 3.0, 3.0]},
    "laydown":      {"ifc_class": "IfcAnnotation", "phase": "temporary", "group": "Site Logistics",
                     "classification": ("Uniclass2015", "SL_25", "Storage areas"), "dims": [10.0, 6.0, 0.1]},
    "gate":         {"ifc_class": "IfcBuildingElementProxy", "phase": "temporary", "group": "Site Logistics",
                     "classification": ("Uniclass2015", "Pr_25_71", "Access control"), "dims": [6.0, 0.2, 2.0]},
    "dumpster":     {"ifc_class": "IfcBuildingElementProxy", "phase": "temporary", "group": "Site Logistics",
                     "classification": ("Uniclass2015", "Pr_40_70", "Waste containers"), "dims": [6.0, 2.4, 2.2]},
    # ── Furniture / FF&E ────────────────────────────────────────────────────────────────────────────
    "desk":   {"ifc_class": "IfcFurniture", "phase": None, "group": "FF&E",
               "classification": ("OmniClass", "23-45 11 00", "Desks"), "dims": [1.6, 0.8, 0.75]},
    "chair":  {"ifc_class": "IfcFurniture", "phase": None, "group": "FF&E",
               "classification": ("OmniClass", "23-45 13 00", "Chairs"), "dims": [0.6, 0.6, 0.9]},
    "sofa":   {"ifc_class": "IfcFurniture", "phase": None, "group": "FF&E",
               "classification": ("OmniClass", "23-45 13 00", "Seating"), "dims": [2.0, 0.9, 0.85]},
    "table":  {"ifc_class": "IfcFurniture", "phase": None, "group": "FF&E",
               "classification": ("OmniClass", "23-45 11 00", "Tables"), "dims": [1.8, 0.9, 0.75]},
    "bed":    {"ifc_class": "IfcFurniture", "phase": None, "group": "FF&E",
               "classification": ("OmniClass", "23-45 21 00", "Beds"), "dims": [2.0, 1.5, 0.6]},
    "cabinet": {"ifc_class": "IfcFurniture", "phase": None, "group": "FF&E",
                "classification": ("OmniClass", "23-45 31 00", "Casework"), "dims": [1.0, 0.6, 2.0]},
    # ── Landscaping ─────────────────────────────────────────────────────────────────────────────────
    "tree":    {"ifc_class": "IfcGeographicElement", "phase": None, "group": "Landscape",
                "classification": ("Uniclass2015", "Pr_45_71_97", "Trees"), "dims": [5.0, 5.0, 7.0]},
    "shrub":   {"ifc_class": "IfcGeographicElement", "phase": None, "group": "Landscape",
                "classification": ("Uniclass2015", "Pr_45_71", "Planting"), "dims": [1.2, 1.2, 1.0]},
    "planter": {"ifc_class": "IfcFurniture", "phase": None, "group": "Landscape",
                "classification": ("Uniclass2015", "Pr_40_10", "Planters"), "dims": [1.0, 1.0, 0.6]},
    "bollard": {"ifc_class": "IfcBuildingElementProxy", "phase": None, "group": "Landscape",
                "classification": ("Uniclass2015", "Pr_25_57", "Bollards"), "dims": [0.2, 0.2, 1.0]},
}

# some IFC classes are IFC4+; fall back to a proxy on an IFC2x3 model that lacks them
_FALLBACK = "IfcBuildingElementProxy"


def catalog() -> dict[str, Any]:
    """The content catalog grouped by bucket, for a content-palette UI."""
    groups: dict[str, list[dict]] = {}
    for key, meta in _C.items():
        groups.setdefault(meta["group"], []).append({
            "key": key, "ifc_class": meta["ifc_class"], "phase": meta["phase"],
            "classification": meta["classification"][1] + " " + meta["classification"][2],
            "default_dims_m": meta["dims"]})
    return {"groups": {g: sorted(items, key=lambda x: x["key"]) for g, items in sorted(groups.items())},
            "count": len(_C),
            "note": "Each item maps to the correct IFC class + phase + classification. Supply a detailed "
                    "mesh (imported glTF/OBJ/SketchUp asset, license-vetted) or place a sized placeholder."}


def spec(category: str) -> dict[str, Any] | None:
    return _C.get((category or "").strip().lower())
