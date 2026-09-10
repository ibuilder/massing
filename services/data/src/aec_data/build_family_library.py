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


def _checkout_root() -> Path | None:
    """The repository this file lives in, or None (a packaged build has no checkout).

    Deliberately a walk to the repo's SHAPE rather than `parents[N]`: the count that used to
    be here is right in a checkout and names a temporary directory inside a PyInstaller
    bundle, which is the defect `services/api/test_frozen_paths.py` exists to forbid. This is
    a small duplicate of `aec_api.apppaths.repo_root` on purpose -- `aec_data` must not
    import `aec_api`, and a shared helper would invert the layering to save six lines.

    **It must use the SAME marker as that function, and the first draft did not.** This looked
    for `apps/` + `services/`, which is what a git checkout has; `apppaths` deliberately does not
    use that, because the production API image is `/app` with `services/` and no `apps/` at all.
    Two helpers whose docstrings say they agree and whose code does not is the drift this
    repository keeps paying for -- so the marker below is `apppaths._ROOT_MARKER`, spelled out
    rather than imported.
    """
    for d in Path(__file__).resolve().parents:
        if (d / "services" / "api" / "src").is_dir():
            return d
    return None


# committed under services/data/families/ so the library ships with the repo. None outside a
# checkout: this script REGENERATES a committed artifact, so there is nowhere else to put it.
_ROOT = _checkout_root()
LIBRARY_DIR = (_ROOT / "services" / "data" / "families") if _ROOT else None
LIBRARY_PATH = (LIBRARY_DIR / "library.ifc") if LIBRARY_DIR else None


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
