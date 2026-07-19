"""RULE-LIB — a user-authored parametric rule-check library (Solibri-flavoured) over the model.

Every rule is two QUERY-DSL selector strings plus a severity:
  * ``scope``   — which elements the rule applies to  (e.g. ``IfcDoor & storey=L1``)
  * ``require`` — the condition each in-scope element MUST satisfy  (e.g. ``Pset_DoorCommon.FireRating=90``)

An element that is *in scope* but does **not** match ``require`` is a violation. Because both halves
are QUERY-DSL, a firm can author "every fire-rated wall must be load-bearing" or "every L1 door needs a
fire rating" with no code, and the same rules drive a severity matrix + BCF/coordination downstream —
the reusable multiplier QUERY-DSL was built for.

Storage is a single JSON blob per project (``{pid}/rule_library.json``) — no migration; an empty
library falls back to the starter set. ``run(idx, rules)`` evaluates every rule and returns per-rule
pass/fail + the offending GUIDs + a by-severity rollup.

Out of scope for v1: geometric/relational checks (clearance-in-front-of, escape distance, accessible
route) need swept geometry, not the property index — they ride the logistics/clash geometry path later.
"""
from __future__ import annotations

import json
import uuid
from typing import Any

from . import query_dsl, storage
from .query_dsl import QueryError

SEVERITIES = ("low", "medium", "high")
_KEY = "{pid}/rule_library.json"
# HARDEN-2 (S2): a stored library is evaluated O(rules × predicates × elements) on every viewer-level
# /rules/run and Model-CI pass — bound what one save can park there so a cheap GET can't be amplified.
MAX_RULES = 200
MAX_SELECTOR_LEN = 500
MAX_ID_LEN = 40

# Seeded when a project has never saved a library — real, useful defaults a firm can edit/extend.
STARTER_RULES: list[dict[str, Any]] = [
    {"id": "fire-door-rating", "name": "Fire doors carry a fire rating", "severity": "high",
     "scope": "IfcDoor", "require": "Pset_DoorCommon.FireRating"},
    {"id": "ext-wall-firerating", "name": "External walls declare a fire rating", "severity": "medium",
     "scope": "IfcWall & Pset_WallCommon.IsExternal=true", "require": "Pset_WallCommon.FireRating"},
    {"id": "loadbearing-declared", "name": "Walls declare load-bearing status", "severity": "low",
     "scope": "IfcWall", "require": "Pset_WallCommon.LoadBearing"},
]


def _norm(r: dict) -> dict:
    """Validate + normalize one rule; raises QueryError (→422) on a missing/garbage/oversized selector."""
    scope = str(r.get("scope") or "").strip()
    require = str(r.get("require") or "").strip()
    if not scope or not require:
        raise QueryError("each rule needs both a 'scope' and a 'require' selector")
    if len(scope) > MAX_SELECTOR_LEN or len(require) > MAX_SELECTOR_LEN:
        raise QueryError(f"selector too long (max {MAX_SELECTOR_LEN} chars)")
    query_dsl.parse(scope)                            # validate the grammar now, not at run time
    query_dsl.parse(require)
    sev = r.get("severity")
    return {"id": str(r.get("id") or uuid.uuid4().hex[:12])[:MAX_ID_LEN],
            "name": (str(r.get("name") or "Rule").strip() or "Rule")[:120],
            "scope": scope, "require": require,
            "severity": sev if sev in SEVERITIES else "medium"}


def load(pid: str) -> list[dict]:
    """The project's saved rules ([] if none saved yet — callers fall back to STARTER_RULES)."""
    try:
        return json.loads(storage.get(_KEY.format(pid=pid))).get("rules", [])
    except Exception:                                 # noqa: BLE001 — no blob yet / unreadable
        return []


def save(pid: str, rules: list[dict]) -> list[dict]:
    """Validate + persist the library. Raises QueryError on any bad rule (nothing is written)."""
    if len(rules or []) > MAX_RULES:
        raise QueryError(f"too many rules ({len(rules)}) — max {MAX_RULES}")
    clean = [_norm(r) for r in (rules or [])]         # validate ALL before persisting (atomic)
    storage.put(_KEY.format(pid=pid), json.dumps({"rules": clean}).encode("utf-8"))
    return clean


def evaluate(idx: dict[str, dict], rule: dict) -> dict:
    """Evaluate one rule over the index → scoped / passed / failed counts + the offending GUIDs."""
    scope_preds = query_dsl.parse(rule["scope"])
    req_preds = query_dsl.parse(rule["require"])
    scoped = 0
    fails: list[str] = []
    for g, e in idx.items():
        if query_dsl.matches(e, scope_preds):
            scoped += 1
            if not query_dsl.matches(e, req_preds):
                fails.append(g)
    return {"id": rule.get("id"), "name": rule.get("name"),
            "severity": rule.get("severity", "medium"),
            "scope": rule["scope"], "require": rule["require"],
            "scoped": scoped, "passed": scoped - len(fails), "failed": len(fails),
            "fail_guids": fails[:500], "truncated": len(fails) > 500,
            "status": "n/a" if scoped == 0 else ("pass" if not fails else "fail")}


def run(idx: dict[str, dict] | None, rules: list[dict]) -> dict:
    """Evaluate the whole library against the model → per-rule results + a by-severity rollup."""
    if not idx:
        return {"model_scored": False, "rules": [], "total_rules": len(rules),
                "note": "No model loaded — load a model to check it against the rules."}
    results = [evaluate(idx, r) for r in rules]
    by_sev: dict[str, int] = {}
    for res in results:
        if res["status"] == "fail":
            by_sev[res["severity"]] = by_sev.get(res["severity"], 0) + 1
    return {"model_scored": True, "rules": results, "total_rules": len(results),
            "failing_rules": sum(1 for r in results if r["status"] == "fail"),
            "total_violations": sum(r["failed"] for r in results),
            "by_severity": by_sev}
