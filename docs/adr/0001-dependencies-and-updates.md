# ADR 0001 — Dependency bundling & update policy

**Status:** accepted · **Date:** 2026-06-23

## Context
A library research pass ([roadmap §L](../roadmap.md)) raised two recurring questions:

1. *Are there libraries we need to create/import for the program to run on its own?*
2. *Do dependencies need to auto-update in the background?*

These touch two non-negotiables: the viewer **must run fully offline** (local WASM, self-hosted
tiles), and `@thatopen/components` ↔ `@thatopen/fragments` are **version-coupled** (a compatible pair
must be pinned).

## Decision

### 1. The app runs standalone — no new library is required
The free single-project product is self-contained already:

- **Desktop** = a **Tauri** shell wrapping the web build, with a **PyInstaller-frozen FastAPI
  sidecar** for the API/conversion. No system Python, Node, or Docker needed at runtime.
- **Geometry** = **web-ifc WASM is self-hosted** in the bundle; IFC→Fragments conversion happens in
  the sidecar. Nothing is fetched from a CDN at runtime, so the viewer works on an air-gapped machine.
- Source-of-truth and editing boundaries are unchanged: IFC in, Fragments served, Blender/Bonsai is
  the *desktop* editor. We do **not** add an in-browser authoring library (see roadmap §L, Pascal).

We do **not** hand-roll new libraries; we lean on the pinned stack (web-ifc, ThatOpen, ifcopenshell)
and our own pure-function engines.

### 2. Dependencies are pinned and ship inside the signed app update — never background-updated alone
- All third-party geometry/WASM/JS deps are **pinned** (exact compatible versions, esp. the ThatOpen
  pair) and **bundled** into each release.
- The **whole application** auto-updates through **signed GitHub releases** (Tauri updater). That is
  the *only* update channel.
- We explicitly reject **independent background auto-update** of geometry/WASM libraries, because it
  would (a) break the offline guarantee (runtime network fetch), and (b) risk pulling an incompatible
  `components`/`fragments` combination that the pinned-pair rule exists to prevent.

### Consequence for the §L evaluations
Anything adopted from the research pass (e.g. an `@ifc-lite/geometry` server converter, a FreeCAD
headless drawing step) follows the same rule: **pin it, bundle it into the sidecar/web build, ship it
in the signed release** — no separate updater, no runtime download.

## Alternatives considered
- *Per-library background updaters* — rejected (offline + version-coupling risks above).
- *Runtime CDN for WASM/tiles* — rejected (violates the offline non-negotiable).
