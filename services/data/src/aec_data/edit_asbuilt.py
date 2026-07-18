"""REL-3 leaf: element **record** writers — phase, as-built verification, manufacturer, classification.

The Pset/classification-writing recipe group split off `edit.py`: no geometry, no placement — these stamp
*data* onto existing elements by GUID (the LOD-500 reliability layer: W10-8 phasing, G1 field-verified
as-built, G2 as-built dimensions, G3 manufacturer/serial + classification codes). Depends only on
`edit_core._element` + ifcopenshell.api. `edit.py` re-exports every name, so `edit.set_phase` /
`edit.phase_summary` / `edit.set_classification` importers (scene, ebc, detailing, RECIPES) are unchanged.
"""
from __future__ import annotations

import contextlib

import ifcopenshell
import ifcopenshell.api

from .edit_core import _element


def _coerce(v, dtype):
    if dtype == "bool":
        return v if isinstance(v, bool) else str(v).lower() in ("1", "true", "yes")
    if dtype == "float":
        return float(v)
    if dtype == "int":
        return int(v)
    return v


def set_element_pset(model: ifcopenshell.file, guid: str, pset: str, prop: str,
                     value, dtype: str = "str") -> str:
    """Set a single property in a Pset on one element (by GUID). GUID-stable."""
    import ifcopenshell.util.element as ue

    el = _element(model, guid)
    existing = ue.get_pset(el, pset, prop="id")
    ps = model.by_id(existing) if existing else \
        ifcopenshell.api.run("pset.add_pset", model, product=el, name=pset)
    ifcopenshell.api.run("pset.edit_pset", model, pset=ps, properties={prop: _coerce(value, dtype)})
    return guid


_PHASE_CODES = {"new": "NEW", "existing": "EXISTING", "demolish": "DEMOLISH", "temporary": "TEMPORARY"}


def set_phase(model: ifcopenshell.file, guids, phase: str = "new") -> int:
    """W10-8: tag elements with a construction **phase / status** (new · existing · demolish ·
    temporary) — the renovation/sequencing dimension needed for LOD-500 as-built + demolition models.
    Stamps `Massing_Phasing.Status` (the widely-used NEW/EXISTING/DEMOLISH/TEMPORARY status coding, so
    it colours/filters and round-trips) on each element. GUID-stable; a bad GUID never aborts the batch.
    Returns the count tagged."""
    code = _PHASE_CODES.get((phase or "new").strip().lower(), (phase or "NEW").strip().upper())
    n = 0
    for g in guids or []:
        try:
            set_element_pset(model, g, "Massing_Phasing", "Status", code, "str")
            n += 1
        except Exception:  # noqa: BLE001 — skip stale/unknown GUIDs, keep tagging the rest
            pass
    return n


def phase_summary(model: ifcopenshell.file) -> dict:
    """Count physical elements per phase/status (unset = not yet phased). Feeds a phasing overview and
    the colour-by-status view."""
    import ifcopenshell.util.element as ue

    counts: dict[str, int] = {"NEW": 0, "EXISTING": 0, "DEMOLISH": 0, "TEMPORARY": 0, "UNSET": 0}
    total = 0
    for el in model.by_type("IfcElement"):
        total += 1
        ps = ue.get_pset(el, "Massing_Phasing") or {}
        status = str(ps.get("Status") or "").upper()
        counts[status if status in counts else "UNSET"] += 1
    return {"total": total, "counts": counts,
            "phased": total - counts["UNSET"], "prop": "Massing_Phasing.Status"}


_VERIFY_METHODS = {"field-measure", "laser-scan", "total-station", "photo", "submittal", "inspection"}


def verify_asbuilt(model: ifcopenshell.file, guids, verified_by: str = "",
                   method: str = "field-measure", note: str = "", date: str | None = None) -> int:
    """G1: stamp elements as **field-verified as-built** — the reliability attribute BIMForum actually
    defines as LOD 500 (LOD 500 has NO geometric requirement; it's verified-as-built *data*). Writes
    `Massing_AsBuilt` (Status=VERIFIED + VerifiedBy / VerifiedDate / Method / Note provenance) on each
    element so the model can report LOD-500 readiness and it round-trips as a Pset. GUID-stable; a bad
    GUID never aborts the batch. Returns the count verified."""
    meth = (method or "field-measure").strip().lower()
    if meth not in _VERIFY_METHODS:
        meth = "field-measure"
    stamp = (date or "").strip() or _today_iso()
    n = 0
    for g in guids or []:
        try:
            set_element_pset(model, g, "Massing_AsBuilt", "Status", "VERIFIED", "str")
            set_element_pset(model, g, "Massing_AsBuilt", "VerifiedBy", str(verified_by or ""), "str")
            set_element_pset(model, g, "Massing_AsBuilt", "VerifiedDate", stamp, "str")
            set_element_pset(model, g, "Massing_AsBuilt", "Method", meth, "str")
            if note:
                set_element_pset(model, g, "Massing_AsBuilt", "Note", str(note), "str")
            n += 1
        except Exception:  # noqa: BLE001 — skip stale/unknown GUIDs, keep verifying the rest
            pass
    return n


def _today_iso() -> str:
    from datetime import date as _date
    return _date.today().isoformat()


def asbuilt_summary(model: ifcopenshell.file) -> dict:
    """LOD-500 readiness: how much of the model is field-verified as-built. Counts physical elements
    with `Massing_AsBuilt.Status==VERIFIED`, broken down by verification method, plus the readiness %.
    The cheap, high-claim 'LOD 500' reliability layer over LOD-400 geometry."""
    import ifcopenshell.util.element as ue

    total = verified = 0
    by_method: dict[str, int] = {}
    for el in model.by_type("IfcElement"):
        total += 1
        ps = ue.get_pset(el, "Massing_AsBuilt") or {}
        if str(ps.get("Status") or "").upper() == "VERIFIED":
            verified += 1
            m = str(ps.get("Method") or "unspecified").lower()
            by_method[m] = by_method.get(m, 0) + 1
    with_mfr = with_serial = with_dims = out_of_tol = 0
    for el in model.by_type("IfcElement"):
        tp = ue.get_pset(el, "Pset_ManufacturerTypeInformation") or {}
        oc = ue.get_pset(el, "Pset_ManufacturerOccurrence") or {}
        # a type may carry the manufacturer info — fall through to the element's type psets
        t = ue.get_type(el)
        if not tp and t is not None:
            tp = ue.get_pset(t, "Pset_ManufacturerTypeInformation") or {}
        if str(tp.get("Manufacturer") or "").strip():
            with_mfr += 1
        if str(oc.get("SerialNumber") or "").strip():
            with_serial += 1
        dm = ue.get_pset(el, "Massing_AsBuiltDim") or {}
        if any(str(k).endswith("_Measured") for k in dm):
            with_dims += 1
            if str(dm.get("WithinTolerance") or "").lower() == "false":
                out_of_tol += 1

    # G3: elements carrying an O&M / warranty document reference (IfcRelAssociatesDocument, purpose-tagged)
    om_els: set[int] = set()
    om_doc_names: set[str] = set()
    _OM_KEYS = ("OPERATION", "MAINTENANCE", "O&M", "WARRANTY", "MANUAL", "GUARANTEE")
    try:
        rels = model.by_type("IfcRelAssociatesDocument")
    except RuntimeError:
        rels = []
    for rel in rels:
        info = getattr(rel, "RelatingDocument", None)
        if info is not None and info.is_a("IfcDocumentReference"):
            info = getattr(info, "ReferencedDocument", None) or info
        purpose = str(getattr(info, "Purpose", "") or "").upper()
        if any(k in purpose for k in _OM_KEYS):
            om_doc_names.add(str(getattr(info, "Name", "") or "").strip())
            for el in (getattr(rel, "RelatedObjects", None) or []):
                if el.is_a("IfcElement"):
                    om_els.add(el.id())

    return {"total": total, "verified": verified, "unverified": total - verified,
            "readiness_pct": round(100.0 * verified / total, 1) if total else 0.0,
            "by_method": by_method, "prop": "Massing_AsBuilt.Status",
            "with_manufacturer": with_mfr, "with_serial": with_serial,
            "with_dimensions": with_dims, "dimensions_out_of_tolerance": out_of_tol,
            "with_om_docs": len(om_els), "om_documents": sorted(n for n in om_doc_names if n)[:20],
            "methods": sorted(_VERIFY_METHODS)}


def record_asbuilt_dimension(model: ifcopenshell.file, guids, dimension: str, measured: float,
                             design: float | None = None, tolerance: float = 0.01) -> dict:
    """G2: record a **field-verified as-built dimension** on element(s) — the measured value, the design
    value (if given), the variance (measured − design), and whether it's within `tolerance` (metres).
    Writes `Massing_AsBuiltDim` (`{Dimension}_Measured` / `_Design` / `_Variance` + `WithinTolerance`), the
    dimensional half of the LOD-500 reliability layer. GUID-stable; a bad GUID never aborts the batch.
    Returns {stamped, variance, within_tolerance}."""
    dim = (dimension or "Length").strip().replace(" ", "")[:32] or "Length"
    try:
        meas = float(measured)
    except (TypeError, ValueError) as e:
        raise ValueError("measured must be a number") from e
    variance = None if design is None else round(meas - float(design), 4)
    within = None if variance is None else (abs(variance) <= float(tolerance))
    n = 0
    for g in guids or []:
        try:
            set_element_pset(model, g, "Massing_AsBuiltDim", f"{dim}_Measured", meas, "float")
            if design is not None:
                set_element_pset(model, g, "Massing_AsBuiltDim", f"{dim}_Design", float(design), "float")
                set_element_pset(model, g, "Massing_AsBuiltDim", f"{dim}_Variance", variance, "float")
                set_element_pset(model, g, "Massing_AsBuiltDim", "WithinTolerance", "true" if within else "false", "str")
            n += 1
        except Exception:  # noqa: BLE001 — skip stale/unknown GUIDs
            pass
    return {"stamped": n, "dimension": dim, "measured": meas, "design": design,
            "variance": variance, "within_tolerance": within}


def set_manufacturer_info(model: ifcopenshell.file, guids, manufacturer: str = "", model_label: str = "",
                          production_year: str = "", serial: str = "", barcode: str = "") -> int:
    """G3: stamp the standard IFC **manufacturer / serial** psets for the LOD-500 / O&M / turnover layer —
    `Pset_ManufacturerTypeInformation` (Manufacturer / ModelLabel / ProductionYear) and
    `Pset_ManufacturerOccurrence` (SerialNumber / BarCode) on each element. These round-trip to COBie and
    asset/CMMS systems. Only non-empty fields are written; GUID-stable; a bad GUID never aborts the batch.
    Returns the count stamped. (Warranty/O&M documents attach separately via attach_document.)"""
    fields_type = [("Manufacturer", manufacturer), ("ModelLabel", model_label),
                   ("ProductionYear", production_year)]
    fields_occ = [("SerialNumber", serial), ("BarCode", barcode)]
    n = 0
    for g in guids or []:
        try:
            wrote = False
            for prop, val in fields_type:
                if str(val or "").strip():
                    set_element_pset(model, g, "Pset_ManufacturerTypeInformation", prop, str(val), "str")
                    wrote = True
            for prop, val in fields_occ:
                if str(val or "").strip():
                    set_element_pset(model, g, "Pset_ManufacturerOccurrence", prop, str(val), "str")
                    wrote = True
            if wrote:
                n += 1
        except Exception:  # noqa: BLE001 — skip stale/unknown GUIDs, keep going
            pass
    return n


def set_classification(model: ifcopenshell.file, guid: str, system: str, code: str,
                       name: str | None = None, edition: str | None = None) -> str:
    """Tag one element (by GUID) with a classification reference — Uniclass 2015, OmniClass,
    Uniformat II, MasterFormat, etc. Reuses an existing IfcClassification for `system` if present,
    so repeated tags don't duplicate the source. GUID-stable; the standard BIM way to carry
    Uniclass/OmniClass codes into downstream takeoff, cost and asset systems.
    """
    import ifcopenshell.api.classification as cls

    el = _element(model, guid)
    src = next((s for s in model.by_type("IfcClassification")
                if (s.Name or "").strip().lower() == system.strip().lower()), None)
    if src is None:
        src = cls.add_classification(model, classification=system)
        if edition:
            with contextlib.suppress(Exception):
                cls.edit_classification(model, classification=src, attributes={"Edition": edition})
    cls.add_reference(model, products=[el], classification=src,
                      identification=code, name=name or code)
    return guid
