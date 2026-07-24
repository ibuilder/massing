"""NORM-VALID (R15) — a normative openBIM validation gauntlet, in the spirit of the buildingSMART
validation service (github.com/buildingSMART/validate, MIT): does this IFC *conform*, not just is it
well-authored. Complements ``model_qa`` (authoring quality — stacked/orphaned/blank elements) with the
conformance layer a downstream tool assumes:

  * **header** — a recognised ``FILE_SCHEMA``, a populated ``FILE_DESCRIPTION`` / ``FILE_NAME``, and
    the ``ViewDefinition[…]`` MVD the file claims to conform to (a file that declares none is telling
    the receiving tool nothing about which subset of IFC to expect — that is a warning, not a pass).
  * **schema** — the declared schema is one of the IFC releases we handle (IFC2X3 / IFC4 / IFC4X3).
  * **normative rules** — the cheaply-checkable subset of the IFC implementer agreements: a single
    ``IfcProject`` carrying a geometric context and a *complete, unambiguous* unit assignment (length /
    area / volume / plane angle, none of them assigned twice), every ``IfcRoot`` GlobalId a valid
    22-char ``IfcGloballyUniqueId`` and unique, OwnerHistory presence (required in IFC2X3, optional
    after), no physical element left outside the spatial structure, and the **relationship cardinality**
    every consuming tool assumes — no dangling relationship (null relating side / empty related set),
    at most one spatial container per element, one whole per part and one voided element per opening,
    no part both aggregated and directly contained, and an unbroken spatial-aggregation chain.

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

# ISO-10303-21 FILE_DESCRIPTION carries the MVD the file claims to conform to, as
# ``ViewDefinition[CoordinationView_V2.0]`` (comma-separated when several). Bounded quantifiers +
# a capped input keep this linear on adversarial header text.
_VIEW_RE = re.compile(r"ViewDefinition\s{0,4}\[([^\]]{0,400})\]", re.IGNORECASE)
_KNOWN_VIEWS = {
    "coordinationview", "coordinationview_v2.0", "referenceview", "referenceview_v1.2",
    "designtransferview", "designtransferview_v1.0", "alignment-basedreferenceview",
    "structuralanalysisview", "quantitytakeoffview", "spaceboundaryaddonview",
    "ifc4referenceview", "ifc4precastconcrete", "notdefined",
}
# the unit types a building model must assign for any downstream quantity to mean anything
_REQUIRED_UNITS = ("LENGTHUNIT", "AREAUNIT", "VOLUMEUNIT", "PLANEANGLEUNIT")
_RECOMMENDED_UNITS = ("MASSUNIT", "TIMEUNIT", "THERMODYNAMICTEMPERATUREUNIT")

# (entity, relating attribute, related attribute) — the objectified relationships whose cardinality
# every consuming tool assumes: a non-null relating side and a non-empty related side.
_REL_CARDINALITY = (
    ("IfcRelAggregates", "RelatingObject", "RelatedObjects"),
    ("IfcRelContainedInSpatialStructure", "RelatingStructure", "RelatedElements"),
    ("IfcRelDefinesByProperties", "RelatingPropertyDefinition", "RelatedObjects"),
    ("IfcRelDefinesByType", "RelatingType", "RelatedObjects"),
    ("IfcRelAssociatesClassification", "RelatingClassification", "RelatedObjects"),
    ("IfcRelAssociatesMaterial", "RelatingMaterial", "RelatedObjects"),
    ("IfcRelVoidsElement", "RelatingBuildingElement", "RelatedOpeningElement"),
    ("IfcRelFillsElement", "RelatingOpeningElement", "RelatedBuildingElement"),
)


def _as_list(v: Any) -> list:
    """Related-side attributes are a SET in most relationships and a single entity in a few
    (Voids/Fills). Normalise so one cardinality walk covers both."""
    if v is None:
        return []
    return list(v) if isinstance(v, (tuple, list, set)) else [v]


def _unit_types(proj: Any) -> tuple[set[str], list[str]]:
    """Return ``(assigned unit types, types assigned more than once)``. A duplicate assignment is
    ambiguous — two LENGTHUNITs mean a consumer cannot know which one the coordinates are in."""
    seen: dict[str, int] = {}
    ctx = getattr(proj, "UnitsInContext", None) if proj is not None else None
    for u in (getattr(ctx, "Units", None) or []):
        ut = getattr(u, "UnitType", None)            # IfcMonetaryUnit has none — skip it
        if not ut:
            continue
        key = str(ut).upper()
        seen[key] = seen.get(key, 0) + 1
    return set(seen), sorted(k for k, n in seen.items() if n > 1)


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
        # NB `model.header`, not `model.wrapped_data.header` — the latter is a *method* on the C++
        # wrapper, so attribute access on it silently raises and every header check reads as empty.
        desc = list(model.header.file_description.description or [])
    except Exception:                                # noqa: BLE001 — malformed/absent header
        desc = []
    checks.append(_check(
        "header.description", "header", "FILE_DESCRIPTION is populated",
        "pass" if any((d or "").strip() for d in desc) else "warn",
        note="; ".join(d for d in desc if d) or "(empty)"))

    # --- MVD lane: the view definition the file CLAIMS to conform to ------------------------------
    # An exchange file that declares no ViewDefinition tells the receiving tool nothing about which
    # subset of IFC to expect — that is an unstated assumption, not a pass.
    blob = "; ".join(d for d in desc if d)[:20_000]
    views = [v.strip() for m in _VIEW_RE.findall(blob) for v in m.split(",") if v.strip()]
    unknown = [v for v in views if v.lower() not in _KNOWN_VIEWS]
    if not views:
        v_status, v_note = "warn", "no ViewDefinition[...] declared — the receiving tool cannot know " \
                                   "which MVD subset this file claims to satisfy"
    elif unknown:
        v_status, v_note = "warn", f"declares {', '.join(views)} — unrecognised: {', '.join(unknown)}"
    else:
        v_status, v_note = "pass", f"declares {', '.join(views)}"
    checks.append(_check(
        "header.view_definition", "header", "FILE_DESCRIPTION declares a known model view definition",
        v_status, count=len(views), sample=views, note=v_note))

    # --- STEP-syntax lane: a populated ISO-10303-21 FILE_NAME header (name + timestamp) ----------
    fn_name = fn_ts = ""
    try:
        fh = model.header.file_name
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

    # --- unit-assignment completeness ------------------------------------------------------------
    # "has units" is not the same as "has the units a quantity take-off needs". Name the missing ones
    # rather than letting a downstream area/volume silently inherit a default.
    assigned, dup_units = _unit_types(proj)
    missing_req = [u for u in _REQUIRED_UNITS if u not in assigned]
    missing_rec = [u for u in _RECOMMENDED_UNITS if u not in assigned]
    checks.append(_check(
        "units.complete", "normative", "IfcUnitAssignment covers length, area, volume and plane angle",
        "pass" if not missing_req else "fail", count=len(missing_req), sample=missing_req,
        note=(f"missing: {', '.join(missing_req)}" if missing_req
              else f"{len(assigned)} unit types assigned")
             + (f" · not assigned (optional): {', '.join(missing_rec)}" if missing_rec else "")))
    checks.append(_check(
        "units.unambiguous", "normative", "No unit type is assigned more than once",
        "pass" if not dup_units else "fail", count=len(dup_units), sample=dup_units,
        note="a repeated UnitType leaves the consuming tool no way to know which one the values are in"))

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

    # --- relationship cardinality (IFC implementer agreements) -----------------------------------
    # An objectified relationship with a null relating side or an empty related set is a dangling
    # record: it parses, it validates against the EXPRESS schema, and it means nothing. Consuming
    # tools read straight through it, so it has to be named here.
    degenerate: list[dict] = []
    for cls, rel_attr, rel_set in _REL_CARDINALITY:
        try:
            rels = model.by_type(cls)
        except Exception:                            # noqa: BLE001 — entity absent from this schema
            continue
        for r in rels:
            relating = getattr(r, rel_attr, None)
            related = _as_list(getattr(r, rel_set, None))
            if relating is None or not related:
                degenerate.append({"class": cls, "guid": getattr(r, "GlobalId", None),
                                   "missing": rel_attr if relating is None else rel_set})
    checks.append(_check(
        "rel.cardinality", "normative", "Objectified relationships have both a relating and a related side",
        "pass" if not degenerate else "fail", count=len(degenerate), sample=degenerate,
        note="a null relating side or an empty related set is a dangling relationship"))

    # --- single-parent rules ---------------------------------------------------------------------
    # Each of these is a "how many parents may I have" agreement. Two answers is worse than none:
    # a consumer picks one arbitrarily and the model means different things in different tools.
    def _multi_parent(cls: str, rel_set: str) -> dict[int, int]:
        counts: dict[int, int] = {}
        try:
            rels = model.by_type(cls)
        except Exception:                            # noqa: BLE001
            return {}
        for r in rels:
            for e in _as_list(getattr(r, rel_set, None)):
                counts[e.id()] = counts.get(e.id(), 0) + 1
        return {eid: n for eid, n in counts.items() if n > 1}

    def _sample(ids: dict[int, int]) -> list[dict]:
        out = []
        for eid, n in list(ids.items())[:20]:
            try:
                e = model.by_id(eid)
                out.append({"class": e.is_a(), "guid": getattr(e, "GlobalId", None), "parents": n})
            except Exception:                        # noqa: BLE001
                out.append({"id": eid, "parents": n})
        return out

    for cid, label, cls, attr in (
            ("rel.single_container", "An element is contained in at most one spatial structure",
             "IfcRelContainedInSpatialStructure", "RelatedElements"),
            ("rel.single_aggregate", "An object is decomposed into at most one whole",
             "IfcRelAggregates", "RelatedObjects"),
            ("rel.single_void", "An opening voids at most one element",
             "IfcRelVoidsElement", "RelatedOpeningElement")):
        multi = _multi_parent(cls, attr)
        checks.append(_check(cid, "normative", label, "pass" if not multi else "fail",
                             count=len(multi), sample=_sample(multi)))

    # An assembly part is placed by its assembly, so it must NOT also hang directly off a storey —
    # a doubly-placed part is counted twice by every downstream take-off.
    aggregated: set[int] = set()
    for rel in model.by_type("IfcRelAggregates"):
        for e in (rel.RelatedObjects or []):
            aggregated.add(e.id())
    directly: set[int] = set()
    for rel in model.by_type("IfcRelContainedInSpatialStructure"):
        for e in (rel.RelatedElements or []):
            directly.add(e.id())
    both = sorted(aggregated & directly)
    checks.append(_check(
        "rel.double_placed", "normative", "No element is both aggregated into a whole and directly contained",
        "pass" if not both else "warn", count=len(both), sample=_sample(dict.fromkeys(both, 2)),
        note="a part placed twice is taken off twice"))

    # --- spatial hierarchy: every spatial element below the project has exactly one parent --------
    spatial = model.by_type("IfcSpatialStructureElement")
    unparented = [e for e in spatial if e.id() not in aggregated]
    checks.append(_check(
        "spatial.hierarchy", "normative", "Every spatial structure element is aggregated under a parent",
        "pass" if not unparented else "fail", count=len(unparented),
        sample=[{"class": e.is_a(), "name": e.Name, "guid": e.GlobalId} for e in unparented],
        note="site → building → storey → space must be an unbroken IfcRelAggregates chain from IfcProject"))

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
