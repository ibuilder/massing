"""Materials & surface styles (M1) — give generated/authored models real IFC materials and colours,
the way Revit assigns materials per category. Each element class gets an IfcMaterial (data) +
an IfcSurfaceStyle colour (so it renders properly in the viewer instead of flat grey). Pure-ish
over an open ifcopenshell model; safe to run as a post-process before writing.

A first step toward Revit-parity material work; layer sets (wall = plasterboard/stud/plasterboard)
and PBR textures are tracked in the roadmap (M-theme)."""
from __future__ import annotations

from typing import Any

# class -> (material name, category, (r,g,b), transparency)
PALETTE: dict[str, tuple[str, str, tuple[float, float, float], float]] = {
    "IfcColumn": ("Concrete", "concrete", (0.70, 0.70, 0.72), 0.0),
    "IfcBeam": ("Concrete", "concrete", (0.70, 0.70, 0.72), 0.0),
    "IfcSlab": ("Concrete", "concrete", (0.76, 0.76, 0.78), 0.0),
    "IfcWall": ("Concrete masonry", "masonry", (0.82, 0.80, 0.76), 0.0),
    "IfcWallStandardCase": ("Concrete masonry", "masonry", (0.82, 0.80, 0.76), 0.0),
    "IfcRoof": ("Roofing membrane", "roofing", (0.48, 0.50, 0.54), 0.0),
    "IfcWindow": ("Glazing", "glass", (0.42, 0.62, 0.86), 0.55),
    "IfcDoor": ("Timber", "wood", (0.55, 0.40, 0.26), 0.0),
    "IfcStair": ("Concrete", "concrete", (0.70, 0.70, 0.72), 0.0),
    "IfcTransportElement": ("Steel", "steel", (0.55, 0.57, 0.60), 0.0),
    "IfcDuctSegment": ("Galvanised steel", "steel", (0.62, 0.64, 0.67), 0.0),
    "IfcPipeSegment": ("Copper", "metal", (0.72, 0.45, 0.30), 0.0),
    "IfcLightFixture": ("Light fixture", "lighting", (0.95, 0.92, 0.80), 0.0),
    "IfcUnitaryEquipment": ("HVAC equipment", "hvac", (0.66, 0.70, 0.74), 0.0),
    "IfcAirTerminal": ("Diffuser", "hvac", (0.88, 0.89, 0.90), 0.0),
    "IfcElectricDistributionBoard": ("Electrical panel", "electrical", (0.40, 0.42, 0.46), 0.0),
    "IfcFurniture": ("Furniture", "furnishing", (0.60, 0.45, 0.30), 0.0),
    "IfcSanitaryTerminal": ("Porcelain", "ceramic", (0.92, 0.92, 0.93), 0.0),
    "IfcElectricAppliance": ("Appliance", "appliance", (0.85, 0.86, 0.88), 0.0),
    "IfcGeographicElement": ("Vegetation", "landscape", (0.30, 0.58, 0.32), 0.0),
}


def palette_to_json(palette: dict | None = None) -> dict[str, dict[str, Any]]:
    """The palette as JSON-friendly rows (for the material editor UI): class → {name, category,
    color:[r,g,b] 0–1, transparency}."""
    palette = palette or PALETTE
    return {cls: {"name": name, "category": cat, "color": [round(c, 4) for c in rgb],
                  "transparency": round(transp, 3)}
            for cls, (name, cat, rgb, transp) in palette.items()}


def palette_from_json(rows: dict[str, dict[str, Any]]) -> dict[str, tuple]:
    """Inverse of `palette_to_json` — a JSON palette (class → {name, category, color, transparency})
    back to the internal tuple form apply_palette consumes. Missing/short colors default to grey."""
    out: dict[str, tuple] = {}
    for cls, r in (rows or {}).items():
        col = r.get("color") or [0.7, 0.7, 0.72]
        rgb = tuple(float(c) for c in (list(col) + [0.7, 0.7, 0.72])[:3])
        out[cls] = (str(r.get("name") or cls.replace("Ifc", "")), str(r.get("category") or "generic"),
                    rgb, float(r.get("transparency") or 0.0))
    return out


def merge_palette(overrides: dict[str, dict[str, Any]] | None) -> dict[str, tuple]:
    """The default PALETTE with per-project JSON overrides applied on top (per class). Classes absent
    from the overrides keep their default material/colour; this is what a project actually renders."""
    merged = dict(PALETTE)
    if overrides:
        merged.update(palette_from_json(overrides))
    return merged


def _body_reps(el):
    rep = getattr(el, "Representation", None)
    return list(rep.Representations) if rep else []


def apply_palette(model, palette: dict | None = None) -> dict[str, Any]:
    """Assign an IfcMaterial + an IfcSurfaceStyle colour to every element of each class in the
    palette. Styles/materials are created once and reused. Returns counts."""
    import ifcopenshell.api

    palette = palette or PALETTE
    mat_cache: dict[str, Any] = {}
    style_cache: dict[str, Any] = {}
    styled, materialed = 0, 0
    for cls, (name, category, rgb, transp) in palette.items():
        elements = model.by_type(cls)
        if not elements:
            continue
        if name not in mat_cache:
            mat_cache[name] = ifcopenshell.api.run("material.add_material", model, name=name, category=category)
            st = ifcopenshell.api.run("style.add_style", model, name=name)
            ifcopenshell.api.run("style.add_surface_style", model, style=st,
                                 ifc_class="IfcSurfaceStyleShading",
                                 attributes={"SurfaceColour": {"Name": None, "Red": rgb[0], "Green": rgb[1], "Blue": rgb[2]},
                                             "Transparency": float(transp)})
            style_cache[name] = st
        mat, st = mat_cache[name], style_cache[name]
        for el in elements:
            try:
                ifcopenshell.api.run("material.assign_material", model, products=[el], material=mat)
                materialed += 1
            except Exception:                # noqa: BLE001 — some elements can't take a material rel
                pass
            for rep in _body_reps(el):
                try:
                    ifcopenshell.api.run("style.assign_representation_styles", model,
                                         shape_representation=rep, styles=[st])
                    styled += 1
                except Exception:            # noqa: BLE001
                    pass
    return {"styled": styled, "materialed": materialed,
            "materials": len(mat_cache), "classes": len([c for c in palette if model.by_type(c)])}
