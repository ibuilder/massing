"""GC portal module engine.

Every business process (RFIs, Submittals, PCO Requests, Change Orders, …) is a *module*
described by a single `module.json` and stored in its **own table** (`mod_<key>`), created
automatically. One shared engine renders CRUD and drives a **role-gated workflow state
machine**. Records can be anchored to the model (pins) and linked into chains (the
change-order process). Every transition is written to the record activity timeline.

Implements the patent-described system (provisional 514712205), modernised on FastAPI.
"""
from __future__ import annotations

import uuid
from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import (
    Float,
    cast,
    func,
    insert,
    or_,
    select,
    update,
)
from sqlalchemy.orm import Session

from . import audit, fin_gov, module_schema, rbac
from .models import EnumOption, RecordActivity, RecordComment, Topic

# the read + workflow-evaluation base is a leaf over the registry (no writes, no cycles); re-exported
# so every existing `modules.list_records` / `.available_actions` / … caller keeps working.
from .modules_query import (  # noqa: F401
    _json_text,
    _transition,
    active_records,
    aggregate,
    available_actions,
    count_records,
    court_party,
    list_records,
    state_counts,
    state_counts_all,
    view_filters,
)

# the registry + table foundation is a leaf (imports only db.Base); re-exported so modules.get_module /
# .TABLES / .load_registry etc. keep working.
from .modules_registry import (  # noqa: F401
    MODULES_DIR,
    REGISTRY,
    REVERSE_REFS,
    TABLES,
    _now,
    _table,
    get_module,
    input_fields,
    load_registry,
    reference_fields,
    rollup_fields,
)

# full-text search is a pure leaf (functions take the Table as an arg); this module injects TABLES.
# Re-exported (not all used here): tests and other engines reach them as `modules._pg_document` etc.
from .modules_search import _is_postgres, _pg_document, _pg_tsquery  # noqa: F401
from .modules_search import index_ddl as _index_ddl
from .modules_search import search_filter as _search_filter  # noqa: F401

# --- workflow ---------------------------------------------------------------


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


def apply_defaults(mod: dict, data: dict) -> dict:
    """MOD-FIELDATTRS — fill declared defaults on a NEW record, and only where the caller said nothing.

    Create-only, deliberately. Applying a default on update would re-fill a field the user had just
    cleared, making "empty" unreachable and the clearing look like it failed.

    Only fills a key that is ABSENT or empty-string. A caller that sent `0` or `false` meaning "no" has
    expressed an intent, and a default that overrode it would be the config out-voting the user — which
    is the whole risk of defaults: the value is invisible precisely because it looks like something
    somebody chose. Note `0` and `false` survive this because neither equals `""` in Python; if that
    test is ever rewritten as a truthiness check (`if not cur`), **both start being overridden** and a
    deliberate zero silently becomes the default. `test_field_attrs` pins that.

    `""` IS filled, and that is the one case where the create-only scope is doing the work: on a NEW
    record an empty string is a form field nobody typed in, not a value someone cleared. On update the
    function does not run at all, so a cleared field stays cleared.
    """
    for f in mod.get("fields", []):
        d = f.get("default")
        if d is None:
            continue
        cur = data.get(f["name"])
        if cur is None or cur == "":
            data[f["name"]] = _resolve_default(d)
    return data


#: Defaults that are computed rather than literal. Only one so far, and it earns its keep: a daily
#: report, a T&M ticket and a manpower log are all filed for the day they happened, so "today" is a
#: fact about the record. A literal date in config would be wrong the day after it was written.
def _resolve_default(d):
    if d == "@today":
        from .timeutil import utc_today
        return utc_today().isoformat()
    return d


def apply_table_totals(mod: dict, merged: dict) -> dict:
    """MOD-TOTALS — a `table` field with `totals_into` writes its sum into the named numeric field.

    Line items and the number the engines read were two separate facts a user had to keep in
    agreement by hand. `tm.summarize` reads `eticket.labor_total`; the labour rows live in
    `labor_lines`; nothing connected them, so itemising a ticket meant typing the total again and
    every later edit could silently disagree with its own lines.

    Declared rather than inferred. A convention like "`<table>_total`" would be invisible in the
    config and would surprise the first module whose field happens to be named that way, so the table
    says where its sum goes and `validate_module` checks the target exists and is numeric.

    Computed over the MERGED record, not the incoming patch: a PATCH that touches only the lines must
    still update the total, and one that touches only the total must not be able to contradict its
    lines — the lines win, because they are the evidence and the total is the summary.
    """
    for f in mod.get("fields", []):
        if f.get("type") != "table" or not f.get("totals_into"):
            continue
        rows = merged.get(f["name"])
        if not isinstance(rows, list):
            continue                      # legacy free text, or the field was never filled in
        col = f.get("total_column")
        if not col:
            continue
        total = 0.0
        for r in rows:
            if not isinstance(r, dict):
                continue
            try:
                total += float(r.get(col) or 0)
            except (TypeError, ValueError):
                continue                  # a bad cell is already reported by validate_record
        merged[f["totals_into"]] = round(total, 2)
    return merged


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
    from sqlalchemy import update as sa_update
    from sqlalchemy.exc import IntegrityError

    from .models import RefCounter

    # The increment is a single atomic `UPDATE … SET n = n + 1 … RETURNING n`. This replaced a
    # read-modify-write under `with_for_update()`, which was correct on exactly one backend:
    # Postgres honours the row lock, but **SQLite treats FOR UPDATE as a no-op**, so two threads
    # both read n=1, both wrote n=2, and both minted "RFI-002" — measured, not theorised;
    # test_race_conditions caught it with four concurrent creates the first time it ran. A lock the
    # backend ignores is worse than no lock, because the code reads as protected. The atomic UPDATE
    # is serialised by the write path itself on both backends, so there is nothing left to ignore.
    for _ in range(2):
        n = db.execute(
            sa_update(RefCounter)
            .where(RefCounter.project_id == project_id, RefCounter.module == key)
            .values(n=RefCounter.n + 1)
            .returning(RefCounter.n)
        ).scalar()
        if n is not None:
            return f"{mod.get('ref_prefix', key.upper())}-{n:03d}"

        # No counter row yet — seed it. SEEDING is the one moment no row-level mechanism can
        # protect (there is no row), so two concurrent FIRST creates can both get here; the
        # composite PK refuses the second, which used to surface as a 500 on an ordinary create.
        # The refusal is the database working — the bug was treating it as a crash. It runs in a
        # SAVEPOINT so the loser's refusal stays local (the same pattern, for the same reason, as
        # `rbac.consume_stepup`), and the loser simply loops back into the atomic increment against
        # the winner's row.
        seed = db.execute(select(func.count()).select_from(TABLES[key])
                          .where(TABLES[key].c.project_id == project_id)).scalar() or 0
        try:
            with db.begin_nested():
                db.add(RefCounter(project_id=project_id, module=key, n=seed))
        except IntegrityError:
            pass                                    # another writer seeded first — use their row
    raise RuntimeError("ref counter neither existed nor could be seeded")   # unreachable


def create_record(db: Session, key: str, project_id: str, body: dict, actor: str,
                  party: str | None, *, commit: bool = True) -> dict:
    """Validate + insert one module record (and its audit-log row). `commit=False` lets a seed loop
    batch many creates into ONE transaction instead of a commit per record (the generate-massing
    seeds were issuing ~20-40 commits per request) — the caller then owns the final ``db.commit()``,
    and a mid-loop failure rolls the whole seed back atomically. Refs stay sequential either way:
    ``_next_ref`` reads through the session, which sees the uncommitted rows."""
    mod = get_module(key)
    t = TABLES[key]
    data = body.get("data", {})
    title_field = mod.get("title_field") or (mod["fields"][0]["name"] if mod.get("fields") else None)
    # `subject` is a universal title alias: modules name their title field differently
    # (title/name/number/system); if it's absent but `subject` was supplied, fill it — so callers,
    # scripts and integrations don't have to special-case each module's field name.
    if title_field and title_field != "subject" and not data.get(title_field) and data.get("subject"):
        data[title_field] = data["subject"]
    apply_defaults(mod, data)            # MOD-FIELDATTRS: before the required check, so a defaulted
                                         # field satisfies `required` rather than failing it
    _validate_fields(mod, data)
    _validate_values(mod, data)
    apply_table_totals(mod, data)        # MOD-TOTALS: line items drive the total the engines read
    if (why := fin_gov.locked_reason(key, project_id, data)):     # FIN-GOV period lock
        raise HTTPException(409, why)
    rid = str(uuid.uuid4())
    row = {
        "id": rid, "project_id": project_id,
        "ref": _next_ref(db, key, project_id, mod),
        "title": data.get(title_field) if title_field else None,
        "workflow_state": mod.get("workflow", {}).get("initial", "open"),
        "party_owner": party, "assignee": body.get("assignee"),
        "created_by": actor, "created_at": _now(), "modified_at": _now(),
        # MOD-GUID: the union of what the caller anchored and what the record's own GlobalId fields
        # name, so the canonical column can never be a subset of the record's own data. `or` keeps a
        # caller-supplied None as None rather than turning it into [].
        "anchor": body.get("anchor"),
        "element_guids": (sorted({*(body.get("element_guids") or []),
                                  *module_schema.guids_from_fields(data)})
                          or body.get("element_guids")),
        "links": body.get("links") or [], "data": data,
        # R41-SCHEMA-STALE: record the shape these values were validated against, so a later
        # rename/removal/retype is a fact about this row rather than a guess at read time.
        "schema_version": module_schema.schema_stamp(mod),
    }
    db.execute(insert(t).values(**row))
    _log(db, project_id, key, rid, actor, party, "create", {"ref": row["ref"]})
    if commit:
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
        element_guids=src.get("element_guids"), links=[], data=data,
        # a revision is a NEW record written now, so it carries today's shape — not the source's.
        schema_version=module_schema.schema_stamp(mod)))
    superseded = dict(src.get("data") or {}); superseded["superseded_by"] = new_id
    db.execute(update(t).where(t.c.id == rid, t.c.project_id == project_id)
               .values(data=superseded, modified_at=_now()))
    _log(db, project_id, key, new_id, actor, party, "revise", {"revises": src["ref"], "revision": rev_n})
    _log(db, project_id, key, rid, actor, party, "superseded", {"by": f"{base}.{rev_n}"})
    db.commit()
    return get_record(db, key, project_id, new_id)


def fts_index_ddl(key: str) -> str:
    """CREATE INDEX DDL for a module's FTS GIN index — injects the `TABLES` registry into the pure
    `modules_search.index_ddl`, preserving the old `fts_index_ddl(key)` signature its callers/tests use."""
    return _index_ddl(key, TABLES[key])


def ensure_fts_indexes(engine) -> None:
    """Postgres-only: create the GIN index behind list_records()'s `@@` search for every module — so
    full-text search is index-backed instead of a per-row seq scan recomputing to_tsvector (brutal at
    100k+ records). No-op on SQLite (dev/CI use the LIKE fallback). Idempotent (CREATE INDEX IF NOT EXISTS)."""
    if engine.dialect.name != "postgresql":
        return
    import logging

    from sqlalchemy import text
    log = logging.getLogger("aec_api.modules")
    for key in TABLES:
        try:
            with engine.begin() as conn:
                conn.execute(text(fts_index_ddl(key)))
        except Exception:            # noqa: BLE001 — an index backfill must never block startup
            log.warning("FTS GIN index for module %r could not be created", key)


def view_alerts(db: Session, project_id: str, user: str) -> list[dict]:
    """Saved-search alerts: for each view this user can read, the total matches + how many are NEW
    since **they** last opened it (a never-opened view counts all matches as new). Powers the 🔔 feed.

    Covers the user's own views AND every `project`-scoped view in the project, each counted from the
    viewer's own last visit via `SavedViewSeen`. Until v0.3.1109 this filtered on `SavedView.user`
    alone, so a shared view alerted nobody but its author — sharing shipped for reading and stopped at
    the feed. The reason it stopped is recorded on the model: `saved_views.last_seen_at` was one
    column on one row, so a second person's "new since" would have been computed from the AUTHOR's
    last visit, which is the same confidently-wrong number the filter miscount produced one layer
    down. The per-viewer table is what makes this safe rather than merely possible.

    `mine` distinguishes a user's own views from views shared with them, because a feed that mixes
    them silently makes "why am I being told about this?" unanswerable.
    """
    from .models import SavedView, SavedViewSeen
    views = db.query(SavedView).filter(
        SavedView.project_id == project_id,
        or_(SavedView.user == user, SavedView.scope == "project"),
    ).order_by(SavedView.created_at).all()
    # One query for every seen-row this user has on these views, rather than one per view.
    seen: dict[str, datetime] = {}
    if views:
        for row in db.query(SavedViewSeen).filter(
                SavedViewSeen.user == user,
                SavedViewSeen.view_id.in_([v.id for v in views])).all():
            seen[row.view_id] = row.last_seen_at
    out = []
    for v in views:
        cfg = v.config or {}
        state, q = cfg.get("state"), cfg.get("q")
        # R22-REPORT-BUILDER item 3 — THE FILTERS COUNT TOO, and until now they did not.
        #
        # `count_records` has taken `filters` since MOD-FILTER, and its docstring names this caller:
        # *"a count that ignores a filter the list applied reports a total the page cannot account
        # for, and a total is exactly the number a user trusts without checking."* The parameter was
        # built for saved-view alerts and the saved-view alert path never passed it.
        #
        # Measured on two RFIs differing by one declared field, with a view saved as
        # `{"filters": [["discipline","eq","Structural"]]}` — which the write route accepted, because
        # nothing validated a config: **the feed said 2 and the view showed 1.** A notification that
        # over-counts trains people to stop opening it, and it is the same confident-wrong-number
        # shape `aggregate` refuses `sum` over text to avoid.
        #
        # The shipped web register only ever saved `{q, state, sort}`, so no browser produced this —
        # but the API accepted filters from anything else, and item 3's schema now *invites* them.
        # Fixing the count is what makes storing them safe.
        # `ValueError` — the stored `filters` are not readable at all. `HTTPException` — they are
        # readable but name a field this module no longer declares, which `_apply_filters` refuses
        # at count time. Both mean the same thing to a reader of the feed: this view's number cannot
        # be computed, so it must not be guessed.
        try:
            filters = view_filters(cfg)
            if filters:
                count_records(db, v.module, project_id, filters=filters)
        except (ValueError, HTTPException):
            filters = None
        if filters is None:
            # Uncountable rather than counted wrong: a view whose stored config cannot be read is
            # reported with `total: None` and a reason, so the UI can say "this view needs re-saving"
            # instead of showing a number that describes different rows than the view does.
            out.append({"id": v.id, "name": v.name, "module": v.module,
                        "total": None, "new": None, "config": cfg,
                        "scope": v.scope, "owner": v.user, "mine": v.user == user,
                        "error": "saved before view configs were validated; re-save to enable alerts"})
            continue
        total = count_records(db, v.module, project_id, state=state, q=q, filters=filters)
        # THIS viewer's last visit, not the view's. A view nobody has opened counts everything as new,
        # which is right for each reader independently: a shared view is new to me the first time I
        # see it however long its author has had it.
        mine_seen = seen.get(v.id)
        new = count_records(db, v.module, project_id, state=state, q=q, since=mine_seen,
                            filters=filters) if mine_seen else total
        out.append({"id": v.id, "name": v.name, "module": v.module, "total": total, "new": new,
                    "config": cfg, "scope": v.scope, "owner": v.user, "mine": v.user == user,
                    "last_seen_at": mine_seen.isoformat() if mine_seen else None})
    return out


#: How far back the comment thread walks a revision chain. Revisions are shallow in practice
#: (a submittal at rev 5 is unusual), so this is a loop guard rather than a policy: `data.revises`
#: is caller-writable JSON, and a cycle there would otherwise spin `get_record` forever.
_REVISION_WALK_MAX = 32


def _revision_ancestry(db: Session, key: str, project_id: str, rid: str) -> list[tuple[str, str]]:
    """`(id, ref)` of every earlier revision of `rid`, oldest first.

    `revise()` writes a NEW record and links it to its source by `data.revises`, so anything keyed
    by `record_id` — comments, above — stops at the revision in hand. Walking the chain is what lets
    a resubmittal show the review that asked for it.
    """
    t = TABLES[key]
    out: list[tuple[str, str]] = []
    seen = {rid}
    cur = rid
    for _ in range(_REVISION_WALK_MAX):
        row = db.execute(select(t.c.data, t.c.ref).where(
            t.c.id == cur, t.c.project_id == project_id)).first()
        if not row:
            break
        prev = ((row._mapping["data"] or {}) or {}).get("revises")
        if not prev or prev in seen:            # unlinked, or a cycle in caller-written JSON
            break
        seen.add(prev)
        prow = db.execute(select(t.c.ref).where(
            t.c.id == prev, t.c.project_id == project_id)).first()
        if not prow:                            # source deleted; the chain simply ends
            break
        out.append((prev, prow._mapping["ref"]))
        cur = prev
    out.reverse()
    return out


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
    # R22-ENTITLEMENT ④ — the thread spans the REVISION CHAIN, not just this record.
    #
    # `revise()` writes a new record with a new id, so comments keyed by `record_id` stayed behind:
    # a reviewer who returned SUB-001 "Revise & Resubmit — anchor spacing does not match detail
    # 5/A-501" opened SUB-001.1 and saw an empty list, with no way to check whether the resubmittal
    # addressed anything. Fifteen modules are `revisable`, so the same held for every reissued RFI.
    #
    # Inherited comments are LABELLED rather than merged flat. A comment written against rev 0 is
    # evidence about rev 0; showing it as though it were written about the revision in hand would be
    # a confident wrong answer — worse than the omission, because it reads as current.
    ancestry = _revision_ancestry(db, key, project_id, rid)
    ref_by_id = dict(ancestry)
    ids = [aid for aid, _ in ancestry] + [rid]
    rec["comments"] = sorted(
        ({"id": cm.id, "author": cm.author, "text": cm.text,
          "created_at": cm.created_at.isoformat() if cm.created_at else None,
          # R22-ENTITLEMENT ⑤: present ONLY when promoted, so a caller cannot read `None` as "not
          # yet" on a build that predates the column. `id` is exposed for the same reason promotion
          # needs it — a comment nobody can address is a comment nobody can act on.
          **({"topic_id": cm.topic_id} if cm.topic_id else {}),
          **({"inherited": True, "on_ref": ref_by_id[cm.record_id]}
             if cm.record_id != rid else {})}
         for cm in db.query(RecordComment).filter(
             RecordComment.module == key, RecordComment.record_id.in_(ids)).all()),
        key=lambda cm: (cm["created_at"] or ""))
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
    # R41-SCHEMA-STALE: does this record's payload still mean what the current schema says it means?
    # Reported on every read rather than only when wrong, so a caller can tell "checked and fine"
    # from "not checked" — a key that appears only on failure is indistinguishable from a key the
    # server forgot to send, which is the shape of bug this whole item is about.
    rec["schema"] = module_schema.schema_status(mod, rec.get("schema_version"), data)
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


def sum_field(db: Session, key: str, project_id: str, field: str,
              states: list[str] | None = None,
              exclude_states: list[str] | None = None) -> float:
    """SQL `SUM` of a numeric JSON field across a project's records — no full-table load into Python.
    Portable: casts the Postgres `->>` text to float; SQLite `json_extract` is already numeric. NULL /
    missing values are skipped by SUM. Optional `states` narrows to those workflow states;
    `exclude_states` drops them (NULL states are kept, matching a Python `not in` check). Use for
    aggregate-only reads (e.g. billed-to-date, open trade AP) instead of
    `list_records(limit=100000)` + a Python sum."""
    if key not in TABLES:
        return 0.0
    t = TABLES[key]
    col = _json_text(db, t.c.data, field)
    expr = func.sum(cast(col, Float)) if _is_postgres(db) else func.sum(col)
    stmt = select(expr).where(t.c.project_id == project_id)
    if states:
        stmt = stmt.where(t.c.workflow_state.in_(states))
    if exclude_states:
        stmt = stmt.where(or_(t.c.workflow_state.is_(None),
                              t.c.workflow_state.notin_(exclude_states)))
    val = db.execute(stmt).scalar()
    return float(val or 0.0)


def count_field_in(db: Session, key: str, project_id: str, field: str, values: list[str]) -> int:
    """SQL `COUNT` of a project's records whose JSON `field` is one of `values` — the classification
    tallies (e.g. OSHA-recordable incidents) without materializing every row into Python."""
    if key not in TABLES or not values:
        return 0
    t = TABLES[key]
    col = _json_text(db, t.c.data, field)
    val = db.execute(select(func.count()).where(t.c.project_id == project_id,
                                                col.in_(values))).scalar()
    return int(val or 0)


def find_id_by_field(db: Session, key: str, project_id: str, field: str, value: str) -> str | None:
    """Id of the first record whose JSON `field` (or the title column) equals `value`
    case-insensitively — one SQL probe selecting only the id column, instead of materializing full
    rows into Python to search (the previous name→id resolutions scanned the table per lookup)."""
    if key not in TABLES or not value:
        return None
    t = TABLES[key]
    want = str(value).strip().lower()
    col = _json_text(db, t.c.data, field)
    return db.execute(
        select(t.c.id).where(t.c.project_id == project_id,
                             or_(func.lower(func.trim(col)) == want,
                                 func.lower(func.trim(t.c.title)) == want))
        .limit(1)).scalar()


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
                   content_type: str | None, data: bytes | None, actor: str, *,
                   chunks=None) -> dict:
    """Attach a file to a record.

    R39-UPLOAD-CAP-APP. Same widening as `docmanager.upload`: pass EITHER `data` (bytes in hand) or
    `chunks` (an iterable from `storage.upload_chunks`), never both and never neither. The routes
    pass `chunks` — Starlette has already spooled the upload to disk, so `await file.read()` was
    copying a file that existed.

    `size` is `put_stream`'s return value on the streaming path — the count actually WRITTEN — so
    the row cannot record a size the stored object does not have. It is used twice below (the row and
    the response) and both now read the same variable rather than re-deriving it.
    """
    from . import storage
    from .models import RecordAttachment

    if (data is None) == (chunks is None):
        raise ValueError("pass exactly one of `data` or `chunks`")
    get_record(db, key, project_id, rid)  # 404 if missing
    aid = str(uuid.uuid4())
    skey = f"records/{project_id}/{key}/{rid}/{aid}_{filename}"
    if chunks is not None:
        size = storage.put_stream(skey, chunks)
    else:
        storage.put(skey, data)
        size = len(data)
    att = RecordAttachment(id=aid, project_id=project_id, module=key, record_id=rid,
                           filename=filename, content_type=content_type, size=size,
                           storage_key=skey, uploaded_by=actor)
    db.add(att)
    _log(db, project_id, key, rid, actor, None, "attach", {"filename": filename})
    db.commit()
    return {"id": aid, "filename": filename, "size": size, "content_type": content_type}


def list_attachments(db: Session, key: str, project_id: str, rid: str) -> list[dict]:
    from .models import RecordAttachment
    # project_id predicate is defense-in-depth: record ids are UUIDs today, but a cross-project row
    # must never surface even if an id is ever reused or a non-UUID id is introduced.
    return [{"id": a.id, "filename": a.filename, "size": a.size,
             "content_type": a.content_type, "uploaded_by": a.uploaded_by,
             "created_at": a.created_at.isoformat() if a.created_at else None}
            for a in db.query(RecordAttachment).filter(
                RecordAttachment.project_id == project_id,
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
        # filter the reverse-reference match in SQL (JSON extraction) so only the matching source rows
        # are fetched — the source table is no longer fully scanned + shipped to Python on the
        # per-record detail view (mirrors _rollup).
        for r in db.execute(select(t.c.id, t.c.ref, t.c.title, t.c.workflow_state)
                            .where(t.c.project_id == project_id,
                                   _json_text(db, t.c.data, field) == rid)):
            m = r._mapping
            incoming.append({"module": src_key, "module_name": src_name, "id": m["id"],
                             "ref": m["ref"], "title": m["title"], "state": m["workflow_state"]})
    return {"outgoing": outgoing, "incoming": incoming}


def delete_record(db: Session, key: str, project_id: str, rid: str, actor: str,
                  party: str | None) -> dict:
    """Delete a record (and its activity/comments). Returns {deleted, ref}."""
    t = TABLES[key]
    rec = get_record(db, key, project_id, rid)  # 404 if missing
    if (why := fin_gov.locked_reason(key, project_id, rec.get("data"))):  # FIN-GOV period lock
        raise HTTPException(409, why)
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


def promote_comment(db: Session, key: str, project_id: str, rid: str, cid: str,
                    author: str, kind: str = "rfi") -> dict:
    """R22-ENTITLEMENT ⑤ — turn a review comment into an RFI/issue Topic somebody owns.

    **The gap this closes.** `RecordComment` had no outward link of any kind, so an agency's review
    comment on an `entitlement` or `permit` was a text blob at the end of a thread: readable, and
    impossible to assign, track or close. The ring's own remainder called this "comment-response
    round-tripping into RFI/issue records", and the round trip was missing in the *outbound*
    direction — ④ had already made comments survive a revision, which is the inbound half.

    Follows `promote_markup` exactly rather than inventing a second idiom: mint a `Topic`, carry the
    source's identity into the description, copy the record's `element_guids` so the RFI lands on the
    model, write the back-link, and audit. **The back-link is the idempotency**: a second promote of
    the same comment 409s instead of minting a duplicate RFI, which is the failure mode a
    "promote" button produces on every double-click.
    """
    rec = get_record(db, key, project_id, rid)          # 404 if the record is missing
    cm = db.get(RecordComment, cid)
    if not cm or cm.project_id != project_id or cm.module != key or cm.record_id != rid:
        raise HTTPException(404, "no such comment on this record")
    if cm.topic_id:
        raise HTTPException(409, "comment already promoted")
    if kind not in ("rfi", "issue"):
        raise HTTPException(422, "kind must be rfi or issue")

    ref = rec.get("ref") or rid
    # `splitlines()` on stripped whitespace-only text yields [], so `[0]` raised IndexError — a 500
    # on a comment the comment route itself accepts (`text: str = Body(...)` has no min-length). The
    # fallback title below was written for exactly this case and was unreachable until now: when the
    # list is non-empty its first element is never blank, so the `or` arm could never fire.
    lines = (cm.text or "").strip().splitlines()
    title = lines[0][:80] if lines else f"{key} {ref} review comment"
    guids = rec.get("element_guids") or None
    t = Topic(project_id=project_id, type=("rfi" if kind == "rfi" else "punch"), status="open",
              author=author, title=title,
              description=(f"Raised from a review comment on {key} {ref}"
                           + (f" by {cm.author}" if cm.author else "") + ".\n\n" + (cm.text or "")),
              element_guids=guids)
    db.add(t)
    db.flush()
    # The `cm.topic_id` check above cannot be the last word: two requests each hold their own session,
    # each read a null back-link, and a plain assignment lets the later commit overwrite the earlier
    # one — minting a duplicate RFI *and* orphaning the first, whose Topic no comment then points at.
    # The claim is therefore a conditional UPDATE. Under Postgres read-committed the loser blocks on
    # the winner's row lock, then re-evaluates `topic_id IS NULL` against the committed row and
    # matches nothing; under SQLite the writes serialize to the same effect. Rolling back discards
    # the Topic flushed a moment ago, so a losing promote leaves nothing behind.
    if not db.execute(update(RecordComment)
                      .where(RecordComment.id == cid, RecordComment.topic_id.is_(None))
                      .values(topic_id=t.id)).rowcount:
        db.rollback()
        raise HTTPException(409, "comment already promoted")
    _log(db, project_id, key, rid, author, None, "comment.promote",
         {"comment": cid, "topic": t.id, "kind": kind})
    audit.record(db, action="record.comment.promote", actor=author, method="POST", topic_id=t.id,
                 path=f"/projects/{project_id}/modules/{key}/{rid}/comments/{cid}/promote",
                 detail={"module": key, "record": rid, "comment": cid})
    db.commit()
    return {"comment_id": cid, "topic": {"id": t.id, "type": t.type, "title": t.title,
                                         "status": t.status, "element_guids": t.element_guids},
            "record": get_record(db, key, project_id, rid)}


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
    merged = apply_table_totals(get_module(key), {**(rec.get("data") or {}), **data})
    # FIN-GOV period lock: a record already in a closed month is frozen, and an open-month record
    # can't be re-dated INTO a closed month — both sides of the merge are checked.
    if (why := fin_gov.locked_reason(key, project_id, rec.get("data"))
            or fin_gov.locked_reason(key, project_id, merged)):
        raise HTTPException(409, why)
    # MOD-GUID: keep `element_guids` in step with the record's own GlobalId fields. Create-only
    # mirroring would have missed the ordinary case — file the record, add the GlobalId when you get
    # back from the field — and left the two stores disagreeing exactly when someone CORRECTS a
    # mistyped id: the old value would sit in the column forever.
    #
    # Not a blind union. Subtract what this record's fields contributed BEFORE, then add what they
    # contribute now, so a correction moves the anchor while a GlobalId set by another route (a pin,
    # a BCF import, anchor-to-selection) is untouched — those were never ours to remove.
    # R41-SCHEMA-STALE: an edit re-validates the whole merged payload against today's schema, so the
    # stamp advances to today's shape. Leaving the old stamp would keep flagging a record the user
    # has just corrected — the flag has to be clearable BY the action that fixes it, or it is noise.
    vals = {"data": merged, "modified_at": _now(),
            "schema_version": module_schema.schema_stamp(get_module(key))}
    was, now = module_schema.guids_from_fields(rec.get("data") or {}), module_schema.guids_from_fields(merged)
    if was != now:
        col = (set(rec.get("element_guids") or []) - set(was)) | set(now)
        vals["element_guids"] = sorted(col) or None
    db.execute(update(t).where(t.c.id == rid).values(**vals))
    _log(db, project_id, key, rid, actor, party, "update", {"fields": list(data.keys())})
    db.commit()
    return get_record(db, key, project_id, rid)


def transition(db: Session, key: str, project_id: str, rid: str, action: str,
               actor: str, party: str | None, note: str | None = None) -> dict:
    # WFE-3: evaluate the project's own workflow, not just the shipped default. `effective` returns
    # the module unchanged when there is no override, so the common path is untouched.
    from . import workflow_config
    mod = workflow_config.effective(get_module(key), project_id)
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
    # move the record AND its ball-in-court: party_owner now tracks whose court the new state is in
    # (WORKFLOW-ENGINE — it was set once at create and then went stale). Terminal states have no next
    # court, so we leave the last owner in place there rather than blanking it.
    vals: dict = {"workflow_state": tr["to"], "modified_at": _now()}
    new_court = court_party(mod, tr["to"])
    if new_court:
        vals["party_owner"] = new_court
    db.execute(update(t).where(t.c.id == rid).values(**vals))
    _log(db, project_id, key, rid, actor, party, f"transition:{action}",
         {"from": rec["workflow_state"], "to": tr["to"], "note": note, "court": new_court})
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
