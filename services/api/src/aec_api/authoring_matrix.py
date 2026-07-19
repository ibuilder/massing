"""AUTHOR-MATRIX — the authoring-coverage matrix (the OpenAEC COMMANDS.md analog).

An honest, single-source answer to "what can this tool actually author?" — derived live from the
`edit.RECIPES` registry (never hand-maintained, so it can't drift) + a small curated category/output
map. Users read it to judge maturity; contributors read it to pick work; the docs copy is generated from
the same function so `docs/authoring-matrix.md` and the endpoint never disagree.
"""
from __future__ import annotations

from typing import Any

# recipe → (category, IFC output / effect). Anything in RECIPES but absent here still shows up under
# "uncategorized", so a newly-added recipe surfaces instead of silently vanishing.
_MAP: dict[str, tuple[str, str]] = {
    # --- create: architectural / structural / enclosure ---
    "add_wall": ("create-structure", "IfcWall"), "add_slab": ("create-structure", "IfcSlab"),
    "add_column": ("create-structure", "IfcColumn"), "add_beam": ("create-structure", "IfcBeam"),
    "add_steel_column": ("create-structure", "IfcColumn (steel profile)"),
    "add_steel_beam": ("create-structure", "IfcBeam (steel profile)"),
    "add_footing": ("create-structure", "IfcFooting"), "add_rebar": ("create-structure", "IfcReinforcingBar"),
    "add_rebar_cage": ("create-structure", "IfcReinforcingBar (cage)"),
    "add_base_plate": ("create-structure", "IfcPlate (base plate)"),
    "add_shear_tab": ("create-structure", "IfcPlate (shear tab) + bolts"),
    "add_roof": ("create-enclosure", "IfcRoof"), "add_covering": ("create-enclosure", "IfcCovering"),
    "add_railing": ("create-enclosure", "IfcRailing"), "add_curtain_wall": ("create-enclosure", "IfcCurtainWall"),
    "add_door": ("create-opening", "IfcDoor + IfcOpeningElement"),
    "add_window": ("create-opening", "IfcWindow + IfcOpeningElement"),
    "add_spaces": ("create-space", "IfcSpace (per storey)"), "add_storey": ("create-space", "IfcBuildingStorey"),
    # --- create: MEP ---
    "add_duct": ("create-mep", "IfcDuctSegment"), "add_pipe": ("create-mep", "IfcPipeSegment"),
    "add_cable_tray": ("create-mep", "IfcCableCarrierSegment"), "add_wire": ("create-mep", "IfcCableSegment"),
    "add_riser": ("create-mep", "vertical MEP riser"), "add_mep_fitting": ("create-mep", "IfcDuct/PipeFitting"),
    "add_mep_terminal": ("create-mep", "IfcDuct/PipeTerminal"), "add_sprinkler": ("create-mep", "IfcFireSuppressionTerminal"),
    "add_fire_equipment": ("create-mep", "fire-protection equipment"),
    "add_fa_device": ("create-mep", "fire-alarm device"), "add_comms_device": ("create-mep", "telecom device"),
    "connect_mep": ("edit-mep", "port-to-port connection"),
    "auto_connect_mep": ("edit-mep", "coincident-port auto-connect sweep"),
    # --- create: content / families / geometry ---
    "add_family": ("create-content", "family occurrence"), "place_content": ("create-content", "catalog content"),
    "add_mesh_representation": ("create-content", "IfcBuildingElementProxy (mesh)"),
    "furnish_spaces": ("create-content", "FF&E per room"),
    "program_fit": ("create-content", "headcount program → zones + seats"),
    # --- annotate (2D) ---
    "add_annotation": ("annotate", "IfcAnnotation (text)"), "add_dimension": ("annotate", "IfcAnnotation (dimension)"),
    "add_tag": ("annotate", "IfcAnnotation (element tag)"), "add_revision_cloud": ("annotate", "IfcAnnotation (rev cloud)"),
    # --- edit-in-place ---
    "move_element": ("edit", "translate"), "rotate_element": ("edit", "rotate"),
    "copy_element": ("edit", "duplicate"), "delete_element": ("edit", "remove"),
    "extrude_profile": ("create-structure", "sketch profile → extruded element"),
    "set_extrusion_depth": ("edit", "push/pull an extrusion depth"),
    "set_wall_slope": ("edit", "sloped-top wall"), "add_opening": ("edit", "void a host"),
    "rename_storey": ("edit", "rename level"), "set_storey_elevation": ("edit", "move level"),
    # --- groups / types / arrays ---
    "create_type": ("type", "IfcTypeProduct"), "edit_type": ("type", "edit type params"),
    "place_type": ("type", "type occurrence"), "create_group": ("group", "IfcGroup"),
    "create_assembly": ("group", "IfcElementAssembly"), "array_element": ("group", "linear/grid array"),
    "assign_material_set": ("data", "IfcMaterialLayerSet"),
    # --- data / classification / detailing ---
    "classify": ("data", "IfcClassificationReference"), "set_classification": ("data", "classification"),
    "set_element_pset": ("data", "Pset property"), "set_pset_on_class": ("data", "Pset (by class)"),
    "batch_tag": ("data", "AEC_Tags label"), "attach_document": ("data", "IfcRelAssociatesDocument"),
    "attach_om_document": ("data", "O&M document ref"), "apply_detailing_rules": ("data", "rule-driven details"),
    "apply_layers": ("data", "property-override layers"), "set_manufacturer_info": ("data", "manufacturer psets"),
    # --- phasing / as-built ---
    "set_phase": ("lifecycle", "Massing_Phasing.Status"), "verify_asbuilt": ("lifecycle", "LOD-500 verified"),
    "record_asbuilt_dimension": ("lifecycle", "as-built dimension"),
    # --- analysis-write ---
    "apply_structural_loads": ("analysis", "IfcStructuralLoad"),
    "apply_structural_supports": ("analysis", "IfcStructuralConnection"),
    "derive_analytical": ("analysis", "IfcStructuralAnalysisModel"),
    "connect_elements": ("edit", "IfcRelConnectsElements"),
    # --- remaining primitives / advanced ---
    "edit_type_params": ("type", "edit type parameters"), "ungroup": ("group", "dissolve a group"),
    "set_pset": ("data", "Pset property"), "map_properties": ("data", "vendor→IDS pset remap"),
    "set_lod": ("data", "LOD stage tag"), "ensure_contexts": ("data", "representation contexts"),
    "derive_representations": ("data", "coarse Box/Axis/FootPrint views"),
    "set_spec_link": ("data", "Pset_Massing_SpecLink breadcrumb"),
    "set_system_predefined": ("edit-mep", "system predefined type"),
    "execute_ifc_code": ("edit", "sandboxed ifcopenshell escape hatch"),
}

_CATEGORY_ORDER = ["create-structure", "create-enclosure", "create-opening", "create-space",
                   "create-mep", "create-content", "annotate", "edit", "edit-mep", "type", "group",
                   "data", "lifecycle", "analysis", "uncategorized"]


def matrix() -> dict[str, Any]:
    """The live authoring-coverage matrix from `edit.RECIPES` + the category map."""
    from aec_data import edit  # type: ignore

    recipes = sorted(edit.RECIPES.keys())
    rows = []
    by_cat: dict[str, list[dict[str, str]]] = {}
    for name in recipes:
        cat, produces = _MAP.get(name, ("uncategorized", ""))
        row = {"recipe": name, "category": cat, "produces": produces}
        rows.append(row)
        by_cat.setdefault(cat, []).append(row)
    ordered = {c: by_cat[c] for c in _CATEGORY_ORDER if c in by_cat}
    for c in by_cat:                                   # any category not in the order list, appended
        ordered.setdefault(c, by_cat[c])
    return {
        "recipe_count": len(recipes),
        "category_count": len(ordered),
        "uncategorized": [r["recipe"] for r in by_cat.get("uncategorized", [])],
        "by_category": {c: {"count": len(v), "recipes": v} for c, v in ordered.items()},
        "note": ("Live from the edit.RECIPES registry — a newly-added recipe appears here automatically "
                 "(uncategorized until mapped). Every recipe is a GUID-stable server-side pass; the CAD "
                 "command line + AI command bar + panels all dispatch these."),
    }


def to_markdown() -> str:
    """Render the matrix as `docs/authoring-matrix.md` — the committed, human-readable coverage table."""
    m = matrix()
    out = ["# Authoring coverage matrix",
           "",
           "> Generated from `edit.RECIPES` by `authoring_matrix.to_markdown()` — do not hand-edit; "
           "re-run the generator (or `GET /reference/authoring-matrix`) after adding a recipe.",
           "",
           f"**{m['recipe_count']} authoring recipes** across **{m['category_count']} categories**. "
           "Every recipe is a GUID-stable server-side pass, dispatchable from the CAD command line, the "
           "AI command bar, the node canvas, or the tool panels.",
           ""]
    for cat, data in m["by_category"].items():
        out.append(f"### {cat} ({data['count']})")
        out.append("")
        out.append("| Recipe | Produces |")
        out.append("| --- | --- |")
        for r in data["recipes"]:
            out.append(f"| `{r['recipe']}` | {r['produces'] or '—'} |")
        out.append("")
    if m["uncategorized"]:
        out.append(f"> ⚠ Uncategorized (add to the map in `authoring_matrix.py`): "
                   f"{', '.join(m['uncategorized'])}")
        out.append("")
    return "\n".join(out)
