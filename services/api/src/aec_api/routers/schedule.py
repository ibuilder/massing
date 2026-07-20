"""Schedule visual + planning endpoints (GC portal): Gantt + Line-of-Balance SVG, CPM, and the
short-interval **lookahead** + **milestone** schedules the field and PM run from."""
from __future__ import annotations

from datetime import date, datetime, timedelta

from fastapi import APIRouter, Body, Depends, Response
from sqlalchemy.orm import Session

from .. import modules as me
from .. import schedule_cpm, schedule_viz, storage
from ..db import get_db
from ..rbac import require_role

router = APIRouter()

_BASELINE_KEY = "{pid}/schedule_baseline.json"


def _svg(s: str) -> Response:
    return Response(s.encode("utf-8"), media_type="image/svg+xml")


def _d(v) -> date | None:
    if not v:
        return None
    try:
        return datetime.fromisoformat(str(v)[:10]).date()
    except ValueError:
        return None


def _activity_status(start: date | None, finish: date | None, pct: float, today: date) -> str:
    """Field status of an activity from its dates + % complete."""
    if pct >= 100:
        return "complete"
    if finish and finish < today:
        return "late"                                # past its finish but not done
    if start and start <= today:
        return "in_progress"
    return "not_started"


@router.post("/projects/{pid}/schedule/from-estimate")
def schedule_from_estimate(pid: str, body: dict = Body(default={}), db: Session = Depends(get_db),
                           actor: str = Depends(require_role("editor"))):
    """EST-1 (the CPM half): write the QTO-driven labour estimate's **crew-day durations into the
    schedule** — one `schedule_activity` per trade group (WBS `EST`, chained FS in trade order), so
    CPM / Gantt / lookahead immediately reflect the model-derived durations. Re-running **upserts**
    the same EST activities (durations refresh, no duplicates; manual activities untouched).
    Body: `{loading?, rate?, crews?, work_week?}`."""
    import math

    from fastapi import HTTPException

    from aec_data import productivity  # type: ignore
    from aec_data.qto import takeoff_file  # type: ignore

    from ..models import Project

    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    if not p.source_ifc:
        raise HTTPException(409, "no source IFC — the estimate needs a model")
    est = productivity.from_takeoff(
        takeoff_file(p.source_ifc, force_geometry=True),
        float(body.get("rate") or 25.0), str(body.get("loading") or "commercial"),
        crews_parallel=max(1, int(body.get("crews") or 1)))
    groups = (est.get("schedule") or {}).get("by_group") or []
    if not groups:
        raise HTTPException(409, "the takeoff produced no schedulable quantities")

    # upsert one EST activity per trade group, chained sequentially (the estimate's conservative path)
    existing = {((r.get("data") or {}).get("trade") or ""): r
                for r in me.list_records(db, "schedule_activity", pid, limit=1_000_000)
                if (r.get("data") or {}).get("wbs") == "EST"}
    written, prev_ref = [], None
    for g in groups:
        dur = max(1, math.ceil(float(g["duration_days"])))
        data = {"name": f"{g['group']} (from model QTO)", "wbs": "EST", "trade": g["group"],
                "duration": dur, "predecessors": prev_ref or "",
                "activity_type": "task"}
        old = existing.get(g["group"])
        if old:
            me.update_record(db, "schedule_activity", pid, old["id"], data, actor=actor, party=None)
            ref = old.get("ref")
        else:
            rec = me.create_record(db, "schedule_activity", pid, {"data": data}, actor=actor, party=None)
            ref = rec["ref"]
        prev_ref = ref
        written.append({"ref": ref, "trade": g["group"], "crew_days": g["crew_days"],
                        "duration_days": dur, "updated": bool(old)})
    cpm_out = schedule_cpm.compute(me.list_records(db, "schedule_activity", pid, limit=1_000_000))
    return {"written": written, "activities": len(written),
            "estimate_total_cost": est.get("total_labor_cost") or est.get("total_cost"),
            "duration_working_days": (est.get("schedule") or {}).get("duration_working_days"),
            "cpm_project_duration": cpm_out.get("project_duration"),
            "note": "EST activities (WBS 'EST') upserted from the QTO-driven labour estimate — "
                    "sequential trade chain; refine predecessors/overlap in the schedule module."}


@router.get("/projects/{pid}/schedule/cpm")
def cpm(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Critical Path Method analysis of the schedule_activity records — early/late dates, total +
    free float, and the critical path (FS dependencies via each activity's `predecessors`)."""
    acts = me.list_records(db, "schedule_activity", pid, limit=1_000_000)
    return schedule_cpm.compute(acts)


@router.post("/projects/{pid}/schedule/optioneer")
def schedule_optioneer(pid: str, body: dict = Body(default={}), db: Session = Depends(get_db),
                       _: str = Depends(require_role("viewer"))):
    """SCHED-OPT (SPRINT B) — deterministic **schedule optioneering** over the Takt line-of-balance model:
    permute crew loading (a 2nd crew on the bottleneck trades) and work-face zoning across a bounded grid,
    score every scenario on makespan / cost / peak-congestion, and return the ranked list with the Pareto
    frontier + a recommended option.

    Body (all optional): `floors`, `trades:[{name,takt_days}]`, `crew_day_rate`, `max_crew_trades`,
    `zone_options:[…]`, `weight_time`, `weight_cost`. Absent `trades` default to the residential takt
    train; absent `floors` are derived from the model's storey count (else 1)."""
    from .. import schedule_options, takt
    from ..models import Project

    floors = body.get("floors")
    if not floors:                                       # derive from the model's storeys, best-effort
        p = db.get(Project, pid)
        if p and p.source_ifc:
            try:
                from ..deps import open_source_ifc
                floors = len(open_source_ifc(db, pid).by_type("IfcBuildingStorey")) or 1
            except Exception:                            # noqa: BLE001 — no/opaque model: fall back to 1
                floors = 1
    base = {
        "floors": int(floors or 1),
        "trades": body.get("trades") or takt.DEFAULT_TRADES,
        "crew_day_rate": body.get("crew_day_rate"),
    }
    kw = {}
    for k in ("max_crew_trades", "weight_time", "weight_cost"):
        if body.get(k) is not None:
            kw[k] = body[k]
    if body.get("zone_options"):
        kw["zone_options"] = tuple(int(z) for z in body["zone_options"])
    return schedule_options.optimize(base, **kw)


@router.get("/projects/{pid}/risk-board")
def risk_board_endpoint(pid: str, db: Session = Depends(get_db),
                        _: str = Depends(require_role("viewer"))):
    """RISK-BOARD — one ranked register unifying every computed risk signal: Monte-Carlo schedule
    risk (P80 buffer + top delay driver) · predictive schedule alerts · EVM cost/schedule indices ·
    pre-flight issuance blockers · overdue coordination issues. Each item deep-links to the engine
    that computed it; a broken lane drops out (reported in `lanes`), never the board."""
    from .. import risk_board
    return risk_board.board(db, pid)


@router.get("/projects/{pid}/schedule/risk")
def schedule_risk_endpoint(pid: str, iterations: int = 1000, seed: int | None = None,
                           ppc: float | None = None,
                           db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """SCHED-RISK: Monte Carlo over the CPM network — P10/P50/P80/P90 completion, per-activity
    criticality index, delay-driver ranking, and the P80 buffer vs the deterministic date.
    `ppc` overrides the calibration; by default the team's own pull-plan PPC (when it exists)
    calibrates the pessimistic tail — an unreliable plan honestly slips more."""
    from .. import schedule_risk
    acts = me.list_records(db, "schedule_activity", pid, limit=1_000_000)
    ppc_val = ppc
    if ppc_val is None:
        try:                                         # the team's own Last Planner reliability
            from .. import pull_plan
            board = pull_plan.board(db, pid)
            ppc_val = (board.get("metrics") or {}).get("ppc_pct")
        except Exception:  # noqa: BLE001 — no pull-plan data → uncalibrated defaults
            ppc_val = None
    return schedule_risk.simulate(acts, iterations=iterations, seed=seed, ppc_pct=ppc_val)


@router.get("/projects/{pid}/schedule/resource-loading")
def resource_loading_endpoint(pid: str, cap: float | None = None, db: Session = Depends(get_db),
                              _: str = Depends(require_role("viewer"))):
    """Resource-loaded schedule — weekly resource histogram (by trade/type), cumulative units + **cost**
    S-curves, peak, and (against an optional ?cap= availability) over-allocation flags. Prefers
    `resource_assignment` records (activity + cost code + units + rate); falls back to activity crew_size."""
    from .. import resource_loading
    return resource_loading.loading(db, pid, cap)


@router.post("/projects/{pid}/schedule/resource-leveling/apply")
def resource_leveling_apply(pid: str, cap: float = Body(..., embed=True),
                            db: Session = Depends(get_db), user: str = Depends(require_role("editor"))):
    """RESOURCE-LEVEL-2 — APPLY one leveling round: shift over-allocated activities forward within
    their CPM float (week-granular, most-float-first, finish never moves). Mutates the schedule —
    the UI gates this behind an explicit confirm. Returns moves + before/after peak."""
    from .. import audit, resource_loading
    res = resource_loading.apply_level(db, pid, cap, actor=user)
    audit.record(db, action="schedule.level_apply", actor=user, method="POST",
                 path=f"/projects/{pid}/schedule/resource-leveling/apply",
                 detail={"cap": cap, "moved": res["moved"]})
    db.commit()
    return res


@router.get("/projects/{pid}/schedule/resource-leveling")
def resource_leveling_endpoint(pid: str, cap: float, db: Session = Depends(get_db),
                               _: str = Depends(require_role("viewer"))):
    """Resource-leveling advisory against a `cap` availability: over-allocated work that still has CPM
    total float can be **smoothed** (shifted within float) to shave the peak without moving the finish.
    Advisory only — never mutates the schedule."""
    from .. import resource_loading
    return resource_loading.level(db, pid, cap)


@router.get("/projects/{pid}/productivity/summary")
def productivity_summary(pid: str, db: Session = Depends(get_db),
                         _: str = Depends(require_role("viewer"))):
    """Field labor productivity — units installed per man-hour per entry, rolled up by trade."""
    from .. import productivity
    return productivity.summary(db, pid)


@router.get("/projects/{pid}/cv-progress/status")
def cv_progress_status(pid: str, _: str = Depends(require_role("viewer"))):
    """Status of the (external, feature-flagged) computer-vision site-progress bridge."""
    from .. import cv_bridge
    return cv_bridge.status()


def _resolve_activity(db: Session, pid: str, key: str) -> str | None:
    """Resolve a schedule_activity reference — an id, or a name matched case-insensitively — to its id.
    Lets a CV service that only knows human task labels ('Frame L2') address activities by name. The
    name lookup is a single id-only SQL probe (find_id_by_field), not a per-estimate table scan."""
    if not key:
        return None
    try:
        me.get_record(db, "schedule_activity", pid, key)
        return key                                          # already a valid id
    except Exception:                                       # noqa: BLE001 — not an id; try name
        return me.find_id_by_field(db, "schedule_activity", pid, "name", key)


def _apply_estimate(db: Session, pid: str, activity_key: str, percent: float, actor: str) -> dict:
    """Write a validated CV estimate to the resolved activity's percent. Never raises."""
    rid = _resolve_activity(db, pid, activity_key)
    if not rid:
        return {"applied": False, "apply_error": f"no schedule_activity matched {activity_key!r}"}
    try:
        me.update_record(db, "schedule_activity", pid, rid, {"percent": percent}, actor, None)
        return {"applied": True, "activity_id": rid}
    except Exception as e:                                  # noqa: BLE001 — write error shouldn't 500 the bridge
        return {"applied": False, "apply_error": str(e)[:120]}


@router.post("/projects/{pid}/cv-progress/ingest")
def cv_progress_ingest(pid: str, payload: dict = Body(default={}),
                       db: Session = Depends(get_db), actor: str = Depends(require_role("editor"))):
    """Accept one external CV progress estimate (no-op unless AEC_CV_BRIDGE is enabled). When enabled,
    `activity` (a schedule_activity id or name) is resolved and the estimate written to its percent."""
    from .. import cv_bridge
    res = cv_bridge.ingest(payload)
    if res.get("accepted") and payload.get("activity"):
        res.update(_apply_estimate(db, pid, payload["activity"], res["percent"], actor))
    return res


@router.post("/projects/{pid}/cv-progress/ingest-batch")
def cv_progress_ingest_batch(pid: str, payload: dict = Body(default={}),
                             db: Session = Depends(get_db), actor: str = Depends(require_role("editor"))):
    """Accept a batch of CV progress estimates — `{"estimates": [{activity, percent}, …]}` — the shape a
    vision service produces per photo sweep. Each valid item is written to its activity; returns per-item
    outcomes + a summary. No-op unless AEC_CV_BRIDGE is enabled."""
    from .. import cv_bridge
    res = cv_bridge.ingest_batch(payload.get("estimates", []))
    if not res.get("accepted"):
        return res
    applied = 0
    for item in res["items"]:
        if item["ok"] and item["activity"]:
            outcome = _apply_estimate(db, pid, item["activity"], item["percent"], actor)
            item.update(outcome)
            applied += 1 if outcome.get("applied") else 0
        elif item["ok"]:
            item["applied"] = False
            item["apply_error"] = "no activity given"
    res["applied"] = applied
    return res


@router.get("/projects/{pid}/schedule/alerts")
def schedule_alerts(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Predictive schedule alerts — overdue work, late/at-risk starts (incomplete predecessor),
    behind-schedule SPI, and a procurement-risk proxy — from the cost-loaded schedule + CPM."""
    from .. import px
    return px.alerts(db, pid)


@router.get("/projects/{pid}/schedule/make-ready")
def schedule_make_ready(pid: str, days: int = 14, db: Session = Depends(get_db),
                        _: str = Depends(require_role("viewer"))):
    """READY-AGENT — every activity starting within `days`, its preconditions checked with **cited
    evidence** (incomplete predecessors by ref + % complete · open submittals by ref/state) and a
    ready/blocked verdict — 'can next week's work actually start?', answered proactively."""
    from .. import px
    return px.make_ready(db, pid, days=days)


@router.get("/projects/{pid}/schedule/optimize")
def schedule_optimize(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Schedule-acceleration ADVISORY off the CPM critical path — crash candidates (longest critical
    activities), fast-track candidates (consecutive critical activities to overlap), and near-critical
    watch. Rule-based + an optional AI narrative; it never rewrites the schedule."""
    from .. import px
    return px.optimize(db, pid)


@router.get("/projects/{pid}/schedule/gantt.svg")
def gantt(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    return _svg(schedule_viz.gantt_svg(db, pid))


@router.get("/projects/{pid}/schedule/lob.svg")
def lob(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    return _svg(schedule_viz.lob_svg(db, pid))


@router.get("/projects/{pid}/schedule/lookahead")
def lookahead(pid: str, weeks: int = 3, start: str | None = None, db: Session = Depends(get_db),
              _: str = Depends(require_role("viewer"))):
    """Short-interval **lookahead** (the field's 3- / 6-week plan): activities active in the window
    [`start`, `start`+`weeks`), grouped by ISO week. An activity is in-window if it overlaps it
    (starts before the end and finishes on/after the start). Each carries trade, %-complete, and a
    field status (not_started / in_progress / late / complete). Defaults to a 3-week window today."""
    weeks = max(1, min(12, weeks))
    d0 = _d(start) or date.today()
    d1 = d0 + timedelta(weeks=weeks)
    rows = me.list_records(db, "schedule_activity", pid, limit=1_000_000)
    buckets: dict[str, list] = {}
    for r in rows:
        data = r.get("data") or {}
        s, f = _d(data.get("start")) or _d(data.get("actual_start")), _d(data.get("finish")) or _d(data.get("actual_finish"))
        if not (s or f):
            continue
        s = s or f; f = f or s
        if s >= d1 or f < d0:                         # no overlap with the window
            continue
        pct = float(data.get("percent") or 0)
        wk = (max(s, d0) - d0).days // 7             # 0-based week index within the window
        label = f"Week {wk + 1} ({(d0 + timedelta(weeks=wk)).isoformat()})"
        buckets.setdefault(label, []).append({
            "ref": r.get("ref"), "name": r.get("title") or data.get("name"),
            "trade": data.get("trade"), "start": data.get("start"), "finish": data.get("finish"),
            "percent": pct, "status": _activity_status(s, f, pct, date.today())})
    for v in buckets.values():
        v.sort(key=lambda a: (a["start"] or "", a["name"] or ""))
    total = sum(len(v) for v in buckets.values())
    return {"start": d0.isoformat(), "finish": d1.isoformat(), "weeks": weeks,
            "count": total, "weeks_detail": [{"week": k, "activities": buckets[k]} for k in sorted(buckets)]}


@router.post("/projects/{pid}/schedule/baseline", status_code=201)
def set_baseline(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("editor"))):
    """Snapshot the current schedule as the **baseline** (each activity's planned start/finish + budget,
    keyed by id). Variance is then measured against this — re-run to re-baseline after an approved
    change. One baseline per project."""
    import json

    snap = {}
    for r in me.list_records(db, "schedule_activity", pid, limit=1_000_000):
        data = r.get("data") or {}
        snap[r["id"]] = {"ref": r.get("ref"), "name": r.get("title") or data.get("name"),
                         "start": data.get("start"), "finish": data.get("finish"),
                         "budget": data.get("budget")}
    payload = {"captured_at": date.today().isoformat(), "count": len(snap), "activities": snap}
    storage.put(_BASELINE_KEY.format(pid=pid), json.dumps(payload).encode("utf-8"))
    return {"captured_at": payload["captured_at"], "count": payload["count"]}


@router.delete("/projects/{pid}/schedule/baseline")
def clear_baseline(pid: str, _: str = Depends(require_role("editor"))):
    """Remove the schedule baseline."""
    storage.delete(_BASELINE_KEY.format(pid=pid))
    return {"cleared": True}


@router.get("/projects/{pid}/schedule/variance")
def variance(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Per-activity slip vs the baseline: **finish_var**/start_var in days (positive = later than
    baseline = slipped), plus added/removed activities. Surfaces how far the job has drifted from
    the plan of record. 409 if no baseline has been set."""
    import json

    try:
        base = json.loads(storage.get(_BASELINE_KEY.format(pid=pid)))
    except Exception:                                # noqa: BLE001
        from fastapi import HTTPException
        raise HTTPException(409, "no baseline set — POST /schedule/baseline first")
    base_acts = base.get("activities", {})
    current = {r["id"]: r for r in me.list_records(db, "schedule_activity", pid, limit=1_000_000)}
    lines = []
    for rid, b in base_acts.items():
        cur = current.get(rid)
        if not cur:
            lines.append({"ref": b.get("ref"), "name": b.get("name"), "status": "removed",
                          "start_var": None, "finish_var": None}); continue
        data = cur.get("data") or {}
        bs, bf = _d(b.get("start")), _d(b.get("finish"))
        cs, cf = _d(data.get("start")), _d(data.get("finish"))
        sv = (cs - bs).days if (cs and bs) else None
        fv = (cf - bf).days if (cf and bf) else None
        lines.append({"ref": cur.get("ref"), "name": cur.get("title") or data.get("name"),
                      "start_var": sv, "finish_var": fv,
                      "status": "slipped" if (fv or 0) > 0 else "improved" if (fv or 0) < 0 else "on_baseline"})
    for rid, cur in current.items():
        if rid not in base_acts:
            data = cur.get("data") or {}
            lines.append({"ref": cur.get("ref"), "name": cur.get("title") or data.get("name"),
                          "status": "added", "start_var": None, "finish_var": None})
    slips = [x["finish_var"] for x in lines if x["finish_var"] is not None]
    summary = {"slipped": sum(1 for x in lines if x["status"] == "slipped"),
               "improved": sum(1 for x in lines if x["status"] == "improved"),
               "on_baseline": sum(1 for x in lines if x["status"] == "on_baseline"),
               "added": sum(1 for x in lines if x["status"] == "added"),
               "removed": sum(1 for x in lines if x["status"] == "removed"),
               "max_slip_days": max(slips) if slips else 0,
               "avg_finish_var": round(sum(slips) / len(slips), 1) if slips else 0}
    lines.sort(key=lambda x: (x["finish_var"] is None, -(x["finish_var"] or 0)))   # biggest slip first
    return {"captured_at": base.get("captured_at"), "baseline_count": len(base_acts),
            "summary": summary, "activities": lines}


# --- RESOURCE-LEVEL: multiple NAMED baselines (a library, vs the single legacy baseline above) -------
@router.get("/projects/{pid}/schedule/baselines")
def list_baselines(pid: str, _: str = Depends(require_role("viewer"))):
    """The project's named-baseline library (metadata only), newest first."""
    from .. import schedule_baselines
    return {"baselines": schedule_baselines.list_metas(pid)}


@router.post("/projects/{pid}/schedule/baselines", status_code=201)
def capture_baseline(pid: str, name: str = Body("", embed=True),
                     db: Session = Depends(get_db), _: str = Depends(require_role("editor"))):
    """Snapshot the current schedule as a new NAMED baseline (e.g. "GMP", "Recovery"). Unlike the
    singular baseline, several coexist so drift can be tracked against each."""
    from .. import schedule_baselines
    return schedule_baselines.capture(db, pid, name)


@router.delete("/projects/{pid}/schedule/baselines/{bid}")
def delete_baseline(pid: str, bid: str, _: str = Depends(require_role("editor"))):
    """Remove a named baseline from the library."""
    from fastapi import HTTPException

    from .. import schedule_baselines
    if not schedule_baselines.delete(pid, bid):
        raise HTTPException(404, "baseline not found")
    return {"deleted": True}


@router.get("/projects/{pid}/schedule/baselines/{bid}/variance")
def named_baseline_variance(pid: str, bid: str, db: Session = Depends(get_db),
                            _: str = Depends(require_role("viewer"))):
    """Per-activity slip of the live schedule vs a chosen NAMED baseline (`bid`, or `latest`)."""
    from fastapi import HTTPException

    from .. import schedule_baselines
    res = schedule_baselines.variance(db, pid, None if bid == "latest" else bid)
    if res is None:
        raise HTTPException(404, "named baseline not found — capture one with POST /schedule/baselines")
    return res


@router.get("/projects/{pid}/schedule/earned-value")
def earned_value(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Schedule **earned value** over the activities that carry a budgeted cost. For each:
    BAC = Σ budget; **EV (BCWP)** = Σ %·budget (work earned); **PV (BCWS)** = Σ planned-fraction·budget
    (where today sits in [start, finish]). **SPI** = EV/PV and the schedule variance **SV** = EV−PV
    tell you, in dollars, whether the job is ahead of or behind plan. AC/CPI need cost actuals and are
    left to the cost engine."""
    today = date.today()
    rows = me.list_records(db, "schedule_activity", pid, limit=1_000_000)
    bac = ev = pv = 0.0
    lines = []
    for r in rows:
        data = r.get("data") or {}
        budget = float(data.get("budget") or 0)
        if budget <= 0:
            continue
        pct = max(0.0, min(100.0, float(data.get("percent") or 0))) / 100.0
        s, f = _d(data.get("start")) or _d(data.get("actual_start")), _d(data.get("finish")) or _d(data.get("actual_finish"))
        if s and f and f > s:
            planned = max(0.0, min(1.0, (today - s).days / (f - s).days))
        elif f:
            planned = 1.0 if today >= f else 0.0
        else:
            planned = 0.0
        a_ev, a_pv = pct * budget, planned * budget
        bac += budget; ev += a_ev; pv += a_pv
        lines.append({"ref": r.get("ref"), "name": r.get("title") or data.get("name"),
                      "budget": round(budget, 2), "percent": round(pct * 100, 1),
                      "ev": round(a_ev, 2), "pv": round(a_pv, 2), "sv": round(a_ev - a_pv, 2)})
    spi = round(ev / pv, 3) if pv else None
    status = "no_data" if not lines else (
        "ahead" if spi and spi > 1.05 else "behind" if spi and spi < 0.95 else "on_track")
    lines.sort(key=lambda x: x["sv"])               # worst schedule variance first
    return {"bac": round(bac, 2), "ev": round(ev, 2), "pv": round(pv, 2),
            "sv": round(ev - pv, 2), "spi": spi, "percent_complete": round(ev / bac * 100, 1) if bac else 0.0,
            "status": status, "activity_count": len(lines), "activities": lines}


@router.get("/projects/{pid}/evm")
def evm_snapshot(pid: str, data_date: str | None = None, db: Session = Depends(get_db),
                 _: str = Depends(require_role("viewer"))):
    """Full Earned Value Management snapshot (ANSI/EIA-748-aligned): joins schedule earned value with
    cost actuals **by cost code (control account)**. Returns PV/EV/AC/BAC, CV/SV/CPI/SPI with health
    bands, the EAC/ETC/VAC/TCPI **forecast family**, a per-control-account table, and per-activity EV.
    `data_date` (YYYY-MM-DD) sets the reporting cut-off; defaults to today."""
    from .. import evm
    return evm.snapshot(db, pid, data_date)


@router.get("/projects/{pid}/evm/earned-schedule")
def evm_earned_schedule(pid: str, period: str = "week", db: Session = Depends(get_db),
                        _: str = Depends(require_role("viewer"))):
    """**Earned Schedule** (time-based EVM): ES, SV(t), SPI(t), IEAC(t) → forecast finish, in `week` or
    `month` periods, plus the PV baseline curve. Stays meaningful at completion, unlike dollar SPI."""
    from .. import evm
    es = evm.earned_schedule(db, pid, date.today(), period if period in ("week", "month") else "week")
    return es or {"note": "No dated, budgeted activities to compute Earned Schedule."}


@router.get("/projects/{pid}/evm/scurve")
def evm_scurve(pid: str, period: str = "week", db: Session = Depends(get_db),
               _: str = Depends(require_role("viewer"))):
    """The EVM **S-curve**: cumulative PV (full baseline) + EV + AC to the data date, over week/month
    buckets, for the three-line performance chart."""
    from .. import evm
    sc = evm.scurve(db, pid, date.today(), period if period in ("week", "month") else "week")
    return sc or {"note": "No dated, budgeted activities to draw an S-curve."}


@router.get("/projects/{pid}/evm/model-ev")
def evm_model_ev(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """**Model-based EV**: earned value from physically-installed model elements (field-verified GUIDs)
    × BAC — the units-complete method sourced from the model. Cross-checks the schedule EV to catch
    over-reported / front-loaded progress."""
    from .. import evm
    return evm.model_ev(db, pid)


@router.get("/projects/{pid}/evm/trend")
def evm_trend(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """CPI/SPI **performance-index trend** across captured `evm_snapshot` records (oldest-first) — shows
    whether cost/schedule efficiency is improving or deteriorating over the reporting periods."""
    from .. import evm
    return evm.trend(db, pid)


@router.post("/projects/{pid}/evm/snapshot")
def evm_capture(pid: str, data_date: str | None = Body(default=None, embed=True),
                period_label: str | None = Body(default=None, embed=True),
                notes: str | None = Body(default=None, embed=True),
                db: Session = Depends(get_db), actor: str = Depends(require_role("editor"))):
    """Capture the current EVM state as a dated `evm_snapshot` baseline, so CPI/SPI can be trended over
    reporting periods. Capture one per period (weekly/monthly)."""
    from .. import evm
    return evm.capture_snapshot(db, pid, actor, None, data_date, period_label, notes)


@router.get("/projects/{pid}/schedule/milestones")
def milestones(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """**Milestone schedule**: the key dates — activities typed `Milestone` (or zero-duration),
    sorted by date, each with a status (met / due_soon / upcoming / late). `met` = 100% complete;
    `late` = past its date and not complete; `due_soon` = within 14 days."""
    today = date.today()
    rows = me.list_records(db, "schedule_activity", pid, limit=1_000_000)
    out = []
    for r in rows:
        data = r.get("data") or {}
        s, f = _d(data.get("start")), _d(data.get("finish"))
        is_ms = (data.get("activity_type") == "Milestone") or (s and f and s == f)
        if not is_ms:
            continue
        when = f or s
        pct = float(data.get("percent") or 0)
        if pct >= 100:
            status = "met"
        elif when and when < today:
            status = "late"
        elif when and when <= today + timedelta(days=14):
            status = "due_soon"
        else:
            status = "upcoming"
        out.append({"ref": r.get("ref"), "name": r.get("title") or data.get("name"),
                    "date": (when.isoformat() if when else None),
                    "days_out": ((when - today).days if when else None),
                    "percent": pct, "status": status})
    out.sort(key=lambda m: (m["date"] or "9999"))
    summary = {k: sum(1 for m in out if m["status"] == k) for k in ("met", "late", "due_soon", "upcoming")}
    return {"count": len(out), "summary": summary, "milestones": out}
