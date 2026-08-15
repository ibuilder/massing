"""RESOURCE-LEVEL — multiple NAMED schedule baselines + variance against any of them.

The single ``/schedule/baseline`` snapshot (one plan-of-record) becomes a small library of named
baselines — "GMP", "Baseline 2 (post-ASI-014)", "Recovery" — each a frozen snapshot of every
``schedule_activity``'s planned start / finish / budget. Variance can then be measured against ANY
chosen baseline, so a team tracks drift from the contract baseline AND from a later re-baseline at the
same time. One JSON blob per project (``{pid}/schedule_baselines.json``) — no migration.

The legacy singular ``/schedule/baseline`` + default ``/schedule/variance`` are untouched; these named
baselines are a superset.
"""
from __future__ import annotations

import json
import uuid
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from . import modules as me
from . import storage

_KEY = "{pid}/schedule_baselines.json"
_MAX = 12                                             # keep a bounded history; oldest drops off

#: Snapshot schema version, stored on each captured baseline.
#:
#: **1** — dates + budget only. Enough for variance (which compares dates activity-by-activity),
#: and *not* enough to rebuild the network the baseline was scheduled from.
#: **2** — adds the logic: durations, predecessors, calendar and constraints.
#:
#: The version is recorded rather than inferred because the two states are indistinguishable from
#: the data. A v1 snapshot and a v2 snapshot of a schedule that genuinely has no relationships look
#: identical, and rebuilding a v1 snapshot as a network would produce a fully-parallel schedule —
#: every activity starting on day one — which `compare` would then diff against the real one and
#: attribute an enormous delay to logic that was never removed. A confident wrong answer, from data
#: that was simply never captured. `schedule_compare` refuses a v1 baseline for that reason.
SCHEMA = 2

#: Fields frozen into a v2 snapshot, beyond the v1 date/budget set.
#:
#: Deliberately **excludes progress** (`actual_start`, `actual_finish`, `percent`,
#: `remaining_duration`). A baseline is the plan as committed; freezing progress into it produces a
#: baseline that already knows how the job went, and every later comparison against it under-reports
#: the slip by exactly the progress that had been recorded on the day it was captured.
_LOGIC_FIELDS = ("duration", "predecessors", "activity_type", "calendar",
                 "constraint", "constraint_date", "wbs")


def _date(v: Any) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _load(pid: str) -> list[dict]:
    try:
        return json.loads(storage.get(_KEY.format(pid=pid))).get("baselines", [])
    except Exception:                                 # noqa: BLE001 — no blob yet
        return []


def _save(pid: str, baselines: list[dict]) -> None:
    storage.put(_KEY.format(pid=pid), json.dumps({"baselines": baselines}).encode("utf-8"))


def _snapshot(db: Session, pid: str) -> dict[str, dict]:
    """Freeze every schedule_activity's planned dates, budget **and logic**, keyed by record id.

    The logic half is what makes a baseline re-schedulable rather than merely comparable: with
    durations and predecessors frozen alongside the dates, `schedule_compare` can run the baseline
    back through the CPM engine and attribute the finish move to specific causes. Without them the
    only available question is "did this activity's dates move", which is variance, not analysis.
    """
    snap = {}
    for r in me.list_records(db, "schedule_activity", pid, limit=1_000_000):
        data = r.get("data") or {}
        frozen = {"ref": r.get("ref"), "name": r.get("title") or data.get("name"),
                  "start": data.get("start"), "finish": data.get("finish"),
                  "budget": data.get("budget")}
        # Absent fields are omitted rather than stored as None, so a re-scheduled snapshot presents
        # the same shape to `build_network` that a live record does.
        frozen.update({k: data[k] for k in _LOGIC_FIELDS if data.get(k) not in (None, "")})
        snap[r["id"]] = frozen
    return snap


def logic_gap(base: dict) -> str | None:
    """Why this baseline cannot be re-scheduled, or `None` if it can.

    A **sentence, returned as data** — not an exception message. A caller that needs to show the
    reason must not have to stringify an exception to get it: `str(exc)` on a response path is how
    an engine's own words reach a user, and it is a finding this repo has already had twice
    (`py/stack-trace-exposure`, v0.3.956 and again here). Composing it here keeps the refusal text
    ours by construction rather than by care.
    """
    if int(base.get("schema") or 1) < SCHEMA:
        return (f"this baseline was captured before logic was frozen into baselines "
                f"(schema {int(base.get('schema') or 1)}, needs {SCHEMA}); it can still be used for "
                "variance, but a delay attribution needs a baseline captured since")
    return None


def to_records(base: dict) -> list[dict]:
    """A v2 snapshot back in the activity-record shape `schedule_engine.build_network` reads.

    Raises `ValueError` on a v1 snapshot. Rebuilding one would succeed — every activity would come
    back as a 1-day task with no predecessors — and produce a fully-parallel schedule that a diff
    would then blame on logic somebody removed. Refusing is the only honest answer available from
    data that was never captured. Callers that report the reason should ask `logic_gap` first; this
    raise is the backstop for the ones that do not.
    """
    gap = logic_gap(base)
    if gap is not None:
        raise ValueError(gap)
    out = []
    for rid, a in (base.get("activities") or {}).items():
        data = {k: v for k, v in a.items() if k not in ("ref", "name")}
        data["name"] = a.get("name")
        out.append({"id": rid, "ref": a.get("ref"), "title": a.get("name"), "data": data})
    return out


def _meta(b: dict) -> dict:
    return {"id": b.get("id"), "name": b.get("name"), "captured_at": b.get("captured_at"),
            "count": len(b.get("activities", {})), "schema": int(b.get("schema") or 1),
            # The one thing a caller needs to know before offering a delay analysis against it.
            "has_logic": int(b.get("schema") or 1) >= SCHEMA}


def list_metas(pid: str) -> list[dict]:
    """Baseline library (metadata only — no frozen activities), newest first."""
    return [_meta(b) for b in reversed(_load(pid))]


def capture(db: Session, pid: str, name: str) -> dict:
    """Snapshot the current schedule as a new named baseline; returns its metadata."""
    baselines = _load(pid)
    b = {"id": uuid.uuid4().hex[:12], "name": (str(name or "").strip() or f"Baseline {len(baselines) + 1}")[:80],
         "captured_at": date.today().isoformat(), "schema": SCHEMA,
         "activities": _snapshot(db, pid)}
    baselines.append(b)
    _save(pid, baselines[-_MAX:])                     # bound the history
    return _meta(b)


def delete(pid: str, bid: str) -> bool:
    baselines = _load(pid)
    kept = [b for b in baselines if b.get("id") != bid]
    if len(kept) == len(baselines):
        return False
    _save(pid, kept)
    return True


def _get(pid: str, bid: str | None) -> dict | None:
    baselines = _load(pid)
    if not baselines:
        return None
    if bid is None:
        return baselines[-1]                          # default: the most recent baseline
    return next((b for b in baselines if b.get("id") == bid), None)


def compute_variance(base_acts: dict[str, dict], current: dict[str, dict]) -> dict:
    """Per-activity slip vs a baseline snapshot: finish_var/start_var in days (positive = later =
    slipped), plus added/removed activities + a rollup. Shared by the named-baseline endpoint."""
    lines = []
    for rid, b in base_acts.items():
        cur = current.get(rid)
        if not cur:
            lines.append({"ref": b.get("ref"), "name": b.get("name"), "status": "removed",
                          "start_var": None, "finish_var": None})
            continue
        data = cur.get("data") or {}
        bs, bf = _date(b.get("start")), _date(b.get("finish"))
        cs, cf = _date(data.get("start")), _date(data.get("finish"))
        sv = (cs - bs).days if (cs and bs) else None
        fv = (cf - bf).days if (cf and bf) else None
        lines.append({"ref": cur.get("ref"), "name": cur.get("title") or data.get("name"),
                      "start_var": sv, "finish_var": fv,
                      "status": "slipped" if (fv or 0) > 0 else "improved" if (fv or 0) < 0 else "on_baseline"})
    for rid, cur in current.items():
        if rid not in base_acts:
            data = cur.get("data") or {}
            lines.append({"ref": cur.get("ref"), "name": cur.get("title") or data.get("name"),
                          "status": "added", "start_var": None, "finish_var": None})
    slips = [x["finish_var"] for x in lines if x["finish_var"] is not None]
    summary = {"slipped": sum(1 for x in lines if x["status"] == "slipped"),
               "improved": sum(1 for x in lines if x["status"] == "improved"),
               "on_baseline": sum(1 for x in lines if x["status"] == "on_baseline"),
               "added": sum(1 for x in lines if x["status"] == "added"),
               "removed": sum(1 for x in lines if x["status"] == "removed"),
               "max_slip_days": max(slips) if slips else 0,
               "avg_finish_var": round(sum(slips) / len(slips), 1) if slips else 0}
    lines.sort(key=lambda x: (x["finish_var"] is None, -(x["finish_var"] or 0)))
    return {"summary": summary, "activities": lines}


def variance(db: Session, pid: str, bid: str | None = None) -> dict | None:
    """Variance of the live schedule against a named baseline (or the most recent). None if the named
    baseline doesn't exist / no baselines captured."""
    base = _get(pid, bid)
    if base is None:
        return None
    current = {r["id"]: r for r in me.list_records(db, "schedule_activity", pid, limit=1_000_000)}
    out = compute_variance(base.get("activities", {}), current)
    return {"baseline": _meta(base), **out}
