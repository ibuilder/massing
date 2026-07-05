"""Built-world technique endpoints (roadmap R): takt/line-of-balance planning (R2), lean PPC
analytics (R4), and research-grade benchmarks (R5)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import benchmarks as bm
from .. import lean
from .. import modules as me
from .. import pull_plan
from .. import takt
from ..db import get_db
from ..models import Project
from ..rbac import current_user, require_role

_P6_KEY = "{pid}/schedule_p6.json"   # imported Primavera P6 activities (drives 4D calendar dates)

router = APIRouter()


class TaktIn(BaseModel):
    floors: int = Field(gt=0)
    trades: list[dict] | None = None
    jit_lead_days: int = 1


@router.post("/schedule/takt")
def schedule_takt(body: TaktIn):
    """Takt / line-of-balance plan — trades flow floor-to-floor at a steady production rate, with a
    just-in-time delivery plan (R2, the Empire State 'vertical assembly line')."""
    return takt.plan(body.floors, body.trades, jit_lead_days=body.jit_lead_days)


@router.get("/schedule/takt.svg")
def schedule_takt_svg(floors: int = 10):
    """Line-of-balance (takt) chart as SVG — floors vs days, one line per trade (R2)."""
    from fastapi import Response
    return Response(takt.takt_svg(takt.plan(max(1, floors))), media_type="image/svg+xml")


@router.get("/benchmarks")
def get_benchmarks():
    """Citable benchmark ranges (cost/sf, cap rates, productivity, lean PPC) for grounding defaults (R5)."""
    return bm.all_benchmarks()


@router.get("/compute/nodes")
def compute_nodes():
    """Node palette for the computational graph — zero-touch nodes over the pure engines (M4)."""
    from .. import compute_graph
    return compute_graph.node_catalog()


@router.post("/compute/graph")
def compute_run(graph: dict):
    """Run a Dynamo/Hypar-style node graph: {nodes, edges} → each node's outputs, in dependency order (M4)."""
    from fastapi import HTTPException

    from .. import compute_graph
    try:
        return compute_graph.run_graph(graph)
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.post("/projects/{pid}/schedule/import-xer", status_code=201)
async def import_xer(pid: str, file: UploadFile = File(...), db: Session = Depends(get_db),
                     actor: str = Depends(require_role("editor"))):
    """Import a Primavera P6 **.xer** export. Parses the TASK table and **upserts each task as an
    editable `schedule_activity` record** (matched to the prior import by P6 activity code), so the
    GC can keep updating, adding, and re-sequencing tasks after import — imported and hand-entered
    activities live in one editable schedule that drives Gantt / Line-of-Balance / CPM / the 4D
    scrub. Re-importing updates the same records (preserving GC edits to others); zero-duration tasks
    are tagged as Milestones. Also keeps the start→finish window for the takt 4D date overlay.
    Returns counts (created/updated) + the date range + a small preview."""
    import json

    from aec_data.schedule import parse_xer  # type: ignore  (data-service engine on sys.path)
    from .. import modules as me, storage

    text = (await file.read()).decode("utf-8", "ignore")
    activities = parse_xer(text)
    if not activities:
        raise HTTPException(422, "no TASK rows found — is this a Primavera P6 .xer export?")
    starts = [a["start"] for a in activities if a.get("start")]
    finishes = [a["finish"] for a in activities if a.get("finish")]

    # prior import's code→record_id index (so re-import updates rather than duplicates)
    prior_index: dict[str, str] = {}
    try:
        prior_index = json.loads(storage.get(_P6_KEY.format(pid=pid))).get("record_ids", {})
    except Exception:                                # noqa: BLE001 — first import / no prior blob
        prior_index = {}

    record_ids: dict[str, str] = {}
    created = updated = 0
    for a in activities:
        code = a.get("activity_id") or ""
        data = {"name": a.get("name") or code or "Activity", "wbs": code,
                "start": a.get("start") or None, "finish": a.get("finish") or None,
                "activity_type": "Milestone" if (a.get("start") and a.get("start") == a.get("finish")) else "Task"}
        rid = prior_index.get(code)
        if rid:
            try:                                     # update the existing imported record (keeps GC edits elsewhere)
                me.update_record(db, "schedule_activity", pid, rid, data, actor, "GC")
                record_ids[code] = rid; updated += 1; continue
            except Exception:                        # noqa: BLE001 — record was deleted → recreate below
                pass
        rec = me.create_record(db, "schedule_activity", pid, {"data": data}, actor, "GC")
        record_ids[code] = rec["id"]; created += 1

    payload = {"activities": activities, "count": len(activities), "record_ids": record_ids,
               "start": min(starts) if starts else None, "finish": max(finishes) if finishes else None}
    storage.put(_P6_KEY.format(pid=pid), json.dumps(payload).encode("utf-8"))
    return {"count": payload["count"], "created": created, "updated": updated,
            "start": payload["start"], "finish": payload["finish"], "preview": activities[:20]}


@router.delete("/projects/{pid}/schedule/import-xer")
def clear_xer(pid: str, db: Session = Depends(get_db), actor: str = Depends(require_role("editor"))):
    """Remove an imported P6 schedule: deletes the activity records this import created (by its
    code→id index) and the date-window blob. Hand-entered activities are untouched."""
    import json

    from .. import modules as me, storage
    removed = 0
    try:
        index = json.loads(storage.get(_P6_KEY.format(pid=pid))).get("record_ids", {})
        for rid in index.values():
            try:
                me.delete_record(db, "schedule_activity", pid, rid, actor, "GC"); removed += 1
            except Exception:                        # noqa: BLE001 — already gone
                pass
    except Exception:                                # noqa: BLE001 — no prior blob
        pass
    storage.delete(_P6_KEY.format(pid=pid))
    return {"cleared": True, "removed_activities": removed}


@router.get("/projects/{pid}/schedule/4d")
def schedule_4d(pid: str, source: str = "auto", db: Session = Depends(get_db),
                _: str = Depends(require_role("viewer"))):
    """4D construction sequence (C3): scrubable timeline frames (cumulative % built per day) over the
    published model's elements.

    Source is **relational by default** (`source=auto`): when the GC **`schedule_activity`** records
    exist they drive the sequence (`source:"gc"`) — each element gets its real calendar finish date
    from the activity that tags its GUID, else from its trade's activities by floor — so the model
    plays the *actual* schedule the team maintains in the portal (the same activities behind the
    Gantt / Line-of-Balance / CPM views). Otherwise it falls back to a takt plan derived from the
    storey count; if a Primavera **P6 .xer** was imported, takt frames carry interpolated calendar
    dates (`source:"p6"`). Force a source with `?source=gc|takt`."""
    import json
    from datetime import date, timedelta

    from .. import fourd, modules as me, storage, takt
    try:
        idx = json.loads(storage.get(f"{pid}/props.json"))
        elements = idx.get("elements", [])
    except Exception:                                # noqa: BLE001 — no published index yet
        elements = []
    floors = max([fourd._floor_index(e.get("storey")) for e in elements] + [0]) + 1

    # relational source: the GC schedule drives the model when activities exist (unless forced off).
    # For `auto`, only use it when the activities can actually sequence the model (have a trade or
    # element tags) — so a bare P6 import without trades keeps the better takt+P6 ordering until the
    # GC assigns trades/elements; `source=gc` forces it regardless.
    if source in ("auto", "gc") and "schedule_activity" in me.TABLES:
        acts = []
        for r in me.list_records(db, "schedule_activity", pid, limit=1_000_000):
            d = dict(r.get("data") or {})
            d["element_guids"] = r.get("element_guids") or []   # generic per-record element tags
            acts.append(d)
        have_dates = any((a.get("finish") or a.get("actual_finish")) for a in acts)
        can_sequence = any(a.get("trade") or a.get("element_guids") for a in acts)
        if have_dates and (source == "gc" or can_sequence):
            return {"floors": floors, **fourd.timeline_from_activities(acts, elements)}
        if source == "gc":                            # explicitly asked for GC but none usable
            return {"floors": floors, "source": "gc", "frames": [], "total_days": 0,
                    "element_count": 0, "by_trade": {}, "linked": 0, "unlinked": 0,
                    "note": "no schedule_activity records with finish dates"}

    plan = takt.plan(floors)
    result = {"floors": floors, "duration_days": plan["duration_days"], "source": "takt",
              **fourd.timeline(plan, elements)}

    # overlay real P6 calendar dates onto the frames when a schedule has been imported
    try:
        p6 = json.loads(storage.get(_P6_KEY.format(pid=pid)))
        d0, d1 = p6.get("start"), p6.get("finish")
        if d0 and d1:
            result.update(source="p6", start_date=d0[:10], finish_date=d1[:10],
                          p6_activities=p6.get("count", 0))
            total = result.get("total_days") or 0
            if total:                                # interpolate a real calendar date per frame
                s = date.fromisoformat(d0[:10]); span = (date.fromisoformat(d1[:10]) - s).days or total
                for fr in result["frames"]:
                    fr["date"] = (s + timedelta(days=round(fr["day"] / total * span))).isoformat()
    except Exception:                                # noqa: BLE001 — no/invalid P6 import → takt dates
        pass
    return result


@router.get("/projects/{pid}/lean/ppc")
def lean_ppc(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Last-Planner Plan Percent Complete + reasons for non-completion from the weekly-plan module (R4)."""
    records = me.list_records(db, "weekly_plan", pid, limit=1_000_000) if "weekly_plan" in me.TABLES else []
    return lean.ppc(records)


@router.get("/projects/{pid}/pull-plan/board")
def pull_plan_board(pid: str, milestone: str | None = None, db: Session = Depends(get_db),
                    _: str = Depends(require_role("viewer"))):
    """The Last Planner phase pull-plan board: trade swimlanes × weeks, the hand-off sequence, the
    make-ready constraint log, and readiness / commitment / PPC. Every stakeholder edits the
    `pull_plan_task` records; pass ?milestone= to focus one phase."""
    return pull_plan.board(db, pid, milestone=milestone)


@router.get("/projects/{pid}/pull-plan/metrics")
def pull_plan_metrics(pid: str, milestone: str | None = None, db: Session = Depends(get_db),
                      _: str = Depends(require_role("viewer"))):
    """Last Planner reliability metrics beyond PPC: Tasks-Made-Ready %, make-ready runway,
    perfect-handoff %, PPC trend by week, and the variance-reason Pareto — the learning-loop signals
    a pull-planning team improves week over week."""
    return pull_plan.metrics(db, pid, milestone=milestone)


@router.get("/projects/{pid}/pull-plan/stream")
async def pull_plan_stream(pid: str, request: Request, _: str = Depends(current_user)):
    """Server-sent events for the collaborative pull board: polls a cheap board signature (row count +
    latest modified_at) server-side every few seconds and pushes it when it changes, so every trade's
    board live-refreshes the moment anyone edits a sticky note. Uses a fresh DB session per poll since
    the generator outlives the request scope (mirrors the notifications stream)."""
    import asyncio
    import json as _json

    from fastapi.responses import StreamingResponse

    from ..db import SessionLocal

    async def gen():
        last = None
        while not await request.is_disconnected():
            with SessionLocal() as db:
                sig = pull_plan.signature(db, pid)
            key = (sig["count"], sig["latest"])
            if key != last:
                last = key
                yield f"data: {_json.dumps(sig)}\n\n"
            await asyncio.sleep(4)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/projects/{pid}/pull-plan/board.pdf")
def pull_plan_pdf(pid: str, milestone: str | None = None, db: Session = Depends(get_db),
                  _: str = Depends(require_role("viewer"))):
    """The pull-plan board as a printable PDF (trade × week matrix + constraint log + PPC)."""
    from fastapi import Response
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    data = pull_plan.pdf(db, pid, p.name or pid, milestone=milestone)
    return Response(content=data, media_type="application/pdf", headers={
        "Content-Disposition": 'attachment; filename="pull-plan.pdf"'})
