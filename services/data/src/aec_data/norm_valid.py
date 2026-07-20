"""NORM-VALID (R15) — a normative openBIM validation gauntlet, in the spirit of the buildingSMART
validation service (github.com/buildingSMART/validate, MIT): does this IFC *conform*, not just is it
well-authored. Complements ``model_qa`` (authoring quality — stacked/orphaned/blank elements) with the
conformance layer a downstream tool assumes:

  * **header** — a recognised ``FILE_SCHEMA`` and a populated ``FILE_DESCRIPTION`` / ``FILE_NAME``.
  * **schema** — the declared schema is one of the IFC releases we handle (IFC2X3 / IFC4 / IFC4X3).
  * **normative rules** — the cheaply-checkable subset of the IFC implementer agreements: a single
    ``IfcProject`` carrying units + a geometric context, every ``IfcRoot`` GlobalId a valid 22-char
    ``IfcGloballyUniqueId`` and unique, OwnerHistory presence (required in IFC2X3, optional after), and
    no physical element left outside the spatial structure.

Each check yields ``pass | warn | fail`` with a count + a small sample. ``passed`` is true when nothing
**fails** (warnings don't block). Pure over an opened model — no I/O — so it unit-tests without fixtures
and can run as an offline job.
"""
from __future__ import annotations

import re
from typing import Any

import ifcopenshell

_KNOWN_SCHEMAS = {"IFC2X3", "IFC4", "IFC4X1", "IFC4X3", "IFC4X3_ADD2"}
_GUID_RE = re.compile(r"^[0-9A-Za-z_$]{22}$")   # IfcGloballyUniqueId base64 alphabet, fixed width


def _check(cid: str, category: str, label: str, status: str, count: int = 0,
           sample: list | None = None, note: str = "") -> dict[str, Any]:
    return {"id": cid, "category": category, "label": label, "status": status,
            "count": count, "sample": (sample or [])[:20], "note": note}


def validate(model: ifcopenshell.file) -> dict[str, Any]:
    """Run the normative gauntlet. Returns ``{schema, passed, summary:{pass,warn,fail}, checks:[…]}``."""
    checks: list[dict[str, Any]] = []
    schema = (getattr(model, "schema", None) or "").upper()

    # --- header ---------------------------------------------------------------------------------
    checks.append(_check(
        "header.schema", "header", "FILE_SCHEMA is a recognised IFC release",
        "pass" if schema in _KNOWN_SCHEMAS else "fail",
        note=f"declared schema: {schema or '(none)'}"))
    try:
        desc = list(model.wrapped_data.header.file_description.description or [])
    except Exception:                                # noqa: BLE001 — malformed/absent header
        desc = []
    checks.append(_check(
        "header.description", "header", "FILE_DESCRIPTION is populated",
        "pass" if any((d or "").strip() for d in desc) else "warn",
        note="; ".join(d for d in desc if d) or "(empty)"))

    # --- STEP-syntax lane: a populated ISO-10303-21 FILE_NAME header (name + timestamp) ----------
    fn_name = fn_ts = ""
    try:
        fh = model.wrapped_data.header.file_name
        fn_name = (getattr(fh, "name", None) or "").strip()
        fn_ts = (getattr(fh, "time_stamp", None) or "").strip()
    except Exception:                                # noqa: BLE001 — malformed/absent header
        pass
    checks.append(_check(
        "header.file_name", "header", "FILE_NAME carries a name + timestamp (ISO-10303-21)",
        "pass" if (fn_name and fn_ts) else "warn",
        note=f"name: {fn_name or '(empty)'} · timestamp: {fn_ts or '(empty)'}"))

    # --- project singularity + units + context --------------------------------------------------
    projects = model.by_type("IfcProject")
    checks.append(_check(
        "project.single", "normative", "Exactly one IfcProject",
        "pass" if len(projects) == 1 else "fail", count=len(projects)))
    proj = projects[0] if projects else None
    checks.append(_check(
        "project.units", "normative", "IfcProject assigns units (UnitsInContext)",
        "pass" if (proj is not None and getattr(proj, "UnitsInContext", None)) else "fail"))
    checks.append(_check(
        "project.context", "normative", "IfcProject declares a geometric representation context",
        "pass" if (proj is not None and getattr(proj, "RepresentationContexts", None)) else "warn"))

    # --- GlobalId validity + uniqueness ---------------------------------------------------------
    roots = model.by_type("IfcRoot")
    bad_fmt: list[dict] = []
    seen: dict[str, int] = {}
    dups: list[str] = []
    for e in roots:
        g = getattr(e, "GlobalId", None)
        if not g or not _GUID_RE.match(g):
            bad_fmt.append({"class": e.is_a(), "guid": g})
        if g:
            seen[g] = seen.get(g, 0) + 1
            if seen[g] == 2:
                dups.append(g)
    checks.append(_check(
        "guid.format", "normative", "Every IfcRoot GlobalId is a valid 22-char IfcGloballyUniqueId",
        "pass" if not bad_fmt else "fail", count=len(bad_fmt), sample=bad_fmt))
    checks.append(_check(
        "guid.unique", "normative", "GlobalIds are unique across the model",
        "pass" if not dups else "fail", count=len(dups), sample=dups))

    # --- OwnerHistory: required in IFC2X3, optional afterwards -----------------------------------
    missing_oh = [e for e in roots
                  if hasattr(e, "OwnerHistory") and getattr(e, "OwnerHistory", None) is None]
    oh_status = "fail" if (schema == "IFC2X3" and missing_oh) else ("pass" if not missing_oh else "warn")
    checks.append(_check(
        "rooted.ownerhistory", "normative", "Rooted entities carry an OwnerHistory",
        oh_status, count=len(missing_oh),
        sample=[{"class": e.is_a(), "guid": e.GlobalId} for e in missing_oh],
        note="required in IFC2X3; optional in IFC4+"))

    # --- containment: no physical element outside the spatial structure --------------------------
    contained: set[int] = set()
    for rel in model.by_type("IfcRelContainedInSpatialStructure"):
        for e in (rel.RelatedElements or []):
            contained.add(e.id())
    for rel in model.by_type("IfcRelAggregates"):
        for e in (rel.RelatedObjects or []):
            contained.add(e.id())
    orphans = [e for e in model.by_type("IfcElement") if e.id() not in contained]
    checks.append(_check(
        "containment.orphans", "normative", "Every physical element sits in the spatial structure",
        "pass" if not orphans else "warn", count=len(orphans),
        sample=[{"class": e.is_a(), "name": e.Name, "guid": e.GlobalId} for e in orphans]))

    # --- bSDD/classification lane: share of physical elements carrying a classification reference --
    elements = model.by_type("IfcElement")
    classified: set[int] = set()
    for rel in model.by_type("IfcRelAssociatesClassification"):
        for e in (getattr(rel, "RelatedObjects", None) or []):
            classified.add(e.id())
    n_el = len(elements)
    n_cl = sum(1 for e in elements if e.id() in classified)
    pct = round(100.0 * n_cl / n_el, 1) if n_el else 0.0
    # a well-linked model carries classifications (Uniclass/OmniClass/MasterFormat via bSDD); none → warn
    checks.append(_check(
        "classification.coverage", "data", "Elements carry a classification reference (bSDD alignment)",
        "pass" if pct >= 50.0 else "warn", count=n_cl,
        note=f"{n_cl}/{n_el} elements classified ({pct}%)"))

    summary = {s: sum(1 for c in checks if c["status"] == s) for s in ("pass", "warn", "fail")}
    return {"schema": schema, "passed": summary["fail"] == 0, "summary": summary,
            "checks": checks,
            "note": "Normative openBIM conformance (header + schema + IFC implementer-agreement rules) — "
                    "complements the model_qa authoring-quality checks and the IDS/LOIN data checks."}


def validate_file(ifc_path: str) -> dict[str, Any]:
    from .ifc_loader import open_model
    return validate(open_model(ifc_path))
