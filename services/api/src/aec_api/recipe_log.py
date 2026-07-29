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

**The storage ceiling, stated so it is a decision rather than a surprise.** `_MAX` (500 entries) ×
`_MAX_ENTRY` (256 KB) = **~131 MB** worst case per project, and `_load()` re-parses the whole file on
every edit, so that figure is also the ceiling on per-edit cost. It is bounded, which the first
version was not (an unbounded params dict measured 602 MB), but bounded is not the same as small.
Reaching it takes an editor posting maximum-size parameters on 500 consecutive edits; a realistic log
is a few hundred bytes per entry. The cap is kept at 256 KB rather than lowered because a smaller one
elides legitimate parameters, and every elision is a replay this module can no longer reproduce —
which is the capability it exists to provide. If that trade ever looks wrong, lower `_MAX_ENTRY`
first: it costs fidelity on large edits, whereas lowering `_MAX` costs history outright.
"""
from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Any

from . import pid_lock, storage

#: Entries kept per project. The undo stack keeps 50; this keeps more because it is a provenance
#: record rather than a working stack, but it is still bounded — an unbounded sidecar is a slow leak.
_MAX = 500

#: Serialized size above which a single parameter VALUE is elided. 8 KB comfortably holds a rule set
#: or a point list, and excludes the mesh arrays that would otherwise dominate the file.
_MAX_VALUE = 8192

#: Serialized size above which the ENTRY is elided further, largest value first.
#:
#: `_MAX_VALUE` alone bounds each value and therefore bounds nothing: `params` comes off the request
#: body, which is capped by `AEC_MAX_UPLOAD_MB` (1 GB by default), so 300 individually-small values
#: of 4 KB each is a 1.2 MB entry that passes every per-value check with `params_elided=False`. At
#: `_MAX` entries that is a ~600 MB sidecar, and `_load()` re-parses the whole file on EVERY edit —
#: so the cost is not disk, it is that each subsequent edit on that project gets slower, permanently.
_MAX_ENTRY = 262_144

#: Parameter keys always elided regardless of size. No recipe in the registry takes a credential
#: today; this is insurance against one that does, because `export()` hands the whole log out. Keyed
#: on the NAME rather than on a recipe allowlist so it covers recipes nobody has written yet.
_SENSITIVE_KEY = re.compile(r"secret|token|password|passwd|licen[cs]e|api[_-]?key|credential|private[_-]?key",
                            re.I)

LOG_VERSION = 1


class LogUnreadable(RuntimeError):
    """The log file exists but could not be parsed.

    Distinct from "there is no log yet", and the distinction is the whole point: conflating them
    meant a corrupt file read as an empty history, the next append wrote that empty history back, and
    the prior entries were gone — silently, and with `record()` reporting success. For a provenance
    artifact that is the worst available failure: it does not break, it just quietly becomes a
    shorter history, and a reader concludes the project is young."""


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
    """The stored log, or an empty one when there is genuinely nothing stored.

    Raises `LogUnreadable` when the key EXISTS but does not parse. Returning an empty log there —
    which is what a bare `except` did — makes the next `record()` append to nothing and `_save()`
    overwrite the file, destroying every prior entry while reporting success. `storage.exists()`
    distinguishes the two cases, so the destructive path is avoidable and therefore not acceptable.
    """
    key = _key(pid)
    try:
        present = storage.exists(key)
    except Exception:  # noqa: BLE001 — a backend that cannot answer is treated as "unknown", below
        present = True
    if not present:
        return {"version": LOG_VERSION, "entries": []}
    try:
        raw = storage.get(key)
    except Exception as e:  # noqa: BLE001 — exists() said yes and get() failed: do not assume empty
        raise LogUnreadable(f"the recipe log for {pid} exists but could not be read: {e}") from e
    if not raw:
        # A present-but-EMPTY file is unreadable, not absent. Zero bytes is the single most likely
        # physical corruption signature — an interrupted write, a disk-full flush, a container killed
        # mid-put — so treating it as "no log yet" would leave the destructive path open in exactly
        # the case the rest of this function exists to close. `_save` always writes at least
        # `{"version":1,"entries":[]}`, so a log that was ever written is never legitimately empty.
        raise LogUnreadable(
            f"the recipe log for {pid} exists but is empty (0 bytes) — most likely an interrupted "
            "write. It has NOT been overwritten; the file is on disk and can be inspected by hand.")
    try:
        d = json.loads(raw.decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        raise LogUnreadable(
            f"the recipe log for {pid} exists but is not valid JSON ({e}). It has NOT been "
            "overwritten — the file is intact on disk and can be recovered by hand.") from e
    if not isinstance(d, dict) or not isinstance(d.get("entries"), list):
        raise LogUnreadable(
            f"the recipe log for {pid} parsed but is not a log document. It has NOT been overwritten.")
    return {"version": d.get("version", LOG_VERSION), "entries": list(d["entries"])}


def _save(pid: str, d: dict) -> None:
    storage.put(_key(pid), json.dumps(d).encode("utf-8"))


def _digest(raw: bytes) -> str:
    return "sha256:" + hashlib.sha256(raw).hexdigest()[:16]


def _credential_stub(v: Any) -> dict[str, Any]:
    return {"__elided__": True, "type": type(v).__name__,
            "reason": "parameter name looks like a credential; the log is exportable"}


def _redact_names(value: Any, _depth: int = 0) -> tuple[Any, bool]:
    """Apply the credential-name denylist at EVERY level, not just the top.

    The denylist exists for "the recipe nobody has written yet", and anything structured enough to
    carry a credential tends to nest — `{"config": {"api_key": ...}}` is a more plausible shape for
    such a recipe than a flat top-level key. Walking only the top level meant the regex never saw it.

    Size elision stays top-level on purpose: it is about bytes, and a top-level value's serialized
    length already accounts for its children. This pass is about NAMES.

    Depth-capped rather than trusted: params arrive from a request body, and a pathological nesting
    depth should cost a stub, not a RecursionError inside an edit that has already succeeded.
    """
    if _depth > 12:
        # FAIL CLOSED. Returning the sub-tree verbatim here meant a credential nested 13 deep was
        # stored in the clear — and the deeper it was buried the safer it was from the scrubber,
        # which is precisely backwards for a guard whose job is to not persist secrets. The stub
        # also marks the entry elided, so `replay_plan` refuses it like every other elision path.
        return {"__elided__": True, "type": type(value).__name__,
                "reason": "beyond the maximum nesting depth the denylist can scan"}, True
    if isinstance(value, dict):
        out: dict[Any, Any] = {}
        hit = False
        for k, v in value.items():
            if _SENSITIVE_KEY.search(str(k)):
                out[k] = _credential_stub(v)
                hit = True
                continue
            nv, sub = _redact_names(v, _depth + 1)
            out[k] = nv
            hit = hit or sub
        return out, hit
    if isinstance(value, (list, tuple)):
        items, hit = [], False
        for v in value:
            nv, sub = _redact_names(v, _depth + 1)
            items.append(nv)
            hit = hit or sub
        return items, hit
    return value, False


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
        if _SENSITIVE_KEY.search(str(k)):
            out[k] = _credential_stub(v)
            elided = True
            continue
        v, hit = _redact_names(v)
        if hit:
            elided = True
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
    return _fit(e)


def _fit(e: dict[str, Any]) -> dict[str, Any]:
    """Elide the largest remaining parameters until the whole entry fits `_MAX_ENTRY`.

    The per-value cap bounds one value; this bounds the record. Largest-first so the smallest number
    of parameters is lost, and it always terminates: each pass removes the biggest remaining
    un-elided value, and with none left the entry is a fixed set of small descriptors.
    """
    params = e.get("params")
    if not isinstance(params, dict):
        return e
    while _size(e) > _MAX_ENTRY:
        candidates = [(len(json.dumps(v, default=str)), k) for k, v in params.items()
                      if not (isinstance(v, dict) and v.get("__elided__"))]
        if not candidates:
            # Out of values to elide and still over. Elision replaces VALUES, so an entry whose bulk
            # is in its KEY NAMES (4000 keys of 200 chars is ~1.3 MB of pure keys) can never be
            # brought under the cap this way. Replace `params` wholesale so the cap is a guarantee
            # rather than a best effort — `replay_plan` already refuses elided entries, so nothing
            # downstream is fooled by the substitution.
            e["params"] = {"__elided__": True, "reason": "entry too large to store",
                           "keys": len(params), "bytes": _size(e)}
            e["params_elided"] = True
            break
        _, worst = max(candidates)
        raw = json.dumps(params[worst], default=str).encode("utf-8")
        params[worst] = {"__elided__": True, "type": type(params[worst]).__name__,
                         "bytes": len(raw), "hash": _digest(raw),
                         "reason": f"entry exceeded {_MAX_ENTRY} bytes"}
        e["params_elided"] = True
    return e


def _size(e: dict[str, Any]) -> int:
    try:
        return len(json.dumps(e, default=str).encode("utf-8"))
    except (TypeError, ValueError):
        return 0                        # unserializable cannot be measured; _shrink already handled it


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
