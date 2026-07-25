"""Module read + workflow-evaluation layer — the self-contained base under `modules.py`.

REL-3. `modules.py` is imported by ~114 files, which made it the riskiest thing in the codebase to
change and the hardest to reason about. It was carried on the backlog as needing *dependency
injection* to split. It does not: these functions call nothing else in `modules.py`, so the
dependency graph is already acyclic and the fix is a **layering cut**, not a seam.

What lives here: the pure workflow evaluators (which transitions are legal from a state, whose court
a record is in) and the read queries (list / count / state rollups / active records). Everything is a
plain function over a `Session` plus the registry — no writes, no audit, no notification side
effects, so it is safe to call from any read path.

`modules.py` re-exports every name below, so the ~114 importers are untouched.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import rbac
from .modules_registry import TABLES
from .modules_search import _is_postgres, _pg_document, _pg_tsquery
from .modules_search import search_filter as _search_filter


def _transition(mod: dict, frm: str, action: str) -> dict | None:
    for t in mod.get("workflow", {}).get("transitions", []):
        if t["from"] == frm and t["action"] == action:
            return t
    return None

def available_actions(mod: dict, state: str, party: str | None) -> list[dict]:
    out = []
    for t in mod.get("workflow", {}).get("transitions", []):
        if t["from"] == state and rbac.party_allowed(party, t.get("party", [])):
            out.append({"action": t["action"], "to": t["to"], "party": t.get("party", []),
                        "requires": t.get("requires") or []})
    return out

def court_party(mod: dict, state: str | None) -> str | None:
    """The party whose court a record in `state` is in — who owes the primary next move.

    Taken from the FIRST outgoing transition declared for the state: module authors list the primary
    forward action first (e.g. an RFI in `open` is answered by the Consultant before the GC's `void`
    escape hatch), so the first transition's party is the real ball-in-court. `/`-joins a move shared
    by several parties (Consultant/OwnersRep). Returns None for a terminal state — nobody's move —
    so `transition` leaves the last owner in place there."""
    if not state:
        return None
    for t in mod.get("workflow", {}).get("transitions", []):
        if t["from"] == state:
            parties = t.get("party") or []
            return "/".join(parties) if parties else None
    return None

def _json_text(db: Session, col, jkey: str):
    """Portable JSON scalar-as-text extraction (Postgres ->> / SQLite json_extract). `jkey` is a
    module-defined field name (safe to interpolate into the SQLite JSON path)."""
    if _is_postgres(db):
        return col.op("->>")(jkey)
    return func.json_extract(col, f"$.{jkey}")

def list_records(db: Session, key: str, project_id: str, state: str | None = None,
                 q: str | None = None, limit: int = 200, offset: int = 0) -> list[dict]:
    if key not in TABLES:
        raise HTTPException(404, f"unknown module {key!r}")
    t = TABLES[key]
    stmt = select(t).where(t.c.project_id == project_id)
    if state:
        stmt = stmt.where(t.c.workflow_state == state)
    if q:
        # filter in SQL (before LIMIT) so search scales + returns the right rows, not just matches
        # within the first page. Postgres full-text ranks by relevance; SQLite falls back to LIKE.
        stmt = stmt.where(_search_filter(db, t, q))
        if _is_postgres(db) and (tsq := _pg_tsquery(q)):
            stmt = stmt.order_by(func.ts_rank(_pg_document(t), func.to_tsquery("english", tsq)).desc())
    stmt = stmt.order_by(t.c.created_at).limit(limit).offset(offset)
    return [dict(r._mapping) for r in db.execute(stmt)]

def count_records(db: Session, key: str, project_id: str, state: str | None = None,
                  q: str | None = None, since: datetime | None = None) -> int:
    """Count matches for a module filter (state / search / created-since) — for saved-view alerts."""
    if key not in TABLES:
        return 0
    t = TABLES[key]
    stmt = select(func.count()).select_from(t).where(t.c.project_id == project_id)
    if state:
        stmt = stmt.where(t.c.workflow_state == state)
    if q:
        stmt = stmt.where(_search_filter(db, t, q))
    if since is not None:
        stmt = stmt.where(t.c.created_at > since)
    return int(db.execute(stmt).scalar() or 0)

def state_counts(db: Session, key: str, project_id: str) -> dict[str, int]:
    """{workflow_state: count} for a module via a single GROUP BY on the indexed `workflow_state`
    column — no JSON `data` is loaded or parsed. For dashboards / rollups that only need status
    tallies. Empty dict for an unknown module; a NULL state is keyed by ""."""
    if key not in TABLES:
        return {}
    t = TABLES[key]
    stmt = (select(t.c.workflow_state, func.count()).where(t.c.project_id == project_id)
            .group_by(t.c.workflow_state))
    return {(state or ""): int(n) for state, n in db.execute(stmt).all()}

def state_counts_all(db: Session, project_id: str) -> dict[str, dict[str, int]]:
    """DASH-UNION (PERF-4): every module's {workflow_state: count} in ONE round-trip — a UNION ALL of
    the per-module GROUP BYs. The dashboard previously issued one query per registered module (~124);
    at scale the round-trips, not the row work, dominated. Only non-empty modules appear in the
    result, so callers keep their `if not total: continue` shape."""
    from sqlalchemy import literal, union_all
    parts = [
        select(literal(key).label("mod"), t.c.workflow_state, func.count().label("n"))
        .where(t.c.project_id == project_id).group_by(t.c.workflow_state)
        for key, t in TABLES.items()
    ]
    if not parts:
        return {}
    out: dict[str, dict[str, int]] = {}
    for mod_key, state, n in db.execute(union_all(*parts)).all():
        out.setdefault(mod_key, {})[state or ""] = int(n)
    return out

def active_records(db: Session, key: str, project_id: str, exclude_states: set[str],
                   with_data: bool = True, states: set[str] | None = None,
                   limit: int | None = None) -> list[dict]:
    """Lean records NOT in `exclude_states` (e.g. closed/done): the columns a dashboard needs —
    id, ref, title, workflow_state, assignee (+ the `data` blob when `with_data`, for due dates).
    Skips parsing JSON for the typically-large tail of completed records.

    `with_data=False` omits the JSON entirely (the big cost at scale) for callers that only need the
    lean columns. `states` restricts to a specific state set (indexed) instead of the whole active
    tail; `limit` caps the rows returned — together they let a dashboard pull just the actionable
    slice of a mega-project module instead of every open row."""
    t = TABLES[key]
    cols = [t.c.id, t.c.ref, t.c.title, t.c.workflow_state, t.c.assignee]
    if with_data:
        cols.append(t.c.data)
    stmt = select(*cols).where(t.c.project_id == project_id)
    if states is not None:
        stmt = stmt.where(t.c.workflow_state.in_(states))
    else:
        stmt = stmt.where(t.c.workflow_state.notin_(exclude_states))
    if limit is not None:
        stmt = stmt.limit(limit)
    return [dict(r._mapping) for r in db.execute(stmt)]
