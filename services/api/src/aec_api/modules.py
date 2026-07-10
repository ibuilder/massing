"""GC portal module engine.

Every business process (RFIs, Submittals, PCO Requests, Change Orders, …) is a *module*
described by a single `module.json` and stored in its **own table** (`mod_<key>`), created
automatically. One shared engine renders CRUD and drives a **role-gated workflow state
machine**. Records can be anchored to the model (pins) and linked into chains (the
change-order process). Every transition is written to the record activity timeline.

Implements the patent-described system (provisional 514712205), modernised on FastAPI.
"""
from __future__ import annotations

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import JSON, Column, DateTime, Index, String, Table, cast, func, insert, or_, select, update
from sqlalchemy.orm import Session

from . import rbac
from .db import Base
from .models import EnumOption, RecordActivity, RecordComment

# repo layout: services/api/modules; the frozen desktop build sets AEC_MODULES_DIR to the
# bundled copy (PyInstaller _MEIPASS/modules) since __file__ no longer resolves there.
MODULES_DIR = Path(os.environ.get("AEC_MODULES_DIR") or (Path(__file__).resolve().parents[2] / "modules"))

REGISTRY: dict[str, dict] = {}
TABLES: dict[str, Table] = {}
# reverse index of reference fields: target_module -> [(source_module, field_name, label)]
# lets a record show "what points at me" without scanning every module.
REVERSE_REFS: dict[str, list[tuple[str, str, str]]] = {}


def reference_fields(mod: dict) -> list[dict]:
    """Fields that point at another module's record (type == 'reference')."""
    return [f for f in mod.get("fields", []) if f.get("type") == "reference" and f.get("module")]


def rollup_fields(mod: dict) -> list[dict]:
    """Computed fields that aggregate a numeric field across incoming related records.
    e.g. {"type":"rollup","source_module":"pco_request","source_field":"rough_cost","op":"sum"}"""
    return [f for f in mod.get("fields", []) if f.get("type") == "rollup"]


def input_fields(mod: dict) -> list[dict]:
    """Fields the user actually enters (excludes computed rollups)."""
    return [f for f in mod.get("fields", []) if f.get("type") != "rollup"]


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _table(key: str) -> Table:
    return Table(
        f"mod_{key}", Base.metadata,
        Column("id", String, primary_key=True),
        Column("project_id", String, index=True),
        Column("ref", String),
        Column("title", String),
        Column("workflow_state", String, index=True),
        Column("party_owner", String, nullable=True),
        Column("assignee", String, nullable=True),
        Column("created_by", String, nullable=True),
        Column("created_at", DateTime(timezone=True)),
        Column("modified_at", DateTime(timezone=True)),
        Column("anchor", JSON, nullable=True),         # {x,y,z} pin on the model
        Column("element_guids", JSON, nullable=True),  # referenced IFC GlobalIds
        Column("links", JSON, nullable=True),          # [{module,id,ref}] change-order chain
        Column("data", JSON),                          # module-defined fields
        # composite index for the hot path: "records in this project in this state" (dashboard
        # rollups, list filters) — more selective than the single-column indexes alone.
        Index(f"ix_mod_{key}_proj_state", "project_id", "workflow_state"),
        # every list_records does `WHERE project_id=? ORDER BY created_at LIMIT/OFFSET` — without this
        # that's a filesort of the whole project's rows on each page (brutal at 100k+ on Postgres).
        Index(f"ix_mod_{key}_proj_created", "project_id", "created_at"),
        # my-work / assignee queues filter `WHERE project_id=? AND assignee=?`.
        Index(f"ix_mod_{key}_proj_assignee", "project_id", "assignee"),
        extend_existing=True,
    )


def load_registry() -> None:
    """Load every modules/<key>/module.json and register its table. Idempotent."""
    if not MODULES_DIR.exists():
        return
    from . import module_schema
    folders = {p.parent.name for p in MODULES_DIR.glob("*/module.json")}
    for mj in sorted(MODULES_DIR.glob("*/module.json")):
        mod = json.loads(mj.read_text(encoding="utf-8"))
        key = mod["key"]
        # Advisory schema check at load: a malformed module logs a warning rather than crashing the
        # API (test_module_config fails the build on any issue). Same rules the config test enforces.
        problems = module_schema.validate_module(mod, known_modules=folders, folder=mj.parent.name)
        if problems:
            import logging
            logging.getLogger("aec_api.modules").warning(
                "module %r has %d config issue(s): %s", key, len(problems), "; ".join(problems))
        REGISTRY[key] = mod
        if key not in TABLES:
            TABLES[key] = _table(key)
    # build the reverse-reference index once everything is registered
    REVERSE_REFS.clear()
    for key, mod in REGISTRY.items():
        for f in reference_fields(mod):
            REVERSE_REFS.setdefault(f["module"], []).append(
                (key, f["name"], mod.get("name", key)))


def get_module(key: str) -> dict:
    mod = REGISTRY.get(key)
    if not mod:
        raise HTTPException(404, f"unknown module {key!r}")
    return mod


# --- workflow ---------------------------------------------------------------
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


# --- CRUD -------------------------------------------------------------------
def _log(db: Session, project_id: str, key: str, rid: str, actor: str,
         party: str | None, action: str, detail: dict | None = None) -> None:
    db.add(RecordActivity(project_id=project_id, module=key, record_id=rid,
                          actor=actor, party=party, action=action, detail=detail))


def _validate_fields(mod: dict, data: dict) -> None:
    missing = [f["name"] for f in mod.get("fields", [])
               if f.get("required") and not data.get(f["name"])]
    if missing:
        raise HTTPException(422, f"missing required field(s): {', '.join(missing)}")


def _validate_values(mod: dict, data: dict) -> None:
    """Reject clearly-invalid field values (select outside options, non-numeric numbers) before a
    write — so bad data can't slip into the JSON `data` blob. Partial (present-only) so PATCH works."""
    from . import module_schema
    problems = module_schema.validate_record(mod, data)
    if problems:
        raise HTTPException(422, "; ".join(problems))


def _next_ref(db: Session, key: str, project_id: str, mod: dict) -> str:
    """Atomically allocate the next ref number from a per-(project, module) counter row, taking a row
    lock (Postgres) so concurrent creates can't read the same value and mint duplicate refs. On first
    use the counter seeds from the current row count so existing data keeps its sequence."""
    from .models import RefCounter
    row = (db.query(RefCounter)
             .filter(RefCounter.project_id == project_id, RefCounter.module == key)
             .with_for_update().first())
    if row is None:
        seed = db.execute(select(func.count()).select_from(TABLES[key])
                          .where(TABLES[key].c.project_id == project_id)).scalar() or 0
        row = RefCounter(project_id=project_id, module=key, n=seed)
        db.add(row)
        db.flush()
    row.n += 1
    db.flush()
    return f"{mod.get('ref_prefix', key.upper())}-{row.n:03d}"


def create_record(db: Session, key: str, project_id: str, body: dict, actor: str,
                  party: str | None) -> dict:
    mod = get_module(key)
    t = TABLES[key]
    data = body.get("data", {})
    title_field = mod.get("title_field") or (mod["fields"][0]["name"] if mod.get("fields") else None)
    # `subject` is a universal title alias: modules name their title field differently
    # (title/name/number/system); if it's absent but `subject` was supplied, fill it — so callers,
    # scripts and integrations don't have to special-case each module's field name.
    if title_field and title_field != "subject" and not data.get(title_field) and data.get("subject"):
        data[title_field] = data["subject"]
    _validate_fields(mod, data)
    _validate_values(mod, data)
    rid = str(uuid.uuid4())
    row = {
        "id": rid, "project_id": project_id,
        "ref": _next_ref(db, key, project_id, mod),
        "title": data.get(title_field) if title_field else None,
        "workflow_state": mod.get("workflow", {}).get("initial", "open"),
        "party_owner": party, "assignee": body.get("assignee"),
        "created_by": actor, "created_at": _now(), "modified_at": _now(),
        "anchor": body.get("anchor"), "element_guids": body.get("element_guids"),
        "links": body.get("links") or [], "data": data,
    }
    db.execute(insert(t).values(**row))
    _log(db, project_id, key, rid, actor, party, "create", {"ref": row["ref"]})
    db.commit()
    return get_record(db, key, project_id, rid)


def revise(db: Session, key: str, project_id: str, rid: str, actor: str, party: str | None) -> dict:
    """Create a tracked revision of a record (e.g. reissue a closed RFI). The revision copies
    the source's data, carries a `<ref>.N` ref, re-opens the workflow, and links back via
    data.revises; the source is marked data.superseded_by. Revision metadata lives in the data
    JSON (no schema migration). Only for modules with `revisable: true`."""
    mod = get_module(key)
    if not mod.get("revisable"):
        raise HTTPException(400, f"{key} records are not revisable")
    t = TABLES[key]
    src = get_record(db, key, project_id, rid)          # 404 if missing
    if (src.get("data") or {}).get("superseded_by"):
        raise HTTPException(409, "record already revised")
    base = src["ref"].split(".")[0]
    rev_n = int((src.get("data") or {}).get("revision") or 0) + 1
    roll = {f["name"] for f in rollup_fields(mod)}
    data = {k: v for k, v in (src.get("data") or {}).items()
            if k not in roll and k not in ("revises", "superseded_by", "revision")}
    data["revision"] = rev_n
    data["revises"] = rid
    new_id = str(uuid.uuid4())
    db.execute(insert(t).values(
        id=new_id, project_id=project_id, ref=f"{base}.{rev_n}", title=src.get("title"),
        workflow_state=mod.get("workflow", {}).get("initial", "open"),
        party_owner=party, assignee=src.get("assignee"), created_by=actor,
        created_at=_now(), modified_at=_now(), anchor=src.get("anchor"),
        element_guids=src.get("element_guids"), links=[], data=data))
    superseded = dict(src.get("data") or {}); superseded["superseded_by"] = new_id
    db.execute(update(t).where(t.c.id == rid, t.c.project_id == project_id)
               .values(data=superseded, modified_at=_now()))
    _log(db, project_id, key, new_id, actor, party, "revise", {"revises": src["ref"], "revision": rev_n})
    _log(db, project_id, key, rid, actor, party, "superseded", {"by": f"{base}.{rev_n}"})
    db.commit()
    return get_record(db, key, project_id, new_id)


def _is_postgres(db: Session) -> bool:
    try:
        return bool(db.bind) and db.bind.dialect.name == "postgresql"
    except Exception:
        return False


def _pg_tsquery(q: str) -> str | None:
    """A safe prefix tsquery from arbitrary user input: alnum words AND-ed, each prefix-matched
    (`conc & beam` -> `conc:* & beam:*`) so 'conc' finds 'concrete' and multi-word narrows."""
    words = re.findall(r"[A-Za-z0-9]+", q.lower())
    return " & ".join(f"{w}:*" for w in words) if words else None


def _pg_document(t: Table):
    """to_tsvector over ref + title + the whole field map (JSON cast to text)."""
    return func.to_tsvector("english", func.concat_ws(
        " ", func.coalesce(t.c.ref, ""), func.coalesce(t.c.title, ""), cast(t.c.data, String)))


def _search_filter(db: Session, t: Table, q: str):
    """Portable search predicate: Postgres full-text (stemmed, prefix, ranked) when available; a
    substring LIKE over ref/title/data everywhere else (SQLite dev)."""
    if _is_postgres(db):
        tsq = _pg_tsquery(q)
        if tsq:
            return _pg_document(t).op("@@")(func.to_tsquery("english", tsq))
    like = f"%{q.lower()}%"
    return or_(
        func.lower(func.coalesce(t.c.ref, "")).like(like),
        func.lower(func.coalesce(t.c.title, "")).like(like),
        func.lower(cast(t.c.data, String)).like(like),
    )


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


def view_alerts(db: Session, project_id: str, user: str) -> list[dict]:
    """Saved-search alerts: for each of the user's saved views, the total matches + how many are NEW
    since they last opened it (a never-opened view counts all matches as new). Powers the 🔔 feed."""
    from .models import SavedView
    views = db.query(SavedView).filter(SavedView.project_id == project_id,
                                       SavedView.user == user).order_by(SavedView.created_at).all()
    out = []
    for v in views:
        cfg = v.config or {}
        state, q = cfg.get("state"), cfg.get("q")
        total = count_records(db, v.module, project_id, state=state, q=q)
        new = count_records(db, v.module, project_id, state=state, q=q, since=v.last_seen_at) \
            if v.last_seen_at else total
        out.append({"id": v.id, "name": v.name, "module": v.module, "total": total, "new": new,
                    "config": cfg})
    return out


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


def get_record(db: Session, key: str, project_id: str, rid: str) -> dict:
    t = TABLES[key]
    r = db.execute(select(t).where(t.c.id == rid, t.c.project_id == project_id)).first()
    if not r:
        raise HTTPException(404, "record not found")
    rec = dict(r._mapping)
    rec["activity"] = [
        {"ts": a.ts.isoformat() if a.ts else None, "actor": a.actor, "party": a.party,
         "action": a.action, "detail": a.detail}
        for a in db.query(RecordActivity).filter(
            RecordActivity.module == key, RecordActivity.record_id == rid)
        .order_by(RecordActivity.ts).all()
    ]
    rec["comments"] = [
        {"author": cm.author, "text": cm.text,
         "created_at": cm.created_at.isoformat() if cm.created_at else None}
        for cm in db.query(RecordComment).filter(
            RecordComment.module == key, RecordComment.record_id == rid)
        .order_by(RecordComment.created_at).all()
    ]
    rec["attachments"] = list_attachments(db, key, project_id, rid)
    # resolve reference fields to a clickable brief {module, id, ref, title}
    mod = get_module(key)
    data = rec.get("data") or {}
    refs: dict[str, dict] = {}
    for f in reference_fields(mod):
        tid = data.get(f["name"])
        if tid:
            b = _brief(db, f["module"], project_id, tid)
            if b:
                refs[f["name"]] = b
    rec["data_refs"] = refs
    # revision chain (revisable modules): prior/next revision briefs + this record's number
    if data.get("revision") or data.get("revises") or data.get("superseded_by"):
        rec["revision"] = {
            "number": data.get("revision", 0),
            "revises": _brief(db, key, project_id, data["revises"]) if data.get("revises") else None,
            "superseded_by": _brief(db, key, project_id, data["superseded_by"]) if data.get("superseded_by") else None,
        }
    # computed rollup fields: aggregate a numeric field across incoming related records
    rolls = rollup_fields(mod)
    if rolls:
        for f in rolls:
            rec.setdefault("data", {})[f["name"]] = _rollup(db, key, project_id, rid, f)
    return rec


def _json_text(db: Session, col, jkey: str):
    """Portable JSON scalar-as-text extraction (Postgres ->> / SQLite json_extract). `jkey` is a
    module-defined field name (safe to interpolate into the SQLite JSON path)."""
    if _is_postgres(db):
        return col.op("->>")(jkey)
    return func.json_extract(col, f"$.{jkey}")


def _rollup(db: Session, key: str, project_id: str, rid: str, f: dict) -> float | int:
    """Aggregate f['source_field'] over incoming records of f['source_module'] that point here."""
    src_key, field = f.get("source_module"), f.get("source_field")
    if not src_key or src_key not in TABLES:
        return 0
    # which reference field in the source module points at *this* module
    ref_field = next((fn for (sk, fn, _) in REVERSE_REFS.get(key, []) if sk == src_key), None)
    if not ref_field:
        return 0
    t = TABLES[src_key]
    # filter the reference match in SQL (JSON extraction) so only the matching rows are fetched — the
    # source table is no longer fully scanned + shipped to Python on every get_record/rollup.
    total, count = 0.0, 0
    for r in db.execute(select(t.c.data).where(t.c.project_id == project_id,
                                               _json_text(db, t.c.data, ref_field) == rid)):
        d = r._mapping["data"] or {}
        count += 1
        try:
            total += float(d.get(field) or 0)
        except (TypeError, ValueError):
            pass
    op = f.get("op", "sum")
    if op == "count":
        return count
    if op == "avg":
        return round(total / count, 2) if count else 0
    return round(total, 2)


def set_assignee(db: Session, key: str, project_id: str, rid: str, assignee: str | None,
                 actor: str, party: str | None) -> dict:
    t = TABLES[key]
    get_record(db, key, project_id, rid)  # 404 if missing
    db.execute(update(t).where(t.c.id == rid, t.c.project_id == project_id)
               .values(assignee=assignee, modified_at=_now()))
    _log(db, project_id, key, rid, actor, party, "assign", {"assignee": assignee})
    db.commit()
    return get_record(db, key, project_id, rid)


def set_element_guids(db: Session, key: str, project_id: str, rid: str, guids: list[str],
                      actor: str, mode: str = "add") -> dict:
    """Tie model elements (IFC GlobalIds) to a record. `mode`: add | remove | set. Used to hard-tie
    a schedule activity to the exact elements it builds (so the 4D scrub is precise, not trade-based)."""
    t = TABLES[key]
    rec = get_record(db, key, project_id, rid)  # 404 if missing
    cur = set(rec.get("element_guids") or [])
    incoming = {g for g in guids if g}
    result = sorted(cur | incoming if mode == "add" else cur - incoming if mode == "remove" else incoming)
    db.execute(update(t).where(t.c.id == rid, t.c.project_id == project_id)
               .values(element_guids=result, modified_at=_now()))
    _log(db, project_id, key, rid, actor, None, "tag-elements", {"count": len(result), "mode": mode})
    db.commit()
    return {"element_guids": result, "count": len(result)}


# --- attachments (bytes live in storage/MinIO) ------------------------------
def add_attachment(db: Session, key: str, project_id: str, rid: str, filename: str,
                   content_type: str | None, data: bytes, actor: str) -> dict:
    from . import storage
    from .models import RecordAttachment

    get_record(db, key, project_id, rid)  # 404 if missing
    aid = str(uuid.uuid4())
    skey = f"records/{project_id}/{key}/{rid}/{aid}_{filename}"
    storage.put(skey, data)
    att = RecordAttachment(id=aid, project_id=project_id, module=key, record_id=rid,
                           filename=filename, content_type=content_type, size=len(data),
                           storage_key=skey, uploaded_by=actor)
    db.add(att)
    _log(db, project_id, key, rid, actor, None, "attach", {"filename": filename})
    db.commit()
    return {"id": aid, "filename": filename, "size": len(data), "content_type": content_type}


def list_attachments(db: Session, key: str, project_id: str, rid: str) -> list[dict]:
    from .models import RecordAttachment
    return [{"id": a.id, "filename": a.filename, "size": a.size,
             "content_type": a.content_type, "uploaded_by": a.uploaded_by,
             "created_at": a.created_at.isoformat() if a.created_at else None}
            for a in db.query(RecordAttachment).filter(
                RecordAttachment.module == key, RecordAttachment.record_id == rid)
            .order_by(RecordAttachment.created_at).all()]


def get_attachment(db: Session, att_id: str):
    from . import storage
    from .models import RecordAttachment
    a = db.get(RecordAttachment, att_id)
    if not a:
        raise HTTPException(404, "attachment not found")
    return a, storage.get(a.storage_key)


def _brief(db: Session, key: str, project_id: str, rid: str) -> dict | None:
    """Lightweight record summary for relation links (no activity/comments)."""
    t = TABLES.get(key)
    if t is None:
        return None
    r = db.execute(select(t.c.id, t.c.ref, t.c.title, t.c.workflow_state)
                   .where(t.c.id == rid, t.c.project_id == project_id)).first()
    if not r:
        return None
    m = r._mapping
    return {"module": key, "module_name": REGISTRY.get(key, {}).get("name", key),
            "id": m["id"], "ref": m["ref"], "title": m["title"], "state": m["workflow_state"]}


def related_records(db: Session, key: str, project_id: str, rid: str) -> dict:
    """Outgoing (this record's reference fields) + incoming (records pointing here)."""
    mod = get_module(key)
    rec = get_record(db, key, project_id, rid)
    data = rec.get("data") or {}
    outgoing = []
    for f in reference_fields(mod):
        tid = data.get(f["name"])
        b = _brief(db, f["module"], project_id, tid) if tid else None
        if b:
            outgoing.append({"label": f["label"], **b})
    incoming = []
    for src_key, field, src_name in REVERSE_REFS.get(key, []):
        t = TABLES[src_key]
        for r in db.execute(select(t.c.id, t.c.ref, t.c.title, t.c.workflow_state, t.c.data)
                            .where(t.c.project_id == project_id)):
            m = r._mapping
            if (m["data"] or {}).get(field) == rid:
                incoming.append({"module": src_key, "module_name": src_name, "id": m["id"],
                                 "ref": m["ref"], "title": m["title"], "state": m["workflow_state"]})
    return {"outgoing": outgoing, "incoming": incoming}


def delete_record(db: Session, key: str, project_id: str, rid: str, actor: str,
                  party: str | None) -> dict:
    """Delete a record (and its activity/comments). Returns {deleted, ref}."""
    t = TABLES[key]
    rec = get_record(db, key, project_id, rid)  # 404 if missing
    db.execute(t.delete().where(t.c.id == rid, t.c.project_id == project_id))
    db.query(RecordActivity).filter(RecordActivity.module == key,
                                    RecordActivity.record_id == rid).delete()
    db.query(RecordComment).filter(RecordComment.module == key,
                                   RecordComment.record_id == rid).delete()
    db.commit()
    return {"deleted": True, "ref": rec["ref"]}


def board(db: Session, key: str, project_id: str, per_state: int = 200) -> dict:
    """Records grouped by workflow state — drives the kanban board.

    Bounded: at most `per_state` cards per column (newest first) plus the TRUE per-state counts from
    `state_counts` (SQL GROUP BY), instead of materializing up to 100k full records per request — a
    memory/DoS vector on large modules. A column deeper than the cap shows count > len(cards)."""
    mod = get_module(key)
    states = mod.get("workflow", {}).get("states", [])
    counts = state_counts(db, key, project_id)
    columns: dict[str, list] = {s: [] for s in states}
    for state in set(list(counts.keys()) + states):
        rows = list_records(db, key, project_id, state=state, limit=max(1, min(per_state, 500)))
        columns[state] = [{"id": r["id"], "ref": r["ref"], "title": r["title"],
                           "assignee": r.get("assignee"), "party_owner": r.get("party_owner")}
                          for r in rows]
    return {"states": states or list(columns.keys()),
            "columns": columns, "counts": counts,
            "transitions": mod.get("workflow", {}).get("transitions", [])}


def search_all(db: Session, project_id: str, q: str, limit: int = 50) -> list[dict]:
    """Cross-module full-text search (ref / title / data) across every module."""
    out = []
    for key, mod in REGISTRY.items():
        for r in list_records(db, key, project_id, q=q, limit=limit):
            out.append({"module": key, "module_name": mod.get("name", key),
                        "icon": mod.get("icon", "•"), "id": r["id"], "ref": r["ref"],
                        "title": r["title"], "state": r["workflow_state"]})
            if len(out) >= limit:
                return out
    return out


def bulk(db: Session, key: str, project_id: str, ids: list[str], action: str,
         actor: str, party: str | None, value: str | None = None) -> dict:
    """Apply an action to many records at once. action ∈ transition|assign|delete."""
    ok, failed = [], []
    for rid in ids:
        try:
            if action == "delete":
                delete_record(db, key, project_id, rid, actor, party)
            elif action == "assign":
                set_assignee(db, key, project_id, rid, value or None, actor, party)
            elif action == "transition":
                transition(db, key, project_id, rid, value or "", actor, party)
            else:
                raise HTTPException(400, f"unknown bulk action {action!r}")
            ok.append(rid)
        except HTTPException as e:
            failed.append({"id": rid, "error": e.detail})
    return {"ok": len(ok), "failed": failed}


def notifications(db: Session, project_id: str, user: str, party: str | None,
                  limit: int = 30) -> list[dict]:
    """Recent activity on records relevant to the user (assigned to them, or their party
    can act on), excluding their own actions — drives the bell feed + unread badge."""
    recent = (db.query(RecordActivity)
              .filter(RecordActivity.project_id == project_id)
              .order_by(RecordActivity.ts.desc()).limit(200).all())
    cache: dict[tuple[str, str], dict | None] = {}
    out = []
    for a in recent:
        if a.actor == user:                      # don't notify me about my own actions
            continue
        ckey = (a.module, a.record_id)
        if ckey not in cache:
            t = TABLES.get(a.module)
            if t is None:
                cache[ckey] = None
            else:
                r = db.execute(select(t.c.ref, t.c.title, t.c.assignee, t.c.workflow_state)
                               .where(t.c.id == a.record_id)).first()
                cache[ckey] = dict(r._mapping) if r else None
        rec = cache[ckey]
        if not rec:
            continue
        mine = rec["assignee"] == user
        actionable = bool(available_actions(REGISTRY.get(a.module, {}), rec["workflow_state"], party))
        if not (mine or actionable):
            continue
        out.append({
            "module": a.module, "module_name": REGISTRY.get(a.module, {}).get("name", a.module),
            "icon": REGISTRY.get(a.module, {}).get("icon", "•"),
            "record_id": a.record_id, "ref": rec["ref"], "title": rec["title"],
            "action": a.action, "actor": a.actor,
            "ts": a.ts.isoformat() if a.ts else None,
            "reason": "assigned" if mine else "your move",
        })
        if len(out) >= limit:
            break
    return out


MY_WORK_PER_MODULE = 100   # newest N actionable rows pulled per module before the global trim
MY_WORK_LIMIT = 500        # cap on the personal work feed (a to-do queue, not a data export)


def my_work(db: Session, project_id: str, user: str, party: str | None,
            limit: int = MY_WORK_LIMIT) -> list[dict]:
    """Cross-module: records assigned to me, plus those where my party can act now.

    Filters in SQL — assignee = me OR workflow_state in the set of states my party can act from
    (precomputed per module from the workflow). Bounded on both axes: each module contributes only
    its newest ``MY_WORK_PER_MODULE`` matches (indexed `(project_id, assignee)` / `(project_id,
    workflow_state)` + `ORDER BY modified_at`), and the merged feed is trimmed to ``limit`` — so a
    mega project with tens of thousands of open records returns a fast, bounded to-do queue instead
    of a multi-megabyte dump of every actionable row."""
    out = []
    for key, mod in REGISTRY.items():
        t = TABLES[key]
        # states from which `party` has at least one available action (no DB, just the workflow)
        actionable_states = {tr["from"] for tr in mod.get("workflow", {}).get("transitions", [])
                             if rbac.party_allowed(party, tr.get("party", []))}
        conds = [t.c.assignee == user]
        if actionable_states:
            conds.append(t.c.workflow_state.in_(actionable_states))
        stmt = (select(t.c.id, t.c.ref, t.c.title, t.c.workflow_state, t.c.assignee, t.c.modified_at)
                .where(t.c.project_id == project_id, or_(*conds))
                .order_by(t.c.modified_at.desc()).limit(MY_WORK_PER_MODULE))
        for r in db.execute(stmt):
            m = r._mapping
            mine = m["assignee"] == user
            out.append({"module": key, "module_name": mod.get("name", key),
                        "icon": mod.get("icon", "•"), "id": m["id"], "ref": m["ref"],
                        "title": m["title"], "state": m["workflow_state"],
                        "assignee": m["assignee"], "modified_at": m["modified_at"],
                        "reason": "assigned" if mine else "ball-in-court"})
    # newest-first across all modules, then cap. Sort on the ISO string (never mix datetime/None,
    # which would raise); assigned-to-me sorts ahead of ball-in-court at equal recency.
    def _key(x: dict) -> tuple[str, int]:
        ts = x["modified_at"]
        return (ts.isoformat() if ts else "", 0 if x["reason"] == "assigned" else 1)
    out.sort(key=_key, reverse=True)
    for x in out:
        x.pop("modified_at", None)
    return out[:limit]


_DUE_FIELDS = ("due_date", "response_due", "need_by", "due")


def _due_field_name(mod: dict) -> str | None:
    names = {f["name"] for f in mod.get("fields", [])}
    return next((c for c in _DUE_FIELDS if c in names), None)


def _terminal_states(mod: dict) -> set[str]:
    """States with no outgoing transition — a record there is done (closed/void/executed/…)."""
    wf = mod.get("workflow", {})
    froms = {t["from"] for t in wf.get("transitions", [])}
    return {s for s in wf.get("states", []) if s not in froms}


def due_feed(db: Session, project_id: str, soon_days: int = 7) -> dict:
    """Cross-module SLA feed: open records (not in a terminal state) past or near their due date,
    bucketed overdue / due-soon. Scans only modules that actually carry a due-date field. Drives the
    'overdue / due this week' dashboard queue — the project-wide deadline view emanager added."""
    from datetime import date, timedelta
    today = date.today()
    soon = today + timedelta(days=max(0, soon_days))
    overdue: list[dict] = []
    due_soon: list[dict] = []
    # Only rows due on/before the horizon can be overdue or due-soon; rows with no due date or due
    # later than `soon` (the whole soon day → < soon+1) are filtered in SQL, so we no longer read every
    # module row + its JSON blob into Python (P0.1 perf). ISO dates compare correctly as text.
    horizon = (soon + timedelta(days=1)).isoformat()
    for key, mod in REGISTRY.items():
        df = _due_field_name(mod)
        if not df or key not in TABLES:
            continue
        terminal = _terminal_states(mod)
        t = TABLES[key]
        duecol = _json_text(db, t.c.data, df)
        q = (select(t.c.id, t.c.ref, t.c.title, t.c.workflow_state, t.c.assignee, duecol.label("due"))
             .where(t.c.project_id == project_id)
             .where(duecol.isnot(None)).where(duecol != "").where(duecol < horizon))
        if terminal:
            q = q.where(t.c.workflow_state.notin_(list(terminal)))
        for r in db.execute(q):
            m = r._mapping
            try:
                d = date.fromisoformat(str(m["due"])[:10])
            except (ValueError, TypeError):
                continue
            item = {"module": key, "module_name": mod.get("name", key), "icon": mod.get("icon", "•"),
                    "id": m["id"], "ref": m["ref"], "title": m["title"], "state": m["workflow_state"],
                    "assignee": m["assignee"], "due_date": d.isoformat(), "days": (d - today).days}
            if d < today:
                overdue.append(item)
            elif d <= soon:
                due_soon.append(item)
    overdue.sort(key=lambda x: x["due_date"])
    due_soon.sort(key=lambda x: x["due_date"])
    return {"overdue": overdue, "due_soon": due_soon,
            "counts": {"overdue": len(overdue), "due_soon": len(due_soon)},
            "as_of": today.isoformat(), "horizon_days": soon_days}


def add_comment(db: Session, key: str, project_id: str, rid: str, text: str,
                author: str) -> dict:
    get_record(db, key, project_id, rid)  # 404 if missing
    db.add(RecordComment(project_id=project_id, module=key, record_id=rid,
                         author=author, text=text))
    _log(db, project_id, key, rid, author, None, "comment", {"text": text[:80]})
    db.commit()
    return get_record(db, key, project_id, rid)


def iter_csv(db: Session, key: str, project_id: str, page: int = 1000):
    """Module record list → CSV, streamed in pages so a 200k-record module never materializes in one
    request (the previous single limit=100000 load was a memory/DoS vector). Yields CSV chunks."""
    import csv
    import io

    mod = get_module(key)
    field_names = [f["name"] for f in mod.get("fields", [])]
    headers = ["ref", "title", "workflow_state", "party_owner", "created_by"] + field_names
    offset = 0
    while True:
        buf = io.StringIO()
        w = csv.writer(buf)
        if offset == 0:
            w.writerow(headers)
        rows = list_records(db, key, project_id, limit=page, offset=offset)
        for r in rows:
            d = r.get("data") or {}
            w.writerow([r["ref"], r["title"], r["workflow_state"], r["party_owner"], r["created_by"]]
                       + [d.get(fn, "") for fn in field_names])
        if offset == 0 or rows:
            yield buf.getvalue()
        if len(rows) < page:
            break
        offset += page


def to_csv(db: Session, key: str, project_id: str) -> str:
    """Whole-module CSV as one string (tests / small modules); prefer iter_csv for responses."""
    return "".join(iter_csv(db, key, project_id))


def update_record(db: Session, key: str, project_id: str, rid: str, data: dict,
                  actor: str, party: str | None, expected_modified_at: str | None = None) -> dict:
    t = TABLES[key]
    rec = get_record(db, key, project_id, rid)
    # optimistic lock (opt-in): if the caller passes the modified_at it loaded and the record has since
    # changed, reject with 409 rather than silently overwriting a concurrent edit. The response carries
    # the current modified_at so the client can nudge "changed by someone else — reload".
    if expected_modified_at is not None:
        cur = rec.get("modified_at")
        cur_iso = cur.isoformat() if hasattr(cur, "isoformat") else (str(cur) if cur else None)
        if cur_iso != expected_modified_at:
            raise HTTPException(409, {"error": "stale_write",
                                      "message": "This record changed since you opened it — reload to see the latest.",
                                      "modified_at": cur_iso})
    _validate_values(get_module(key), data)         # partial: only the fields being changed
    merged = {**(rec.get("data") or {}), **data}
    db.execute(update(t).where(t.c.id == rid).values(data=merged, modified_at=_now()))
    _log(db, project_id, key, rid, actor, party, "update", {"fields": list(data.keys())})
    db.commit()
    return get_record(db, key, project_id, rid)


def transition(db: Session, key: str, project_id: str, rid: str, action: str,
               actor: str, party: str | None, note: str | None = None) -> dict:
    mod = get_module(key)
    t = TABLES[key]
    rec = get_record(db, key, project_id, rid)
    tr = _transition(mod, rec["workflow_state"], action)
    if not tr:
        raise HTTPException(409, f"action {action!r} not allowed from state {rec['workflow_state']!r}")
    if not rbac.party_allowed(party, tr.get("party", [])):
        raise HTTPException(403, f"party {party or 'none'} cannot {action} "
                                 f"(requires {tr.get('party')})")
    # field gate: a transition can declare `requires: [field, …]` that must be filled before it fires
    # (e.g. an RFI can't be Answered without an answer; a COR can't be Approved without an amount).
    # Generalizes the attachment gate below; surfaced to the UI via available_actions(... include_requires).
    required = tr.get("requires") or []
    if required:
        data = rec.get("data") or {}
        missing = [f for f in required if data.get(f) in (None, "", [], {})]
        if missing:
            labels = {fl["name"]: fl.get("label", fl["name"]) for fl in mod.get("fields", [])}
            raise HTTPException(400, f"{action!r} requires: {', '.join(labels.get(m, m) for m in missing)}")
    # evidence gate: modules can require a photo/attachment before entering a sign-off state
    if tr["to"] in (mod.get("close_requires_attachment") or []):
        from .models import RecordAttachment
        n = db.query(RecordAttachment).filter(
            RecordAttachment.project_id == project_id, RecordAttachment.module == key,
            RecordAttachment.record_id == rid).count()
        if not n:
            raise HTTPException(400, f"{action!r} requires at least one attachment (photo/evidence) first")
    db.execute(update(t).where(t.c.id == rid).values(workflow_state=tr["to"], modified_at=_now()))
    _log(db, project_id, key, rid, actor, party, f"transition:{action}",
         {"from": rec["workflow_state"], "to": tr["to"], "note": note})
    db.commit()
    # fire an outbound webhook (opt-in, fail-open) so external automation can react — include the
    # record's resolved distribution (CC) emails so a listener can notify them.
    from . import distribution as _dist
    from . import webhooks
    try:
        recipients = _dist.record_emails(db, project_id, key, rec.get("data"))
    except Exception:                              # noqa: BLE001 — never block a transition
        recipients = []
    webhooks.record_transition(project_id, key, rid, rec.get("ref"),
                               rec["workflow_state"], tr["to"], action, actor, distribution=recipients)
    return get_record(db, key, project_id, rid)


def link_record(db: Session, key: str, project_id: str, rid: str, target: dict,
                actor: str, party: str | None) -> dict:
    """Link this record to another (change-order chain). target = {module, id}."""
    t = TABLES[key]
    rec = get_record(db, key, project_id, rid)
    tmod, tid = target["module"], target["id"]
    tref = get_record(db, tmod, project_id, tid)["ref"]
    links = (rec.get("links") or []) + [{"module": tmod, "id": tid, "ref": tref}]
    db.execute(update(t).where(t.c.id == rid).values(links=links, modified_at=_now()))
    _log(db, project_id, key, rid, actor, party, "link", {"to": f"{tmod}:{tref}"})
    db.commit()
    return get_record(db, key, project_id, rid)


# --- E1: project-level custom enum options ----------------------------------
def list_enum_options(db: Session, project_id: str) -> dict[str, dict[str, list[str]]]:
    """All custom options for a project, nested {module: {field: [values]}}."""
    out: dict[str, dict[str, list[str]]] = {}
    rows = db.execute(select(EnumOption).where(EnumOption.project_id == project_id)
                      .order_by(EnumOption.created_at))
    for (o,) in rows:
        out.setdefault(o.module, {}).setdefault(o.field, []).append(o.value)
    return out


def add_enum_option(db: Session, project_id: str, module: str, field: str, value: str,
                    actor: str | None) -> dict:
    """Add a custom option to a module field's enum. Validates the field is a real
    select/multiselect, and is idempotent against the JSON options + existing customs."""
    mod = get_module(module)
    f = next((x for x in mod.get("fields", []) if x["name"] == field), None)
    if not f or f.get("type") not in ("select", "multiselect"):
        raise HTTPException(422, f"{module}.{field} is not a select field")
    value = (value or "").strip()
    if not value:
        raise HTTPException(422, "value required")
    existing = set(f.get("options", [])) | set(
        list_enum_options(db, project_id).get(module, {}).get(field, []))
    if value not in existing:
        db.add(EnumOption(project_id=project_id, module=module, field=field,
                          value=value, created_by=actor))
        db.commit()
    return {"module": module, "field": field, "value": value,
            "options": list_enum_options(db, project_id).get(module, {}).get(field, [])}


def project_pins(db: Session, project_id: str) -> list[dict]:
    """Every anchored module record, as a pin for the 3D viewer overlay."""
    pins = []
    for key, mod in REGISTRY.items():
        if not mod.get("pinnable"):
            continue
        t = TABLES[key]
        # prune un-anchored rows in SQL (most records have no pin) — the Python check still guards the
        # JSON-'null' edge case. (P0.1 perf)
        rows = db.execute(select(t).where(t.c.project_id == project_id, t.c.anchor.isnot(None)))
        for r in rows:
            m = r._mapping
            if not m["anchor"]:  # JSON-null safe (SQLite stores None as JSON null)
                continue
            pins.append({
                "module": key, "module_name": mod["name"], "icon": mod.get("icon", "•"),
                "id": m["id"], "ref": m["ref"], "title": m["title"],
                "status": m["workflow_state"], "anchor": m["anchor"],
                "element_guids": m["element_guids"],
            })
    return pins
