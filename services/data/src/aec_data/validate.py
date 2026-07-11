"""IDS / model validation (Bonsai-native openBIM QA parity, guide ANALYSIS & QA).

Validates an IFC against an buildingSMART IDS spec using ifctester. Accepts an uploaded
.ids file, or builds a sensible default QA spec set when none is given. Returns a compact
per-specification pass/fail summary plus the failing element GUIDs (so the viewer can
highlight them). `failures_to_bcf_records()` turns that result into BCF-ready topics — one per
failing specification, its failing elements selected as components — which the API exports as a
.bcfzip punch list (see routers/analysis.py `/validate?format=bcf`)."""
from __future__ import annotations

from typing import Any

import ifcopenshell
from ifctester import ids

from .ifc_loader import open_model


def default_specs() -> ids.Ids:
    """A starter QA rule set — extend or replace with a project IDS."""
    spec_set = ids.Ids(title="AEC platform default QA")

    # 1. every column must carry a Name (concrete entity; passes on a well-named model)
    s1 = ids.Specification(name="Columns have a Name")
    s1.applicability.append(ids.Entity(name="IFCCOLUMN"))
    s1.requirements.append(ids.Attribute(name="Name", cardinality="required"))
    spec_set.specifications.append(s1)

    # 2. slabs should declare a load-bearing flag (Pset_SlabCommon.LoadBearing)
    s2 = ids.Specification(name="Slabs declare LoadBearing")
    s2.applicability.append(ids.Entity(name="IFCSLAB"))
    s2.requirements.append(ids.Property(
        propertySet="Pset_SlabCommon", baseName="LoadBearing",
        dataType="IFCBOOLEAN", cardinality="required",
    ))
    spec_set.specifications.append(s2)

    return spec_set


def _entity_guids(entities) -> list[str]:
    out = []
    for e in entities or []:
        guid = getattr(e, "GlobalId", None)
        if guid:
            out.append(guid)
    return out


def validate(model: ifcopenshell.file, ids_path: str | None = None) -> dict[str, Any]:
    spec_set = ids.open(ids_path) if ids_path else default_specs()
    spec_set.validate(model)

    specs_out: list[dict[str, Any]] = []
    total_pass = total_fail = 0
    for spec in spec_set.specifications:
        passed = list(getattr(spec, "passed_entities", []) or [])
        failed = list(getattr(spec, "failed_entities", []) or [])
        total_pass += len(passed)
        total_fail += len(failed)
        specs_out.append({
            "name": spec.name,
            "status": "pass" if not failed else "fail",
            "applicable": len(passed) + len(failed),
            "passed": len(passed),
            "failed": len(failed),
            "failed_guids": _entity_guids(failed)[:500],
        })

    return {
        "title": spec_set.info.get("title", "IDS"),
        "status": "pass" if total_fail == 0 else "fail",
        "summary": {"specifications": len(specs_out), "passed": total_pass, "failed": total_fail},
        "specifications": specs_out,
    }


def validate_file(ifc_path: str, ids_path: str | None = None) -> dict[str, Any]:
    return validate(open_model(ifc_path), ids_path)


def failures_to_bcf_records(result: dict[str, Any]) -> list[dict[str, Any]]:
    """Turn a `validate()` result into BCF-ready 'record' dicts — one topic per FAILING specification,
    tied to that spec's failing element GUIDs. Hand these to `bcf_io.export_records_bcfzip` so an IDS
    audit round-trips to Solibri / ACC / BIMcollab as a punch list of non-conformances (the failing
    elements are the topic's selected components, so a coordinator can jump straight to them). Returns
    an empty list for a fully-passing model."""
    import uuid

    title = result.get("title", "IDS")
    out: list[dict[str, Any]] = []
    for spec in result.get("specifications", []):
        if spec.get("status") != "fail":
            continue
        name = spec.get("name", "specification")
        failed, applicable = int(spec.get("failed", 0)), int(spec.get("applicable", 0))
        out.append({
            "id": str(uuid.uuid4()),
            "ref": "IDS",
            "title": f"IDS non-conformance: {name}",
            "workflow_state": "open",
            "element_guids": list(spec.get("failed_guids") or []),
            "data": {
                "priority": "High",
                "subject": f"IDS non-conformance: {name}",
                "description": (f"{failed} of {applicable} applicable element(s) failed the requirement "
                                f"“{name}”. IDS: {title}."),
            },
        })
    return out
