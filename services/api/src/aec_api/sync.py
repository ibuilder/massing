"""External-system sync — the other half of interoperability: pull records from a connected
source into the GC-portal module model. Procore RFIs / submittals / change events → the matching
modules, idempotent by the Procore record id stored in each imported record's data."""
from __future__ import annotations

import logging
from typing import Any

from sqlalchemy.orm import Session

from . import connectors
from . import modules as me

# kind -> (module key, connectors fetch attr)
KINDS: dict[str, tuple[str, str]] = {
    "rfi": ("rfi", "procore_rfis"),
    "submittal": ("submittal", "procore_submittals"),
    "change_event": ("change_event", "procore_change_events"),
}


def _existing_procore_ids(db: Session, module_key: str, project_id: str) -> set:
    """The procore_ids already imported — selected as ONE json-extracted column in SQL, not by
    materializing every record dict (the previous limit=1_000_000 list_records pulled each record's
    full JSON blob into memory just to read one key)."""
    from sqlalchemy import func, select
    t = me.TABLES[module_key]
    if db.get_bind().dialect.name == "postgresql":
        col = t.c.data.op("->>")("procore_id")
    else:                                          # SQLite
        col = func.json_extract(t.c.data, "$.procore_id")
    rows = db.execute(select(col).where(t.c.project_id == project_id, col.isnot(None)))
    return {str(r[0]) for r in rows}             # normalize: PG ->> yields text, SQLite the raw type


def _sync_kind(db: Session, project_id: str, kind: str, token: str, procore_project_id: str,
               actor: str, party: str | None, mappings: dict | None = None) -> dict[str, Any]:
    module_key, fetch_attr = KINDS[kind]
    items = getattr(connectors, fetch_attr)(token, procore_project_id)
    have = _existing_procore_ids(db, module_key, project_id)
    imported = 0
    for it in items:
        m = connectors.map_procore(kind, it, mappings)        # admin field mapping applied
        if not m["procore_id"] or str(m["procore_id"]) in have:
            continue
        me.create_record(db, module_key, project_id,
                         {"data": {**m["data"], "procore_id": m["procore_id"]}}, actor, party)
        have.add(str(m["procore_id"]))
        imported += 1
    return {"module": module_key, "fetched": len(items), "imported": imported,
            "skipped": len(items) - imported}


def sync_procore(db: Session, project_id: str, token: str, procore_project_id: str,
                 kinds: list[str], actor: str, party: str | None,
                 mappings: dict | None = None) -> dict[str, Any]:
    """Import the requested Procore record kinds into their modules (idempotent), applying the
    connection's admin field mapping. Re-running only imports records not already present."""
    results = {k: _sync_kind(db, project_id, k, token, procore_project_id, actor, party, mappings)
               for k in kinds if k in KINDS}
    return {"source": "procore", "results": results,
            "imported_total": sum(r["imported"] for r in results.values())}


# --- two-way: push local changes back to Procore -------------------------------
_PUSHABLE_RFI = {"answered", "closed"}


def push_procore(db: Session, project_id: str, token: str, procore_project_id: str,
                 kinds: list[str], actor: str) -> dict[str, Any]:
    """Push locally-resolved records back to Procore (v1: RFI status + answer). Only records
    imported from Procore (have procore_id) are pushed; idempotent via procore_pushed_state."""
    results: dict[str, Any] = {}
    if "rfi" in kinds:
        pushed = skipped = 0
        errors: list[str] = []
        for r in me.list_records(db, "rfi", project_id, limit=1_000_000):
            d = r.get("data") or {}
            ext, state = d.get("procore_id"), r["workflow_state"]
            if not ext or state not in _PUSHABLE_RFI:
                continue
            if d.get("procore_pushed_state") == state:
                skipped += 1
                continue
            try:
                connectors.procore_update_rfi(token, procore_project_id, str(ext),
                                              connectors.map_rfi_to_procore(r))
                me.update_record(db, "rfi", project_id, r["id"], {"procore_pushed_state": state}, actor, None)
                pushed += 1
            except Exception as e:               # noqa: BLE001 — one bad push mustn't stop the rest
                errors.append(str(e).splitlines()[0][:100])
        results["rfi"] = {"pushed": pushed, "skipped": skipped, "errors": errors}
    return {"source": "procore", "direction": "push", "results": results,
            "pushed_total": sum(v["pushed"] for v in results.values())}


# --- scheduled / auto-sync -----------------------------------------------------
def _aware(dt):
    from datetime import timezone
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def run_schedule(db: Session, sched, actor: str = "procore-sync") -> dict[str, Any]:
    """Run one schedule now (used by run-now + the background loop)."""
    from .models import Connection
    c = db.get(Connection, sched.connection_id)
    if not c or c.type != "procore" or not (c.config or {}).get("access_token"):
        return {"error": "connection missing or not a configured Procore connection"}
    token, kinds = c.config["access_token"], (sched.kinds or list(KINDS))
    mappings = (c.config or {}).get("mappings")
    out = sync_procore(db, sched.project_id, token, str(sched.procore_project_id), kinds, actor, None, mappings)
    if getattr(sched, "push", False):           # two-way schedule: also push local changes back
        out["push"] = push_procore(db, sched.project_id, token, str(sched.procore_project_id), ["rfi"], actor)
    return out


def run_due(db: Session, now=None) -> list[dict[str, Any]]:
    """Run every enabled schedule whose interval has elapsed; record last_run/last_result."""
    from datetime import datetime, timedelta, timezone

    from .models import SyncSchedule
    now = now or datetime.now(timezone.utc)
    ran = []
    for s in db.query(SyncSchedule).filter(SyncSchedule.enabled.isnot(False)).all():
        if s.last_run is not None and (now - _aware(s.last_run)) < timedelta(minutes=s.interval_minutes or 60):
            continue
        try:
            res = run_schedule(db, s)
        except Exception as e:                   # noqa: BLE001 — one bad schedule mustn't stop the rest
            # log it too: an expired token / broken connection must be visible in logs, not only in
            # a last_result field nobody polls (a sync can otherwise stay silently broken for weeks).
            logging.getLogger("aec.autosync").warning("schedule %s failed: %s", s.id, e)
            res = {"error": str(e)[:160]}
        s.last_run = now
        s.last_result = res
        db.commit()
        ran.append({"schedule_id": s.id, "result": res})
    return ran
