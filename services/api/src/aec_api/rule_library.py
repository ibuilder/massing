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


# --- RULE-PACK FOLD (R18/R16 remainder): the per-IfcSpace pack, same library surface ----------------
# Space checks are GEOMETRIC (footprints, envelopes, shared walls) — they can't be property-index
# selectors without silently-never-matching rules (a false "pass"). So the pack keeps its own honest
# shape, is stored beside the rule library, and /rules/run folds its results into the same rollup.
_SPACE_KEY = "{pid}/space_rule_pack.json"
_MAX_PACK_TYPES = 50


def validate_space_pack(pack: dict) -> dict:
    """Validate + normalize a space rule pack. Sections (all optional): ``dimensional``
    ({min_room_dim/min_area/min_ceiling_height, by_type{}, severity}), ``daylight``
    ({types[], severity}), ``wet_wall`` ({types[], wet_types[]?, severity}). Raises QueryError."""
    if not isinstance(pack, dict):
        raise QueryError("the space pack must be an object")
    out: dict[str, Any] = {}
    def _sev(section: dict, default: str = "medium") -> str:
        s = str(section.get("severity") or default).lower()
        if s not in SEVERITIES:
            raise QueryError(f"severity must be one of {', '.join(SEVERITIES)}")
        return s
    dim = pack.get("dimensional")
    if dim is not None:
        if not isinstance(dim, dict):
            raise QueryError("dimensional must be an object")
        by_type = dim.get("by_type") or {}
        if not isinstance(by_type, dict) or len(by_type) > _MAX_PACK_TYPES:
            raise QueryError(f"by_type must be an object with at most {_MAX_PACK_TYPES} types")
        for k in ("min_room_dim", "min_area", "min_ceiling_height"):
            v = dim.get(k)
            if v is not None and (not isinstance(v, (int, float)) or v < 0 or v > 1000):
                raise QueryError(f"dimensional.{k} must be a number in [0, 1000]")
        out["dimensional"] = {**{k: dim.get(k) for k in
                                 ("min_room_dim", "min_area", "min_ceiling_height") if dim.get(k)},
                              "by_type": by_type, "severity": _sev(dim)}
    for key in ("daylight", "wet_wall"):
        sec = pack.get(key)
        if sec is None:
            continue
        if not isinstance(sec, dict):
            raise QueryError(f"{key} must be an object")
        types = sec.get("types") or []
        if not isinstance(types, list) or not types or len(types) > _MAX_PACK_TYPES:
            raise QueryError(f"{key}.types must be a non-empty list (max {_MAX_PACK_TYPES})")
        out[key] = {"types": [str(t)[:60] for t in types], "severity": _sev(sec)}
        if key == "wet_wall" and sec.get("wet_types"):
            out[key]["wet_types"] = [str(t)[:60] for t in (sec["wet_types"] or [])][:_MAX_PACK_TYPES]
    if not out:
        raise QueryError("the space pack has no sections (dimensional / daylight / wet_wall)")
    return out


def load_space_pack(pid: str) -> dict | None:
    try:
        raw = storage.get(_SPACE_KEY.format(pid=pid))
    except Exception:                                       # noqa: BLE001 — absent blob = no pack
        return None
    try:
        return json.loads(raw.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        return None


def save_space_pack(pid: str, pack: dict) -> dict:
    clean = validate_space_pack(pack)
    storage.put(_SPACE_KEY.format(pid=pid), json.dumps(clean).encode("utf-8"))
    return clean


def run_space_pack(model, pack: dict) -> list[dict]:
    """Run the stored space pack through the adjacency engine → rule-shaped rows (one per section)
    that fold into the same by-severity rollup as the property rules."""
    from aec_data import adjacency  # type: ignore

    program: dict[str, Any] = {}
    if pack.get("dimensional"):
        d = pack["dimensional"]
        program["dimensional"] = {k: d[k] for k in
                                  ("min_room_dim", "min_area", "min_ceiling_height") if d.get(k)}
        if d.get("by_type"):
            program["dimensional"]["by_type"] = d["by_type"]
    if pack.get("daylight"):
        program["needs_daylight"] = pack["daylight"]["types"]
    if pack.get("wet_wall"):
        program["needs_wet_wall"] = pack["wet_wall"]["types"]
        if pack["wet_wall"].get("wet_types"):
            program["wet_types"] = pack["wet_wall"]["wet_types"]
    r = adjacency.evaluate(model, program)
    rows: list[dict] = []
    if pack.get("dimensional"):
        v = r["dimensional"]["violations"]
        rows.append({"id": "space:dimensional", "name": "Space dimensional compliance",
                     "severity": pack["dimensional"]["severity"], "scoped": r["dimensional"]["checked"],
                     "passed": r["dimensional"]["passed"], "failed": len(v),
                     "fail_guids": [x["guid"] for x in v][:500],
                     "detail": [f"{x['name'] or x['guid']}: {'; '.join(x['issues'])}" for x in v][:50],
                     "status": "n/a" if r["dimensional"]["checked"] == 0 else
                               ("pass" if not v else "fail")})
    if pack.get("daylight"):
        v = r["program"]["daylight_violations"]
        n = sum(x["spaces"] for x in r["program"]["daylight_results"])
        rows.append({"id": "space:daylight", "name": "Spaces needing daylight sit on the envelope",
                     "severity": pack["daylight"]["severity"], "scoped": n,
                     "passed": n - len(v), "failed": len(v),
                     "fail_guids": [x["guid"] for x in v][:500],
                     "status": "n/a" if n == 0 else ("pass" if not v else "fail")})
    if pack.get("wet_wall"):
        v = r["program"]["wet_wall_violations"]
        n = sum(x["spaces"] for x in r["program"]["wet_wall_results"])
        rows.append({"id": "space:wet_wall", "name": "Spaces needing a shared wet wall",
                     "severity": pack["wet_wall"]["severity"], "scoped": n,
                     "passed": n - len(v), "failed": len(v),
                     "fail_guids": [x["guid"] for x in v][:500],
                     "status": "n/a" if n == 0 else ("pass" if not v else "fail")})
    return rows
