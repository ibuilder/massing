"""Build a real, shippable IFC family library from the parametric catalog.

The `families` folder shipped no actual `.ifc` content — geometry was only generated in-model on demand.
This writes the whole catalog to a standalone **`library.ifc`** (every family as a data-rich,
GUID-stable `IfcTypeProduct` with mapped box geometry), so the platform ships a browsable openBIM
family library out of the box. The same file can be imported into any project via
`families.import_types_from_ifc` / the `/families/import` endpoint, and it's a template a deployment
extends with richer or manufacturer content.

Run:  PYTHONPATH=src ./.venv/Scripts/python.exe -m aec_data.build_family_library
Fully offline — the geometry is generated locally with IfcOpenShell (no downloads)."""
from __future__ import annotations

from pathlib import Path

import ifcopenshell
import ifcopenshell.api

from . import families

# committed under services/data/families/ so the library ships with the repo
LIBRARY_DIR = Path(__file__).resolve().parents[2] / "families"
LIBRARY_PATH = LIBRARY_DIR / "library.ifc"


def build_model(name: str = "Massing Family Library") -> ifcopenshell.file:
    """A minimal IFC4 project with a Body context, then every catalog family as a typed product."""
    model = ifcopenshell.api.run("project.create_file", version="IFC4")
    ifcopenshell.api.run("root.create_entity", model, ifc_class="IfcProject", name=name)
    ifcopenshell.api.run("unit.assign_unit", model, length={"is_metric": True, "raw": "METERS"})
    ctx = ifcopenshell.api.run("context.add_context", model, context_type="Model")
    ifcopenshell.api.run("context.add_context", model, context_type="Model",
                         context_identifier="Body", target_view="MODEL_VIEW", parent=ctx)
    for spec in families.CATALOG:
        families.ensure_type(model, spec["key"])       # builds the typed product + mapped geometry
    return model


def build(out_path: Path = LIBRARY_PATH) -> dict:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    model = build_model()
    model.write(str(out_path))
    types = model.by_type("IfcTypeProduct")
    return {"path": str(out_path), "families": len(types),
            "size_bytes": out_path.stat().st_size,
            "categories": sorted({s["category"] for s in families.CATALOG})}


if __name__ == "__main__":
    result = build()
    print(f"Wrote {result['families']} families -> {result['path']} "
          f"({result['size_bytes']} bytes); categories: {', '.join(result['categories'])}")
