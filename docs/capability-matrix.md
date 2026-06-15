# Capability matrix — this platform vs. Bonsai / Revit / Navisworks

Maps the BIM Software Capability Matrix to what this open platform implements. **Built** =
working + verified here; **Bridge** = via the Blender/Bonsai desktop editor (Phase 6);
**Paid** = optional Autodesk APS; **Out of scope** = not pursued.

| Capability | Bonsai | Revit | Navisworks | **This platform** |
|---|---|---|---|---|
| **MODELING & AUTHORING** | | | | |
| Parametric model authoring | Yes | Native | No | **Bridge** (Blender+Bonsai via Bonsai-MCP) |
| Native IFC authoring (model IS IFC) | Native | No | No | **Built (headless)** — `ifcopenshell.api` recipes + `/edit` round-trip; **Bridge** for GUI |
| Parametric families / components | Partial | Native | No | **Built** — `place_type` recipe instantiates IFC types; `families/` libraries; **Bridge** for parametric authoring |
| Parametric stairs/roofs/complex | Yes | Yes | No | **Bridge** |
| **DOCUMENTATION** | | | | |
| Construction drawings (plans/sections) | Partial | Native | No | **Built** — IFC section-cut → SVG plans (per storey) + sections |
| Schedules / takeoff tied to model | Yes | Yes | Yes | **Built** — QTO + generic schedule export |
| Sheet sets & title blocks | Partial | Yes | No | **Built** — sheet composer (multi-view + title block) → SVG + PDF |
| **COORDINATION & REVIEW** | | | | |
| Model federation (combine models) | Partial | Partial | Native | **Built** — multi `.frag` load, per-model layers |
| **Clash detection** | Yes | Partial | Native | **Built** — AABB broad + **mesh narrow phase** (exact penetration volume), → BCF clash topics |
| Markup / redline / viewpoints | Partial | Partial | Yes | **Built** — BCF pins/viewpoints, restore |
| Real-time nav of huge models | Yes | Partial | Yes | **Built** — Fragments streaming + culling |
| **4D / 5D** | | | | |
| 4D scheduling | Yes | Partial | Native | **Built** — activity↔element mapping, timeline data |
| 5D quantification / cost | Yes | Partial | Yes | **Built** — QTO + cost-code map + geometry fallback |
| **ANALYSIS & QA** | | | | |
| Structural / load visualization | Yes | Yes | No | **Built (partial)** — color-by-data overlay |
| Energy / MEP systems analysis | No | Yes | No | Out of scope |
| **IDS / model validation (QA)** | Yes | Partial | Partial | **Built** — ifctester, → highlight failures |
| Photorealistic rendering | Yes | Partial | Yes | **Bridge** (Blender render engine) |
| **INTEROP & AUTOMATION** | | | | |
| IFC import/export | Native | Yes | Yes | **Built** — IFC→Fragments; BCF in/out |
| Vendor-neutral / openBIM | Yes | No | No | **Built** — IFC + BCF + IDS throughout |
| Scripting / API | Yes | Yes | Partial | **Built** — FastAPI + Python; MCP bridge |
| **COLLABORATION & COST** | | | | |
| Multi-user / cloud collab | Partial | Yes | Partial | **Built** — server API + project-scoped RBAC (viewer/reviewer/editor/admin), audit log; Postgres/MinIO stack |
| Licensing | Free | Paid | Paid | **Free / open** (GPL editor kept separate) |

## Verified this round
- **Clash detection** (`services/data/.../clash.py`): bakes world geometry via the
  IfcOpenShell iterator, vectorized AABB overlap between IFC-class groups. On the structural
  sample: 2783 broad-phase candidates; 42 significant (≥0.05 m³); top = pile-cap × column
  0.477 m³. `POST /projects/{id}/clash?...&create_topics=true` turns clashes into BCF
  **clash topics** (pins/issues). Verified in UI: 30 clash topics listed alongside the RFI.
- **IDS validation** (`services/data/.../validate.py`): ifctester against an uploaded `.ids`
  or built-in default specs. On the sample: Columns-have-a-Name 203/203 pass; Slabs-declare-
  LoadBearing 0/299 fail. `POST /projects/{id}/validate`. Verified in UI: result summary +
  "Highlight 299 failures" → failing slabs highlighted green in 3D.

## Honest gaps (next, all open-source)
- ~~Clash narrow phase~~ ✅ done — trimesh + manifold3d boolean intersection gives exact
  penetration volume per pair; the API/UI now report `method: "mesh"`.
- ~~2D plans/sections~~ ✅ done — `drawings.py` cuts geometry with a plane → SVG (plan per
  storey at a 1.2 m cut height; X/Y sections), served at `/projects/{id}/drawings/*`.
- ~~Sheet composer~~ ✅ done — `compose()` lays out multiple views in a grid with a title
  block; renders to SVG and PDF (reportlab). `GET /drawings/sheet.{svg,pdf}`.
- ~~Dimension lines + grid bubbles~~ ✅ done — structural grid derived from IfcColumn
  positions (no IfcGrid needed); plans draw numbered/lettered grid bubbles, grid lines, and
  grid-spacing dimensions (mm). `GET /drawings/plan.svg`.
- ~~Elevations~~ ✅ done — orthographic outline views (N/S/E/W) via per-element convex-hull
  silhouettes + storey level lines. `GET /drawings/elevation.svg?direction=`.
- ~~Grid on sheet cells~~ ✅ done — composed sheet plan cells now carry grid bubbles, grid
  lines, and overall dimensions (per-cell transform via drawing primitives, SVG + PDF).
- **Room tags / leaders**: text annotations bound to elements on the views.
- **Hidden-line removal**: elevations are outline silhouettes (no depth sorting yet).
- **Federation UI**: a discipline picker to load several `.frag` and toggle by model.
- **Authoring in-browser**: stays a Bonsai-bridge concern by design (GPL boundary).
