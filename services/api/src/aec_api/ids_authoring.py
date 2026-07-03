"""IDS authoring — turn information requirements into a standards-valid buildingSMART IDS 1.0 file.

We already *validate* models against an IDS (`aec_data.validate`); this is the upstream half BIMIDS
sells: **authoring** the requirements. It ships a starter template library (what data each element type
should carry, by use case), builds a real IDS via `ifctester` (round-trips through the same validator),
and generates an EIR (Exchange Information Requirements) contract document. Spec → implement → validate,
closing the openBIM loop for the config-driven platform."""
from __future__ import annotations

from typing import Any

# Starter requirement templates: element group -> the properties a model should carry for it.
# Each requirement is (property_set, base_name, data_type). Editable per project; these are sane
# defaults drawn from the standard IFC common property sets (Pset_*Common).
TEMPLATES: dict[str, dict[str, Any]] = {
    "walls": {"label": "Walls", "ifc_class": "IFCWALL",
              "requirements": [("Pset_WallCommon", "FireRating", "IFCLABEL"),
                               ("Pset_WallCommon", "LoadBearing", "IFCBOOLEAN"),
                               ("Pset_WallCommon", "IsExternal", "IFCBOOLEAN"),
                               ("Pset_WallCommon", "ThermalTransmittance", "IFCTHERMALTRANSMITTANCEMEASURE")]},
    "doors": {"label": "Doors", "ifc_class": "IFCDOOR",
              "requirements": [("Pset_DoorCommon", "FireRating", "IFCLABEL"),
                               ("Pset_DoorCommon", "IsExternal", "IFCBOOLEAN"),
                               ("Pset_DoorCommon", "AcousticRating", "IFCLABEL")]},
    "windows": {"label": "Windows", "ifc_class": "IFCWINDOW",
                "requirements": [("Pset_WindowCommon", "IsExternal", "IFCBOOLEAN"),
                                 ("Pset_WindowCommon", "ThermalTransmittance", "IFCTHERMALTRANSMITTANCEMEASURE")]},
    "slabs": {"label": "Slabs", "ifc_class": "IFCSLAB",
              "requirements": [("Pset_SlabCommon", "FireRating", "IFCLABEL"),
                               ("Pset_SlabCommon", "LoadBearing", "IFCBOOLEAN")]},
    "spaces": {"label": "Spaces", "ifc_class": "IFCSPACE",
               "requirements": [("Pset_SpaceCommon", "Reference", "IFCLABEL"),
                                ("Qto_SpaceBaseQuantities", "NetFloorArea", "IFCAREAMEASURE")]},
    "columns": {"label": "Columns", "ifc_class": "IFCCOLUMN",
                "requirements": [("Pset_ColumnCommon", "LoadBearing", "IFCBOOLEAN"),
                                 ("Pset_ColumnCommon", "FireRating", "IFCLABEL")]},
    "beams": {"label": "Beams", "ifc_class": "IFCBEAM",
              "requirements": [("Pset_BeamCommon", "LoadBearing", "IFCBOOLEAN"),
                               ("Pset_BeamCommon", "FireRating", "IFCLABEL")]},
}

# Use cases bundle element groups into a purpose-driven requirement set.
USE_CASES: dict[str, dict[str, Any]] = {
    "handover_cobie": {"label": "Handover (COBie)", "groups": ["walls", "doors", "windows", "spaces"]},
    "fire_life_safety": {"label": "Fire & life safety", "groups": ["walls", "doors", "slabs", "columns", "beams"]},
    "energy": {"label": "Energy analysis", "groups": ["walls", "windows"]},
    "quantities": {"label": "Quantity takeoff", "groups": ["walls", "slabs", "spaces", "columns", "beams"]},
}


def templates() -> dict:
    """The authoring catalog: element templates + use-case bundles."""
    return {
        "elements": [{"key": k, "label": v["label"], "ifc_class": v["ifc_class"],
                      "requirements": [{"pset": p, "property": n, "data_type": d}
                                       for (p, n, d) in v["requirements"]]}
                     for k, v in TEMPLATES.items()],
        "use_cases": [{"key": k, "label": v["label"], "groups": v["groups"]} for k, v in USE_CASES.items()],
    }


def specs_for_use_case(use_case: str) -> list[dict]:
    """IDS specs (name / ifc_class / requirements) for a named use case — for model scoring."""
    uc = USE_CASES.get(use_case)
    return _specs_for(uc["groups"]) if uc else []


def _specs_for(groups: list[str]) -> list[dict]:
    out = []
    for g in groups:
        t = TEMPLATES.get(g)
        if not t:
            continue
        out.append({"name": f"{t['label']} data requirements", "ifc_class": t["ifc_class"],
                    "requirements": [{"pset": p, "property": n, "data_type": d}
                                     for (p, n, d) in t["requirements"]]})
    return out


def build_ids(title: str, specs: list[dict], *, ifc_version: str = "IFC4",
              author: str = "", purpose: str = "") -> str:
    """Build a buildingSMART IDS 1.0 XML string from spec dicts.

    specs: [{name, ifc_class, requirements:[{pset, property, data_type}]}]. Uses ifctester so the
    output is schema-valid and round-trips through our own validator."""
    from ifctester import ids

    doc = ids.Ids(title=title or "Information requirements", author=author or None,
                  purpose=purpose or None)
    for s in specs:
        spec = ids.Specification(name=s.get("name") or "Specification", ifcVersion=ifc_version)
        spec.applicability.append(ids.Entity(name=(s.get("ifc_class") or "IFCWALL").upper()))
        for r in s.get("requirements", []):
            spec.requirements.append(ids.Property(
                propertySet=r["pset"], baseName=r["property"],
                dataType=(r.get("data_type") or "IFCLABEL").upper(),
                cardinality="required"))
        doc.specifications.append(spec)
    return doc.to_string()


def build_from_use_case(use_case: str, title: str = "", **kw) -> str:
    uc = USE_CASES.get(use_case)
    if not uc:
        raise ValueError(f"unknown use case {use_case!r}")
    return build_ids(title or uc["label"], _specs_for(uc["groups"]), **kw)


def eir_markdown(title: str, specs: list[dict], *, project: str = "", author: str = "") -> str:
    """A human-readable Exchange Information Requirements document (drop into the BIM contract)."""
    lines = [f"# Exchange Information Requirements — {title}", ""]
    if project:
        lines.append(f"**Project:** {project}  ")
    if author:
        lines.append(f"**Prepared by:** {author}  ")
    lines += ["", "The following information must be present in delivered IFC models. Compliance is "
              "checked automatically with the accompanying IDS file.", ""]
    for s in specs:
        lines.append(f"## {s.get('name') or s.get('ifc_class')}  (`{s.get('ifc_class')}`)")
        lines.append("")
        lines.append("| Property set | Property | Data type |")
        lines.append("|---|---|---|")
        for r in s.get("requirements", []):
            lines.append(f"| {r['pset']} | {r['property']} | {r.get('data_type', 'IFCLABEL')} |")
        lines.append("")
    return "\n".join(lines)


def eir_for_use_case(use_case: str, **kw) -> str:
    uc = USE_CASES[use_case]
    return eir_markdown(uc["label"], _specs_for(uc["groups"]), **kw)
