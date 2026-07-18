"""Worked example plugin — copy this directory to start your own.

`register(api)` is the single entry point. Each recipe you register follows the SAME contract as every
core recipe: `fn(model, params) -> summary`, where `model` is the open ifcopenshell file and the edit
must be GUID-stable (mutate in place; never delete + recreate an element you mean to keep). Your recipe
becomes `<plugin-name>.<recipe-name>` and is instantly drivable from POST /edit, the CAD command line,
the AI bar, and MCP run_recipe — and it appears in the authoring matrix.
"""


def brand_walls(model, params):
    """Stamp Pset_Brand.{prop}={value} on every IfcWall — the smallest real GUID-stable edit.
    Reuses the platform's own pset primitive so IFC round-tripping stays correct."""
    from aec_data import edit  # the host's recipe toolkit is importable — build on it, don't re-invent

    return edit.set_pset_on_class(model, "IfcWall", params.get("pset") or "Pset_Brand",
                                  params.get("prop") or "Brand", params.get("value") or "Acme")


def register(api):
    api.register_recipe("brand_walls", brand_walls,
                        category="properties", produces="IfcPropertySet")
