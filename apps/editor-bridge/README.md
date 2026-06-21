# Editor bridge (Phase 6) — authoring & round-trip

IFC authoring runs on **`ifcopenshell.api`** — the same engine Bonsai drives inside Blender,
and what **Bonsai-MCP** executes over its socket. So the platform can author/edit IFC three
ways, all GUID-stable (pins/RFIs/clashes survive a re-publish):

1. **Server / AI-driven** (implemented, verified): `services/data/src/aec_data/edit.py`
   recipes, exposed at `POST /projects/{id}/edit` and `POST /projects/{id}/publish`.
2. **Desktop GUI**: Blender 4.x + **Bonsai** add-on, edited by hand.
3. **Claude over Bonsai-MCP**: Claude calls the same recipes against the live Blender session.

## Recipes (safe, high-value — preferred over free-form code)
| Recipe | Params | Effect |
|---|---|---|
| `set_pset` | ifc_class, pset, prop, value, dtype | add/edit a Pset property on every element of a class |
| `batch_tag` | ifc_class, label | tag elements (drives viewer layers/filters) |
| `place_type` | type_guid, storey | instantiate an IFC type ("family") on a storey |

See `recipes.py` for the reference IfcOpenShell implementations and `edit.py` for the
registry the API/MCP invoke by name.

## Round-trip (verified headless)
```
edit IFC (ifcopenshell.api) ─► save new version ─► reconvert to .frag (converter)
   ─► rebuild properties index ─► viewer streams the update
```
Because every edit preserves GlobalIds, a pin/RFI/clash pinned to element GUID X still
resolves after the model is re-authored and re-published.

## Bonsai-MCP connection (desktop GUI path)
1. Install Blender **4.x** + the **Bonsai** add-on (Blender Extensions or daily build).
2. Install **Bonsai-MCP** (MIT): the add-on side starts a socket server inside Blender;
   the MCP server side bridges Claude Code to it. Host/port in `bonsai-mcp.config.json`.
3. ⚠️ `execute_blender_code` runs arbitrary Python — gate it, **save first**, and chunk
   large operations (`max_elements_per_call` in the config).
4. On save, the platform re-runs Phase 1 conversion + index (the `publish` step).

## Bridge client (`bridge.py`) — runs recipes with the safety gates
`BonsaiBridge` turns a recipe into a gated, ordered plan and sends it to the Bonsai socket:
```bash
python bridge.py set_pset '{"ifc_class":"IfcSlab","pset":"Pset_SlabCommon","prop":"LoadBearing","value":true}'   # dry-run (default): prints the plan
python bridge.py set_pset '{...}' --run                                                                          # live: requires Blender on the socket
```
It enforces CLAUDE.md's gates from `bonsai-mcp.config.json`: **save before execute**, **chunk** to
`max_elements_per_call`, and **confirm** before any arbitrary-Python execute (`--run`). `plan()` is
pure (no Blender/socket) so the gating is unit-tested in `test_bridge.py` (save-first ordering,
3-way chunking, dry-run default, confirm gate) — run `python test_bridge.py`.

> The gating + plan generation are verified offline; the live socket send needs **Blender 4.x +
> Bonsai + Bonsai-MCP** running (this machine has Blender 3.5). The authoring engine itself
> (ifcopenshell.api) is verified end-to-end via `edit.py` and the `/edit` + `/publish` endpoints —
> so the bridge is the last hop, ready to point at a Blender session.
