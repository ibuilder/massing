"""Serves the Phase 1 properties index (geometry stays in .frag, data comes from here).
Selection in the viewer raycasts to a GUID, then fetches Psets from these endpoints."""
from __future__ import annotations

import json

from fastapi import APIRouter, Body, Depends, HTTPException, UploadFile, File

from .. import ai, storage
from ..rbac import require_role

router = APIRouter()

# project_id -> { guid -> element record }  (loaded from uploaded props.json)
_INDEX: dict[str, dict[str, dict]] = {}
_META: dict[str, dict] = {}


def _load(pid: str, payload: dict) -> int:
    _META[pid] = {k: payload.get(k) for k in ("schema", "project", "counts", "facets")}
    _INDEX[pid] = {e["guid"]: e for e in payload.get("elements", [])}
    return len(_INDEX[pid])


@router.post("/projects/{pid}/properties/index")
async def upload_index(pid: str, file: UploadFile = File(...), _: str = Depends(require_role("editor"))):
    """Upload the props.json produced by the data service (`aec_data.cli index`)."""
    payload = json.loads(await file.read())
    storage.put(f"{pid}/props.json", json.dumps(payload).encode("utf-8"))
    n = _load(pid, payload)
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
def list_elements(pid: str, ifc_class: str | None = None, storey: str | None = None, limit: int = 500,
                  _: str = Depends(require_role("viewer"))):
    _ensure_loaded(pid)
    if pid not in _INDEX:
        raise HTTPException(404, "no properties index for project")
    out = []
    for e in _INDEX[pid].values():
        if ifc_class and e["ifc_class"] != ifc_class:
            continue
        if storey and e["storey"] != storey:
            continue
        out.append(e)
        if len(out) >= limit:
            break
    return out


# --- thematic colouring + data-QA (built-world analytics over the property index) ---------------
# NOTE: these static /elements/<verb> routes must be registered BEFORE /elements/{guid} below,
# or FastAPI matches "facets-list"/"color-by"/"qa" as a {guid} and 404s.
_ATTR_FACETS = [("ifc_class", "IFC class"), ("storey", "Storey / level"),
                ("type_name", "Type"), ("name", "Name")]


def _prop_value(e: dict, prop: str):
    """Resolve a colour-by key against an element. Top-level attribute (e.g. "ifc_class") or a
    nested "Group::Prop" path into psets/qtos (e.g. "Pset_WallCommon::IsExternal")."""
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
            v = e.get(key)
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
