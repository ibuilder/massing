"""Design standards ruleset (B3): the approved / preferred / prohibited assemblies, materials and
products a project standardizes on, and a check of the loaded model against them.

This is the rules layer Higharc-style design automation leans on — the generator and in-viewer
authoring should honor it, and the model can be audited against it. The check flags any element whose
type or material name matches a *prohibited* standard; when an approved set is declared for a category
it also flags elements that match nothing approved. Keyword-based so it works on the openBIM property
data the model already carries (no proprietary catalog).
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from . import modules as me


def _d(r: dict) -> dict:
    return r.get("data") or r


def ruleset(db: Session, pid: str) -> dict[str, Any]:
    rows = me.list_records(db, "design_standard", pid, limit=100000) if "design_standard" in me.TABLES else []
    items = [{"name": _d(r).get("name", ""), "category": _d(r).get("category", ""),
              "status": _d(r).get("status", ""), "discipline": _d(r).get("discipline", ""),
              "match_keyword": (_d(r).get("match_keyword") or "").strip(),
              "spec_reference": _d(r).get("spec_reference", "")} for r in rows]
    by_status = {s: [i for i in items if i["status"] == s] for s in ("approved", "preferred", "prohibited")}
    return {"count": len(items), "items": items, "by_status": by_status,
            "note": "Approved / preferred / prohibited assemblies, materials and products. The generator "
                    "and authoring honor these; the model is audited against them."}


def _element_terms(e: dict) -> str:
    """The lower-cased searchable text for an element: its type name + any material-ish strings."""
    parts = [str(e.get("type_name") or ""), str(e.get("material") or ""), str(e.get("ifc_class") or "")]
    psets = e.get("psets")
    if isinstance(psets, dict):
        for pset in psets.values():
            if isinstance(pset, dict):
                for k, v in pset.items():
                    if "material" in str(k).lower():
                        parts.append(str(v))
    return " ".join(parts).lower()


def check(db: Session, pid: str, idx: dict[str, dict] | None) -> dict[str, Any]:
    """Audit the loaded model against the ruleset. Returns the ruleset only when no model is loaded."""
    rs = ruleset(db, pid)
    prohibited = [i for i in rs["by_status"]["prohibited"] if i["match_keyword"]]
    approved_kw = [i["match_keyword"].lower() for i in rs["by_status"]["approved"] + rs["by_status"]["preferred"]
                   if i["match_keyword"]]
    if not idx:
        return {"model_scored": False, "elements": 0, "violations": [], "prohibited_hits": 0,
                "unapproved": 0, "ruleset": rs,
                "note": "No model loaded — showing the ruleset only."}
    violations: list[dict] = []
    prohibited_hits = unapproved = 0
    for gid, e in idx.items():
        terms = _element_terms(e)
        hit = next((p for p in prohibited if p["match_keyword"].lower() in terms), None)
        if hit:
            prohibited_hits += 1
            violations.append({"guid": gid, "type": e.get("type_name") or e.get("ifc_class", ""),
                               "issue": f"prohibited: matches '{hit['name']}'"})
        elif approved_kw and not any(kw in terms for kw in approved_kw):
            unapproved += 1
            if len(violations) < 200:
                violations.append({"guid": gid, "type": e.get("type_name") or e.get("ifc_class", ""),
                                   "issue": "no approved standard matched"})
    return {"model_scored": True, "elements": len(idx), "prohibited_hits": prohibited_hits,
            "unapproved": unapproved, "violations": violations[:200], "ruleset": rs,
            "note": "Elements flagged when their type/material matches a prohibited standard, or (when an "
                    "approved set is declared) match nothing approved."}
