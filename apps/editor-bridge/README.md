# Editor bridge (Phase 6)

Connects the desktop authoring environment (Blender 4.x + **Bonsai** add-on) to this
platform via **Bonsai-MCP** (MIT, fork of BlenderMCP) — a local socket server that lets
Claude Code query and modify live IFC in Blender.

Workflow:
1. Curate/version IFC type libraries in `../../families/` ("families" = IFC types).
2. Install the Bonsai-MCP add-on (Blender side) + MCP server side; document connection here.
3. Prefer a small set of safe edit **recipes** (place type, set Pset, batch tag) over
   free-form `execute_blender_code` — that tool runs arbitrary Python: gate it, **save
   first**, chunk big ops.
4. On save: re-run Phase 1 conversion → updated `.frag` → viewer refreshes. Pins survive
   because they reference GUIDs.

See root guide §9. License note: Blender/Bonsai are GPL — keep the editor a separate
process you *use*, not code linked into a proprietary product.
