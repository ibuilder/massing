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
    """Freeze every schedule_activity's planned dates + budget, keyed by record id."""
    snap = {}
    for r in me.list_records(db, "schedule_activity", pid, limit=1_000_000):
        data = r.get("data") or {}
        snap[r["id"]] = {"ref": r.get("ref"), "name": r.get("title") or data.get("name"),
                         "start": data.get("start"), "finish": data.get("finish"),
                         "budget": data.get("budget")}
    return snap


def _meta(b: dict) -> dict:
    return {"id": b.get("id"), "name": b.get("name"), "captured_at": b.get("captured_at"),
            "count": len(b.get("activities", {}))}


def list_metas(pid: str) -> list[dict]:
    """Baseline library (metadata only — no frozen activities), newest first."""
    return [_meta(b) for b in reversed(_load(pid))]


def capture(db: Session, pid: str, name: str) -> dict:
    """Snapshot the current schedule as a new named baseline; returns its metadata."""
    baselines = _load(pid)
    b = {"id": uuid.uuid4().hex[:12], "name": (str(name or "").strip() or f"Baseline {len(baselines) + 1}")[:80],
         "captured_at": date.today().isoformat(), "activities": _snapshot(db, pid)}
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
