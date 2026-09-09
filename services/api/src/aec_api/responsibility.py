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


MAX_ROLES = 16          # role columns a matrix may carry; `set_config` truncates at it


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


def set_config(db: Session, pid: str, roles: list[str], mode: str, actor: str, *,
               rename: dict[str, str] | None = None, drop: list[str] | None = None,
               commit: bool = True) -> dict:
    """Upsert the config row (role columns + mode) **and migrate every row to match, atomically.**

    The columns and the cells keyed by them are one fact stored in two places, so changing the
    columns without migrating the cells leaves the matrix self-contradictory. `rename` and `drop`
    say how the cells move; the mode's doer letter (R↔D) is remapped whenever `mode` changes,
    because `matrix()` hides any letter that is not valid in the current mode — a stranded "R"
    under DACI does not look wrong, it looks *absent*, and the row simply reports no doer.

    **Every write here shares one transaction.** The panel used to do this from the browser as one
    PATCH per row followed by this call, and a failure part-way committed the rows it had already
    reached: a half-applied rename leaves one logical role under two names, only one of which is
    still a column, and re-running does not repair it because the rows that already moved no longer
    match the name being renamed.

    Refuses, before writing anything:
      * a `rename` whose source is still a column, or whose target is not one — the caller's own
        `roles` list disagreeing with its own `rename` is a bug, and guessing which half is right
        would write the inconsistency rather than the intent;
      * a `drop` naming a column that is still in `roles` — clearing a live column's cells while
        leaving the column standing is silent data loss.
    Raised as `ValueError`, not returned as an `{"error": ...}` dict, so a caller that forgets to
    check cannot proceed as though it had succeeded — which is the exact failure this fixes.
    """
    mode = mode if mode in MODES else "RACI"
    roles = [str(r).strip() for r in roles if str(r).strip()][:MAX_ROLES] or DEFAULT_ROLES
    # Strip on both sides, because `roles` is stripped above: an untrimmed rename target would not
    # be found in the stripped column list and the whole call would 400 on a legitimate rename.
    rename = {k: v for k, v in ((str(k).strip(), str(v).strip()) for k, v in (rename or {}).items())
              if k and v and k != v}
    drop = [d for d in (str(d).strip() for d in (drop or [])) if d]
    have = set(roles)
    for src, dst in rename.items():
        if src in have:
            raise ValueError(f"cannot rename {src!r}: it is still one of the role columns")
        if dst not in have:
            raise ValueError(f"cannot rename {src!r} to {dst!r}: {dst!r} is not a role column")
    for d in drop:
        if d in have:
            raise ValueError(f"cannot clear {d!r}: it is still a role column — remove it first")
    # Two sources onto one target is a MERGE, and the loop below would resolve it by writing
    # `nxt[dst]` twice — the second letter wins, the first is gone, and `rows_remapped` counts the
    # row as successfully migrated. Silently losing a letter is the defect this whole change is
    # about, so refuse rather than pick. Raised in review.
    targets = list(rename.values())
    for dst in targets:
        if targets.count(dst) > 1:
            srcs = sorted(k for k, v in rename.items() if v == dst)
            raise ValueError(f"cannot rename {' and '.join(repr(x) for x in srcs)} both to {dst!r}"
                             " — that would merge two roles into one cell")

    rows, cfg = _rows_and_config(db, pid)
    # The same collision one level down, and it can only be seen in the DATA: a row that already
    # carries the target as well as the source. `roles` and `rename` agree, the request is
    # well-formed, and the row still loses a letter. Checked over every row BEFORE the first write,
    # so the refusal costs nothing and leaves nothing half-applied.
    for r in rows:
        cur = (r.get("data") or {}).get("assignments") or {}
        for src, dst in rename.items():
            if src in cur and dst in cur:
                act = (r.get("data") or {}).get("activity") or r.get("ref") or r["id"]
                raise ValueError(
                    f"cannot rename {src!r} to {dst!r}: {act!r} has a letter on both, so one "
                    "would be lost — clear one of them first")
    before = ((cfg.get("data") if cfg else None) or {}).get("mode")
    before = before if before in MODES else "RACI"
    # R→D (or D→R) only when the mode actually moves. Letters that are already correct, and letters
    # that are neither doer, are left alone — this migrates the grid, it does not rewrite it.
    old_doer, new_doer = DOER[before], DOER[mode]
    remapped = 0
    for r in rows:
        cur = (r.get("data") or {}).get("assignments") or {}
        nxt = {}
        for role, letter in cur.items():
            role = rename.get(role, role)
            if role in drop:
                continue
            if before != mode and letter == old_doer:
                letter = new_doer
            nxt[role] = letter
        if nxt != cur:
            mod.update_record(db, KEY, pid, r["id"], {"assignments": nxt}, actor, None, commit=False)
            remapped += 1

    data = {"kind": "config", "activity": "· matrix settings", "roles": roles, "mode": mode}
    if cfg:
        mod.update_record(db, KEY, pid, cfg["id"], data, actor, None, commit=False)
    else:
        mod.create_record(db, KEY, pid, {"data": data}, actor, None, commit=False)
    if commit:
        db.commit()
    return {"roles": roles, "mode": mode, "rows_remapped": remapped}


def _validate(rows: list[dict], roles: set[str], mode: str) -> dict:
    """Per-row rule checks + role load. Exactly one Accountable, at least one doer (R/D).

    **Counted over the CURRENT columns only, and that is the whole point.** An assignment keyed by
    a role that is not a column is invisible: the grid renders `roles`, so the cell has nowhere to
    appear. Counting it toward "exactly one Accountable" reported a row as complete while the user
    looked at an empty line — and `apply_template` produces exactly that state, because it appends
    rows and *replaces* the role columns, so a second template orphans every earlier row.

    The orphans are not discarded, they are reported: `unknown_role` is what explains a blank row,
    and it is the only place that explanation exists. `accountable_load` is likewise a load across
    the columns that exist — crediting a role nobody can see overstates a real person's ownership.
    """
    doer = DOER[mode]
    missing_accountable, no_responsible, unknown_role = [], [], []
    a_load: dict[str, int] = {}
    for r in rows:
        a = r["assignments"]
        visible = {k: v for k, v in a.items() if k in roles}
        n_acc = sum(1 for v in visible.values() if v == "A")
        n_doer = sum(1 for v in visible.values() if v == doer)
        if n_acc != 1:
            missing_accountable.append({"ref": r["ref"], "activity": r["activity"], "count": n_acc})
        if n_doer < 1:
            no_responsible.append({"ref": r["ref"], "activity": r["activity"]})
        for role, v in a.items():
            if role not in roles:
                unknown_role.append({"ref": r["ref"], "role": role})
            elif v == "A":
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


# ROLES-BIM — the ISO 19650 information-management org: appointing party + lead-appointed-party
# information function, the BIM management line, the delivery task team, and QA/QC. Distinct from the
# construction delivery roles above, and a template may declare its own role columns (`roles`).
BIM_ROLES = ["Appointing Party", "Information Manager", "BIM Manager",
             "BIM Coordinator", "Task Team", "QA/QC"]


def _brow(activity, phase, category, cells):
    a = {BIM_ROLES[i]: cells[i] for i in range(len(cells)) if cells[i]}
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
    # ROLES-BIM — ISO 19650 information-management duties across the BIM-org personas (own role columns)
    "bim_iso19650": {
        "name": "BIM information management (ISO 19650)",
        "description": "The information-management org: appointing party, information manager, and the "
                       "BIM management / task-team / QA line across the ISO 19650-2 activities.",
        "roles": BIM_ROLES,
        "rows": [
            # cols: Appointing Party · Information Manager · BIM Manager · BIM Coordinator · Task Team · QA/QC
            _brow("Establish EIR / information requirements", "Appointment", "Information Mgmt", ["A", "R", "C", "", "", ""]),
            _brow("Produce & maintain the BEP", "Appointment", "Information Mgmt", ["C", "A", "R", "C", "", ""]),
            _brow("Set up & administer the CDE", "Mobilisation", "Information Mgmt", ["I", "A", "R", "C", "", ""]),
            _brow("Author discipline models (TIDP)", "Production", "Design", ["I", "C", "A", "C", "R", ""]),
            _brow("Federate & coordinate / clash detection", "Production", "Quality", ["I", "C", "A", "R", "C", ""]),
            _brow("Model QA — standards & IDS checks", "Production", "Quality", ["I", "C", "A", "C", "C", "R"]),
            _brow("Review & authorize for Shared / Published", "Delivery", "Approvals", ["C", "A", "R", "C", "", "C"]),
            _brow("Deliver information to appointing party", "Delivery", "Information Mgmt", ["A", "R", "C", "", "C", ""]),
            _brow("Archive & PIM → AIM handover", "Handover", "Information Mgmt", ["A", "R", "C", "", "C", ""]),
        ],
    },
}


def templates() -> list[dict]:
    return [{"key": k, "name": v["name"], "description": v["description"], "rows": len(v["rows"]),
             "roles": v.get("roles") or DEFAULT_ROLES}
            for k, v in TEMPLATES.items()]


def apply_template(db: Session, pid: str, key: str, mode: str, actor: str, *,
                   commit: bool = True) -> dict:
    """Append a starter template's rows, and give it the columns its cells are keyed by.

    **The columns are MERGED into the existing set, not swapped for it, whenever rows already
    exist.** This function appends rows and the panel's own dialog promises *"Existing rows are
    kept"* — but it used to replace the role columns outright, and `bim_iso19650` ships its own.
    Loading a second template therefore kept every earlier row and orphaned all of its assignments
    onto columns that no longer existed: the rows rendered blank, and the assignments survived only
    in `_validate`'s `unknown_role`. Keeping the rows and discarding what they say is not keeping
    them.

    On an empty matrix there is nothing to orphan, so the template's roles are adopted as-is and a
    fresh project still gets exactly the columns its template describes.
    """
    tpl = TEMPLATES.get(key)
    if not tpl:
        return {"error": f"unknown template {key!r}", "created": 0}
    mode = mode if mode in MODES else "RACI"
    # DACI reuses the same cell letters except the doer: R→D.
    remap = (lambda v: "D" if v == "R" else v) if mode == "DACI" else (lambda v: v)
    tpl_roles = list(tpl.get("roles") or DEFAULT_ROLES)
    existing_rows, _ = _rows_and_config(db, pid)
    if existing_rows:
        # union, existing columns first so the grid the user knows does not reshuffle under them
        have = config(db, pid)["roles"]
        roles = have + [r for r in tpl_roles if r not in have]
        if len(roles) > MAX_ROLES:
            # REFUSE BEFORE MUTATING. `set_config` truncates at the cap, and the union puts the
            # TEMPLATE's new columns last — so a silent truncation would orphan the very rows this
            # call is about to create, which is the defect this merge exists to prevent, arriving
            # by a second door. Nothing is written.
            return {"error": f"this matrix already has {len(have)} role columns and the "
                             f"{key!r} template needs {len(roles) - len(have)} more, over the "
                             f"{MAX_ROLES}-column limit — remove unused columns first. "
                             "Nothing was changed.", "created": 0}
    else:
        roles = tpl_roles
    # One transaction for the whole application: the config, the doer remap `set_config` performs on
    # any EXISTING rows when the mode moves, and the template's own rows. Seeding half a template
    # onto a matrix whose mode has already flipped is the same self-contradiction as a half rename.
    cfg_out = set_config(db, pid, roles, mode, actor, commit=False)
    created = 0
    for r in tpl["rows"]:
        data = {
            "activity": r["activity"], "phase": r["phase"], "category": r["category"],
            "assignments": {role: remap(v) for role, v in r["assignments"].items()},
        }
        mod.create_record(db, KEY, pid, {"data": data}, actor, None, commit=False)
        created += 1
    if commit:
        db.commit()
    return {"applied": key, "created": created, "mode": mode,
            "rows_remapped": cfg_out["rows_remapped"]}
