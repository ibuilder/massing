# Authoring the model

Massing is a modeling program, not a viewer with an edit button. You can start from a blank IFC and
draw a building; you can also open somebody else's IFC and edit it without breaking their GUIDs.

## The one rule that explains the design

**Every element is addressed by its IFC GlobalId (GUID), and edits are applied server-side by named
recipes.** The browser never rewrites IFC.

That sounds like an implementation detail. It is the reason the rest of the platform works:

- A pin, an RFI, a cost line and a schedule activity can all point at the same wall — and still point
  at it after you move the wall.
- Two people can edit and the result is diffable by GUID.
- An estimate can be re-run against a changed model and every delta attributed to an element.

Viewer IDs are transient and are never used to identify anything durable.

## Starting a model

**New model** creates a blank IFC with levels and a grid datum — a real project, not an empty scene.
You can also start from a template, or from a generated massing (see [Generating a building](#generating-a-building-from-a-zoning-envelope)).

Manage levels as you go; the level a thing belongs to is part of its IFC identity, not a display filter.

## Drawing

The **Draft** toolkit draws real IFC. What you can place:

| Category | Elements |
| --- | --- |
| Structure | Walls (including **sloped-top** parapet, shed and gable), columns, slabs, steel connections, rebar cages |
| Openings | Doors, windows, curtain walls |
| MEP | Ducts, pipes and fittings with **port-to-port connectivity** |
| Site | Logistics, furniture, landscaping from the content library (auto-classified) |

**Drawing inference** snaps automatically — on-axis, parallel, perpendicular — so lines land where you
meant rather than where you clicked.

### The CAD command line
An AutoCAD-style command line, for people whose hands already know it:

```
WALL 0,0 5,0 3        draw a wall from (0,0) to (5,0), 3m high
COLUMN 2,2            place a column
```

With aliases, history, and spacebar-repeat. There is also an **AI command bar** — describe what to
build in plain English and it produces a *validated plan* you approve before anything is written.

### Editing what is there
- **◈ Edit in place** — drag an element to move it. GUID preserved.
- **Model undo/redo** — versioned and GUID-stable, not a viewport undo.
- **Groups and arrays**, **phasing**, **LOD dialing (100 → 500)**.
- **Model browser** — group by discipline or storey, search, build selection sets.

## Families and types

Massing places **types** (`IfcTypeProduct`), not meshes. A family is an IFC type carrying a mapped
representation; placing it instances an occurrence that shares that representation.

This is why a family swap updates every instance, and why the file does not grow linearly with
placements. Full detail in [families.md](../families.md); `families/` in the repo is an empty drop-in
directory for curated or manufacturer content.

## Guardrails

**`/edit/precheck`** rejects edits that would produce broken IFC *before* anything is written. An
authoring tool that lets you save an invalid model has moved the failure to whoever opens it next.

There are two escape hatches for cases the recipes do not cover — a **procedural mesh**
representation, and an **AST-sandboxed ifcopenshell** execution path. The sandboxed path is
**feature-flagged off** by default. Treat it as a power tool: a denylist cannot see every method
reachable through an injected object, so it is gated rather than trusted.

## Generating a building from a zoning envelope

`POST /projects/{id}/generate/massing` turns a site's zoning constraints into a real IFC massing model
*and* an acquisition proforma. `POST /generate/massing/preview` does the program and proforma
statelessly, writing no model — useful for screening sites.

This is the "generate, then model by hand" path: the generator gets you a defensible starting envelope,
and the Draft tools take it from there.

## Bringing in other geometry

| Input | Becomes |
| --- | --- |
| DXF floor plan | **2D → BIM**: IFC walls + spaces |
| Point cloud (PCD/XYZ/LAS/LAZ) | **Scan-to-BIM deviation**: as-built vs model surface, % within tolerance + heatmap |
| Meshes (OBJ/STL/PLY/glTF) | Georeferenced reference overlay |
| GIS (GeoJSON vectors, GeoTIFF DEM) | Terrain and site context overlay |

Reference overlays are exactly that — context, not model elements.

### Georeferencing
Massing keeps **real coordinates for export** while rendering near the scene origin. Set-origin and CRS
handling exist because a model rendered at its true survey coordinates has floating-point precision
problems, and a model that loses them cannot be exported for survey or GIS use. Both requirements are
real, so they are handled separately rather than compromised.

## Federation and coordination

Layer and align multiple models, then run **federated cross-discipline clash** — AABB broad phase, mesh
boolean narrow phase, exact penetration volume. Clashes become **BCF topics**, so they round-trip with
any BCF-compatible openBIM tool rather than being trapped here.

## Checking your work

| Check | What it tells you |
| --- | --- |
| **IDS validation** (ifctester) | Does the model satisfy an information requirement? Failing elements highlight. |
| **Model QA** | Structural completeness and data-health scoring. |
| **Code pre-check** | IBC occupancy load and egress capacity, edition-aware, IBC-cited. |
| **Decision readiness** | Ranked gaps that will *become* RFIs if you issue the set as-is. |
| **MEP connectivity** | Port-to-port connectivity plus a dangling-element report. |

The canonical proof of the round-trip: IDS flagged 299 slabs missing `LoadBearing`; the authoring
round-trip edited them; republish; IDS re-validated **PASS (299/299)** with the slab's pin GUID
unchanged.

## Where authoring runs, and why

The browser renders, selects, snaps and drafts. Python (ifcopenshell) writes IFC. Massing is a thin
offline-capable client over a Python authoring service, deliberately — not a fat in-browser CAD kernel.
The reasoning is in [client-vs-server.md](../client-vs-server.md).

Two consequences worth knowing:
- IFC is **pre-converted to Fragments on the server**; the browser never parses full IFC at runtime.
- Geometry and metadata travel separately — geometry streams as `.frag`, data comes from the API.

## Reference

- [authoring-matrix.md](../authoring-matrix.md) — every recipe and its coverage. Generated from
  `edit.RECIPES`; re-run the generator rather than editing it.
- [reference/api.md](../reference/api.md) — the authoring endpoints.
- [mcp.md](../mcp.md) — driving authoring from an AI agent, through the same gated engines the UI uses.
