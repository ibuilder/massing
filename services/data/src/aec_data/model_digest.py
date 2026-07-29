"""R23-DIGEST — a deterministic, multi-scale digest of an IFC model, and a diff between two of them.

**What this is for.** Two IFC files land a fortnight apart and someone has to answer "what changed?".
Today that question is answered by opening both and looking. A digest turns it into arithmetic: a
compact JSON summary at four scales — project → storey → class → element — where **every node
carries a hash over its own content plus its children's hashes**. That Merkle shape is the whole
point: comparing two projects is one string comparison, and when it differs you descend only into
the storeys whose hashes differ. You never walk the elements of a storey that did not change.

**Systems and zones are axes, not levels.** The ring entry names the scales as
"project → storey → zone → system → element", but that hierarchy does not exist in IFC and pretending
it does would produce a tree that lies. `IfcZone` groups spaces and `IfcSystem` groups distribution
elements; both cut *across* storeys, and an element can belong to several. So the digest has one
**spatial spine** that owns elements (project → storey → class → element) and two **grouping axes**
that reference them by GlobalId. Nothing is double-counted, and a duct that runs three floors appears
under one system and three storeys, which is the truth about it.

**Determinism is a claim, so it is tested.** `test_model_digest.py` digests the same file twice from
separate opens and asserts byte-identical JSON. To hold that:

- no timestamp, path, filesystem stat, `id()` or iteration-order-dependent value enters a hash;
- every mapping is emitted with sorted keys and every list is sorted by a stable key;
- every float is rounded to a fixed number of decimals *before* it is hashed, because IEEE noise in
  the last bits of a mesh volume is not a change to the building.

**A digest states its configuration.** `mode` records how it was measured (`psets` or
`psets+geometry`), what rounding was used, and where it was pruned. `diff()` refuses to compare
digests whose configurations differ instead of reporting the configuration change as a building
change — a geometry-derived volume and a pset-derived volume disagree for reasons that have nothing
to do with the model, and a diff that blames the building for that is worse than no diff at all.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

import ifcopenshell
import ifcopenshell.util.element as ue

from .ifc_loader import open_model, physical_elements, storey_name

DIGEST_VERSION = 1

# Rounding applied BEFORE hashing. These are not display precisions — they are the threshold below
# which the digest declares two models the same. A millimetre on a placement and a litre on a volume
# are below the noise floor of anything that authored the file.
ROUND = {"length": 3, "area": 3, "volume": 4, "weight": 1, "point": 3}

SCALES = ("project", "storey", "class", "element")

# Base quantity keys, same canonical names qto.py uses so a digest quantity and an estimate quantity
# mean the same thing. Duplicated deliberately rather than imported: qto pulls in the geometry
# backend at import time, and the default digest path must not require it.
_QTY_KEYS = {
    "length": ("Length", "NetLength", "GrossLength"),
    "area": ("NetArea", "GrossArea", "Area", "NetSideArea", "GrossSideArea"),
    "volume": ("NetVolume", "GrossVolume", "Volume"),
    "weight": ("NetWeight", "GrossWeight", "Weight"),
}

# Which unit scale power applies to each canonical quantity: lengths scale linearly with the file's
# length unit, areas as its square, volumes as its cube. Weight is a mass unit and is left alone.
_QTY_POWER = {"length": 1, "area": 2, "volume": 3, "weight": 0}

# Which rounding bucket each canonical quantity uses. One map, so a quantity is rounded the same way
# wherever it appears — element record, roll-up, and delta.
_QTY_ROUND = {"length": "length", "area": "area", "volume": "volume", "weight": "weight"}


class DigestError(ValueError):
    """A digest could not be produced or two digests could not be compared."""


def _canon(obj: Any) -> str:
    """Canonical JSON: sorted keys, no insignificant whitespace, unicode kept as-is.

    `ensure_ascii=False` matters — a storey named "Niveau 1" must hash the same whether or not the
    encoder decided to escape it."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def _hash(obj: Any) -> str:
    """16 hex chars of SHA-256 over the canonical form. 64 bits is ~4 billion nodes before a
    birthday collision is even worth thinking about, and it keeps the digest readable."""
    return hashlib.sha256(_canon(obj).encode("utf-8")).hexdigest()[:16]


def _r(value: float | None, kind: str) -> float | None:
    if value is None:
        return None
    try:
        out = round(float(value), ROUND[kind])
    except (TypeError, ValueError):
        return None
    # -0.0 and 0.0 are equal but do not serialize equal, which would make a digest of an unchanged
    # model differ from itself depending on which side of zero a rounding landed.
    return out + 0.0 if out != 0 else 0.0


def _unit_scale(model: ifcopenshell.file) -> float:
    try:
        import ifcopenshell.util.unit as uunit
        return float(uunit.calculate_unit_scale(model))
    except Exception:                       # noqa: BLE001 — a file with no unit assignment
        return 1.0


def _pset_fingerprint(element) -> str | None:
    """A hash over every property set on the element, values included.

    This is the cheap half of change detection and often the interesting half: a wall whose
    `FireRating` moved from 1HR to 2HR has not moved a millimetre, and no geometric comparison will
    ever see it. Returns None when the element carries no psets, so "no properties" and "properties
    that happen to hash to X" are distinguishable."""
    try:
        psets = ue.get_psets(element)
    except Exception:                       # noqa: BLE001 — malformed pset graph on one element
        return None
    if not psets:
        return None
    # Drop ifcopenshell's bookkeeping key: it is the entity's STEP id, which is stable within a file
    # but not across a re-export of the same building, and would report every element as changed.
    clean = {
        name: {k: _scalar(v) for k, v in sorted(props.items()) if k != "id"}
        for name, props in sorted(psets.items())
    }
    return _hash(clean)


def _scalar(value: Any) -> Any:
    """Reduce a property value to something JSON-canonical and float-noise-free."""
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, (int,)):
        return value
    if isinstance(value, float):
        return round(value, 6)
    if isinstance(value, (list, tuple)):
        return [_scalar(v) for v in value]
    return str(value)


def _pset_quantities(element, scale: float) -> dict[str, float]:
    """Base quantities from IfcElementQuantity, converted to SI (metres / m² / m³)."""
    try:
        qtos = ue.get_psets(element, qtos_only=True)
    except Exception:                       # noqa: BLE001
        return {}
    out: dict[str, float] = {}
    for qset in qtos.values():
        for canonical, keys in _QTY_KEYS.items():
            if canonical in out:
                continue
            for k in keys:
                v = qset.get(k)
                if isinstance(v, (int, float)) and not isinstance(v, bool):
                    converted = float(v) * (scale ** _QTY_POWER[canonical])
                    rounded = _r(converted, _QTY_ROUND[canonical])
                    if rounded is not None:
                        out[canonical] = rounded
                    break
    return out


def _geom_quantities(element, settings, shape_mod, np_mod) -> dict[str, float]:
    """Geometry-derived volume/area when the element carries no base quantities.

    Opt-in (`geometry=True`) and never mixed silently with the pset path: the mode is recorded in the
    digest header and `diff()` refuses to compare across modes. Meshing every element of a real model
    is minutes of work, which is why it is not the default for a summary whose selling point is that
    it is cheap enough to take on every publish."""
    try:
        import ifcopenshell.geom as _geom
        shape = _geom.create_shape(settings, element)
        geo = shape.geometry                       # keep `shape` alive: geo.verts views into it
        verts = np_mod.asarray(geo.verts, dtype=float).reshape(-1, 3)
        if verts.size == 0:
            return {}
        return {
            "volume": _r(float(shape_mod.get_volume(geo)), "volume") or 0.0,
            "area": _r(float(shape_mod.get_area(geo)), "area") or 0.0,
        }
    except Exception:                       # noqa: BLE001 — an unmeshable element is unmeasured, not fatal
        return {}


def _origin(element, scale: float) -> list[float] | None:
    """The element's placement origin in metres, rounded to the millimetre.

    Origin rather than a full transform: a 4×4 carries rotation and a rotated-in-place element is a
    change worth catching, but the matrix is also where floating-point noise concentrates after a
    round trip through another tool. Origin at mm resolution is the change a person would call
    "it moved"."""
    placement = getattr(element, "ObjectPlacement", None)
    if placement is None:
        return None
    try:
        import ifcopenshell.util.placement as _pl
        m = _pl.get_local_placement(placement)
        return [_r(float(m[i][3]) * scale, "point") or 0.0 for i in range(3)]
    except Exception:                       # noqa: BLE001 — a placement graph we cannot resolve
        return None


def _element_record(element, scale: float, geom_ctx) -> dict[str, Any]:
    """One element, reduced to the facts that decide whether it changed."""
    quantities = _pset_quantities(element, scale)
    if geom_ctx is not None and not quantities:
        quantities = _geom_quantities(element, *geom_ctx)
    etype = None
    try:
        t = ue.get_type(element)
        etype = getattr(t, "Name", None) if t is not None else None
    except Exception:                       # noqa: BLE001
        etype = None
    record = {
        "guid": element.GlobalId,
        "class": element.is_a(),
        "name": getattr(element, "Name", None) or None,
        "type": etype or None,
        "storey": storey_name(element),
        "origin": _origin(element, scale),
        "quantities": {k: quantities[k] for k in sorted(quantities)},
        "psets": _pset_fingerprint(element),
    }
    record["hash"] = _hash({k: v for k, v in record.items() if k != "guid"})
    return record


# The element fields a diff reports on. `hash` is derived from these, so listing it would report
# every change twice; `guid` is the join key and cannot differ within a matched pair.
_COMPARED = ("class", "name", "type", "storey", "origin", "quantities", "psets")


def _rollup(records: list[dict[str, Any]]) -> dict[str, float]:
    """Sum the canonical quantities across a set of element records.

    Rounded again after summing: adding a thousand values each rounded to 4 places produces a tail
    that is not itself meaningful, and an unrounded total would make a digest sensitive to the order
    its elements were visited in."""
    totals: dict[str, float] = {}
    for r in records:
        for k, v in (r.get("quantities") or {}).items():
            totals[k] = totals.get(k, 0.0) + float(v)
    return {k: _r(totals[k], _QTY_ROUND.get(k, "length")) or 0.0 for k in sorted(totals)}


def _class_nodes(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_class: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        by_class.setdefault(r["class"], []).append(r)
    nodes = []
    for cls in sorted(by_class):
        # Ordered by CONTENT, not by GlobalId. An element's own hash deliberately excludes its GUID
        # (so a re-export that renumbers every id still compares), and ordering the list by GUID
        # while hashing without it makes the parent hash depend on something the children do not —
        # two models with identical elements then hash differently whenever the random GUID order
        # happens to differ. That is a flake, not a difference in the building. GUID is the tiebreak
        # so the emitted order is still stable within one file.
        members = sorted(by_class[cls], key=lambda r: (r["hash"], r["guid"]))
        node = {
            "scale": "class",
            "key": cls,
            "elements": len(members),
            "quantities": _rollup(members),
            "children": members,
        }
        node["hash"] = _node_hash(node)
        nodes.append(node)
    return nodes


def _node_hash(node: dict[str, Any]) -> str:
    """A node's hash covers its own summary plus its children's hashes — never their full content.

    That is what makes the tree a Merkle tree rather than a hash of the whole file: a change deep in
    one storey propagates up one path, and every other path's hash is provably untouched, so a
    comparison can stop at the highest node that still matches."""
    return _hash({
        "scale": node["scale"],
        "key": node.get("key"),
        "guid": node.get("guid"),
        "name": node.get("name"),
        "elements": node.get("elements"),
        "quantities": node.get("quantities"),
        # SORTED, so the hash describes the SET of children rather than the order they were emitted
        # in. A storey is a collection of elements; two storeys holding the same elements are the
        # same storey, and nothing about iteration order should be able to say otherwise.
        "children": sorted(c["hash"] for c in node.get("children", [])),
    })


def _groups(model: ifcopenshell.file, ifc_class: str, scale_name: str) -> list[dict[str, Any]]:
    """The grouping axes (IfcZone / IfcSystem) as GUID references, not as owners of elements."""
    out = []
    try:
        groups = model.by_type(ifc_class)
    except RuntimeError:                    # class absent from this schema
        return []
    for g in groups:
        members: set[str] = set()
        try:
            for rel in getattr(g, "IsGroupedBy", None) or []:
                for obj in getattr(rel, "RelatedObjects", None) or []:
                    guid = getattr(obj, "GlobalId", None)
                    if guid:
                        members.add(guid)
        except Exception:                   # noqa: BLE001 — malformed grouping graph on this group
            pass
        node = {
            "scale": scale_name,
            "key": g.GlobalId,
            "guid": g.GlobalId,
            "name": getattr(g, "Name", None) or None,
            "predefined_type": str(getattr(g, "PredefinedType", None) or "") or None,
            "elements": len(members),
            "members": sorted(members),
        }
        node["hash"] = _hash({k: v for k, v in node.items() if k != "key"})
        out.append(node)
    return sorted(out, key=lambda n: n["key"])


def digest(path: str, *, geometry: bool = False, prune_at: str | None = None) -> dict[str, Any]:
    """Digest the IFC at `path`.

    `geometry=True` meshes elements that carry no base quantities, which is slow and changes what the
    numbers mean — it is recorded in `mode` and gates `diff()`.

    `prune_at` cuts the tree at a scale ("project", "storey", "class") for a cheap overview. A pruned
    digest keeps its hashes — they are computed before pruning, so a pruned digest still proves what
    the full one would have said — but it cannot be diffed below the scale it was cut at, and
    `diff()` says so rather than reporting the missing levels as deletions.
    """
    if prune_at is not None and prune_at not in SCALES:
        raise DigestError(f"prune_at must be one of {', '.join(SCALES)}, not {prune_at!r}")

    model = open_model(path)
    scale = _unit_scale(model)

    geom_ctx = None
    if geometry:
        try:
            import ifcopenshell.geom as _geom
            import ifcopenshell.util.shape as _shape
            import numpy as _np
            geom_ctx = (_geom.settings(), _shape, _np)
        except Exception as exc:            # noqa: BLE001
            raise DigestError(f"geometry=True but the geometry backend is unavailable: {exc}") from exc

    records = [_element_record(el, scale, geom_ctx) for el in physical_elements(model)]

    by_storey: dict[str, list[dict[str, Any]]] = {}
    for r in records:
        by_storey.setdefault(r["storey"] or "", []).append(r)

    storey_elev = {}
    for st in model.by_type("IfcBuildingStorey"):
        name = getattr(st, "Name", None) or ""
        storey_elev[name] = _r((float(getattr(st, "Elevation", 0) or 0)) * scale, "point")

    storeys = []
    for name in sorted(by_storey):
        members = by_storey[name]
        node = {
            "scale": "storey",
            # "" is the honest key for elements with no spatial container — a real and common
            # condition in imported models. Naming it "(unassigned)" would invent a storey.
            "key": name,
            "name": name or None,
            "elevation": storey_elev.get(name),
            "elements": len(members),
            "quantities": _rollup(members),
            "children": _class_nodes(members),
        }
        node["hash"] = _node_hash(node)
        storeys.append(node)

    project = next(iter(model.by_type("IfcProject")), None)
    root = {
        "scale": "project",
        "key": getattr(project, "GlobalId", None),
        "guid": getattr(project, "GlobalId", None),
        "name": getattr(project, "Name", None) or None,
        "elements": len(records),
        "quantities": _rollup(records),
        "children": storeys,
    }
    root["hash"] = _node_hash(root)

    out = {
        "digest_version": DIGEST_VERSION,
        "mode": {
            "measured": "psets+geometry" if geometry else "psets",
            "rounding": dict(sorted(ROUND.items())),
            "pruned_at": prune_at,
            "schema": model.schema,
            "length_unit_scale": round(scale, 9),
        },
        "tree": _prune(root, prune_at) if prune_at else root,
        "systems": _groups(model, "IfcSystem", "system"),
        "zones": _groups(model, "IfcZone", "zone"),
    }
    return out


def _prune(node: dict[str, Any], scale: str) -> dict[str, Any]:
    """Drop children below `scale`, keeping every hash intact."""
    depth = SCALES.index(scale)
    def walk(n: dict[str, Any], d: int) -> dict[str, Any]:
        copy = {k: v for k, v in n.items() if k != "children"}
        if d < depth:
            copy["children"] = [walk(c, d + 1) for c in n.get("children", [])]
        return copy
    return walk(node, 0)


def _index(node: dict[str, Any], scale: str) -> dict[str, dict[str, Any]]:
    """Every node at `scale`, keyed. Elements key on GlobalId; storeys and classes on their key."""
    out: dict[str, dict[str, Any]] = {}
    def walk(n: dict[str, Any]):
        if n.get("scale") == scale or (scale == "element" and "guid" in n and "scale" not in n):
            out[n.get("guid") or n.get("key") or ""] = n
            return
        for c in n.get("children", []):
            walk(c)
    walk(node)
    return out


def _incompatible(a: dict[str, Any], b: dict[str, Any]) -> str | None:
    """Why these two digests cannot be honestly compared — or None."""
    if a.get("digest_version") != b.get("digest_version"):
        return (f"digest_version {a.get('digest_version')} vs {b.get('digest_version')}: "
                "the record shape changed, so field-level differences are not attributable")
    ma, mb = a.get("mode", {}), b.get("mode", {})
    if ma.get("measured") != mb.get("measured"):
        return (f"measured {ma.get('measured')!r} vs {mb.get('measured')!r}: "
                "geometry-derived and pset-derived quantities disagree for reasons that are not "
                "changes to the building")
    if ma.get("rounding") != mb.get("rounding"):
        return "rounding differs, so equal values would compare unequal"
    if ma.get("pruned_at") != mb.get("pruned_at"):
        return (f"pruned_at {ma.get('pruned_at')!r} vs {mb.get('pruned_at')!r}: "
                "one side is missing levels the other has, which would read as deletions")
    return None


def diff(before: dict[str, Any], after: dict[str, Any]) -> dict[str, Any]:
    """Compare two digests, keyed by GlobalId.

    Returns `compatible: false` with a stated reason rather than a misleading comparison when the
    two were not produced the same way. Element changes name **which fields** moved — "changed" on
    its own is not actionable, and the field list is the difference between a diff you can hand to a
    reviewer and one they have to re-derive by hand.
    """
    reason = _incompatible(before, after)
    if reason:
        return {"compatible": False, "reason": reason, "identical": False}

    ta, tb = before.get("tree", {}), after.get("tree", {})
    pruned = (before.get("mode", {}) or {}).get("pruned_at")
    identical = ta.get("hash") == tb.get("hash")

    result: dict[str, Any] = {
        "compatible": True,
        "reason": None,
        "identical": identical,
        "project": {"before": ta.get("hash"), "after": tb.get("hash")},
        "quantities": _quantity_delta(ta.get("quantities") or {}, tb.get("quantities") or {}),
        "storeys": _key_delta(_index(ta, "storey"), _index(tb, "storey")),
    }

    if pruned in ("project", "storey", "class"):
        # Say what was not compared. A diff that silently stops short reads as "nothing else
        # changed", which is the one thing it cannot know.
        result["elements"] = None
        result["elements_not_compared"] = (
            f"both digests were pruned at {pruned!r}; element-level changes were not examined")
        return result

    ea, eb = _index(ta, "element"), _index(tb, "element")
    added = sorted(set(eb) - set(ea))
    removed = sorted(set(ea) - set(eb))
    changed = []
    for guid in sorted(set(ea) & set(eb)):
        ra, rb = ea[guid], eb[guid]
        if ra.get("hash") == rb.get("hash"):
            continue
        fields = [f for f in _COMPARED if ra.get(f) != rb.get(f)]
        changed.append({
            "guid": guid,
            "class": rb.get("class") or ra.get("class"),
            "name": rb.get("name") or ra.get("name"),
            "fields": fields,
            "before": {f: ra.get(f) for f in fields},
            "after": {f: rb.get(f) for f in fields},
        })

    result["elements"] = {
        "added": [{"guid": g, "class": eb[g].get("class"), "name": eb[g].get("name")} for g in added],
        "removed": [{"guid": g, "class": ea[g].get("class"), "name": ea[g].get("name")} for g in removed],
        "changed": changed,
        "unchanged": len(set(ea) & set(eb)) - len(changed),
    }
    result["groups"] = {
        "systems": _key_delta({n["key"]: n for n in before.get("systems", [])},
                              {n["key"]: n for n in after.get("systems", [])}),
        "zones": _key_delta({n["key"]: n for n in before.get("zones", [])},
                            {n["key"]: n for n in after.get("zones", [])}),
    }
    return result


def _key_delta(a: dict[str, dict], b: dict[str, dict]) -> dict[str, Any]:
    """Added / removed / changed for a keyed set of nodes, compared on their hashes."""
    return {
        "added": sorted(set(b) - set(a)),
        "removed": sorted(set(a) - set(b)),
        "changed": sorted(k for k in set(a) & set(b) if a[k].get("hash") != b[k].get("hash")),
        "unchanged": sorted(k for k in set(a) & set(b) if a[k].get("hash") == b[k].get("hash")),
    }


def _quantity_delta(a: dict[str, float], b: dict[str, float]) -> dict[str, dict[str, float]]:
    out = {}
    for k in sorted(set(a) | set(b)):
        before, after = float(a.get(k, 0.0)), float(b.get(k, 0.0))
        out[k] = {"before": before, "after": after,
                  "delta": _r(after - before, _QTY_ROUND.get(k, "length")) or 0.0}
    return out


def summary(d: dict[str, Any]) -> dict[str, Any]:
    """The one-screen version: project hash, element count, per-storey hashes and counts.

    Kept here rather than in the router so the CLI and the API agree on what "the summary" is."""
    tree = d.get("tree", {})
    return {
        "digest_version": d.get("digest_version"),
        "mode": d.get("mode"),
        "hash": tree.get("hash"),
        "name": tree.get("name"),
        "elements": tree.get("elements"),
        "quantities": tree.get("quantities"),
        "storeys": [
            {"key": s.get("key"), "elevation": s.get("elevation"),
             "elements": s.get("elements"), "hash": s.get("hash")}
            for s in tree.get("children", [])
        ],
        "systems": len(d.get("systems", [])),
        "zones": len(d.get("zones", [])),
    }
