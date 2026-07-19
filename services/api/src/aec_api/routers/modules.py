"""GC portal module endpoints — config-driven CRUD + role-gated workflow + model pins.

One set of routes serves every module (RFIs, Submittals, the change-order chain, …). The
acting user's *party role* gates workflow transitions; the *capability role* gates writes."""
from __future__ import annotations

import logging

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Query, Request, Response, UploadFile
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .. import ai, audit, mailer, rbac
from .. import modules as mod_engine
from .. import sync as sync_engine
from ..db import get_db
from ..models import Connection, Project, ProjectMember, SyncSchedule, User
from ..rbac import current_user, require_role
from .authoring_shared import safe_filename

router = APIRouter()


def _party(pid: str, db: Session, user: str) -> str | None:
    return rbac.party_role_for(db, pid, user)


def _digest_body(project_name: str, user: str, items: list[dict]) -> tuple[str, str]:
    """Plain-text + HTML body for a user's work-queue digest."""
    lines = [f"{it['icon']} [{it['module_name']}] {it['ref']} — {it['title']}"
             f"  ({it['state']}, {it['reason']})" for it in items]
    text = (f"Hi {user},\n\nYou have {len(items)} open item(s) on {project_name}:\n\n"
            + "\n".join(lines) + "\n\n— Massing")
    rows = "".join(
        f"<li><b>{it['ref']}</b> — {it['title']} "
        f"<span style='color:#777'>({it['module_name']} · {it['state']} · {it['reason']})</span></li>"
        for it in items)
    html = (f"<p>Hi {user},</p><p>You have <b>{len(items)}</b> open item(s) on "
            f"<b>{project_name}</b>:</p><ul>{rows}</ul><p style='color:#999'>— Massing</p>")
    return text, html


@router.get("/modules")
def list_modules():
    """Module catalog (drives dynamic UI). Returns each module.json."""
    return [
        {"key": m["key"], "name": m["name"], "section": m.get("section"), "revisable": m.get("revisable", False),
         "workspace": m.get("workspace", "construction"),
         "icon": m.get("icon"), "pinnable": m.get("pinnable", False),
         "title_field": m.get("title_field"), "ref_prefix": m.get("ref_prefix"),
         "fields": m.get("fields", []), "workflow": m.get("workflow", {}),
         "relations": m.get("relations", []), "list_columns": m.get("list_columns")}
        for m in mod_engine.REGISTRY.values()
    ]


@router.get("/modules/graph")
def modules_graph(workspace: str | None = None):
    """The module-relations graph: one node per module, one edge per cross-module link (reference +
    rollup fields). Optionally scope to a `workspace` (keeps its modules + the targets they reference).
    Drives a node-canvas relations view — see how the ~180 config modules actually wire together."""
    from .. import module_graph
    return module_graph.build(mod_engine.REGISTRY, workspace=workspace)


@router.post("/projects/{pid}/sync/procore")
def sync_procore(pid: str, connection_id: str = Body(..., embed=True),
                 procore_project_id: str = Body(..., embed=True),
                 kinds: list[str] = Body(default=["rfi", "submittal", "change_event"], embed=True),
                 db: Session = Depends(get_db), user: str = Depends(require_role("editor"))):
    """Import a Procore project's RFIs / submittals / change events into the matching modules
    (idempotent). Uses a saved Procore connection's token. Editor+ (it writes records)."""
    c = db.get(Connection, connection_id)
    if not c or c.type != "procore":
        raise HTTPException(400, "connection_id must reference a Procore connection")
    token = (c.config or {}).get("access_token")
    if not token:
        raise HTTPException(400, "Procore connection has no access token")
    return sync_engine.sync_procore(db, pid, token, str(procore_project_id), kinds, user,
                                    _party(pid, db, user), (c.config or {}).get("mappings"))


@router.post("/projects/{pid}/sync/procore/push")
def push_procore(pid: str, connection_id: str = Body(..., embed=True),
                 procore_project_id: str = Body(..., embed=True),
                 kinds: list[str] = Body(default=["rfi"], embed=True),
                 db: Session = Depends(get_db), user: str = Depends(require_role("editor"))):
    """Two-way: push locally-resolved records (v1: RFI status + answer) back to Procore. Only
    records imported from Procore are pushed; idempotent."""
    c = db.get(Connection, connection_id)
    if not c or c.type != "procore":
        raise HTTPException(400, "connection_id must reference a Procore connection")
    token = (c.config or {}).get("access_token")
    if not token:
        raise HTTPException(400, "Procore connection has no access token")
    return sync_engine.push_procore(db, pid, token, str(procore_project_id), kinds, user)


class ScheduleIn(BaseModel):
    connection_id: str
    procore_project_id: str
    kinds: list[str] = ["rfi", "submittal", "change_event"]
    interval_minutes: int = 60
    enabled: bool = True
    push: bool = False


def _sched_public(s: SyncSchedule) -> dict:
    return {"id": s.id, "connection_id": s.connection_id, "procore_project_id": s.procore_project_id,
            "kinds": s.kinds or [], "interval_minutes": s.interval_minutes,
            "enabled": s.enabled is not False, "push": bool(s.push), "last_run": s.last_run,
            "last_result": s.last_result}


@router.get("/projects/{pid}/sync/schedules")
def list_schedules(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("admin"))):
    """Auto-sync schedules for this project (Procore → modules on an interval)."""
    return [_sched_public(s) for s in db.query(SyncSchedule).filter(SyncSchedule.project_id == pid).all()]


@router.post("/projects/{pid}/sync/schedules", status_code=201)
def create_schedule(pid: str, body: ScheduleIn, db: Session = Depends(get_db),
                    _: str = Depends(require_role("admin"))):
    c = db.get(Connection, body.connection_id)
    if not c or c.type != "procore":
        raise HTTPException(400, "connection_id must reference a Procore connection")
    s = SyncSchedule(project_id=pid, connection_id=body.connection_id,
                     procore_project_id=str(body.procore_project_id), kinds=body.kinds,
                     interval_minutes=max(5, body.interval_minutes), enabled=body.enabled, push=body.push)
    db.add(s)
    db.commit()
    return _sched_public(s)


@router.put("/projects/{pid}/sync/schedules/{sid}")
def update_schedule(pid: str, sid: str, enabled: bool | None = Body(default=None, embed=True),
                    interval_minutes: int | None = Body(default=None, embed=True),
                    kinds: list[str] | None = Body(default=None, embed=True),
                    push: bool | None = Body(default=None, embed=True),
                    db: Session = Depends(get_db), _: str = Depends(require_role("admin"))):
    s = db.get(SyncSchedule, sid)
    if not s or s.project_id != pid:
        raise HTTPException(404, "no such schedule")
    if enabled is not None:
        s.enabled = enabled
    if interval_minutes is not None:
        s.interval_minutes = max(5, interval_minutes)
    if kinds is not None:
        s.kinds = kinds
    if push is not None:
        s.push = push
    db.commit()
    return _sched_public(s)


@router.delete("/projects/{pid}/sync/schedules/{sid}")
def delete_schedule(pid: str, sid: str, db: Session = Depends(get_db),
                    _: str = Depends(require_role("admin"))):
    s = db.get(SyncSchedule, sid)
    if not s or s.project_id != pid:
        raise HTTPException(404, "no such schedule")
    db.delete(s)
    db.commit()
    return {"ok": True}


@router.post("/projects/{pid}/sync/schedules/{sid}/run-now")
def run_schedule_now(pid: str, sid: str, db: Session = Depends(get_db),
                     user: str = Depends(require_role("editor"))):
    from datetime import datetime, timezone
    s = db.get(SyncSchedule, sid)
    if not s or s.project_id != pid:
        raise HTTPException(404, "no such schedule")
    res = sync_engine.run_schedule(db, s, actor=user)
    s.last_run = datetime.now(timezone.utc)
    s.last_result = res
    db.commit()
    return res


@router.post("/projects/{pid}/ai/draft-rfi")
def draft_rfi(pid: str, element: dict = Body(default={}, embed=True),
              note: str | None = Body(default=None, embed=True),
              _: str = Depends(require_role("reviewer"))):
    """Draft an RFI (subject/question/discipline/priority) from a selected element's IFC context.
    Uses Claude when ANTHROPIC_API_KEY is set; otherwise returns a deterministic template draft.
    Reviewer+ (same gate as creating RFIs; avoids anonymous LLM-token burn)."""
    draft = ai.draft_rfi(element or {}, note)
    return {"ai_enabled": ai.ai_enabled(), **draft}


@router.post("/projects/{pid}/ai/triage-rfi")
def triage_rfi(pid: str, rid: str | None = Body(default=None, embed=True),
               rfi: dict = Body(default={}, embed=True),
               db: Session = Depends(get_db), _: str = Depends(require_role("reviewer"))):
    """Triage an RFI — auto-categorize (discipline / category / urgency), name the ball-in-court party,
    and draft a response. Pass `rid` to triage an existing RFI record, or `rfi` data directly. Uses
    Claude when configured; a deterministic template otherwise."""
    data = rfi or {}
    if rid:
        try:
            data = mod_engine.get_record(db, "rfi", pid, rid).get("data") or {}
        except HTTPException:
            pass
    return {"ai_enabled": ai.ai_enabled(), **ai.triage_rfi(data)}


@router.get("/projects/{pid}/my-work")
def my_work(pid: str, db: Session = Depends(get_db), user: str = Depends(require_role("viewer"))):
    """Cross-module work queue for the current user (assigned + ball-in-court)."""
    return mod_engine.my_work(db, pid, user, _party(pid, db, user))


@router.get("/projects/{pid}/notifications")
def notifications(pid: str, db: Session = Depends(get_db), user: str = Depends(require_role("viewer"))):
    """Recent activity relevant to the caller (assigned / ball-in-court), newest first."""
    return mod_engine.notifications(db, pid, user, _party(pid, db, user))


@router.get("/projects/{pid}/due-feed")
def due_feed(pid: str, days: int = 7, db: Session = Depends(get_db),
            _: str = Depends(require_role("viewer"))):
    """Cross-module SLA feed — open records past or near their due date (overdue / due-soon)."""
    return mod_engine.due_feed(db, pid, soon_days=days)


def _build_digests(db: Session, pid: str) -> list[dict]:
    """Per-member work-queue digests for everyone on the project who has open items."""
    project = db.get(Project, pid)
    pname = project.name if project else pid
    out = []
    for mem in db.query(ProjectMember).filter(ProjectMember.project_id == pid).all():
        items = mod_engine.my_work(db, pid, mem.user, mem.party_role)
        if not items:
            continue
        u = db.get(User, mem.user)
        text, html = _digest_body(pname, mem.user, items)
        out.append({"user": mem.user, "email": (u.email if u else None), "count": len(items),
                    "subject": f"[{pname}] {len(items)} open item(s) need your attention",
                    "text": text, "html": html})
    return out


@router.get("/projects/{pid}/notifications/digest/preview")
def digest_preview(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("admin"))):
    """Preview the per-member digests (no send) — also reports whether SMTP is configured."""
    digests = _build_digests(db, pid)
    return {"smtp_configured": mailer.smtp_configured(),
            "recipients": [{"user": d["user"], "email": d["email"], "count": d["count"],
                            "subject": d["subject"], "text": d["text"]} for d in digests]}


@router.post("/projects/{pid}/notifications/digest")
def send_digest(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("admin"))):
    """Send each member with open items a work-queue digest email. No-op-but-logged per
    recipient when SMTP is unconfigured (status 'disabled'); members without an email are
    skipped. Returns a per-recipient result summary."""
    results: dict[str, list[str]] = {}
    skipped: list[str] = []
    for d in _build_digests(db, pid):
        if not d["email"]:
            skipped.append(d["user"])
            continue
        status = mailer.send_email(d["email"], d["subject"], d["text"], d["html"])
        results.setdefault(status, []).append(d["user"])
    return {"smtp_configured": mailer.smtp_configured(), "results": results, "skipped_no_email": skipped}


@router.get("/projects/{pid}/notifications/stream")
async def notifications_stream(pid: str, request: Request, user: str = Depends(require_role("viewer"))):
    """Server-sent events: pushes the notification feed to the client and re-pushes when
    the relevant activity count changes (polled server-side every few seconds). Uses a
    fresh DB session per poll since the generator outlives the request scope."""
    import asyncio
    import json as _json

    from fastapi.responses import StreamingResponse

    from ..db import SessionLocal

    async def gen():
        last = None
        while not await request.is_disconnected():
            with SessionLocal() as db:
                party = _party(pid, db, user)
                items = mod_engine.notifications(db, pid, user, party)
            sig = len(items), (items[0]["ts"] if items else None)
            if sig != last:
                last = sig
                yield f"data: {_json.dumps({'count': len(items), 'items': items[:8]})}\n\n"
            await asyncio.sleep(5)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


# --- saved views (server-side, per user+module) -----------------------------
@router.get("/projects/{pid}/modules/{key}/views")
def list_views(pid: str, key: str, db: Session = Depends(get_db), user: str = Depends(require_role("viewer"))):
    from ..models import SavedView
    rows = db.query(SavedView).filter(SavedView.project_id == pid, SavedView.module == key,
                                      SavedView.user == user).order_by(SavedView.created_at).all()
    return [{"id": v.id, "name": v.name, "config": v.config} for v in rows]


@router.post("/projects/{pid}/modules/{key}/views", status_code=201)
def save_view(pid: str, key: str, name: str = Body(..., embed=True),
              config: dict = Body(default={}, embed=True),
              db: Session = Depends(get_db), user: str = Depends(require_role("reviewer"))):
    from ..models import SavedView
    v = db.query(SavedView).filter(SavedView.project_id == pid, SavedView.module == key,
                                   SavedView.user == user, SavedView.name == name).first()
    if v:
        v.config = config
    else:
        v = SavedView(project_id=pid, module=key, user=user, name=name, config=config)
        db.add(v)
    db.commit()
    return {"id": v.id, "name": v.name, "config": v.config}


@router.get("/projects/{pid}/views/alerts")
def view_alerts(pid: str, db: Session = Depends(get_db), user: str = Depends(require_role("viewer"))):
    """Saved-search alert feed: each of my saved views with its total + new-since-last-seen counts."""
    return mod_engine.view_alerts(db, pid, user)


@router.post("/projects/{pid}/modules/{key}/views/{vid}/seen")
def mark_view_seen(pid: str, key: str, vid: str, db: Session = Depends(get_db),
                   user: str = Depends(require_role("reviewer"))):
    """Mark a saved view as seen now — clears its 'new' alert count."""
    from datetime import datetime, timezone

    from ..models import SavedView
    v = db.get(SavedView, vid)
    if not v or v.user != user or v.project_id != pid:
        raise HTTPException(404, "view not found")
    v.last_seen_at = datetime.now(timezone.utc)
    db.commit()
    return {"ok": True, "last_seen_at": v.last_seen_at.isoformat()}


@router.delete("/projects/{pid}/modules/{key}/views/{vid}")
def delete_view(pid: str, key: str, vid: str, db: Session = Depends(get_db),
                user: str = Depends(require_role("editor"))):
    from ..models import SavedView
    v = db.get(SavedView, vid)
    if v and v.user == user:
        db.delete(v); db.commit()
    return {"deleted": bool(v)}


@router.get("/projects/{pid}/enum-options")
def list_enum_options(pid: str, db: Session = Depends(get_db), user: str = Depends(require_role("viewer"))):
    """E1 — project-level custom select options, nested {module: {field: [values]}}."""
    return mod_engine.list_enum_options(db, pid)


@router.post("/projects/{pid}/modules/{key}/enum/{field}", status_code=201)
def add_enum_option(pid: str, key: str, field: str, value: str = Body(..., embed=True),
                    db: Session = Depends(get_db), user: str = Depends(require_role("reviewer"))):
    """E1 — add a custom option to a module field's select enum (no JSON edit)."""
    return mod_engine.add_enum_option(db, pid, key, field, value, user)


@router.get("/projects/{pid}/search")
def search(pid: str, q: str, limit: int = 50, db: Session = Depends(get_db),
           _: str = Depends(require_role("viewer"))):
    """Cross-module full-text search (ref / title / field data)."""
    # clamp like the record-list route — an unbounded limit fans out an oversized SQL LIMIT per module
    return mod_engine.search_all(db, pid, q, max(1, min(int(limit or 50), 200)))


@router.post("/projects/{pid}/modules/{key}/bulk")
def bulk_action(pid: str, key: str, ids: list[str] = Body(..., embed=True),
                action: str = Body(..., embed=True), value: str | None = Body(None, embed=True),
                db: Session = Depends(get_db), user: str = Depends(require_role("reviewer"))):
    """Apply transition / assign / delete to many records at once."""
    res = mod_engine.bulk(db, key, pid, ids, action, user, _party(pid, db, user), value)
    # the engine already committed; audit.record only adds a row, so commit it too (get_db doesn't)
    audit.record(db, action=f"module.bulk:{key}:{action}", actor=user, method="POST",
                 path=f"/projects/{pid}/modules/{key}/bulk",
                 detail={"module": key, "action": action, "count": len(ids), "value": value})
    db.commit()
    return res


@router.get("/projects/{pid}/modules/{key}")
def list_records(pid: str, key: str, state: str | None = None, q: str | None = None,
                 limit: int = 200, offset: int = 0, db: Session = Depends(get_db),
                 _: str = Depends(require_role("viewer"))):
    # clamp the caller-supplied page size — an unbounded ?limit= materializes the whole module
    limit = max(1, min(int(limit or 200), 1000))
    return mod_engine.list_records(db, key, pid, state, q, limit, max(0, int(offset or 0)))


@router.post("/projects/{pid}/modules/{key}", status_code=201)
def create_record(pid: str, key: str, body: dict = Body(...), db: Session = Depends(get_db),
                  user: str = Depends(require_role("reviewer"))):
    return mod_engine.create_record(db, key, pid, body, user, _party(pid, db, user))


@router.get("/projects/{pid}/modules/{key}/export.csv")
def export_csv(pid: str, key: str, db: Session = Depends(get_db),
               _: str = Depends(require_role("viewer"))):
    from fastapi.responses import StreamingResponse
    if key not in mod_engine.TABLES:
        raise HTTPException(404, "unknown module")
    # stream page-by-page — a 200k-record module never sits in memory as one string
    return StreamingResponse(mod_engine.iter_csv(db, key, pid), media_type="text/csv",
                             headers={"Content-Disposition": f'attachment; filename="{key}.csv"'})


@router.get("/projects/{pid}/modules/{key}/import-template.csv")
def import_template(pid: str, key: str, _: str = Depends(require_role("viewer"))):
    """A header-only CSV of the module's importable fields — fill it in and re-upload to bulk-import."""
    from .. import imports
    if key not in mod_engine.TABLES:
        raise HTTPException(404, "unknown module")
    return Response(imports.template_csv(key), media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="{key}-import-template.csv"'})


@router.post("/projects/{pid}/modules/{key}/import/preview")
async def import_preview(pid: str, key: str, file: UploadFile = File(...),
                         db: Session = Depends(get_db), _: str = Depends(require_role("reviewer"))):
    """Step 1 of a generic Excel/CSV import: parse the sheet, auto-suggest a column->field mapping,
    coerce a sample, and flag unmapped required fields. No records are created."""
    from .. import imports
    if key not in mod_engine.TABLES:
        raise HTTPException(404, "unknown module")
    return imports.preview(key, await file.read(), file.filename)


@router.post("/projects/{pid}/modules/{key}/import")
async def import_records(pid: str, key: str, file: UploadFile = File(...), mapping: str = Form("{}"),
                         db: Session = Depends(get_db), user: str = Depends(require_role("editor"))):
    """Step 2: import the sheet using a column->field mapping (JSON {source_header: field_name}).
    Validates required fields + coerces types per row; one bad row never aborts the batch."""
    import json

    from .. import imports
    if key not in mod_engine.TABLES:
        raise HTTPException(404, "unknown module")
    try:
        m = json.loads(mapping or "{}")
        if not isinstance(m, dict):
            raise ValueError
    except ValueError:
        raise HTTPException(422, "mapping must be a JSON object {source_header: field_name}")
    res = imports.do_import(db, key, pid, await file.read(), file.filename, m, user, _party(pid, db, user))
    audit.record(db, action="module.import", method="POST", path=f"/projects/{pid}/modules/{key}/import",
                 detail={"module": key, "imported": res.get("imported", 0)})
    db.commit()
    return res


@router.get("/projects/{pid}/modules/{key}/log.pdf")
def module_log(pid: str, key: str, db: Session = Depends(get_db),
               _: str = Depends(require_role("viewer"))):
    """Printable register (log) of every record in a module — the RFI log, submittal log,
    change-order log, etc., all from the same engine."""
    from .. import report
    from ..models import Project
    if key not in mod_engine.TABLES:
        raise HTTPException(404, "unknown module")
    p = db.get(Project, pid)
    pdf = report.module_log_pdf(db, pid, key, p.name if p else pid)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{key}_log.pdf"'})


# NOTE: must precede the /{rid} route so "board" isn't captured as a record id.
@router.get("/projects/{pid}/modules/{key}/board")
def module_board(pid: str, key: str, db: Session = Depends(get_db),
                 _: str = Depends(require_role("viewer"))):
    """Records grouped by workflow state — kanban board."""
    return mod_engine.board(db, key, pid)


@router.get("/projects/{pid}/modules/{key}/{rid}")
def get_record(pid: str, key: str, rid: str, db: Session = Depends(get_db),
               _: str = Depends(require_role("viewer"))):
    rec = mod_engine.get_record(db, key, pid, rid)
    mod = mod_engine.get_module(key)
    rec["available_actions"] = mod_engine.available_actions(
        mod, rec["workflow_state"], _party(pid, db, _))
    return rec


@router.patch("/projects/{pid}/modules/{key}/{rid}")
def update_record(pid: str, key: str, rid: str, data: dict = Body(...),
                  expected_modified_at: str | None = None,
                  db: Session = Depends(get_db), user: str = Depends(require_role("reviewer"))):
    """Partial-update a record. Pass ?expected_modified_at=<the modified_at you loaded> to opt into the
    optimistic lock: a concurrent edit returns 409 (with the current modified_at) instead of a silent
    overwrite."""
    return mod_engine.update_record(db, key, pid, rid, data, user, _party(pid, db, user),
                                    expected_modified_at=expected_modified_at)


@router.delete("/projects/{pid}/modules/{key}/{rid}")
def delete_record(pid: str, key: str, rid: str, db: Session = Depends(get_db),
                  user: str = Depends(require_role("editor"))):
    """Delete a record (editor+). Removes its activity/comments too."""
    res = mod_engine.delete_record(db, key, pid, rid, user, _party(pid, db, user))
    audit.record(db, action=f"module.delete:{key}", actor=user, method="DELETE",
                 path=f"/projects/{pid}/modules/{key}/{rid}", topic_id=rid, detail={"module": key})
    db.commit()  # engine committed the delete; persist the audit row too (get_db doesn't auto-commit)
    return res


@router.get("/projects/{pid}/modules/{key}/{rid}/related")
def related_records(pid: str, key: str, rid: str, db: Session = Depends(get_db),
                    _: str = Depends(require_role("viewer"))):
    """Outgoing references + incoming records that point at this one."""
    return mod_engine.related_records(db, key, pid, rid)


@router.post("/projects/{pid}/modules/{key}/{rid}/revise", status_code=201)
def revise_record(pid: str, key: str, rid: str, db: Session = Depends(get_db),
                  user: str = Depends(require_role("reviewer"))):
    """Create a tracked revision of a record (revisable modules only); re-opens the workflow."""
    return mod_engine.revise(db, key, pid, rid, user, _party(pid, db, user))


@router.post("/projects/{pid}/modules/{key}/{rid}/transition")
def transition(pid: str, key: str, rid: str, action: str = Body(..., embed=True),
               note: str | None = Body(default=None, embed=True),
               db: Session = Depends(get_db), user: str = Depends(require_role("reviewer"))):
    res = mod_engine.transition(db, key, pid, rid, action, user, _party(pid, db, user), note)
    # workflow transitions are the contractual state changes (RFI answered, CO approved) — audit them.
    # the engine committed the transition; commit the audit row too (get_db doesn't auto-commit).
    audit.record(db, action=f"module.transition:{key}:{action}", actor=user, method="POST",
                 path=f"/projects/{pid}/modules/{key}/{rid}/transition", topic_id=rid,
                 detail={"module": key, "action": action,
                         "state": res.get("workflow_state") if isinstance(res, dict) else None})
    db.commit()
    return res


@router.post("/projects/{pid}/modules/{key}/{rid}/link")
def link_record(pid: str, key: str, rid: str, target: dict = Body(...),
                db: Session = Depends(get_db), user: str = Depends(require_role("reviewer"))):
    return mod_engine.link_record(db, key, pid, rid, target, user, _party(pid, db, user))


@router.post("/projects/{pid}/modules/{key}/{rid}/comments", status_code=201)
def add_comment(pid: str, key: str, rid: str, text: str = Body(..., embed=True),
                db: Session = Depends(get_db), user: str = Depends(require_role("reviewer"))):
    return mod_engine.add_comment(db, key, pid, rid, text, user)


@router.post("/projects/{pid}/modules/{key}/{rid}/assign")
def assign_record(pid: str, key: str, rid: str, assignee: str | None = Body(None, embed=True),
                  db: Session = Depends(get_db), user: str = Depends(require_role("reviewer"))):
    """Set (or clear) the record's assignee — drives the cross-module work queue."""
    return mod_engine.set_assignee(db, key, pid, rid, assignee, user, _party(pid, db, user))


@router.post("/projects/{pid}/modules/{key}/{rid}/elements")
def tag_elements(pid: str, key: str, rid: str, guids: list[str] = Body(..., embed=True),
                 mode: str = Body("add", embed=True), db: Session = Depends(get_db),
                 user: str = Depends(require_role("reviewer"))):
    """Tie model elements (IFC GlobalIds) to a record (mode: add | remove | set). For a schedule
    activity this hard-ties the exact elements it builds, so the 4D scrub is precise (not trade-based)."""
    return mod_engine.set_element_guids(db, key, pid, rid, guids, user, mode)


@router.post("/projects/{pid}/modules/{key}/{rid}/attachments", status_code=201)
async def upload_attachment(pid: str, key: str, rid: str, file: UploadFile = File(...),
                            db: Session = Depends(get_db), user: str = Depends(require_role("reviewer"))):
    """Attach a file to a record (stored in object storage / MinIO)."""
    data = await file.read()
    return mod_engine.add_attachment(db, key, pid, rid, file.filename or "file",
                                     file.content_type, data, user)


@router.post("/projects/{pid}/modules/{key}/{rid}/attachments/bulk", status_code=201)
async def upload_attachments_bulk(pid: str, key: str, rid: str,
                                  files: list[UploadFile] = File(...),
                                  db: Session = Depends(get_db),
                                  user: str = Depends(require_role("reviewer"))):
    """Attach **many** files at once — the field reality (a super dumps a batch of site photos rather
    than uploading them one by one). Each is stored like a single upload; returns all created + a count."""
    out = []
    for f in files:
        data = await f.read()
        out.append(mod_engine.add_attachment(db, key, pid, rid, f.filename or "file",
                                             f.content_type, data, user))
    return {"count": len(out), "attachments": out}


@router.get("/projects/{pid}/modules/{key}/bcf/export")
def export_module_bcf(pid: str, key: str, version: str = Query("2.1", pattern="^(2\\.1|3\\.0)$"),
                      db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Export a module's records as a BCF .bcfzip (coordination issues round-trip with Solibri / ACC /
    BIMcollab). Pinned / element-tied records carry a viewpoint (components + camera). `version` = 2.1
    (default) or 3.0."""
    from .. import bcf_io
    # list_records already returns every column BCF needs (title/ref/workflow_state/assignee/data/
    # anchor/element_guids) — the old per-row get_record was a pure N+1 that also pulled
    # comments/timeline/rollups BCF never uses (~12s on an 8k-issue module). One query now.
    cap = 25_000
    recs = mod_engine.list_records(db, key, pid, limit=cap + 1)
    truncated = len(recs) > cap
    if truncated:
        recs = recs[:cap]
        logging.getLogger("aec.bcf").warning(
            "BCF export of %s truncated to %d records (project %s)", key, cap, pid)
    data = bcf_io.export_records_bcfzip(recs, topic_type="Clash" if key == "coordination_issue" else "Issue",
                                        version=version)
    headers = {"Content-Disposition": f'attachment; filename="{key}.bcfzip"'}
    if truncated:
        headers["X-Truncated"] = f"{cap}"
    return Response(data, media_type="application/octet-stream", headers=headers)


@router.post("/projects/{pid}/modules/{key}/bcf/import", status_code=201)
async def import_module_bcf(pid: str, key: str, file: UploadFile = File(...),
                            db: Session = Depends(get_db), user: str = Depends(require_role("reviewer"))):
    """Import a BCF .bcfzip from another BIM tool as records in this module (each topic → a record,
    carrying its pinned components + camera). Returns the count created."""
    from .. import bcf_io
    parsed = bcf_io.parse_records_bcfzip(await file.read())
    party = _party(pid, db, user)
    created = []
    for p in parsed:
        body = {"data": p["data"], "anchor": p.get("anchor"), "element_guids": p.get("element_guids") or []}
        created.append(mod_engine.create_record(db, key, pid, body, user, party)["id"])
    return {"count": len(created), "ids": created}


# NOTE: distinct path from bim.py's /attachments/{id}/download — that route (registered first) serves
# the `Attachment` table, while module-record attachments live in `RecordAttachment`. Sharing the path
# meant bim.py shadowed this handler and returned 404 for every module-record attachment (broken image
# thumbnails in the portal). `inline` disposition so <img> renders it rather than forcing a download.
@router.get("/module-attachments/{att_id}/download")
def download_attachment(att_id: str, request: Request, db: Session = Depends(get_db),
                        user: str = Depends(current_user)):
    # no `pid` in the path, so gate like bim.py's attachment download (require_role needs a path pid,
    # which is why the old shared route 422'd): current_user + the attachment's own project + a valid
    # signed URL. Works for <img> in open mode and supports short-lived signed URLs under RBAC.
    from .bim import _download_allowed
    att, data = mod_engine.get_attachment(db, att_id)
    if not _download_allowed(request, db, getattr(att, "project_id", None), user):
        raise HTTPException(403, "not a member of this attachment's project")
    # SECURITY: only serve INLINE (renders in the browser on the API origin) for a safe raster-image
    # allowlist — thumbnails are the only inline use case. Everything else (text/html, image/svg+xml
    # with embedded <script>, PDFs, arbitrary blobs) is forced to `attachment` so a malicious upload
    # can't execute JS on the API origin against a lured victim's session (stored-XSS). The declared
    # type is also normalized to octet-stream for the download path so `nosniff` fully applies.
    ctype = (att.content_type or "").split(";")[0].strip().lower()
    inline_ok = ctype in ("image/png", "image/jpeg", "image/gif", "image/webp", "image/bmp")
    disposition = "inline" if inline_ok else "attachment"
    media = ctype if inline_ok else "application/octet-stream"
    # CORP so an <img> can embed the (image-only) inline path cross-origin: the SPA is COEP-isolated
    # (require-corp, for the viewer's SharedArrayBuffer WASM), which otherwise blocks cross-origin
    # image subresources.
    return Response(data, media_type=media,
                    headers={"Content-Disposition": f'{disposition}; filename="{safe_filename(att.filename)}"',
                             "Cross-Origin-Resource-Policy": "cross-origin",
                             "X-Content-Type-Options": "nosniff",
                             "Content-Security-Policy": "sandbox; default-src 'none'"})


@router.get("/projects/{pid}/modules/{key}/{rid}/pdf")
def record_pdf(pid: str, key: str, rid: str, db: Session = Depends(get_db),
               _: str = Depends(require_role("viewer"))):
    import io

    from reportlab.lib.pagesizes import letter
    from reportlab.pdfgen import canvas

    mod = mod_engine.get_module(key)
    r = mod_engine.get_record(db, key, pid, rid)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=letter)
    w, h = letter
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, h - 50, f"{mod['name']} — {r['ref']}")
    c.setFont("Helvetica", 10)
    c.drawString(40, h - 68, f"Status: {r['workflow_state']}    Party: {r['party_owner'] or '-'}    By: {r['created_by'] or '-'}")
    y = h - 100
    for f in mod.get("fields", []):
        v = r["data"].get(f["name"])
        if v in (None, ""):
            continue
        c.setFont("Helvetica-Bold", 10); c.drawString(40, y, f"{f['label']}:")
        c.setFont("Helvetica", 10)
        for i, line in enumerate(str(v)[:600].split("\n")):
            c.drawString(170, y - i * 13, line[:70])
            y -= 13 if i else 0
        y -= 16
        if y < 80:
            c.showPage(); y = h - 60
    if r.get("activity"):
        c.setFont("Helvetica-Bold", 11); c.drawString(40, y - 6, "Activity"); y -= 22
        c.setFont("Helvetica", 9)
        for a in r["activity"]:
            c.drawString(50, y, f"{(a['ts'] or '')[:16]}  {a['actor'] or ''}  {a['action']}")
            y -= 12
            if y < 60:
                c.showPage(); y = h - 60
    c.showPage(); c.save()
    return Response(buf.getvalue(), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{r["ref"]}.pdf"'})


@router.get("/projects/{pid}/module-pins")
def module_pins(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Every anchored GC record across pinnable modules — for the 3D viewer overlay."""
    return mod_engine.project_pins(db, pid)
