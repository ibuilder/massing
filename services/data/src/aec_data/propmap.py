"""Property mapping / normalization (Wave 9 · W9-1) — the "transform" verb between IDS validation and
COBie/deliverable export.

Federated models name the same concept differently (`Pset_WallCommon.FireRating` vs a vendor's
`Fire_Rating` vs `FireRatingValue`). IDS *flags* the mismatch; nothing in the stack *fixes* it. This
engine (1) **detects** the psets/properties actually present, (2) **plans** a dry-run remap onto a target
(IDS/employer) structure, and (3) **applies** it as a GUID-stable edit — so messy inputs become
standards-clean IFC without touching geometry. Applied via the `map_properties` recipe, so it flows
through the normal /edit → republish path and pins/RFIs/clashes (keyed by GUID) survive.

A rule: `{from_pset, from_prop, to_pset?, to_prop, cast?, keep_source?}` — move (default) or copy
(`keep_source`) a property to a target pset/prop across every element that carries it, with optional
type coercion.
"""
from __future__ import annotations

from typing import Any

import ifcopenshell
import ifcopenshell.api
import ifcopenshell.util.element as ue


def _short(v: Any) -> str:
    return str(v)[:48]


def _cast(v: Any, kind: str | None) -> Any:
    """Coerce a value to the target type. Unknown/failed casts pass the value through unchanged."""
    if not kind or kind == "string":
        return str(v)
    try:
        if kind == "number":
            f = float(v)
            return int(f) if f.is_integer() else f
        if kind == "bool":
            return str(v).strip().lower() in ("1", "true", "yes", "y")
    except (TypeError, ValueError):
        return v
    return v


def detect(model: ifcopenshell.file) -> dict[str, Any]:
    """Every (pset, property) actually present on elements — the 'source' side a user maps FROM —
    with an occurrence count, the value's Python type, and a sample value."""
    seen: dict[tuple[str, str], dict[str, Any]] = {}
    elements = model.by_type("IfcElement")
    for el in elements:
        for pset, props in ue.get_psets(el).items():
            if not isinstance(props, dict):
                continue
            for prop, val in props.items():
                if prop == "id":
                    continue
                rec = seen.get((pset, prop))
                if rec is None:
                    seen[(pset, prop)] = {"pset": pset, "prop": prop, "count": 1,
                                          "kind": type(val).__name__, "sample": _short(val)}
                else:
                    rec["count"] += 1
    return {
        "element_count": len(elements),
        "properties": sorted(seen.values(), key=lambda r: (-r["count"], r["pset"], r["prop"])),
    }


def _run(model: ifcopenshell.file, rules: list[dict[str, Any]], dry: bool) -> dict[str, Any]:
    """Shared plan/apply core. In dry mode nothing is written; both modes return the per-rule
    match counts + before/after samples so the UI can preview and confirm."""
    out_rules: list[dict[str, Any]] = []
    changed_total = 0
    elements = model.by_type("IfcElement")
    for r in rules:
        fp, fprop = r["from_pset"], r["from_prop"]
        tp, tprop = r.get("to_pset") or fp, r["to_prop"]
        cast = r.get("cast")
        keep = bool(r.get("keep_source"))
        rename_in_place = (fp == tp and fprop == tprop)
        matched = 0
        samples: list[dict[str, str]] = []
        for el in elements:
            src = ue.get_pset(el, fp)
            if not isinstance(src, dict) or fprop not in src or src[fprop] in (None, ""):
                continue
            val = _cast(src[fprop], cast)
            matched += 1
            if len(samples) < 3:
                samples.append({"guid": el.GlobalId, "from": _short(src[fprop]), "to": _short(val)})
            if dry:
                continue
            # write the target property (create the target pset if needed). NB: the pset id lives in
            # the get_pset dict under "id" — the `prop="id"` shortcut returns None here (ifcopenshell 0.8.5).
            tgt = ue.get_pset(el, tp)
            ps = (model.by_id(tgt["id"]) if isinstance(tgt, dict) and "id" in tgt
                  else ifcopenshell.api.run("pset.add_pset", model, product=el, name=tp))
            ifcopenshell.api.run("pset.edit_pset", model, pset=ps, properties={tprop: val})
            # move semantics: drop the source property unless copying or renaming in place
            if not keep and not rename_in_place:
                ifcopenshell.api.run("pset.edit_pset", model, pset=model.by_id(src["id"]),
                                     properties={fprop: None})   # None removes the property
        out_rules.append({"from": f"{fp}.{fprop}", "to": f"{tp}.{tprop}", "matched": matched,
                          "cast": cast or "string", "keep_source": keep, "samples": samples})
        changed_total += matched
    return {"rules": out_rules, "changed": changed_total, "dry_run": dry}


def plan(model: ifcopenshell.file, rules: list[dict[str, Any]]) -> dict[str, Any]:
    """Dry-run: how many elements each rule would touch, with before/after samples. No mutation."""
    return _run(model, rules, dry=True)


def apply(model: ifcopenshell.file, rules: list[dict[str, Any]]) -> int:
    """Apply the ruleset in place; returns the total number of property values remapped."""
    return _run(model, rules, dry=False)["changed"]
