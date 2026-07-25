"""WFE-3 — per-project workflow overrides.

Module workflows ship as `module.json` defaults: sensible for most jobs, wrong for some. One owner
wants a second approval before a change order is executed; another runs submittals without a
consultant review. Today that means editing the shipped module — which changes it for every project.

An override is a per-project blob (`{pid}/workflow_config.json`, no migration) holding a replacement
transition list per module key. `effective(mod, pid)` returns the module with its workflow swapped,
and the engine evaluates that instead of the default.

**The validation is the feature.** A workflow is not just a schema — records are *sitting in* its
states right now. An override that removes the last way out of a state does not fail loudly; it
silently strands every record already there, and nobody notices until someone asks why a submittal
has been in review for three weeks. So `validate()` checks the graph *and* counts the live records
each change would trap, and `save()` refuses rather than reporting it as a warning nobody reads.

Pure over the module dict + a DB session for the record counts.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy.orm import Session

from .query_dsl import QueryError  # reused so the routers' 422 mapping already covers us

_KEY = "{pid}/workflow_config.json"
MAX_TRANSITIONS = 60                          # a workflow, not a rules engine
MAX_ACTION_LEN = 40


def load(pid: str) -> dict[str, Any]:
    """Every module override saved for this project ({} when none)."""
    from . import storage
    try:
        return json.loads(storage.get(_KEY.format(pid=pid))).get("modules", {})
    except Exception:                         # noqa: BLE001 — no blob yet / unreadable
        return {}


def effective(mod: dict, pid: str, cfg: dict | None = None) -> dict:
    """`mod` with its workflow transitions replaced by this project's override, if it has one.

    Returns the module unchanged when there is no override — so every caller can route through this
    without paying for a copy on the common path.
    """
    over = (cfg if cfg is not None else load(pid)).get(mod.get("key"))
    if not over or not over.get("transitions"):
        return mod
    wf = dict(mod.get("workflow") or {})
    wf["transitions"] = over["transitions"]
    out = dict(mod)
    out["workflow"] = wf
    out["workflow_overridden"] = True         # so a UI can say the states aren't the shipped ones
    return out


def _states(mod: dict) -> list[str]:
    return list((mod.get("workflow") or {}).get("states") or [])


def _norm(mod: dict, transitions: list[dict]) -> list[dict]:
    """Validate + normalise a transition list against the module's declared states."""
    if not isinstance(transitions, list) or not transitions:
        raise QueryError("transitions must be a non-empty list")
    if len(transitions) > MAX_TRANSITIONS:
        raise QueryError(f"too many transitions ({len(transitions)}) — max {MAX_TRANSITIONS}")
    states = set(_states(mod))
    if not states:
        raise QueryError(f"module {mod.get('key')!r} has no workflow to override")
    out: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for t in transitions:
        if not isinstance(t, dict):
            raise QueryError("each transition must be an object")
        frm, to = str(t.get("from") or "").strip(), str(t.get("to") or "").strip()
        action = str(t.get("action") or "").strip()
        if not frm or not to or not action:
            raise QueryError("each transition needs 'from', 'to' and 'action'")
        if len(action) > MAX_ACTION_LEN:
            raise QueryError(f"action {action!r} is too long (max {MAX_ACTION_LEN})")
        for s, label in ((frm, "from"), (to, "to")):
            if s not in states:
                raise QueryError(f"{label} state {s!r} is not declared by {mod.get('key')!r} "
                                 f"(states: {', '.join(sorted(states))}) — an override may rewire the "
                                 f"states a module HAS, never invent new ones")
        if (frm, action) in seen:
            raise QueryError(f"duplicate transition {frm!r} + {action!r} — the engine would pick one "
                             f"arbitrarily")
        seen.add((frm, action))
        clean: dict[str, Any] = {"from": frm, "to": to, "action": action}
        for opt in ("party", "requires"):
            v = t.get(opt)
            if v:
                if not isinstance(v, list) or not all(isinstance(x, str) for x in v):
                    raise QueryError(f"{opt!r} must be a list of strings")
                clean[opt] = v
        out.append(clean)
    return out


def _reachability(mod: dict, transitions: list[dict]) -> tuple[set[str], set[str]]:
    """(states reachable from the initial state, states with no way out)."""
    initial = (mod.get("workflow") or {}).get("initial")
    edges: dict[str, list[str]] = {}
    for t in transitions:
        edges.setdefault(t["from"], []).append(t["to"])
    reachable: set[str] = set()
    stack = [initial] if initial else []
    while stack:
        s = stack.pop()
        if s in reachable:
            continue
        reachable.add(s)
        stack.extend(edges.get(s, []))
    dead = {s for s in _states(mod) if s not in edges}
    return reachable, dead


def validate(db: Session, pid: str, key: str, transitions: list[dict]) -> dict[str, Any]:
    """Validate an override against the module AND against the records that already exist.

    Raises `QueryError` when the override would strand live records — a state that records are
    sitting in with no transition out. That is not a warning: a stranded record looks identical to a
    record nobody has got to yet, so it goes unnoticed for as long as anyone is willing to wait.
    """
    from . import modules as me
    from . import modules_registry

    mod = modules_registry.get_module(key)
    clean = _norm(mod, transitions)
    reachable, dead = _reachability(mod, clean)

    counts = me.state_counts(db, key, pid)
    # a state is only a problem if it (a) has no way out AND (b) is not terminal in the shipped
    # workflow — a genuinely terminal state SHOULD have no exit
    shipped_dead = {s for s in _states(mod)
                    if not any(t["from"] == s for t in (mod.get("workflow") or {}).get("transitions") or [])}
    stranding = {s: counts.get(s, 0) for s in dead
                 if s not in shipped_dead and counts.get(s, 0) > 0}
    if stranding:
        detail = ", ".join(f"{n} in {s!r}" for s, n in sorted(stranding.items()))
        raise QueryError(
            f"this override would strand live records with no way out: {detail}. Add a transition "
            f"out of those states, or move the records first — a stranded record looks exactly like "
            f"one nobody has got to yet.")

    orphan_records = {s: counts.get(s, 0) for s in _states(mod)
                      if s not in reachable and counts.get(s, 0) > 0}
    return {
        "transitions": clean,
        "reachable": sorted(reachable),
        "unreachable": sorted(set(_states(mod)) - reachable),
        # a state that is unreachable but already holds records is legal (they got there under the old
        # workflow) — reported so the operator can decide, not refused
        "unreachable_with_records": orphan_records,
        "dead_ends": sorted(dead),
        "record_counts": counts,
    }


def save(db: Session, pid: str, key: str, transitions: list[dict]) -> dict[str, Any]:
    """Validate then persist one module's override. Nothing is written if validation fails."""
    from . import storage
    result = validate(db, pid, key, transitions)
    cfg = load(pid)
    cfg[key] = {"transitions": result["transitions"]}
    storage.put(_KEY.format(pid=pid), json.dumps({"modules": cfg}).encode("utf-8"))
    return result


def clear(pid: str, key: str) -> bool:
    """Drop one module's override, returning it to the shipped workflow. True when one was removed."""
    from . import storage
    cfg = load(pid)
    if key not in cfg:
        return False
    cfg.pop(key)
    storage.put(_KEY.format(pid=pid), json.dumps({"modules": cfg}).encode("utf-8"))
    return True
