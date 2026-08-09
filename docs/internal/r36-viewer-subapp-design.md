# R36-VIEWER-SUBAPP — design pass and slice plan

*Written 2026-08-09 at v0.3.913. Every claim below was measured against the tree, not read off the
roadmap entry — which turned out to be stale in the one place that decides the shape of the work.*

---

## 0. The finding that reframes the item

The roadmap entry says:

> Today 2D has a real path (plan SVG → sheet → PDF) while 3D only captures a hero image, so the two
> are not yet peers and the mode switch would expose that immediately. **Slice the print path first.**

That was true when written. It is not true now, and it is not false in the way you would guess.
**CANVAS-PEER already shipped the hard half** — a server-side axonometric that is a *drawing*, not a
screenshot: `axon_basis()` computes a true isometric (`atan(1/√2)`, computed rather than typed
because a rounded 35.264 measurably skewed it), `axon_outlines()` produces per-element silhouettes
that **keep their GlobalId**, depth-sorted far→near. `services/api/test_axon_view.py` asserts a plan
and an axonometric composing on one A3 sheet.

So the projection engine is done. What is missing is **reach**, and there are two independent gaps:

**Gap 1 — two composition paths that disagree.** `compose_viewports()` handles `kind: "axon"`. The
shipping path — `sheet()` → `compose()` → `_view_for_spec()`, which every sheet route uses — does
not. `_view_for_spec` branches on `section`, then `elevation`, then **falls through to plan**.
Measured just now:

```
spec kind='plan'   -> label='PLAN'       sub='cut @ 1.20 m'
spec kind='axon'   -> label='ISO VIEW'   sub='cut @ 1.20 m'      <-- a PLAN, titled ISO VIEW
```

The title comes from the caller, so the sheet **says ISO VIEW and draws a plan cut at 1.20 m**. Not a
missing feature — a drawing that lies about what it is. This is a live defect independent of R36 and
should be fixed on its own, before any of the interface work.

**Gap 2 — no route carries view specs.** `sheet.svg` / `sheet.pdf` / `sheet.dxf` accept
`sheet, page, purpose, rev, scale`. There is no way for any client to say *which views* it wants.
`default_sheet()` picks them server-side. So even with Gap 1 closed, nothing can ask for an axon.

**Consequence for the plan:** the roadmap's "slice the print path first" is right, and the slice is
one-tenth the size the entry implies. It is a dispatcher branch plus a spec parameter, not a
rendering pipeline.

---

## 1. Requirements

### Functional
| # | Requirement | Source |
|---|---|---|
| F1 | One subapp, three modes: **Model ▸ Sheets ▸ Specs**, switching in place | roadmap |
| F2 | Selection carries across modes **by GlobalId** — pick a door in 3D, see it on the sheet | roadmap + non-negotiable |
| F3 | Takeoff/markup is a **plugin of** the subapp, not a fourth mode | roadmap |
| F4 | **Print is part of the interface**: 2D and 3D are both placeable on a sheet | user directive |
| F5 | Mode switch never loses the model (no reload, no re-convert) | implied by R42 |

### Non-functional
| # | Requirement | Measured basis |
|---|---|---|
| N1 | Mode switch < 100 ms | it is a canvas swap; the 3D model must stay resident |
| N2 | Sheet render stays server-side | `bake()` + numpy + trimesh; no browser equivalent |
| N3 | Offline-capable | CLAUDE.md non-negotiable — rules out any hosted render service |
| N4 | No new runtime dependency | standing constraint; axon path already uses numpy/trimesh |
| N5 | `app.ts` cannot grow | per-file ratchet, pinned at 3,715 with zero headroom |

### Constraints that actually bind
- **GlobalId only, never viewer ids** — already honoured by `axon_outlines`, which is what makes F2
  possible at all.
- **`app.ts` is full.** Any mode machinery lands in new modules or it does not land. This is not a
  style preference; the size gate fails the build.
- **One engineer, interleaved with other lanes.** Rules out a big-bang refactor; favours slices that
  each ship green.

---

## 2. High-level design

```
                    ┌─────────────────────────────────────────────┐
                    │  viewer subapp  (one surface, three modes)  │
                    │                                             │
   rail ──────────► │   ┌────────┐  ┌────────┐  ┌────────┐        │
   (unchanged)      │   │ Model  │  │ Sheets │  │ Specs  │  mode  │
                    │   │  3D    │  │  2D    │  │ text   │  switch│
                    │   └───┬────┘  └───┬────┘  └───┬────┘        │
                    │       │           │           │             │
                    │       └───────────┴───────────┘             │
                    │                   │                         │
                    │          selectionBus (GlobalId)   ◄── F2   │
                    └───────────────────┼─────────────────────────┘
                                        │
                    ┌───────────────────▼─────────────────────────┐
                    │  print: ONE spec vocabulary, one composer   │
                    │                                             │
                    │   [{kind: plan},{kind: section},            │
                    │    {kind: elevation},{kind: axon}]  ◄── F4  │
                    │            │                                │
                    │      _view_for_spec  ──► compose ──► svg    │
                    │                                     pdf     │
                    │                                     dxf     │
                    └─────────────────────────────────────────────┘
```

**The load-bearing idea:** the three modes are not three apps. They are three *renderers over one
selection and one model*, and print is not a fourth thing — it is the same **view-spec vocabulary**
the sheet composer already speaks. Making `axon` a first-class kind is what makes "2D and 3D are
peers" true in the data rather than promised in the UI.

### Why not the alternatives

| Option | Verdict |
|---|---|
| **Raster the 3D canvas onto sheets** (`toDataURL` → place image) | **Rejected.** `drawings_render.py` has no raster path at all, so it means building one. Worse, it breaks F2 permanently: a PNG has no GlobalIds, so the sheet view becomes unclickable and un-keynotable — the exact peer-ness the item is about. It also makes print depend on a browser having been open. |
| **Server-side WebGL/offscreen render** | **Rejected.** New heavyweight dependency (N4), and still raster (F2). |
| **Three separate pages with shared state** | **Rejected.** Fails F1 explicitly ("in-place, never separate pages") and F5 — a page change drops the loaded fragments. |
| **Extend `_view_for_spec` to `axon`; carry specs on the route** | **Chosen.** No new dependency, no new renderer, keeps GlobalIds, and closes a live defect on the way. |

---

## 3. Deep dive

### 3.1 The spec vocabulary (the contract everything else hangs off)

```jsonc
{"kind": "plan",      "elevation": 0.0, "cut_height": 1.2, "title": "PLAN L1"}
{"kind": "section",   "axis": "x", "offset": 12.5,         "title": "SECTION A-A"}
{"kind": "elevation", "direction": "north",                "title": "NORTH ELEVATION"}
{"kind": "axon",      "azimuth_deg": 45, "elevation_deg": 35.264,
                      "rect": [0.5, 0, 0.5, 1],            "title": "ISO VIEW"}   // ← the addition
```

Three rules this vocabulary must obey, each of which is a defect today or nearly:

1. **An unknown kind is refused, never substituted.** The current fall-through to plan is how
   "ISO VIEW" came to name a plan. A spec the composer does not understand must raise, not guess.
2. **An axonometric declares NTS.** It has no true paper scale; `test_axon_view` already asserts it
   must not claim a denominator. A scale bar on an axonometric is a false statement on a drawing an
   engineer may seal.
3. **Every viewport keeps its GlobalIds.** This is F2's whole basis and the non-negotiable.

### 3.2 Selection across modes

`R38-SYNC-SELECT` already syncs 3D ↔ plan pane both directions. The subapp generalises it from a
pair to a bus: modes publish and subscribe `{guid, source}`. Two rules:

- **Echo suppression by source, not by value.** A → B → A loops are the classic failure here; the
  existing pair-wise sync already solved it and the shape must carry over.
- **A GlobalId absent from a mode is stated, not swallowed.** Selecting an element that has no
  representation on the current sheet must say so — the honest-partial-state rule this codebase
  keeps relearning (most recently the R42 delta indicator).

### 3.3 Where the code lands (N5 is a hard constraint)

| Concern | Home | Why |
|---|---|---|
| mode state + switch | `apps/web/src/viewer/subapp.ts` (new) | `app.ts` is on its pin |
| selection bus | extend the existing sync module | do not build a second mechanism |
| spec builders | `apps/web/src/viewer/sheetSpecs.ts` (new, pure) | testable without a canvas — the lesson from `deltaCommit.ts` |
| `axon` dispatch | `services/data/src/aec_data/drawings.py::_view_for_spec` | one branch, where the other three live |
| specs on the wire | `routers/drawings.py` sheet routes | new optional `specs` body/param |

---

## 4. Scale and reliability

- **Sheet render cost** is dominated by `bake(model)`, already the case for every existing sheet.
  An axon viewport adds a projection over meshes that are already baked — no new order of cost.
- **The one real scale risk** is a caller asking for many axon viewports on a tall model; the
  existing `max_plans` sampling in `default_sheet` is the precedent for a cap. Cap it and say so
  rather than silently truncating.
- **Failure mode to design for:** `axon_outlines` already logs when silhouettes are skipped and calls
  the result INCOMPLETE. That warning must reach the sheet, not just the log — an incomplete drawing
  that looks complete is the worst artefact this system can produce.

---

## 5. Trade-offs, stated

| Decision | Gain | Cost | Revisit when |
|---|---|---|---|
| Vector axon over raster capture | GlobalIds survive; offline; no new dep | silhouette-only — no materials, no shadows | a client asks for presentation renders |
| Specs on the route | any client can compose a sheet | a new public contract to keep stable | a second consumer appears (pyRevit bridge) |
| Modes in one surface | F1/F5, model stays resident | one more thing `app.ts` coordinates | `subapp.ts` itself approaches a pin |
| Refuse unknown kinds | no more silent substitution | a breaking change for any caller sending junk | — do it now, while there are no external callers |

---

## 6. Slices

Each ships green on its own; none depends on the next.

| # | Slice | Size | Why this order |
|---|---|---|---|
| ~~1~~ | ~~Refuse unknown view kinds + add `axon` to `_view_for_spec`~~ | S | **SHIPPED v0.3.915.** Closed the live defect. The branch moved DOWN into the shared dispatcher so both composers get it; an unknown kind now raises; `VIEW_KINDS` is exported and both dispatchers are asserted to agree kind-by-kind. |
| ~~2~~ | ~~Carry the view list on the sheet routes~~ | S | **SHIPPED v0.3.915.** Not a JSON body — a compact `views=` grammar (`views=plan@0,section:x@12.5,axon@30x20`), because a sheet should stay a **linkable URL**. `drawings.parse_views()` is pure and refuses an unparseable token rather than dropping it: a sheet quietly missing a viewport is wrong in the one way nobody checks. All three sheet routes share one `_compose_sheet` helper so they cannot drift; omitting `views` keeps the existing default-sheet behaviour exactly. |
| 3 | `sheetSpecs.ts` + a "place this view on a sheet" control | M | First user-visible peer-ness. Print is now genuinely mode-agnostic. |
| 4 | `subapp.ts` — mode switch Model ▸ Sheets ▸ Specs, in place | M | Only now does the switch expose nothing embarrassing. |
| 5 | Selection bus across modes | M | F2. Builds on R38-SYNC-SELECT rather than replacing it. |
| 6 | Takeoff/markup as a plugin of the subapp | M | Last, because it consumes the bus. |

**Slices 1–2 shipped v0.3.915.** Next is slice 3 — the first user-visible peer-ness, and the point at
which ADR-001's deferred question reopens: if a "place this view on a sheet" control needs
per-viewport `rect`/`scale`, Option B (migrating the routes to `compose_viewports`) stops being
optional and the UI becomes its test.

**Start at slice 1 regardless of whether R36 proceeds.** It is a correctness fix that happens to be
the foundation.

---

## 7. What I would revisit

- **The two composition paths.** `compose()` and `compose_viewports()` both exist and disagree about
  what kinds they support. Slice 1 fixes the symptom; the real question is whether they should be one
  function. I did not resolve it here because I have not read enough of `compose_viewports`' callers
  to know what depends on the difference — and a merge done on a guess would be worse than the split.
- **Whether `axon` should carry a camera from the live 3D view.** Matching the user's current
  viewpoint is the obvious next ask ("print what I'm looking at"), and it is a bigger question than
  it appears: the 3D camera is perspective, an axonometric is parallel, so "the same view" is not
  well-defined. Deliberately out of scope until someone asks.
