"""AUTHOR-MATRIX — the authoring-coverage matrix (the OpenAEC COMMANDS.md analog).

An honest, single-source answer to "what can this tool actually author?" — derived live from the
`edit.RECIPES` registry (never hand-maintained, so it can't drift) + a small curated category/output
map. Users read it to judge maturity; contributors read it to pick work; the docs copy is generated from
the same function so `docs/authoring-matrix.md` and the endpoint never disagree.

**Being derived from the engine is not the same as being true about the product, and this file used
to conflate them.** It said every recipe was "dispatchable from the CAD command line, the AI command
bar, the node canvas, or the tool panels". The CAD line and the AI bar both dispatch from
`nlauthor.RECIPE_SPECS`, which is a CURATED subset naming 12 of the 96 — and ten recipes had no
caller on any surface at all: not the web client, not a router, not MCP, not the planner. The matrix
could not drift from the ENGINE and was overcounting the PRODUCT by ten capabilities no user could
invoke.

So each row now carries `reach`, and `UNREACHED` names what nothing can invoke.
`services/api/test_recipe_reach.py` derives that set from the tree and fails when this file disagrees,
so the honest form of the claim cannot rot back into the confident one.

**MEP-AUTOCONNECT then found the correction had a second layer.** Two of the ten — `auto_connect_mep`
and `set_system_predefined` — were wired and are now `ui`. The third, `add_sprinkler`, turned out never
to have been a gap: `add_fire_equipment(kind="sprinkler")` authors the identical element and has
shipped on a button all along. It is in `SUPERSEDED`, not `UNREACHED`, and the difference is not
bookkeeping. *A reachability sweep answers "does anything call this?", which is one question short of
"can a user do this?" — the same shape of mistake this file was written to fix, one layer further in.
Listing a duplicate among the gaps understates coverage and invites work that would ship a second
control for an outcome users already had.*
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
    "add_connection_assembly": ("create-structure", "connection plate+bolts + IfcRelConnectsWithRealizingElements"),
    "add_roof": ("create-enclosure", "IfcRoof"), "add_covering": ("create-enclosure", "IfcCovering"),
    "add_roof_window": ("create-enclosure", "IfcWindow (SKYLIGHT) voiding a roof"),
    "add_railing": ("create-enclosure", "IfcRailing"), "add_curtain_wall": ("create-enclosure", "IfcCurtainWall"),
    "add_stair": ("create-enclosure", "IfcStair"), "add_ramp": ("create-enclosure", "IfcRamp"),
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
    "set_profile_dims": ("edit", "resize an extruded profile in place"),
    "set_wall_thickness": ("edit", "wall thickness (profile XDim sugar)"),
    "set_wall_slope": ("edit", "sloped-top wall"), "add_opening": ("edit", "void a host"),
    "rename_storey": ("edit", "rename level"), "set_storey_elevation": ("edit", "move level"),
    # --- groups / types / arrays ---
    "create_type": ("type", "IfcTypeProduct"), "edit_type": ("type", "edit type params"),
    "place_type": ("type", "type occurrence"), "create_group": ("group", "IfcGroup"),
    "create_assembly": ("group", "IfcElementAssembly"), "array_element": ("group", "linear/grid array"),
    "set_array_params": ("group", "re-edit a placed array's count/pitch"),
    "assign_material_set": ("data", "IfcMaterialLayerSet"),
    # --- data / classification / detailing ---
    "classify": ("data", "IfcClassificationReference"), "set_classification": ("data", "classification"),
    "set_element_pset": ("data", "Pset property"), "set_pset_on_class": ("data", "Pset (by class)"),
    "reset_prop_to_type": ("data", "Reset property to type"),
    "resolve_wall_joins": ("edit", "butt-join L/T wall joins"),
    "set_props_by_guid": ("data", "Pset batch (XLSX round-trip)"),
    "purge_orphan_psets": ("maintenance", "purge orphaned property sets"),
    "purge_empty_groups": ("maintenance", "purge empty groups"),
    "rebase_origin": ("maintenance", "shift model origin (georeference-preserving)"),
    "convert_length_unit": ("maintenance", "convert the project length unit"),
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

# Recipes the engine can run that NO surface invokes — derived by `test_recipe_reach.py`, which fails
# if this disagrees with the tree. Each is implemented and tested; each is simply not reachable, which
# is a different fact from "not built" and a more useful one. Listing a recipe here is a DECISION that
# it stays internal for now, not a place to park work: the gate makes the decision visible.
#
#   add_connection_assembly  steel connection plate + bolts + IfcRelConnectsWithRealizingElements
#   batch_tag                stamp a Pset value across many elements at once
#   convert_length_unit      project length unit (mm/m/ft), rescaling so real size is unchanged
#   derive_representations   coarse Box/Axis/FootPrint views derived from Body geometry
#   place_type               place an occurrence of an existing IfcTypeObject
#   program_fit              headcount program -> zoned + auto-furnished spaces
#   purge_empty_groups       delete groups with no members — GET /model/maintenance reports what it
#                            WOULD remove and offers no way to remove it
#   purge_orphan_psets       delete property sets attached to nothing — same dry-run-only story
#   rebase_origin            shift the model origin, preserving georeferencing
#   reset_prop_to_type       drop an instance override so the type value shows through — the UI ships
#                            `set_element_pset`, which is the OTHER half of that pair
#   resolve_wall_joins       butt L/T wall joins — `analysis.py` DETECTS them and names this as the
#                            resolution, which nothing can invoke
#   set_spec_link            stamp the Pset_Massing_SpecLink breadcrumb
#
# Three of these — add_sprinkler, auto_connect_mep, set_system_predefined — were already found by
# SCALE-SEAM (93) and recorded in a doc comment in `apps/web/src/api/mep.ts`: "referenced NOWHERE in
# apps/web/src. Backend recipes with no web exposure at all. Recorded, not fixed." That note was right
# and had no way to stay right. It is now a check.
#
# MEP-AUTOCONNECT then took all three off the list, and only two of them by wiring. `auto_connect_mep`
# and `set_system_predefined` are now typed client methods invoked from the MEP systems panel. The
# third is the finding: **`add_sprinkler` was never a missing capability.** See SUPERSEDED below.
#
# SKYLIGHT took `add_roof_window` off the list (2026-09-05). It was the entry whose own description
# named its counterpart — "the roof counterpart of the wired add_door/add_window" — and the engine
# function's docstring says the same thing from the other side: "the flat-roof counterpart of the
# wall-hosted add_opening". *Two descriptions, written independently, both said a shipped tool had a
# missing twin; neither was a check, so the asymmetry sat there.* It is now on the envelope section
# beside the curtain wall.
# DOCSTRING-REACH (2026-09-05) added SIX to this list without anything being un-wired, because the
# gate had been counting a DOCSTRING as a caller. `test_recipe_reach.py` stripped `#`, `//` and
# `/* */` on the principle that "a mention in a comment is not a call" — and a Python docstring is a
# string literal, so it survived. Every one of the six was a ROUTE DESCRIBING what to POST:
# `authoring.py` ("recipe: set_pset | batch_tag | place_type"), `authoring_docs.py` (a dry-run
# maintenance report naming the cleanup recipes), `analysis.py` and `authoring_analysis.py`.
#
# *The principle was right and the implementation covered one of the two ways this tree writes
# prose. A gate can state the correct rule and still measure the wrong set — which is the same shape
# as the defect this whole file exists to catch, one level down.*
#
# WALL-JOINS (2026-09-06) then checked the sentence DOCSTRING-REACH ended on — *"four of the six are
# a product gap of a familiar kind: the DIAGNOSIS ships and the REPAIR does not"* — against the
# screen rather than the server, and it was right about ONE of the four:
#
#   | recipe                | diagnosis on screen | repair on screen | the claim |
#   |-----------------------|---------------------|------------------|-----------|
#   | `purge_orphan_psets`  | yes                 | **yes**          | wrong — the repair ships |
#   | `purge_empty_groups`  | yes                 | **yes**          | wrong — the repair ships |
#   | `resolve_wall_joins`  | **no**              | no               | wrong — the diagnosis is dark too |
#   | `set_spec_link`       | yes                 | no               | correct |
#
# **The two purges were never unreachable.** `apps/web/src/viewer/tools/qaSection.ts` has shipped a
# per-row *Purge* button in "Model cleanup (maintenance)" all along. It POSTs `row["recipe"]` — a
# name the SERVER handed it, from `ifcpatch_lib.scan` — so the string appears as a literal only in
# the engine file the gate excludes as a catalog, and `callers()` could not see it. That exclusion is
# right for a dispatch TABLE and wrong for a capability ADVERTISEMENT, and the two live in the same
# file. `test_recipe_reach.py` now reads `ifcpatch_lib.RECIPES` as a third reach source beside
# `RECIPE_SPECS`, and checks it against what `scan()` actually returns rather than against the tuple.
#
# *This is the THIRD shape of the same false positive — a check reading the registry's own
# description of itself. First comments, then docstrings, now a name the server sends as DATA. What
# is common is not the syntax: it is that "reachable" was being decided by grepping for the name,
# and a dispatch by value has no name to grep.*
#
# **`resolve_wall_joins` was the opposite error, and worse for being in the same sentence.** The
# roadmap said `analysis.py` "detects L/T wall joins and names a resolution nothing can invoke",
# which reads as half a feature shipping. `GET /model/wall-joins` and `api.wallJoins` both existed —
# and `api.wallJoins` sat on the uncalled-method ratchet in `apps/web/src/api/clientCallers.test.ts`
# with no caller anywhere in the app. *A route and a client method are two thirds of a feature, and
# counting either one reports it as shipped.* Both halves are now one QA tool: scan, list the joins
# (clicking one selects both walls by GlobalId), butt-join, re-scan to confirm.
# MODEL-SETUP took `convert_length_unit` and `rebase_origin` out of this set on 2026-09-08. Both had
# been in the RECIPES registry — and so runnable through `POST /projects/{pid}/edit` — the whole
# time; what was missing was a control, and the reason one could not simply be added is worth keeping:
# **nothing exposed the current state.** "Convert to millimetres" without saying what the units are
# now is a coin flip the user is asked to call, so `GET /projects/{pid}/model/setup` came first and
# the panel reads before it offers. `rebase_origin` is the sharper of the two — it shifts the site
# placement AND pushes the same offset into the IfcMapConversion, which is this project's stated
# georeferencing rule, implemented correctly and reachable by nobody.
UNREACHED: frozenset[str] = frozenset({
    "add_connection_assembly", "batch_tag", "derive_representations",
    "place_type", "program_fit", "reset_prop_to_type", "set_spec_link",
})

# Recipes that nothing invokes AND nothing should: a reachable recipe already authors the identical
# result, so wiring these would put a second control behind the same outcome. This is a distinct verdict
# from UNREACHED — that one says "a capability no user can reach", which is a defect; this one says
# "a duplicate spelling of a capability users already have", which is not.
#
# The distinction is the whole point of separating the two sets. A reachability sweep answers "does
# anything call it?" and stops there; it cannot tell a gap from a synonym, so it reports both as gaps
# and invites work on the synonym. `test_recipe_reach.py` asserts the equivalence itself — the IFC
# class, predefined type, system and discipline both recipes land on — so an entry here stops being
# true the moment the two stop agreeing, and the recipe falls back to being a real gap.
SUPERSEDED: dict[str, str] = {
    # add_fire_equipment(kind="sprinkler") resolves through the same add_mep_terminal to the same
    # IfcFireSuppressionTerminal/SPRINKLER on the same "Fire Protection" system with discipline "fire",
    # and has been on the viewer's 🧯 button since MEP-FP.
    "add_sprinkler": "add_fire_equipment",
}

_CATEGORY_ORDER = ["create-structure", "create-enclosure", "create-opening", "create-space",
                   "create-mep", "create-content", "annotate", "edit", "edit-mep", "type", "group",
                   "data", "lifecycle", "analysis", "uncategorized"]


def matrix() -> dict[str, Any]:
    """The live authoring-coverage matrix from `edit.RECIPES` + the category map."""
    from aec_data import edit, nlauthor  # type: ignore

    recipes = sorted(edit.RECIPES.keys())
    specs = set(nlauthor.RECIPE_SPECS)          # what the CAD line + AI planner can dispatch
    rows = []
    by_cat: dict[str, list[dict[str, str]]] = {}
    for name in recipes:
        cat, produces = _MAP.get(name, ("uncategorized", ""))
        # `cad+ai` reaches the command line and the planner; `ui` is invoked by a panel, a router or
        # MCP; `superseded` is authored identically by a reachable recipe; `none` means the engine can
        # run it and nothing asks it to. `superseded` is checked BEFORE `none` on purpose: both are
        # uncalled, and reporting a duplicate as a gap is what invites someone to close it.
        if name in specs:
            reach = "cad+ai"
        elif name in SUPERSEDED:
            reach = "superseded"
        elif name in UNREACHED:
            reach = "none"
        else:
            reach = "ui"
        row = {"recipe": name, "category": cat, "produces": produces, "reach": reach}
        if reach == "superseded":
            row["superseded_by"] = SUPERSEDED[name]
        rows.append(row)
        by_cat.setdefault(cat, []).append(row)
    ordered = {c: by_cat[c] for c in _CATEGORY_ORDER if c in by_cat}
    for c in by_cat:                                   # any category not in the order list, appended
        ordered.setdefault(c, by_cat[c])
    return {
        "recipe_count": len(recipes),
        "category_count": len(ordered),
        "cad_ai_count": len(specs),
        "unreached_count": len(UNREACHED),
        "unreached": sorted(UNREACHED),
        "superseded_count": len(SUPERSEDED),
        "superseded": {k: SUPERSEDED[k] for k in sorted(SUPERSEDED)},
        "uncategorized": [r["recipe"] for r in by_cat.get("uncategorized", [])],
        "by_category": {c: {"count": len(v), "recipes": v} for c, v in ordered.items()},
        "note": ("Live from the edit.RECIPES registry — a newly-added recipe appears here automatically "
                 "(uncategorized until mapped). Every recipe is a GUID-stable server-side pass. What "
                 "can INVOKE one differs per recipe and is stated per row: `cad+ai` is dispatchable "
                 f"from the CAD command line and the AI planner ({len(specs)} of {len(recipes)}, the "
                 "curated nlauthor.RECIPE_SPECS); `ui` is invoked by a panel, a router or MCP; "
                 "`superseded` means nothing calls it and nothing should, because a reachable recipe "
                 "authors the identical result; `none` means the engine can run it and no surface asks "
                 "it to — the only one of the four that is a gap."),
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
           "Every recipe is a GUID-stable server-side pass. **What can invoke one differs per recipe**, "
           "and the Reach column says which: "
           f"`cad+ai` — dispatchable from the CAD command line and the AI planner "
           f"({m['cad_ai_count']} of {m['recipe_count']}, the curated `nlauthor.RECIPE_SPECS`); "
           "`ui` — invoked by a tool panel, a router or MCP; "
           "`superseded` — nothing calls it and nothing should, a reachable recipe authors the same "
           "result; `none` — the engine can run it and no surface asks it to.",
           ""]
    if m["unreached"]:
        out += [f"> ⚠ **{m['unreached_count']} recipes are reachable from no surface**: "
                + ", ".join(f"`{r}`" for r in m["unreached"])
                + ". They are implemented and tested; they are not something a user can invoke, so "
                  "they are not coverage. Pinned by `services/api/test_recipe_reach.py`.",
                ""]
    if m["superseded"]:
        out += ["> **Superseded** — uncalled, and correctly so: "
                + ", ".join(f"`{k}` → `{v}`" for k, v in m["superseded"].items())
                + ". A reachable recipe authors the identical result, so these are duplicate spellings "
                  "rather than gaps. The equivalence is asserted in "
                  "`services/api/test_recipe_reach.py`, so an entry stops being true if the two "
                  "recipes stop agreeing.",
                ""]
    for cat, data in m["by_category"].items():
        out.append(f"### {cat} ({data['count']})")
        out.append("")
        out.append("| Recipe | Produces | Reach |")
        out.append("| --- | --- | --- |")
        for r in data["recipes"]:
            out.append(f"| `{r['recipe']}` | {r['produces'] or '—'} | {r['reach']} |")
        out.append("")
    if m["uncategorized"]:
        out.append(f"> ⚠ Uncategorized (add to the map in `authoring_matrix.py`): "
                   f"{', '.join(m['uncategorized'])}")
        out.append("")
    return "\n".join(out)
