"""Serves the Phase 1 properties index (geometry stays in .frag, data comes from here).
Selection in the viewer raycasts to a GUID, then fetches Psets from these endpoints."""
from __future__ import annotations

import json
import os

from fastapi import APIRouter, Body, Depends, File, HTTPException, UploadFile

from .. import ai, classification, storage
from ..rbac import require_role

router = APIRouter()


def _discipline_name(e: dict) -> str:
    """The NCS discipline for an element, derived from its IFC class via the MasterFormat map
    (Discipline Spine D2). Elements whose class isn't mapped fall into 'General'. Pure function of the
    already-indexed ifc_class — no republish, no extra scan."""
    return classification.discipline_name(classification.discipline_of_ifc_class(e.get("ifc_class") or "")) or "General"

# project_id -> { guid -> element record }  (loaded from uploaded props.json)
# P0.3: bounded LRU so a worker that serves many projects doesn't hold every project's full element
# list in memory forever. Evicted projects are transparently reloaded from storage on next access.
_INDEX: dict[str, dict[str, dict]] = {}
_META: dict[str, dict] = {}
_LRU: list[str] = []                    # pids in least→most-recently-used order
_MAX_PROJECTS = int(os.environ.get("AEC_PROPS_CACHE_PROJECTS", "16"))


def _touch(pid: str) -> None:
    """Mark `pid` most-recently-used and evict the least-recently-used over the cap."""
    if pid in _LRU:
        _LRU.remove(pid)
    _LRU.append(pid)
    while len(_LRU) > max(1, _MAX_PROJECTS):
        old = _LRU.pop(0)
        _INDEX.pop(old, None)
        _META.pop(old, None)


def _load(pid: str, payload: dict) -> int:
    _META[pid] = {k: payload.get(k) for k in ("schema", "project", "counts", "facets")}
    _INDEX[pid] = {e["guid"]: e for e in payload.get("elements", [])}
    _touch(pid)
    return len(_INDEX[pid])


@router.post("/projects/{pid}/properties/index")
async def upload_index(pid: str, file: UploadFile = File(...), _: str = Depends(require_role("editor"))):
    """Upload the props.json produced by the data service (`aec_data.cli index`). Size-gated —
    json.loads of an unbounded upload would parse an arbitrarily large body entirely in RAM."""
    max_mb = int(os.environ.get("AEC_PROPS_MAX_MB", "100") or "100")
    raw = await file.read()
    if len(raw) > max_mb * 1024 * 1024:
        raise HTTPException(413, f"properties index exceeds {max_mb} MB (raise AEC_PROPS_MAX_MB)")
    payload = json.loads(raw)
    storage.put(f"{pid}/props.json", json.dumps(payload).encode("utf-8"))
    n = _load(pid, payload)
    # A new index IS "the model changed": bump the model version so open 2D views regenerate (the
    # on-demand drawings render live from the model — this is the auto-propagate signal, no event bus).
    from .. import model_capabilities as _mc
    from .. import model_events
    model_events.bump(pid, _mc.model_signature(_INDEX.get(pid)).get("signature"))
    return {"loaded": n, "meta": _META[pid]}


def _ensure_loaded(pid: str) -> None:
    if pid in _INDEX:
        return
    key = f"{pid}/props.json"
    if storage.exists(key):
        _load(pid, json.loads(storage.get(key)))


@router.get("/projects/{pid}/properties/meta")
def meta(pid: str, _: str = Depends(require_role("viewer"))):
    _ensure_loaded(pid)
    if pid not in _META:
        raise HTTPException(404, "no properties index for project")
    return _META[pid]


@router.get("/projects/{pid}/elements")
def list_elements(pid: str, ifc_class: str | None = None, storey: str | None = None,
                  discipline: str | None = None, limit: int = 500,
                  _: str = Depends(require_role("viewer"))):
    """Query the property index. `?discipline=` accepts an NCS code or name (e.g. 'S' or 'Structural');
    each element is returned with its derived `discipline` (Discipline Spine D2)."""
    _ensure_loaded(pid)
    if pid not in _INDEX:
        raise HTTPException(404, "no properties index for project")
    want_disc = classification.discipline_code(discipline) if discipline else None
    out = []
    for e in _INDEX[pid].values():
        if ifc_class and e["ifc_class"] != ifc_class:
            continue
        if storey and e["storey"] != storey:
            continue
        disc = _discipline_name(e)
        if want_disc and classification.discipline_code(disc) != want_disc:
            continue
        out.append({**e, "discipline": disc})
        if len(out) >= limit:
            break
    return out


# --- thematic colouring + data-QA (built-world analytics over the property index) ---------------
# NOTE: these static /elements/<verb> routes must be registered BEFORE /elements/{guid} below,
# or FastAPI matches "facets-list"/"color-by"/"qa" as a {guid} and 404s.
_ATTR_FACETS = [("discipline", "Discipline"), ("ifc_class", "IFC class"),
                ("storey", "Storey / level"), ("type_name", "Type"), ("name", "Name")]


def _prop_value(e: dict, prop: str):
    """Resolve a colour-by key against an element. The synthetic "discipline" key derives from the IFC
    class (D2); otherwise a top-level attribute (e.g. "ifc_class") or a nested "Group::Prop" path into
    psets/qtos (e.g. "Pset_WallCommon::IsExternal")."""
    if prop == "discipline":
        return _discipline_name(e)
    if "::" in prop:
        grp, name = prop.split("::", 1)
        for container in ("psets", "qtos"):
            d = e.get(container)
            if isinstance(d, dict) and isinstance(d.get(grp), dict) and name in d[grp]:
                return d[grp][name]
        return None
    return e.get(prop)


@router.get("/projects/{pid}/elements/facets-list")
def color_facets(pid: str, _: str = Depends(require_role("viewer"))):
    """The properties you can colour by: top-level attributes + every pset/qto property present,
    each with its distinct-value count (drives the viewer's 'Color by…' picker)."""
    _ensure_loaded(pid)
    idx = _INDEX.get(pid)
    if not idx:
        raise HTTPException(404, "no properties index for project")
    attrs: dict[str, set] = {}
    props: dict[str, set] = {}
    for e in idx.values():
        for key, _label in _ATTR_FACETS:
            v = _prop_value(e, key)          # resolves the synthetic "discipline" facet (D2) too
            if v not in (None, ""):
                attrs.setdefault(key, set()).add(str(v))
        for container in ("psets", "qtos"):
            d = e.get(container)
            if isinstance(d, dict):
                for grp, kv in d.items():
                    if isinstance(kv, dict):
                        for name, val in kv.items():
                            if val not in (None, ""):
                                props.setdefault(f"{grp}::{name}", set()).add(str(val))
    return {
        "attributes": [{"prop": k, "label": lbl, "distinct": len(attrs.get(k, ()))}
                       for k, lbl in _ATTR_FACETS if k in attrs],
        "properties": sorted(({"prop": k, "label": k.replace("::", " · "), "distinct": len(v)}
                              for k, v in props.items()), key=lambda x: x["prop"])[:300],
    }


@router.get("/projects/{pid}/elements/color-by")
def color_by(pid: str, prop: str, bins: int = 6, _: str = Depends(require_role("viewer"))):
    """Bucket every element by a chosen property → colour buckets for the 3D viewer. Numeric
    properties are binned into ranges; categorical ones grouped by value (top 24 + Other)."""
    _ensure_loaded(pid)
    idx = _INDEX.get(pid)
    if not idx:
        raise HTTPException(404, "no properties index for project")
    vals: dict[str, object] = {}
    for g, e in idx.items():
        v = _prop_value(e, prop)
        if v not in (None, ""):
            vals[g] = v

    def _is_num(x) -> bool:
        try:
            float(x)
            return not isinstance(x, bool)
        except (TypeError, ValueError):
            return False

    numeric = bool(vals) and all(_is_num(v) for v in vals.values())
    buckets: list[dict] = []
    if numeric:
        nums = {g: float(v) for g, v in vals.items()}
        lo, hi = min(nums.values()), max(nums.values())
        if hi <= lo:
            buckets = [{"label": f"{lo:g}", "guids": list(nums)}]
        else:
            n = max(1, min(int(bins), 8))
            step = (hi - lo) / n
            slots: list[list[str]] = [[] for _ in range(n)]
            for g, x in nums.items():
                slots[min(n - 1, int((x - lo) / step))].append(g)
            for i in range(n):
                buckets.append({"label": f"{lo + step * i:.3g} – {lo + step * (i + 1):.3g}", "guids": slots[i]})
    else:
        from collections import Counter
        top = [k for k, _ in Counter(str(v) for v in vals.values()).most_common(24)]
        groups: dict[str, list[str]] = {k: [] for k in top}
        other: list[str] = []
        for g, v in vals.items():
            (groups[str(v)] if str(v) in groups else other).append(g)
        buckets = [{"label": k, "guids": groups[k]} for k in top]
        if other:
            buckets.append({"label": "Other", "guids": other})
    colored = sum(len(b["guids"]) for b in buckets)
    return {
        "prop": prop, "kind": "numeric" if numeric else "categorical",
        "total": len(idx), "colored": colored, "unset": len(idx) - colored,
        "buckets": [{"label": b["label"], "count": len(b["guids"]), "guids": b["guids"]} for b in buckets],
    }


@router.get("/projects/{pid}/elements/by-discipline")
def elements_by_discipline(pid: str, _: str = Depends(require_role("viewer"))):
    """Model composition by NCS discipline (Discipline Spine D2): element count + a class breakdown per
    discipline, in NCS sheet order. Derived from the property index — one pass, no republish."""
    _ensure_loaded(pid)
    idx = _INDEX.get(pid)
    if not idx:
        raise HTTPException(404, "no properties index for project")
    order = {d["name"]: i for i, d in enumerate(classification.disciplines())}
    by: dict[str, dict] = {}
    for e in idx.values():
        name = _discipline_name(e)
        d = by.setdefault(name, {"discipline": name, "code": classification.discipline_code(name),
                                 "count": 0, "classes": {}})
        d["count"] += 1
        cls = e.get("ifc_class") or "?"
        d["classes"][cls] = d["classes"].get(cls, 0) + 1
    out = sorted(by.values(), key=lambda x: order.get(x["discipline"], 99))
    for d in out:
        d["classes"] = sorted(({"ifc_class": k, "count": v} for k, v in d["classes"].items()),
                              key=lambda x: -x["count"])
    return {"total": len(idx), "disciplines": out}


# (key, label, severity) — the headline % + 3D highlight are driven by "required" rules; "recommended"
# rules (type, property sets) are reported so gaps are visible without failing the whole model.
_QA_RULES = [("name", "Name", "required"), ("ifc_class", "IFC class", "required"),
             ("storey", "Storey / level", "required"), ("type_name", "Type", "recommended"),
             ("__pset", "Has property set", "recommended")]


@router.get("/projects/{pid}/elements/qa")
def data_qa(pid: str, _: str = Depends(require_role("viewer"))):
    """BIM data-completeness check: for each attribute, how many elements have it, and which are
    missing it. The headline compliance % + the 3D highlight use the required rules; recommended
    rules (type, property sets) are reported separately so gaps surface without failing everything."""
    _ensure_loaded(pid)
    idx = _INDEX.get(pid)
    if not idx:
        raise HTTPException(404, "no properties index for project")
    rules = []
    noncompliant: set[str] = set()
    for key, label, severity in _QA_RULES:
        missing = []
        for g, e in idx.items():
            if key == "__pset":
                d = e.get("psets")
                ok = isinstance(d, dict) and len(d) > 0
            else:
                ok = e.get(key) not in (None, "")
            if not ok:
                missing.append(g)
        rules.append({"key": key, "label": label, "severity": severity,
                      "present": len(idx) - len(missing), "missing": len(missing),
                      "missing_guids": missing[:5000]})
        if severity == "required":
            noncompliant.update(missing)
    total = len(idx)
    return {
        "total": total, "compliant": total - len(noncompliant), "noncompliant": len(noncompliant),
        "compliant_pct": round(100 * (total - len(noncompliant)) / total, 1) if total else 100.0,
        "rules": rules, "noncompliant_guids": list(noncompliant)[:5000],
    }


# Code-readiness rules — does the model carry the DATA a code review needs? (property-level, not a
# certified geometric code check). Each rule targets an IFC class, tries several attribute/pset keys,
# and either checks presence or a numeric minimum (with a code reference for the reviewer).
_CODE_RULES = [
    {"id": "egress_door_width", "label": "Egress door width recorded", "code": "IBC 1010.1.1",
     "applies": "IfcDoor", "keys": ["Pset_DoorCommon::Width", "OverallWidth", "Width"], "min": 0.813,
     "note": "Egress doors need ≥ 32 in (0.813 m) clear width — record a width to review it."},
    {"id": "fire_rating", "label": "Fire rating on walls", "code": "IBC Table 601/602",
     "applies": "IfcWall", "keys": ["Pset_WallCommon::FireRating", "FireRating"], "min": None,
     "note": "Rated assemblies must carry a fire-resistance rating."},
    {"id": "space_area", "label": "Spaces carry floor area", "code": "IBC 1004.5",
     "applies": "IfcSpace", "keys": ["Qto_SpaceBaseQuantities::NetFloorArea", "NetFloorArea", "GrossFloorArea"],
     "min": None, "note": "Occupant load = floor area ÷ load factor; area must be present per space."},
    {"id": "space_occupancy", "label": "Spaces classify occupancy", "code": "IBC 1004",
     "applies": "IfcSpace", "keys": ["Pset_SpaceOccupancyRequirements::OccupancyType", "OccupancyType"],
     "min": None, "note": "Occupancy classification drives egress + separation requirements."},
    {"id": "stair_present", "label": "Egress stairs modelled", "code": "IBC 1011",
     "applies": "IfcStair", "keys": ["name", "type_name"], "min": None,
     "note": "At least one egress stair should exist and be identifiable."},
    {"id": "classification", "label": "Elements typed/classified", "code": "BS 1192 / COBie",
     "applies": "*", "keys": ["type_name"], "min": None,
     "note": "Type/classification supports coordinated, checkable data."},
]


def _first_value(e: dict, keys: list[str]):
    for k in keys:
        v = _prop_value(e, k)
        if v not in (None, ""):
            return v
    return None


@router.get("/projects/{pid}/elements/code-check")
def code_check(pid: str, _: str = Depends(require_role("viewer"))):
    """Code-readiness check: does the model carry the data a plan review needs (egress door widths,
    fire ratings, space areas/occupancy, egress stairs, classification)? Property-level, not a
    certified code review. Returns per-rule pass/fail + the elements to highlight in 3D."""
    _ensure_loaded(pid)
    idx = _INDEX.get(pid)
    if not idx:
        raise HTTPException(404, "no properties index for project")
    checks = []
    all_fail: set[str] = set()
    for rule in _CODE_RULES:
        applies = rule["applies"]
        subject = [(g, e) for g, e in idx.items() if applies == "*" or e.get("ifc_class") == applies]
        if not subject and applies != "*":
            checks.append({**{k: rule[k] for k in ("id", "label", "code", "note")},
                           "applies": applies, "checked": 0, "passed": 0, "failed": 0,
                           "below_min": 0, "fail_guids": [], "status": "n/a"})
            continue
        fails, below = [], 0
        for g, e in subject:
            v = _first_value(e, rule["keys"])
            if v in (None, ""):
                fails.append(g)
                continue
            if rule.get("min") is not None:
                try:
                    if float(v) < float(rule["min"]):
                        fails.append(g)
                        below += 1
                except (TypeError, ValueError):
                    pass
        checked = len(subject)
        passed = checked - len(fails)
        checks.append({**{k: rule[k] for k in ("id", "label", "code", "note")},
                       "applies": applies, "checked": checked, "passed": passed, "failed": len(fails),
                       "below_min": below, "fail_guids": fails[:5000],
                       "status": "pass" if not fails else "fail"})
        all_fail.update(fails)
    checked_rules = [c for c in checks if c["status"] != "n/a"]
    tot_checked = sum(c["checked"] for c in checked_rules)
    tot_passed = sum(c["passed"] for c in checked_rules)
    return {
        "code": "IBC (data-readiness)", "rules": len(checked_rules),
        "checked": tot_checked, "passed": tot_passed,
        "readiness_pct": round(100 * tot_passed / tot_checked, 1) if tot_checked else 100.0,
        "checks": checks, "fail_guids": list(all_fail)[:5000],
    }


@router.get("/projects/{pid}/elements/{guid}")
def element(pid: str, guid: str, _: str = Depends(require_role("viewer"))):
    _ensure_loaded(pid)
    rec = _INDEX.get(pid, {}).get(guid)
    if not rec:
        raise HTTPException(404, "element not found")
    return rec


def _model_snapshot(pid: str) -> dict:
    """A compact, grounded summary of the model's data for the AI assistant (or for direct display
    when AI is off): element total, counts by class + storey, the property sets present, and the
    indexer's precomputed counts/facets."""
    idx = _INDEX.get(pid, {})
    by_class: dict[str, int] = {}
    by_storey: dict[str, int] = {}
    pset_keys: set[str] = set()
    for e in idx.values():
        by_class[e.get("ifc_class", "?")] = by_class.get(e.get("ifc_class", "?"), 0) + 1
        st = e.get("storey") or "(unassigned)"
        by_storey[st] = by_storey.get(st, 0) + 1
        psets = e.get("psets") or e.get("properties") or {}
        if isinstance(psets, dict):
            pset_keys.update(psets.keys())
    meta = _META.get(pid, {})
    return {
        "project": meta.get("project"),
        "total_elements": len(idx),
        "counts_by_class": dict(sorted(by_class.items(), key=lambda x: -x[1])[:40]),
        "counts_by_storey": by_storey,
        "property_sets": sorted(pset_keys)[:60],
        "indexer_counts": meta.get("counts"),
        "facets": meta.get("facets"),
    }


@router.post("/projects/{pid}/ask")
def ask_model(pid: str, body: dict = Body(...), _: str = Depends(require_role("viewer"))):
    """Ask a plain-English question about the model. Grounds the answer in a snapshot of the property
    index (counts by class/storey, Psets, facets); uses the configured AI provider, and degrades to
    returning the snapshot itself when no AI key is set (so the data is still useful offline)."""
    _ensure_loaded(pid)
    if pid not in _INDEX:
        raise HTTPException(404, "no properties index for project — upload one first")
    question = (body.get("question") or "").strip()
    if not question:
        raise HTTPException(422, "question required")
    return ai.ask(question, _model_snapshot(pid))
