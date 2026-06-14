# Project: AEC BIM Viewer

## What this is
A standalone web BIM viewer + data platform for AEC firms. IFC is the source of truth.
Blender/Bonsai is the desktop editor (not the web viewer). RVT support is an optional,
paid Autodesk bridge — never assume RVT can be read offline.

## Non-negotiables
- Reference model elements by IFC GlobalId (GUID), never by transient viewer IDs.
- Pre-convert IFC to Fragments on the server; never parse full IFC in the browser at runtime.
- Keep geometry and metadata separate: geometry streams as .frag; data comes from the API.
- Pins/RFIs/punchlist follow the BCF model so they round-trip with other BIM tools.
- The viewer must run fully offline (local WASM, self-hosted tiles).

## Stack
- Web: Vite + TS, web-ifc, @thatopen/{fragments,components,components-front,ui}, three (pinned pair).
- Services: Python, ifcopenshell, FastAPI, SQLAlchemy/Postgres, MinIO.
- Editor: Blender + Bonsai, driven via Bonsai-MCP.
- Optional: Autodesk APS Model Derivative (RVT→IFC), behind a feature flag with a cost warning.

## Build order
Phase 0 smoke tests → 1 conversion → 2 large-model → 3 viewer/tools → 4 API/BCF
→ 5 data export → 6 editor/families → 7 deploy.

## Watch out for
- @thatopen/components and @thatopen/fragments version coupling — pin a compatible pair.
- Bonsai-MCP execute_blender_code runs arbitrary Python: gate it, save first, chunk big ops.
- Set-origin/georeferencing: preserve real coordinates for export, render near scene origin.

## Local environment notes (this machine)
- node v20.3.1, npm 9.6.7, docker 24.0.6 — OK.
- python 3.10.6 — guide targets ≥ 3.11. Works for ifcopenshell 0.8.x / FastAPI / pydantic v2,
  but prefer a 3.11+ interpreter for the `services/` venvs if available.
- Repo root: C:\Server\modelmaker (Windows / PowerShell).
