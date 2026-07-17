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


def furniture_bom(model) -> dict[str, Any]:
    """W9-6b: an **FF&E / furnishings bill of materials** from the placed content — count each furniture /
    furnishing item (by Name), with its IFC class and the storeys it appears on, into a schedule an owner or
    FF&E vendor can order from. Composes `IfcFurniture` / `IfcFurnishingElement` /
    `IfcSystemFurnitureElement` (the classes `place_content` + `furnish` author)."""
    from .ifc_loader import storey_name

    rows: dict[str, dict[str, Any]] = {}
    total = 0
    for cls in ("IfcFurniture", "IfcFurnishingElement", "IfcSystemFurnitureElement"):
        try:
            elements = model.by_type(cls)
        except RuntimeError:                                 # class not in this schema
            continue
        for el in elements:
            nm = (getattr(el, "Name", None) or cls.replace("Ifc", "")).strip() or cls.replace("Ifc", "")
            r = rows.setdefault(nm, {"item": nm, "ifc_class": el.is_a(), "count": 0, "storeys": set()})
            r["count"] += 1
            total += 1
            st = storey_name(el)
            if st:
                r["storeys"].add(st)
    items = sorted(({"item": r["item"], "ifc_class": r["ifc_class"], "count": r["count"],
                     "storeys": sorted(r["storeys"])} for r in rows.values()),
                   key=lambda x: (-x["count"], x["item"]))
    return {"total": total, "line_count": len(items), "items": items,
            "note": "FF&E bill of materials from the model's placed furnishings — counts by item + the "
                    "levels each appears on. An order/procurement starting point; verify finishes/specs."}


# CONTENT-1 (import): filename/name keyword → catalog category, so an imported "office-chair.glb" auto-files
# as `chair` (IfcFurniture). Longer/more-specific synonyms first so "mobile crane" beats "crane".
_SYNONYMS: list[tuple[str, str]] = [
    ("mobile crane", "mobile_crane"), ("mobile_crane", "mobile_crane"), ("crawler crane", "mobile_crane"),
    ("tower crane", "tower_crane"), ("tower_crane", "tower_crane"), ("crane", "tower_crane"),
    ("material hoist", "hoist"), ("man hoist", "hoist"), ("hoist", "hoist"), ("elevator hoist", "hoist"),
    ("porta john", "sanitary_unit"), ("porta-john", "sanitary_unit"), ("portajohn", "sanitary_unit"),
    ("porta potty", "sanitary_unit"), ("portable toilet", "sanitary_unit"), ("toilet", "sanitary_unit"),
    ("restroom", "sanitary_unit"), ("sanitary", "sanitary_unit"), ("wc", "sanitary_unit"),
    ("site fence", "site_fence"), ("hoarding", "site_fence"), ("fence", "site_fence"), ("barrier", "site_fence"),
    ("site office", "site_office"), ("site trailer", "site_office"), ("job trailer", "site_office"),
    ("trailer", "site_office"), ("container office", "site_office"), ("office", "site_office"),
    ("laydown", "laydown"), ("lay down", "laydown"), ("storage area", "laydown"),
    ("gate", "gate"), ("dumpster", "dumpster"), ("skip", "dumpster"), ("waste bin", "dumpster"),
    ("office chair", "chair"), ("chair", "chair"), ("stool", "chair"),
    ("desk", "desk"), ("workstation", "desk"), ("sofa", "sofa"), ("couch", "sofa"),
    ("dining table", "table"), ("table", "table"), ("bed", "bed"), ("cabinet", "cabinet"), ("wardrobe", "cabinet"),
    ("shrub", "shrub"), ("bush", "shrub"), ("hedge", "shrub"), ("tree", "tree"), ("planter", "planter"),
    ("plant pot", "planter"), ("bollard", "bollard"),
]


def detect_category(name: str) -> str | None:
    """Guess a catalog category from a filename / asset name by keyword (longest synonym wins). Returns the
    category key or None if nothing matches — the import then asks for an explicit category."""
    s = (name or "").lower().replace("_", " ").replace("-", " ")
    best: tuple[int, str] | None = None
    for kw, cat in _SYNONYMS:
        if kw in s and (best is None or len(kw) > best[0]):
            best = (len(kw), cat)
    return best[1] if best else None


def parse_mesh(data: bytes, ext: str = ".glb", scale: float = 1.0, max_faces: int = 200_000) -> tuple:
    """CONTENT-1 (import): parse an uploaded mesh (glTF/GLB/OBJ/STL/PLY) into `(verts, faces)` ready for
    `add_mesh_representation` — verts in **metres** as `[[x,y,z]…]`, faces 0-based `[[i,j,k]…]`. The mesh is
    recentred so its min-corner sits at the origin (it then places at the [E,N] point, base at z=0); glTF's
    Y-up is rotated to IFC's Z-up. `scale` multiplies the size. Raises on an unparseable or over-large mesh."""
    import io

    import numpy as np
    import trimesh

    ft = (ext or ".glb").lstrip(".").lower()
    mesh = trimesh.load(io.BytesIO(data), file_type=ft, force="mesh")   # concatenate a Scene into one mesh
    if mesh is None or not hasattr(mesh, "vertices") or len(mesh.vertices) == 0:
        raise ValueError("no mesh geometry found in the file")
    v = np.asarray(mesh.vertices, dtype=float)
    f = np.asarray(mesh.faces, dtype=int)
    if len(f) == 0:
        raise ValueError("mesh has no faces")
    if len(f) > max_faces:
        raise ValueError(f"mesh has {len(f)} faces (> {max_faces}); decimate it before importing")
    if ft in ("gltf", "glb"):                      # glTF is Y-up; IFC is Z-up → rotate +90° about X
        v = v[:, [0, 2, 1]] * np.array([1.0, -1.0, 1.0])
    v = (v - v.min(axis=0)) * float(scale)          # min-corner to origin, then scale
    return v.tolist(), f.tolist()
