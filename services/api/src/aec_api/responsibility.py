"""Responsibility matrix (RACI / DACI) — who does the work, who owns the outcome, who's consulted,
who's informed, across a project's deliverables and decisions.

This is the formal Responsibility Assignment Matrix (RAM) the PMBOK references and that ISO 19650
needs for its MIDP/TIDP (task-team ↔ deliverable ↔ milestone). One row per activity/deliverable;
one column per project role; each cell an assignment letter.

  RACI — R Responsible (does the work, ≥1) · A Accountable (owns it, exactly 1) · C Consulted · I Informed
  DACI — D Driver (coordinates, ≥1)        · A Approver (final call, exactly 1) · C Contributor · I Informed

Storage reuses the config-module engine (CRUD, RBAC, audit, search) with zero new tables:
  * a single **config row** (`data.kind == "config"`) holds the project's role columns + mode;
  * every other `responsibility` record is a **matrix row** whose `data.assignments` maps role → letter.
The engine assembles the grid, validates it (single-Accountable, at-least-one-Responsible, role load),
and ships starter templates for the common construction phases.
"""
from __future__ import annotations

from sqlalchemy.orm import Session

from . import modules as mod

KEY = "responsibility"
MODES = ("RACI", "DACI")
# the accountable/approver letter is "A" in both schemes; the doer is R (RACI) or D (DACI).
DOER = {"RACI": "R", "DACI": "D"}
LETTERS = {"RACI": ["R", "A", "C", "I"], "DACI": ["D", "A", "C", "I"]}

# A sensible construction default; every project can rename / add / remove columns in the UI.
DEFAULT_ROLES = ["Owner", "Architect/EOR", "GC / PM", "Superintendent",
                 "Subcontractor", "Consultant", "Cx Agent"]


def _rows_and_config(db: Session, pid: str) -> tuple[list[dict], dict]:
    recs = mod.list_records(db, KEY, pid, limit=1000)
    config = None
    rows = []
    for r in recs:
        d = r.get("data") or {}
        if d.get("kind") == "config":
            config = r
        else:
            rows.append(r)
    return rows, config


def config(db: Session, pid: str) -> dict:
    """The project's role columns + matrix mode (defaults if never set)."""
    _, cfg = _rows_and_config(db, pid)
    d = (cfg.get("data") if cfg else None) or {}
    roles = d.get("roles") or DEFAULT_ROLES
    mode = d.get("mode") if d.get("mode") in MODES else "RACI"
    return {"id": cfg["id"] if cfg else None, "roles": list(roles), "mode": mode}


def set_config(db: Session, pid: str, roles: list[str], mode: str, actor: str) -> dict:
    """Upsert the single config row (role columns + mode)."""
    mode = mode if mode in MODES else "RACI"
    roles = [str(r).strip() for r in roles if str(r).strip()][:16] or DEFAULT_ROLES
    _, cfg = _rows_and_config(db, pid)
    data = {"kind": "config", "activity": "· matrix settings", "roles": roles, "mode": mode}
    if cfg:
        mod.update_record(db, KEY, pid, cfg["id"], data, actor, None)
    else:
        mod.create_record(db, KEY, pid, {"data": data}, actor, None)
    return {"roles": roles, "mode": mode}


def _validate(rows: list[dict], roles: set[str], mode: str) -> dict:
    """Per-row rule checks + role load. Exactly one Accountable, at least one doer (R/D)."""
    doer = DOER[mode]
    missing_accountable, no_responsible, unknown_role = [], [], []
    a_load: dict[str, int] = {}
    for r in rows:
        a = r["assignments"]
        n_acc = sum(1 for v in a.values() if v == "A")
        n_doer = sum(1 for v in a.values() if v == doer)
        if n_acc != 1:
            missing_accountable.append({"ref": r["ref"], "activity": r["activity"], "count": n_acc})
        if n_doer < 1:
            no_responsible.append({"ref": r["ref"], "activity": r["activity"]})
        for role, v in a.items():
            if role not in roles:
                unknown_role.append({"ref": r["ref"], "role": role})
            if v == "A":
                a_load[role] = a_load.get(role, 0) + 1
    return {
        "missing_accountable": missing_accountable,
        "no_responsible": no_responsible,
        "unknown_role": unknown_role,
        "accountable_load": a_load,
        "clean": not (missing_accountable or no_responsible),
    }


def matrix(db: Session, pid: str) -> dict:
    """The full grid: roles (columns) × rows (activities) with letters, plus validation + summary."""
    raw, cfg = _rows_and_config(db, pid)
    d = (cfg.get("data") if cfg else None) or {}
    roles = d.get("roles") or DEFAULT_ROLES
    mode = d.get("mode") if d.get("mode") in MODES else "RACI"
    rows = []
    for r in raw:
        data = r.get("data") or {}
        assignments = {k: v for k, v in (data.get("assignments") or {}).items()
                       if v in LETTERS[mode]}
        rows.append({
            "id": r["id"], "ref": r.get("ref"),
            "activity": data.get("activity") or r.get("title") or "—",
            "phase": data.get("phase"), "category": data.get("category"),
            "milestone": data.get("milestone"), "reference": data.get("reference"),
            "assignments": assignments,
        })
    rows.sort(key=lambda r: (r["phase"] or "~", r["ref"] or ""))
    validation = _validate(rows, set(roles), mode)
    return {
        "mode": mode, "letters": LETTERS[mode], "doer": DOER[mode],
        "roles": list(roles), "rows": rows, "count": len(rows),
        "validation": validation,
        "summary": {
            "activities": len(rows),
            "clean": validation["clean"],
            "issues": len(validation["missing_accountable"]) + len(validation["no_responsible"]),
        },
    }


# --- starter templates -------------------------------------------------------
# Column order matches DEFAULT_ROLES: Owner, Architect/EOR, GC/PM, Super, Sub, Consultant, Cx.
def _row(activity, phase, category, cells):
    a = {DEFAULT_ROLES[i]: cells[i] for i in range(len(cells)) if cells[i]}
    return {"activity": activity, "phase": phase, "category": category, "assignments": a}


TEMPLATES: dict[str, dict] = {
    "design_delivery": {
        "name": "Design delivery (SD → CD)",
        "description": "Who authors, coordinates and approves the design deliverables.",
        "rows": [
            _row("Establish design basis & program", "Design", "Design", ["A", "R", "C", "", "", "C", ""]),
            _row("Produce discipline models & drawings", "Design", "Design", ["I", "A", "C", "", "", "R", ""]),
            _row("Coordinate / clash resolution", "Design", "Quality", ["I", "A", "R", "", "C", "C", ""]),
            _row("Design QA / standards check", "Design", "Quality", ["I", "A", "C", "", "", "R", ""]),
            _row("Owner design approval", "Design", "Approvals", ["A", "R", "C", "", "", "", ""]),
        ],
    },
    "buyout": {
        "name": "Procurement / buyout",
        "description": "Solicit, level and award trade packages.",
        "rows": [
            _row("Define bid packages & scope", "Procurement", "Procurement", ["C", "C", "A", "R", "", "", ""]),
            _row("Solicit & level bids", "Procurement", "Cost", ["I", "", "A", "R", "C", "", ""]),
            _row("Award & execute subcontracts", "Procurement", "Cost", ["A", "", "R", "", "I", "", ""]),
            _row("Buyout budget reconciliation", "Procurement", "Cost", ["I", "", "A", "R", "", "", ""]),
        ],
    },
    "construction": {
        "name": "Construction execution",
        "description": "Field production, quality, safety and change control.",
        "rows": [
            _row("Daily production & sequencing", "Construction", "Schedule", ["I", "", "A", "R", "R", "", ""]),
            _row("Quality inspections & NCRs", "Construction", "Quality", ["I", "C", "A", "R", "R", "", ""]),
            _row("Site safety program", "Construction", "Safety", ["I", "", "A", "R", "R", "", ""]),
            _row("RFIs & submittals", "Construction", "Design", ["I", "A", "R", "C", "R", "C", ""]),
            _row("Change orders", "Construction", "Cost", ["A", "C", "R", "", "C", "", ""]),
        ],
    },
    "closeout": {
        "name": "Closeout & handover",
        "description": "Punch, commissioning, and the record-model / O&M handover.",
        "rows": [
            _row("Punch list & completion", "Closeout", "Quality", ["A", "C", "R", "R", "R", "", ""]),
            _row("Commissioning", "Commissioning", "Quality", ["A", "C", "C", "C", "R", "", "R"]),
            _row("O&M / COBie handover", "Closeout", "Information Mgmt", ["A", "C", "R", "", "R", "", "C"]),
            _row("Record model / as-builts", "Closeout", "Information Mgmt", ["I", "A", "R", "", "R", "C", ""]),
            _row("Warranty & final payment", "Closeout", "Cost", ["A", "", "R", "", "C", "", ""]),
        ],
    },
}


def templates() -> list[dict]:
    return [{"key": k, "name": v["name"], "description": v["description"], "rows": len(v["rows"])}
            for k, v in TEMPLATES.items()]


def apply_template(db: Session, pid: str, key: str, mode: str, actor: str) -> dict:
    """Create matrix rows from a starter template; also (re)sets the config to the default roles."""
    tpl = TEMPLATES.get(key)
    if not tpl:
        return {"error": f"unknown template {key!r}", "created": 0}
    mode = mode if mode in MODES else "RACI"
    # DACI reuses the same cell letters except the doer: R→D.
    remap = (lambda v: "D" if v == "R" else v) if mode == "DACI" else (lambda v: v)
    set_config(db, pid, DEFAULT_ROLES, mode, actor)
    created = 0
    for r in tpl["rows"]:
        data = {
            "activity": r["activity"], "phase": r["phase"], "category": r["category"],
            "assignments": {role: remap(v) for role, v in r["assignments"].items()},
        }
        mod.create_record(db, KEY, pid, {"data": data}, actor, None)
        created += 1
    return {"applied": key, "created": created, "mode": mode}
