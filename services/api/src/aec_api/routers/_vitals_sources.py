"""Where each vital comes from — the wiring, kept apart from the arithmetic.

`vitals.py` assembles six numbers and knows nothing about how to fetch them; this module knows how to
fetch them and does no arithmetic. The split is what lets the assembler be tested without a database,
and it keeps the "which engine owns this number" decision in one readable list instead of scattered
through a router.

**Every call is the engine's own public entry point.** None of these numbers is recomputed here,
because a second implementation is a second answer — which is the defect (`finding 03`: the app
contradicts itself on screen) that made a single vitals endpoint necessary in the first place.
"""
from __future__ import annotations

from typing import Any

from .. import adjacency, bim_kpi, dashboard, schedule_cpm
from .. import modules as me


def _quiet(fn, *a, **kw):
    """An engine that cannot answer yet is not an error.

    A project with no schedule genuinely has no float; a project with no solved scenario genuinely
    has no IRR. Both are answers, and both must degrade to `None` with a note rather than 500 the
    strip that renders on every screen.
    """
    try:
        return fn(*a, **kw)
    except Exception:                                    # noqa: BLE001 — any gap means "not yet"
        return None


def _lod_counts(db, pid: str) -> dict[str, Any] | None:
    """LOD stage histogram — `representations.lod_summary`, the same call `/projects/{pid}/lod` makes.

    (First draft of this reached for `element_facts.lod_summary`, which does not exist. Verified
    against the route rather than assumed — the module that *sounds* like the owner often is not.)
    """
    def _read():
        from aec_data import representations as rep  # type: ignore
        from aec_data.ifc_loader import open_model  # type: ignore

        from ..models import Project
        proj = db.query(Project).filter(Project.id == pid).first()
        if not proj or not proj.source_ifc:
            return None
        return rep.lod_summary(open_model(proj.source_ifc))
    return _quiet(_read)


def _irr(db, pid: str) -> float | None:
    """Equity IRR from the solved proforma — never from a stored copy.

    Read from the scenario the finance room shows. If nothing is solved this is `None`, and the strip
    says "no solved scenario" rather than rendering 0% — a zero IRR claims the deal is worthless,
    which is a different statement from "not underwritten yet".
    """
    def _read() -> float | None:
        rows = me.list_records(db, "proforma_scenario", pid, limit=50) or []
        for r in rows:
            d = r.get("data") or {}
            for k in ("equity_irr", "irr", "levered_irr", "project_irr"):
                v = d.get(k)
                if isinstance(v, (int, float)):
                    return float(v) / 100.0 if abs(float(v)) > 1.5 else float(v)
        return None
    return _quiet(_read)


def gather(db, pid: str) -> dict[str, Any]:
    """Every engine result the assembler needs, each degraded independently."""
    cost = _quiet(dashboard.build, db, pid, "GC") or {}
    budget = ((cost.get("cost") or {}).get("budget")) if isinstance(cost, dict) else None

    acts = _quiet(me.list_records, db, "schedule_activity", pid, limit=1_000_000) or []
    return {
        "lod_counts": _lod_counts(db, pid),
        "scorecard": _quiet(bim_kpi.scorecard, db, pid),
        "cpm": _quiet(schedule_cpm.compute, acts) if acts else None,
        "spaces": _quiet(adjacency.summary, db, pid),
        "budget": budget,
        "irr": _irr(db, pid),
    }
