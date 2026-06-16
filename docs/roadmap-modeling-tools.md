# Roadmap — Modeling tools in the viewer toolbar

Goal: add authoring tools (walls, slabs, roof, columns, openings, spaces) to the floating
viewer toolbar, so users can sketch/edit BIM geometry without leaving the web viewer — while
keeping **IFC as the source of truth** and **never parsing/authoring full IFC in the browser
at runtime** (per CLAUDE.md non-negotiables).

## Architecture decision: author server-side, stream Fragments back
The browser is a *viewer + sketch surface*, not the geometry kernel. The toolbar collects
intent (a polyline + height for a wall, a boundary for a slab) and POSTs lightweight
parameters to the API. The API uses **ifcopenshell.api** (already a dependency, see
`services/api`) to mutate the project IFC, re-runs the IFC→.frag conversion for the touched
storey, and streams the updated Fragments tile back. This reuses the existing conversion +
publish pipeline and guarantees the .frag the user sees is derived from real IFC.

Heavier parametric edits (families, complex sweeps) route to the **Blender + Bonsai** desktop
editor over the existing Bonsai-MCP bridge — gated, save-first, chunked (per CLAUDE.md).

```
toolbar (sketch params) ──POST /authoring/{type}──► ifcopenshell.api mutate IFC
        ▲                                                   │
        └────────── stream updated .frag ◄── IFC→.frag (touched storey only)
```

## Tool set (phased)

### Phase A — primitives (parametric, server-authored)  ✅ DONE
Implemented as `ifcopenshell.api` recipes in `services/data/src/aec_data/edit.py`, invoked
through the existing `POST /projects/{id}/edit` (+ background republish) — *not* per-type
endpoints. Each has a viewer tool in the floating toolbar (ground-click capture → params →
author → reload). Verified at the data layer on `basichouse.ifc`.

| Tool | Gesture | Recipe | IFC entity | Status |
|------|---------|--------|-----------|--------|
| Wall | 2 clicks + height/thickness | `add_wall` | `IfcWall` (rect profile, rotated extrusion) | ✅ |
| Slab | polygon + thickness | `add_slab` | `IfcSlab` (arbitrary profile) | ✅ |
| Column | 1 click + height | `add_column` | `IfcColumn` | ✅ |
| Beam | 2 clicks + depth | `add_beam` | `IfcBeam` (horizontal sweep) | ✅ |
| Roof | polygon + thickness | `add_roof` | `IfcRoof` (flat; **pitch = future**) | ✅ |
| Space | pick boundary | (room tags) | `IfcSpace` (+ quantities) | partial (existing) |

### Phase B — editing & openings  *(delete + openings done; move/rotate next)*
- **Delete by GUID** ✅ — `delete_element` recipe (`root.remove_product`, drops placement /
  representation / voids); viewer **Delete** tool acts on the current selection.
- **Door / window placement** ✅ — `add_door` / `add_window` recipes create an
  `IfcOpeningElement` that voids the host wall (`feature.add_feature`) and an `IfcDoor`/
  `IfcWindow` that fills it (`feature.add_filling`). Viewer tools act on the selected wall.
  Centered for now (positioning along the wall + swing/hand are future). Verified at the data
  layer: door 8→9 with +1 void/+1 fill; window 19→20.
- **Move / rotate by GUID** ✅ — `move_element` (E/N/Z metre delta) and `rotate_element`
  (degrees about Z) edit the world placement via `geometry.edit_object_placement(is_si=True)`;
  viewer Move (✥) / Rotate (⟲) tools act on the selection. Verified: wall moves
  (2.5,0,0)→(4.5,1,0) m, column rotates 45°.
- **Per-element Pset edit** ✅ — `set_element_pset` (pset/prop/value/dtype on one GUID);
  viewer **Edit property** (✎) tool. Verified: FireRating → "2HR" round-trips.
- **Copy** *(deferred)* — `root.copy_class` gives a new GUID + independent placement but
  doesn't copy the representation; deep-copy rendered empty and sharing broke the original's
  geometry in the python geom iterator. Needs proper representation duplication, verified via
  the web-ifc converter (what actually renders) rather than the geom iterator.

> **Unit fix (this phase):** all authoring recipes now build placement matrices in **metres**
> and let `edit_object_placement(is_si=True)` convert to file units. Previously they divided by
> the unit scale *and* the API converted again, placing geometry 1000× too far on mm-unit IFCs
> (e.g. basichouse) — invisible/unusable. Entity-count tests missed it; position checks caught it.

### Phase C — drafting aids (client-only, no IFC write)
- Snap (endpoint / midpoint / grid / intersection), ortho lock, temp dimensions.
- Section box / clip plane (the ✂ tool already exists — extend to a 6-face box).
- Grids & levels overlay (read from `IfcGrid` / storey elevations already parsed).
- Measure (already shipped: ↔ distance, ▱ area).

### Recommended additional tools (industry parity — Bonsai/Revit/Navisworks)
- **Type/family picker** (wall types, slab assemblies) backed by a server-side type library.
- **Align / array / mirror** transforms.
- **Quantities live readout** (the energy/MEP + quantity engine already exists; surface inline).
- **Clash re-run on edit** (mesh clash engine exists — trigger after an authoring write).
- **Undo/redo** as a server-side IFC change stack keyed by GUID (BCF-style change log so it
  round-trips). Pairs with the existing change-order / pin model.

## Toolbar UX
- Add an **authoring group** to the floating `#viewer-tools` palette, separated from the
  existing nav/measure/section/iso/clash icons. Gate it behind the `editor`/`admin` capability
  role (RBAC) — viewers/reviewers don't see write tools.
- Each tool: click icon → enter sketch mode → on-canvas hints → confirm → server write →
  optimistic Fragments reload with a `withLoading` overlay + toast.

## Dependencies / risks
- `ifcopenshell.api` authoring is in place; extend, don't re-architect.
- Per-edit full-model re-conversion is too slow on mega-models → convert only the touched
  storey/subset and merge tiles. Validate against the Phase 2 large-model target.
- Preserve georeferencing/origin on every write (render near origin, store real coords).
- Bonsai-MCP `execute_blender_code` runs arbitrary Python → keep gated, save-first, chunked.
