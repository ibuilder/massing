"""Project assistant — extends "ask the model" from the BIM property index to the *whole project*:
module status tallies (RFIs, submittals, COs, punch, safety…), schedule KPIs, budget, and the risk
headline. Builds one grounded snapshot and answers via the AI provider; without a key it returns the
snapshot so the data is still useful. (A step toward an OpenConstructionERP-style DB chat.)"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

_KEY_MODULES = ("rfi", "submittal", "cor", "change_event", "punchlist", "inspection",
                "incident", "daily_report", "deficiency", "ncr", "permit")


def project_snapshot(db: Session, pid: str) -> dict[str, Any]:
    from . import modules as me
    from . import px
    from .models import Project
    p = db.get(Project, pid)
    snap: dict[str, Any] = {"project": p.name if p else pid}
    mods: dict[str, Any] = {}
    for key in _KEY_MODULES:
        if key in me.TABLES:
            counts = me.state_counts(db, key, pid)
            if counts:
                mods[key] = counts
    snap["modules"] = mods
    try:
        s = px.summary(db, pid)
        snap["schedule"] = s.get("schedule")
        snap["budget"] = s.get("budget")
        snap["overall_status"] = s.get("status")
    except Exception:                              # noqa: BLE001 — snapshot is best-effort
        pass
    try:
        snap["risk_headline"] = px.risk_digest(db, pid).get("headline")
    except Exception:                              # noqa: BLE001
        pass
    try:
        from . import rentroll
        rr = rentroll.rent_roll(db, pid)
        if rr.get("lease_count"):
            # RENTROLL-BASIS -- an assistant quoting an occupancy it cannot qualify is the one
            # consumer that will be asked to explain the number later.
            snap["rent_roll"] = {"occupancy_pct": rr["occupancy_pct"],
                                 "occupancy_basis": rr.get("occupancy_basis"),
                                 "in_place_gross_income": rr["in_place_gross_income"]}
            if rr.get("occupancy_basis") == "leased":
                snap["rent_roll"]["occupancy_note"] = rr.get("occupancy_note")
    except Exception:                              # noqa: BLE001
        pass
    return snap


def ask(db: Session, pid: str, question: str) -> dict[str, Any]:
    from . import ai
    return ai.ask(question, project_snapshot(db, pid))
