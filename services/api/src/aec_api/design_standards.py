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


#: Violations returned per check. The COUNTS are always complete; this caps the list.
VIOLATION_CAP = 200


def _coverage(prohibited: list[dict], approved_kw: list[str], flagged: int, listed: int,
              scored: bool) -> dict[str, Any]:
    """What the counts above do NOT say, in the one place a consumer can read it.

    Three facts, and each of them was recoverable-with-effort rather than stated, which is the same
    thing as absent for a screen that has to decide what to render:

    * **`truncated`** — the violation LIST is capped at `VIOLATION_CAP` while `prohibited_hits` and
      `unapproved` stay complete, so a consumer printing `len(violations)` beside the word
      "violations" reports the page as the total. That is TRUNC-COUNTED, and the fix belongs here
      rather than in each consumer: the engine knows the cap and the total, and a screen that has to
      reconstruct "am I seeing all of them?" from two other numbers will sometimes not bother.
    * **`approved_declared`** — `unapproved` is counted only when an approved set EXISTS
      (`elif approved_kw and ...`), so with none declared it is permanently 0. Correct, and
      indistinguishable on screen from "every element matched something approved". *A zero that
      means "nothing to compare against" and a zero that means "nothing failed" are different
      answers to different questions.*
    * **`prohibited_declared`** — the same question for the other half: 0 prohibited hits over 0
      prohibited rules is not a clean model.

    `model_scored` stays a top-level field rather than moving in here: it is what the existing
    `services/api/test_design_engine.py` asserts, and a coverage object is a place to ADD what was
    missing, not to relocate what consumers already read.
    """
    return {
        "flagged": flagged,
        "listed": listed,
        "truncated": flagged > listed,
        "cap": VIOLATION_CAP,
        "approved_declared": len(approved_kw),
        "prohibited_declared": len(prohibited),
        "reason": ("no model is loaded, so nothing was audited" if not scored
                   else "no standard is declared with a match keyword, so nothing could be audited"
                   if not (prohibited or approved_kw)
                   else "no approved or preferred standard is declared, so 'unapproved' counts nothing"
                   if not approved_kw
                   else "no prohibited standard is declared, so 'prohibited' counts nothing"
                   if not prohibited
                   else "every declared standard was applied to every element in the index"),
    }


def check(db: Session, pid: str, idx: dict[str, dict] | None) -> dict[str, Any]:
    """Audit the loaded model against the ruleset. Returns the ruleset only when no model is loaded."""
    rs = ruleset(db, pid)
    prohibited = [i for i in rs["by_status"]["prohibited"] if i["match_keyword"]]
    approved_kw = [i["match_keyword"].lower() for i in rs["by_status"]["approved"] + rs["by_status"]["preferred"]
                   if i["match_keyword"]]
    if not idx:
        # The two zeros below are the reason `coverage` exists: on a project with no model they read
        # as a clean audit, and `model_scored` is the only thing that says otherwise.
        return {"model_scored": False, "elements": 0, "violations": [], "prohibited_hits": 0,
                "unapproved": 0, "ruleset": rs,
                "coverage": _coverage(prohibited, approved_kw, 0, 0, scored=False),
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
            if len(violations) < VIOLATION_CAP:
                violations.append({"guid": gid, "type": e.get("type_name") or e.get("ifc_class", ""),
                                   "issue": "no approved standard matched"})
    listed = min(len(violations), VIOLATION_CAP)
    return {"model_scored": True, "elements": len(idx), "prohibited_hits": prohibited_hits,
            "unapproved": unapproved, "violations": violations[:VIOLATION_CAP], "ruleset": rs,
            # `flagged` is the sum of the two complete counts, NOT `len(violations)`: the loop stops
            # appending unapproved rows at the cap (`if len(violations) < VIOLATION_CAP`) while still counting
            # them, so the list is short of the total by design and the sum is the only honest total.
            "coverage": _coverage(prohibited, approved_kw, prohibited_hits + unapproved, listed,
                                  scored=True),
            "note": "Elements flagged when their type/material matches a prohibited standard, or (when an "
                    "approved set is declared) match nothing approved."}
