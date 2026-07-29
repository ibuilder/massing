"""R23-RECIPE-ARTIFACT — the edit-recipe log as a first-class, replayable artifact.

**The ring entry's premise needed correcting before this could be built.** It reads: *"make the
edit-recipe log first-class: versioned, diffable, exportable, replayable against a fresh IFC. It
already IS a CAD operation timeline; formalising it serves provenance, the as-built audit trail, and
AI consumption in one move."*

There was no timeline to formalise. What existed was two things, neither of which is one:

* `edit_history.json` — a stack of **file paths** for undo/redo. No recipe, no parameters, no actor,
  no time. Restoring a prior path is all it has to do, and it does that.
* the audit log — one row per edit. `/edit` records `detail=result`, which is the recipe's
  **outputs**; `/edit/batch` records `[s["recipe"] for s in steps]`, the recipe **names**.

So the *inputs* were nowhere. Every capability the item asks for depends on them: you cannot replay
an operation you did not record the arguments to, cannot diff two edits whose arguments you never
kept, and cannot export a provenance trail that says only "something called add_wall happened".

This module records the missing half. Each entry is what would have to be true to re-run the edit on
a different file: the recipe, its parameters, who ran it, when, the source it ran against and the
source it produced, and the outputs it claimed.

**Parameters are recorded, and parameters can be large.** A mesh recipe carries vertex arrays;
`map_properties` carries a whole rule set. An unbounded log turns a sidecar JSON into something that
has to be paged in on every read. So a parameter value over `_MAX_VALUE` bytes is replaced by a
descriptor — its type, size and a hash — and the entry is marked `params_elided`. A replay of an
elided entry is **refused**, not attempted with the descriptor: the point of the log is that a replay
either reproduces the edit or says it cannot.

**Replay is a plan, not an execution.** `replay_plan()` returns the steps in order for the caller to
apply through the existing `/edit/batch` path. Re-running edits is exactly the kind of thing that
should have one author and one audit row, and a log that could re-run itself would have neither.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from . import pid_lock, storage

#: Entries kept per project. The undo stack keeps 50; this keeps more because it is a provenance
#: record rather than a working stack, but it is still bounded — an unbounded sidecar is a slow leak.
_MAX = 500

#: Serialized size above which a single parameter VALUE is elided. 8 KB comfortably holds a rule set
#: or a point list, and excludes the mesh arrays that would otherwise dominate the file.
_MAX_VALUE = 8192

LOG_VERSION = 1


def _key(pid: str) -> str:
    return f"{storage.safe_seg(pid)}/recipe_log.json"


def _locked(fn):
    """Serialize load→mutate→save per project — same rationale as `edit_history._locked`."""
    import functools

    @functools.wraps(fn)
    def wrap(pid, *a, **k):
        with pid_lock.mutating(pid):
            return fn(pid, *a, **k)
    return wrap


def _load(pid: str) -> dict:
    try:
        d = json.loads(storage.get(_key(pid)).decode("utf-8"))
        return {"version": d.get("version", LOG_VERSION), "entries": list(d.get("entries") or [])}
    except Exception:  # noqa: BLE001 — no log yet / unreadable → empty, never fatal
        return {"version": LOG_VERSION, "entries": []}


def _save(pid: str, d: dict) -> None:
    storage.put(_key(pid), json.dumps(d).encode("utf-8"))


def _digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()[:16]


def _shrink(params: Any) -> tuple[Any, bool]:
    """Params with over-large values replaced by descriptors. Returns (params, elided?).

    A descriptor keeps what a reader needs to recognise the value — its type, its length and a hash —
    without keeping the value. It is deliberately NOT a truncation: half a vertex array looks like a
    vertex array and would invite somebody to use it.
    """
    if not isinstance(params, dict):
        return params, False
    out: dict[str, Any] = {}
    elided = False
    for k, v in params.items():
        try:
            # STRICT dumps, no `default=`. With a fallback encoder this never raises — every value
            # "serializes" — so a value that cannot round-trip would be stored as-is and then fail in
            # `_save`, where `append_safe` swallows it and the WHOLE entry is silently lost. Eliding
            # one parameter is a gap you can see; losing the entry is a gap you cannot.
            raw = json.dumps(v).encode("utf-8")
        except (TypeError, ValueError):
            out[k] = {"__elided__": True, "type": type(v).__name__, "reason": "not JSON-serializable"}
            elided = True
            continue
        if len(raw) > _MAX_VALUE:
            out[k] = {"__elided__": True, "type": type(v).__name__, "bytes": len(raw),
                      "length": len(v) if isinstance(v, (list, tuple, str, dict)) else None,
                      "hash": _digest(raw)}
            elided = True
        else:
            out[k] = v
    return out, elided


def entry(recipe: str, params: dict | None, *, actor: str | None, source_in: str | None,
          source_out: str | None, outputs: Any = None, batch: str | None = None,
          at: str | None = None) -> dict[str, Any]:
    """Build one log entry. Pure — separated from `record` so it can be tested without storage."""
    shrunk, elided = _shrink(params or {})
    e: dict[str, Any] = {
        "recipe": recipe,
        "params": shrunk,
        "params_elided": elided,
        "actor": actor,
        "at": at or datetime.now(timezone.utc).isoformat(),
        # Basenames, not full paths: the log is exported and read elsewhere, and a server filesystem
        # layout is neither useful to the reader nor something to hand out.
        "source_in": _base(source_in),
        "source_out": _base(source_out),
        "outputs": outputs,
    }
    if batch:
        e["batch"] = batch
    return e


def _base(path: str | None) -> str | None:
    if not path:
        return None
    return str(path).replace("\\", "/").rsplit("/", 1)[-1]


@_locked
def record(pid: str, entries: list[dict[str, Any]]) -> int:
    """Append entries. Returns the number stored.

    Callers wrap this in a try/except: a provenance record that can break an edit is a worse trade
    than a provenance record with a gap in it. `append_safe` does that wrapping so no call site has
    to remember."""
    if not entries:
        return 0
    d = _load(pid)
    d["entries"] = (d["entries"] + list(entries))[-_MAX:]
    _save(pid, d)
    return len(entries)


def append_safe(pid: str, entries: list[dict[str, Any]]) -> None:
    """Fail-open `record`. The edit has already happened and been committed by the time this runs;
    raising here would turn a logging fault into a failed edit that in fact succeeded."""
    try:
        record(pid, entries)
    except Exception:  # noqa: BLE001 — see docstring; a gap in the log beats a false failure
        import logging
        logging.getLogger("aec").warning("recipe_log: could not record %d entry(ies) for %s",
                                         len(entries), pid, exc_info=True)


def log(pid: str, *, limit: int = 200, offset: int = 0, recipe: str | None = None) -> dict[str, Any]:
    """The log, newest first."""
    d = _load(pid)
    rows = list(reversed(d["entries"]))
    if recipe:
        rows = [r for r in rows if r.get("recipe") == recipe]
    total = len(rows)
    page = rows[max(0, offset): max(0, offset) + max(1, limit)]
    return {
        "version": d["version"], "total": total, "returned": len(page),
        "offset": max(0, offset), "entries": page,
        "recipes": sorted({r.get("recipe") for r in d["entries"] if r.get("recipe")}),
        "elided": sum(1 for r in d["entries"] if r.get("params_elided")),
        "bounded_at": _MAX,
        "note": (f"the log keeps the most recent {_MAX} entries; older edits have been dropped"
                 if len(d["entries"]) >= _MAX else None),
    }


def diff(a: dict[str, Any], b: dict[str, Any]) -> dict[str, Any]:
    """What changed between two entries — which parameters differ, and how.

    Only meaningful for two runs of the SAME recipe, and that is asserted rather than assumed: the
    parameter names of `add_wall` and `set_pset` have nothing to say to each other, and a key-by-key
    comparison across them would report every field as changed and mean nothing.
    """
    if a.get("recipe") != b.get("recipe"):
        return {"comparable": False,
                "reason": f"different recipes ({a.get('recipe')!r} vs {b.get('recipe')!r}) — their "
                          "parameters are not the same vocabulary, so a field-level diff would be "
                          "noise rather than information"}
    pa, pb = a.get("params") or {}, b.get("params") or {}
    keys = sorted(set(pa) | set(pb))
    changed = [{"param": k, "before": pa.get(k), "after": pb.get(k)}
               for k in keys if pa.get(k) != pb.get(k)]
    return {
        "comparable": True, "recipe": a.get("recipe"),
        "changed": changed, "unchanged": [k for k in keys if pa.get(k) == pb.get(k)],
        "identical": not changed,
        "elided": bool(a.get("params_elided") or b.get("params_elided")),
        "elided_warning": ("one or both entries have elided parameters; a value replaced by a "
                           "descriptor compares by hash, so an unchanged descriptor means the value "
                           "was identical but a changed one only means it differed")
                          if (a.get("params_elided") or b.get("params_elided")) else None,
    }


class ReplayError(ValueError):
    """The log cannot produce a faithful replay, and will not produce an unfaithful one."""


def replay_plan(entries: list[dict[str, Any]], *, indices: list[int] | None = None) -> dict[str, Any]:
    """Ordered `{recipe, params}` steps for `/edit/batch`.

    Refuses on any entry whose parameters were elided. The alternative — replaying with the
    descriptor in place of the value — produces a recipe call that looks like the original and is
    not, which is the one outcome a provenance feature must never produce. Refusing names the
    entries, so the caller knows which edits cannot be reproduced and why.
    """
    picked = entries if indices is None else [entries[i] for i in indices
                                              if 0 <= i < len(entries)]
    if indices is not None and len(picked) != len(indices):
        raise ReplayError("one or more indices are outside the log")
    if not picked:
        raise ReplayError("nothing to replay")
    bad = [i for i, e in enumerate(picked) if e.get("params_elided")]
    if bad:
        names = ", ".join(f"#{i} {picked[i].get('recipe')}" for i in bad)
        raise ReplayError(
            f"{len(bad)} entry(ies) have elided parameters and cannot be replayed faithfully: {names}. "
            "Replaying them with the stored descriptor would call the recipe with something that "
            "resembles the original argument and is not it")
    return {
        "steps": [{"recipe": e["recipe"], "params": e.get("params") or {}} for e in picked],
        "count": len(picked),
        "note": "apply with POST /projects/{pid}/edit/batch — one version, one audit row, one author. "
                "This module does not execute; a replay should have an author the same way the "
                "original edit did",
    }


def export(pid: str) -> dict[str, Any]:
    """The whole log as a portable document, oldest first — the provenance artifact.

    Oldest-first because this is meant to be read as a sequence of operations, and because that is
    the order `replay_plan` needs. `log()` is newest-first because that is the order a person reads a
    history in. The two orders are deliberate and are each stated in the payload."""
    d = _load(pid)
    return {
        "version": d["version"], "project": pid, "order": "oldest_first",
        "count": len(d["entries"]), "entries": d["entries"],
        "elided": sum(1 for r in d["entries"] if r.get("params_elided")),
        "replayable": all(not r.get("params_elided") for r in d["entries"]),
        "bounded_at": _MAX,
    }
