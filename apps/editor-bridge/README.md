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

> This machine has Blender 3.5; Bonsai requires 4.x, so the GUI path here is documented
> rather than run. The authoring engine itself (ifcopenshell.api) is verified end-to-end
> via `edit.py` and the `/edit` + `/publish` endpoints.
