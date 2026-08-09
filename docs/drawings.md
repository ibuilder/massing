# Drawings and sheets — how a model becomes a drawing set

*For contributors adding a view kind, debugging a sheet, or wiring a new drawing endpoint. Companion
to [client-vs-server.md](client-vs-server.md): drawing generation is entirely server-side, and this
doc explains what runs where inside that half.*

Everything below was measured against the tree at v0.3.913, not summarised from memory. Where the
code and this page could drift, the enforcing test is named — prose is not a check.

---

## The one-paragraph version

A drawing is **derived from the IFC**, never captured from the screen. The model is baked once into
triangle meshes, each keeping its `GlobalId`; a *view* is a geometric operation over those meshes
(cut, project, silhouette) that yields polylines; a *sheet* places views into a page layout with a
titleblock; a *renderer* writes that layout as SVG, DXF or PDF. Because every stage carries the
GlobalId through, a drawing is clickable and reconcilable against the model — which is the whole
reason it is not a screenshot.

```
 IFC ──bake()──► meshes [(guid, ifc_class, trimesh)]
                    │
                    ├─ cut_baked()          → plan / section polylines
                    ├─ elevation_outlines() → elevation silhouettes (depth-sorted)
                    └─ axon_outlines()      → axonometric silhouettes (depth-sorted)
                    │
                    ▼
              compose()  or  compose_viewports()      ← TWO composers; see below
                    │
                    ▼
              layout dict
                    │
      ┌─────────────┼─────────────┐
      ▼             ▼             ▼
render_sheet_svg  _dxf   render_sheet_pdf
```

`bake()` is the expensive stage and is cached (`bake_cache_stats()` reports hits). Everything
downstream is cheap by comparison, so a sheet with six views costs about what a sheet with one does.

---

## Endpoints

All under `/projects/{pid}/drawings/`.

| Endpoint | Returns |
|---|---|
| `storeys` | the levels available to draw |
| `plan.svg` · `section.svg` · `elevation.svg` | a single view |
| `plan.dxf` · `section.dxf` · `elevation.dxf` | the same, as CAD linework |
| `sheet.svg` · `sheet.dxf` · `sheet.pdf` | a composed sheet with titleblock |
| `{drawing_id}/revise` | issue a revision |

The `sheet.*` endpoints take `sheet` (number, e.g. `A-101`), `page`, `purpose`, `rev` and `scale`.
**They do not take view specs** — the views are chosen server-side by `default_sheet()`, which samples
up to four storeys evenly plus a section and an elevation. A caller cannot currently say *which*
views it wants; see [ADR-001](internal/adr-001-sheet-composition.md).

Pages are `A4`, `A3` (default) and `A1`, in points — `PAGES` in
[`services/data/src/aec_data/drawings.py`](../services/data/src/aec_data/drawings.py).

---

## The view-spec vocabulary

A view is requested as a plain dict. The `kind` selects the geometry operation; the other keys are
per-kind.

```jsonc
{"kind": "plan",      "elevation": 0.0, "cut_height": 1.2, "title": "PLAN L1"}
{"kind": "section",   "axis": "x", "offset": 12.5,         "title": "SECTION A-A"}
{"kind": "elevation", "direction": "north",                "title": "NORTH ELEVATION"}
{"kind": "axon",      "azimuth": 45, "elevation_angle": 35.264, "title": "ISO VIEW"}
```

`compose_viewports()` accepts three more keys, which are what make a sheet a real paper-space sheet
rather than a grid of pictures:

```jsonc
{"rect":    [0.5, 0, 0.5, 1],   // fractions of the drawable area
 "scale":   100,                 // 1:100 on paper — CROPS to the rect, does not shrink to fit
 "classes": ["IfcWall"]}         // per-viewport class freeze (structure-only, MEP-only…)
```

### Three traps in this vocabulary

**1. `elevation` means three different things.** A storey height on a plan
(`{"kind":"plan","elevation":0.0}`), a view direction as a kind (`{"kind":"elevation"}`), and a
projection angle — which is why the axonometric's angle had to be called `elevation_angle`. Note also
that the *spec key* is `azimuth`/`elevation_angle` while the *function parameters* on
`axon_outlines()` are `azimuth_deg`/`elevation_deg`. Read the call site, not the neighbouring key.

**2. An unknown `kind` currently renders a PLAN.** `_view_for_spec()` branches on `section`, then
`elevation`, then falls through. Measured at v0.3.913:

```
spec kind='plan'   ->  label='PLAN'      sub='cut @ 1.20 m'
spec kind='axon'   ->  label='ISO VIEW'  sub='cut @ 1.20 m'    ← a plan, titled ISO VIEW
```

The title comes from the caller, so a sheet can **say one thing and draw another**. This is a known
defect with a decision recorded against it — [ADR-001](internal/adr-001-sheet-composition.md),
action items 1–2. Do not rely on the fall-through.

**3. An axonometric has no paper scale.** It must report `NTS` and must not claim a
denominator — a scale bar on an axonometric is a false statement on a document an engineer may seal.
Enforced by [`services/api/test_axon_view.py`](../services/api/test_axon_view.py).

---

## The two composers

This is the subsystem's one real architectural wrinkle, and it will bite you if you add a view kind.

| | `drawings.compose()` | `sheet_layout.compose_viewports()` |
|---|---|---|
| layout | uniform fit-to-cell grid (`cols`) | paper-space viewports (`rect`, `scale`, `classes`, clipping) |
| dispatch | `_view_for_spec()` | `_view_polys()`, falling back to `_view_for_spec()` |
| knows `axon` | **no** | **yes** |
| used by | `sheet.svg` · `sheet.dxf` · `sheet.pdf` | the sheet-regions endpoint, presets |

`sheet_layout.py` describes itself as *"the mature endpoint of that idea"* and is five weeks newer,
but the three user-facing sheet routes still run the older grid composer. **A view kind added only to
`_view_polys` is invisible to every shipping sheet route** — which is exactly how `axon` came to work
in one path and silently render a plan in the other.

**If you are adding a view kind:** put it in `_view_for_spec()`, the shared helper, so both composers
see it. Full reasoning and the decision on whether to unify the two:
[ADR-001](internal/adr-001-sheet-composition.md).

---

## Rules that are not negotiable here

- **GlobalId survives every stage.** `bake()` emits `(guid, ifc_class, mesh)` and each outline keeps
  its guid through projection. This is the CLAUDE.md non-negotiable — elements are referenced by
  GUID, never by transient viewer ids — and it is what lets a sheet view be selected, keynoted and
  reconciled. A stage that drops the guid has broken the product, not just the drawing.
- **Drawings are derived, not captured.** There is no raster path in
  [`drawings_render.py`](../services/data/src/aec_data/drawings_render.py) and adding one should be
  argued for explicitly: a captured image has no GlobalIds, so it cannot be clicked, scheduled or
  checked against the model.
- **An incomplete drawing must say so.** `axon_outlines()` logs a warning naming how many silhouettes
  were skipped and calls the result INCOMPLETE. A drawing that is missing elements while looking
  finished is the worst artefact this subsystem can produce.

---

## Where things live

| Concern | File |
|---|---|
| bake, cuts, projections, `compose`, `sheet` | [`services/data/src/aec_data/drawings.py`](../services/data/src/aec_data/drawings.py) |
| SVG / DXF / PDF writers | [`services/data/src/aec_data/drawings_render.py`](../services/data/src/aec_data/drawings_render.py) |
| paper-space viewports | [`services/data/src/aec_data/sheet_layout.py`](../services/data/src/aec_data/sheet_layout.py) |
| routes | [`services/api/src/aec_api/routers/drawings.py`](../services/api/src/aec_api/routers/drawings.py) |
| drawing set / index | [`services/api/src/aec_api/drawingset.py`](../services/api/src/aec_api/drawingset.py) |

**Tests to read before changing any of it** — each encodes a rule this page only describes:
[`test_axon_view.py`](../services/api/test_axon_view.py) (projection correctness, GUID survival, NTS),
[`test_sheet_layout.py`](../services/api/test_sheet_layout.py) (fixed scale, clipping, class freeze),
[`test_sheet_recover.py`](../services/api/test_sheet_recover.py) (degenerate input).
