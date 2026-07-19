"""Built-world technique endpoints (roadmap R): takt/line-of-balance planning (R2), lean PPC
analytics (R4), and research-grade benchmarks (R5)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from .. import benchmarks as bm
from .. import lean, pull_plan, takt
from .. import modules as me
from ..db import get_db
from ..models import Project
from ..rbac import require_role

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
    return Response(takt.takt_svg(takt.plan(max(1, floors))), media_type="image/svg+xml")


class TaktProgressIn(BaseModel):
    floors: int = Field(gt=0)
    trades: list[dict] | None = None
    jit_lead_days: int = 1
    actuals: list[dict] = Field(default_factory=list)   # [{trade, floors_done, as_of_day?}]
    as_of_day: int | None = None


@router.post("/schedule/takt/progress")
def schedule_takt_progress(body: TaktProgressIn):
    """Actual-vs-takt tracking (R2/R4): compare each trade's actual floors complete against the
    line-of-balance plan → floor variance (+ahead/−behind), achieved production rate (floors/week),
    and an on/ahead/behind read. `actuals` = [{trade, floors_done, as_of_day?}, …]."""
    plan = takt.plan(body.floors, body.trades, jit_lead_days=body.jit_lead_days)
    return {"plan": plan, "progress": takt.progress(plan, body.actuals, body.as_of_day)}


def _takt_actuals_from_activities(acts: list[dict], floors: int) -> tuple[list[dict], int]:
    """Roll GC `schedule_activity` records up into per-trade actual floors-complete + an as-of day.
    A floor counts as done for a trade when its activity is 100% complete or carries an actual finish.
    `as_of_day` is the elapsed span from the earliest activity start to the latest actual finish, so
    the actual-vs-takt read is grounded in the schedule's own dates (no wall-clock dependency)."""
    from datetime import date

    def _d(v):
        try:
            return date.fromisoformat(str(v)[:10])
        except Exception:                            # noqa: BLE001 — missing/blank date
            return None

    done: dict[str, int] = {}
    starts: list[date] = []
    fins: list[date] = []
    for a in acts:
        trade = a.get("trade")
        if not trade:
            continue
        s = _d(a.get("start") or a.get("actual_start"))
        if s:
            starts.append(s)
        pct = a.get("percent_complete")
        af = _d(a.get("actual_finish"))
        complete = (pct is not None and float(pct) >= 100) or af is not None
        if complete:
            done[trade] = done.get(trade, 0) + 1
            if af:
                fins.append(af)
    as_of = (max(fins) - min(starts)).days if (starts and fins) else 0
    actuals = [{"trade": t, "floors_done": min(floors, n), "as_of_day": max(0, as_of)}
               for t, n in done.items()]
    return actuals, max(0, as_of)


@router.get("/projects/{pid}/schedule/takt/progress")
def project_takt_progress(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Project actual-vs-takt: derive per-trade floors-complete from the GC `schedule_activity`
    records and compare to the takt plan sized from the model's storey count. Also returns PPC so a
    dashboard card can show plan health + Last-Planner reliability together (R2/R4)."""
    import json

    from .. import storage
    try:
        idx = json.loads(storage.get(f"{pid}/props.json"))
        from .. import fourd
        floors = max([fourd._floor_index(e.get("storey")) for e in idx.get("elements", [])] + [0]) + 1
    except Exception:                                # noqa: BLE001 — no published index yet
        floors = 1
    acts = [dict(r.get("data") or {}) for r in me.list_records(db, "schedule_activity", pid, limit=1_000_000)] \
        if "schedule_activity" in me.TABLES else []
    actuals, as_of = _takt_actuals_from_activities(acts, floors)
    plan = takt.plan(floors)
    prog = takt.progress(plan, actuals, as_of)
    ppc_records = me.list_records(db, "weekly_plan", pid, limit=1_000_000) if "weekly_plan" in me.TABLES else []
    return {"floors": floors, "plan": plan, "progress": prog, "ppc": lean.ppc(ppc_records)}


@router.get("/projects/{pid}/schedule/takt.svg")
def project_takt_svg(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Line-of-balance chart for the project with the **actual ascent overlaid** (dashed) on the plan."""
    import json

    from .. import storage
    try:
        idx = json.loads(storage.get(f"{pid}/props.json"))
        from .. import fourd
        floors = max([fourd._floor_index(e.get("storey")) for e in idx.get("elements", [])] + [0]) + 1
    except Exception:                                # noqa: BLE001
        floors = 1
    acts = [dict(r.get("data") or {}) for r in me.list_records(db, "schedule_activity", pid, limit=1_000_000)] \
        if "schedule_activity" in me.TABLES else []
    actuals, as_of = _takt_actuals_from_activities(acts, floors)
    plan = takt.plan(floors)
    overlay = takt.progress(plan, actuals, as_of)["overlay"]
    return Response(takt.takt_svg(plan, overlay), media_type="image/svg+xml")


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
    """Import a Primavera P6 export — **.xer** (tab-delimited) or **.xml (PMXML)**, auto-detected from
    the content. Parses the tasks/activities and **upserts each as an
    editable `schedule_activity` record** (matched to the prior import by P6 activity code), so the
    GC can keep updating, adding, and re-sequencing tasks after import — imported and hand-entered
    activities live in one editable schedule that drives Gantt / Line-of-Balance / CPM / the 4D
    scrub. Re-importing updates the same records (preserving GC edits to others); zero-duration tasks
    are tagged as Milestones. Also keeps the start→finish window for the takt 4D date overlay.
    Returns counts (created/updated) + the date range + a small preview."""
    import json

    from aec_data.schedule import parse_schedule  # type: ignore  (data-service engine on sys.path)

    from .. import modules as me
    from .. import storage

    text = (await file.read()).decode("utf-8", "ignore")
    activities = parse_schedule(text)            # auto-detects XER (tab-delimited) or PMXML (XML)
    if not activities:
        raise HTTPException(422, "no activities found — is this a Primavera P6 .xer or .xml export?")
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

    from .. import modules as me
    from .. import storage
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


def _schedule_activities(db: Session, pid: str) -> list[dict]:
    """The project's LIVE schedule as export-ready activity dicts — every `schedule_activity` record
    (imported *and* hand-entered, with the GC's edits), keyed by its P6 activity code (`wbs`). This is
    what makes the round-trip real: edits made in the web app flow back out to the scheduler's tool."""
    out = []
    for r in me.list_records(db, "schedule_activity", pid, limit=100000):
        d = r.get("data") or {}
        out.append({"activity_id": d.get("wbs") or r.get("ref") or "",
                    "name": d.get("name") or r.get("title") or "", "start": d.get("start") or "",
                    "finish": d.get("finish") or "", "activity_type": d.get("activity_type") or "Task",
                    "percent": d.get("percent") or 0})
    return out


@router.get("/projects/{pid}/schedule/export")
def export_schedule(pid: str, fmt: str = Query("xer", pattern="^(xer|msp)$"),
                    db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """SCHED-P6 — export the live schedule for **round-trip** into a scheduler's tool. `fmt=xer` →
    Primavera P6 **.xer**; `fmt=msp` → **MS-Project XML (MSPDI)**. Both carry the P6 activity code
    (task_code / `<WBS>`), so re-importing a scheduler's updated file matches the same records by code
    — the GC's web edits go out, the scheduler's updates come back, no GUID drift. Reflects the current
    edited state of every `schedule_activity` (imported + hand-entered), not the frozen import."""
    from aec_data.schedule import to_mspdi, to_xer  # type: ignore  (data-service engine on sys.path)

    activities = _schedule_activities(db, pid)
    if not activities:
        raise HTTPException(404, "no schedule activities to export — import a P6 file or add activities first")
    project = db.get(Project, pid)
    pname = (project.name if project else None) or "Schedule"
    if fmt == "msp":
        body = to_mspdi(activities, pname)
        return Response(body, media_type="application/xml",
                        headers={"Content-Disposition": 'attachment; filename="schedule.xml"'})
    body = to_xer(activities, pname)
    return Response(body, media_type="application/octet-stream",
                    headers={"Content-Disposition": 'attachment; filename="schedule.xer"'})


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

    from .. import fourd, storage, takt
    from .. import modules as me
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
async def pull_plan_stream(pid: str, request: Request, _: str = Depends(require_role("viewer"))):
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
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    data = pull_plan.pdf(db, pid, p.name or pid, milestone=milestone)
    return Response(content=data, media_type="application/pdf", headers={
        "Content-Disposition": 'attachment; filename="pull-plan.pdf"'})
