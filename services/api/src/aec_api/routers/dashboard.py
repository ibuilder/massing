"""Role-tailored dashboard endpoint (GC portal)."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from sqlalchemy.orm import Session

from .. import ai, dashboard, mailer, oauth, rbac, report
from .. import modules as me
from ..db import get_db
from ..models import Project
from ..rbac import require_role

router = APIRouter()


@router.get("/projects/{pid}/dashboard")
def get_dashboard(pid: str, party: str | None = None, db: Session = Depends(get_db),
                  user: str = Depends(require_role("viewer"))):
    """Dashboard tailored to `party` (defaults to the caller's project party role)."""
    party = party or rbac.party_role_for(db, pid, user) or "GC"
    return dashboard.build(db, pid, party)


_RECORDABLE = {"Recordable", "Lost Time", "Fatality"}
_LOST_TIME = {"Lost Time", "Fatality"}


@router.get("/portfolio/construction")
def construction_portfolio(db: Session = Depends(get_db), _: str = Depends(rbac.current_user)):
    """Owner / program view: construction health across all projects — cost over/under (flags
    forecast overruns), open risks + cost exposure, recordable incidents, open RFIs."""
    from .. import cost as cost_engine
    rows = []
    tot = {"budget": 0.0, "projected_over_under": 0.0, "open_risks": 0, "risk_exposure": 0.0,
           "recordables": 0, "open_rfis": 0, "over_budget_count": 0}
    for p in db.query(Project).all():
        cs = cost_engine.summary(db, p.id)
        # P0.1 perf: only the (small) open/mitigating risk rows are loaded for the exposure sum; RFIs
        # use a SQL COUNT (no rows loaded); incidents are bounded. Was list_records(limit=1_000_000) x3.
        risks = [r for st in ("open", "mitigating")
                 for r in me.list_records(db, "risk", p.id, state=st, limit=100_000)]
        exposure = sum(float((r.get("data") or {}).get("cost_exposure") or 0) for r in risks)
        recordables = sum(1 for i in me.list_records(db, "incident", p.id, limit=100_000)
                          if (i.get("data") or {}).get("classification") in _RECORDABLE)
        open_rfis = me.count_records(db, "rfi", p.id, state="open")
        over_under = float(cs.get("projected_over_under") or 0)
        rows.append({"id": p.id, "name": p.name, "budget": cs.get("budget", 0),
                     "projected_over_under": over_under, "pct_spent": cs.get("pct_spent", 0),
                     "over_budget": over_under > 0, "open_risks": len(risks),
                     "risk_exposure": round(exposure, 2), "recordables": recordables, "open_rfis": open_rfis})
        tot["budget"] += cs.get("budget", 0); tot["projected_over_under"] += over_under
        tot["open_risks"] += len(risks); tot["risk_exposure"] += exposure
        tot["recordables"] += recordables; tot["open_rfis"] += open_rfis
        tot["over_budget_count"] += 1 if over_under > 0 else 0
    tot["risk_exposure"] = round(tot["risk_exposure"], 2)
    rows.sort(key=lambda r: r["projected_over_under"], reverse=True)
    return {"projects": rows, "totals": tot, "project_count": len(rows)}


@router.get("/portfolio/executive")
def executive_portfolio(db: Session = Depends(get_db), _: str = Depends(rbac.current_user)):
    """Cross-project executive roll-up — every project's on-schedule (SPI, % complete, lookahead,
    late milestones) next to on-budget (GMP, EAC, variance-at-completion) with its overall status,
    plus portfolio totals and a status tally. The 'how's the whole book doing?' view, built on the
    same px-summary each project's dashboard shows."""
    from sqlalchemy import func

    from .. import px
    from ..models import Scenario

    # latest solved scenario per project → developer returns (IRR / EM) alongside the GC status
    returns_by_proj: dict[str, dict] = {}
    # only the latest scenario per project (windowed) — not every scenario's full result blob
    _latest = (db.query(Scenario.project_id, func.max(Scenario.created_at).label("mx"))
               .filter(Scenario.project_id.isnot(None)).group_by(Scenario.project_id).subquery())
    for s in db.query(Scenario).join(
            _latest, (Scenario.project_id == _latest.c.project_id) & (Scenario.created_at == _latest.c.mx)):
        if s.project_id and s.result:
            returns_by_proj[s.project_id] = s.result.get("returns", {}) or {}

    rows = []
    tot = {"gmp": 0.0, "eac": 0.0, "variance_at_completion": 0.0, "committed": 0.0, "equity": 0.0}
    tally = {"on_track": 0, "at_risk": 0, "behind": 0}
    w_eq = w_irr = 0.0
    for p in db.query(Project).all():
        try:
            s = px.summary(db, p.id)
        except Exception:                              # noqa: BLE001 — a project with no data still lists
            s = {"status": "on_track", "schedule": {}, "budget": {}}
        sched, bud = s.get("schedule", {}), s.get("budget", {})
        ret = returns_by_proj.get(p.id, {})
        irr, em = ret.get("equity_irr"), ret.get("equity_multiple")
        rows.append({
            "id": p.id, "name": p.name, "status": s.get("status"),
            "spi": sched.get("spi"), "cpi": bud.get("cpi"), "pct_complete": sched.get("pct_complete", 0),
            "lookahead_3wk": sched.get("lookahead_3wk", 0),
            "milestones_late": (sched.get("milestones") or {}).get("late", 0),
            "gmp": bud.get("gmp", 0), "eac": bud.get("eac", 0),
            "variance_at_completion": bud.get("variance_at_completion", 0),
            "committed_pct": bud.get("committed_pct", 0),
            "equity_irr": irr, "equity_multiple": em})
        tot["gmp"] += bud.get("gmp", 0); tot["eac"] += bud.get("eac", 0)
        tot["variance_at_completion"] += bud.get("variance_at_completion", 0)
        tot["committed"] += bud.get("committed", 0)
        if s.get("status") in tally:
            tally[s["status"]] += 1
        eq = float((ret or {}).get("total_contributions") or 0)
        if irr is not None and eq:
            w_eq += eq; w_irr += irr * eq
            tot["equity"] += eq
    tot = {k: round(v, 2) for k, v in tot.items()}
    tot["blended_equity_irr"] = round(w_irr / w_eq, 4) if w_eq else None
    rows.sort(key=lambda r: (r["status"] != "behind", r["status"] != "at_risk", r["variance_at_completion"]))
    return {"projects": rows, "totals": tot, "status_tally": tally, "project_count": len(rows)}


@router.get("/projects/{pid}/safety/metrics")
def safety_metrics(pid: str, hours: float | None = None, db: Session = Depends(get_db),
                   _: str = Depends(require_role("viewer"))):
    """Safety analytics: incidents by OSHA class, recordable/lost-time counts, lost days, and
    TRIR/DART (per 200k hours) using `hours` or hours summed from timesheets + manpower logs."""
    incs = me.list_records(db, "incident", pid, limit=1_000_000)
    by_class: dict[str, int] = {}
    recordable = lost_time = lost_days = 0
    for r in incs:
        d = r.get("data") or {}
        cls = d.get("classification") or "Unclassified"
        by_class[cls] = by_class.get(cls, 0) + 1
        if cls in _RECORDABLE:
            recordable += 1
        if cls in _LOST_TIME:
            lost_time += 1
        try:
            lost_days += int(float(d.get("lost_days") or 0))
        except (TypeError, ValueError):
            pass
    if hours is None:                              # derive man-hours from the logs if not supplied
        SHIFT = 8.0                                # standard crew shift when a log gives headcount, not hours
        hours = sum(float((x.get("data") or {}).get("hours") or 0)
                    for x in me.list_records(db, "timesheet", pid, limit=1_000_000))
        for x in me.list_records(db, "manpower_log", pid, limit=1_000_000):
            d = x.get("data") or {}
            h = float(d.get("hours") or 0)
            if not h:                              # crew count × an 8h shift = man-hours for the day
                h = float(d.get("count") or d.get("headcount") or 0) * SHIFT
            hours += h
    trir = round(recordable * 200000 / hours, 2) if hours else None
    dart = round(lost_time * 200000 / hours, 2) if hours else None
    return {"incident_count": len(incs), "by_class": by_class, "recordable_count": recordable,
            "lost_time_count": lost_time, "lost_days": lost_days, "hours_worked": round(hours, 1),
            "trir": trir, "dart": dart,
            "observation_count": me.count_records(db, "observation", pid),
            "toolbox_talk_count": me.count_records(db, "toolbox_talk", pid)}


@router.get("/capabilities")
def capabilities():
    """Which optional integrations are wired (for at-a-glance status badges). Not sensitive —
    just feature flags + the configured SSO provider ids."""
    from .. import licensing, rbac
    return {"ai": ai.ai_enabled(), "email": mailer.smtp_configured(),
            "sso": [p["id"] for p in oauth.enabled_providers()],
            "local_mode": rbac.LOCAL_MODE,
            "license_tier": licensing.current_tier()}


@router.get("/license")
def license_state():
    """The Massing licence state — plan tier, per-tier feature entitlements, and whether a valid key
    is recorded (key is masked, never returned in full). Drives the Settings licence panel."""
    from .. import licensing
    return licensing.state()


@router.get("/projects/{pid}/ai/risk-summary")
def risk_summary(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("reviewer"))):
    """AI/rules risk read over the project dashboard (owner/PM reporting)."""
    d = dashboard.build(db, pid, "GC")
    return {**ai.risk_summary(d.get("kpis", {}), d.get("cost")), "ai_enabled": ai.ai_enabled()}


@router.get("/projects/{pid}/risk-digest")
def risk_digest(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Project risk digest across cost + schedule + open items + safety, with a prioritized narrative."""
    from .. import px
    return px.risk_digest(db, pid)


_ASK_COUNT_MODULES = ("rfi", "submittal", "change_event", "pco_request", "cor", "punchlist",
                      "ncr", "deficiency", "inspection", "incident", "daily_report", "commitment")


def _ask_context(db: Session, pid: str) -> dict:
    """A compact, token-bounded snapshot of the project for grounding the AI assistant: dashboard
    KPIs + cost, per-module record counts, and a sample of open RFIs/change events."""
    d = dashboard.build(db, pid, "GC")
    ctx: dict = {"kpis": d.get("kpis", {}), "cost": d.get("cost")}
    counts: dict[str, int] = {}
    for m in _ASK_COUNT_MODULES:
        if m in me.TABLES:
            try:
                counts[m] = me.count_records(db, m, pid)   # SQL COUNT, no JSON row load
            except Exception:        # noqa: BLE001 — a missing/odd module never breaks the snapshot
                pass
    ctx["record_counts"] = counts
    def _sample(mod: str, n: int = 15) -> list[dict]:
        if mod not in me.TABLES:
            return []
        out = []
        for r in me.list_records(db, mod, pid, limit=n):
            data = r.get("data") or {}
            out.append({"ref": r.get("ref"), "title": data.get("subject") or r.get("title"),
                        "status": r.get("workflow_state")})
        return out
    ctx["open_rfis"] = _sample("rfi")
    ctx["change_events"] = _sample("change_event")
    return ctx


@router.post("/projects/{pid}/ai/ask")
def ai_ask(pid: str, body: dict, db: Session = Depends(get_db),
           _: str = Depends(require_role("viewer"))):
    """Ask a natural-language question about the project; answered (by Claude when configured)
    against a live snapshot of KPIs, costs and open items. Degrades to returning the snapshot."""
    from fastapi import HTTPException
    question = (body or {}).get("question", "").strip()
    if not question:
        raise HTTPException(422, "question is required")
    ctx = _ask_context(db, pid)
    return {**ai.ask(question, ctx), "ai_enabled": ai.ai_enabled()}


@router.post("/projects/{pid}/ai/estimate")
def ai_estimate(pid: str, body: dict, _: str = Depends(require_role("viewer"))):
    """Draft a Bill of Quantities from a plain-text project description (Claude when configured;
    a graceful stub otherwise — never fabricates numbers without the model)."""
    from fastapi import HTTPException
    description = (body or {}).get("description", "").strip()
    if not description:
        raise HTTPException(422, "description is required")
    return {**ai.estimate_boq(description), "ai_enabled": ai.ai_enabled()}


@router.get("/projects/{pid}/report.pdf")
def status_report(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """One-page project status report (KPIs, cost, open items by module, ball-in-court) as a PDF."""
    proj = db.get(Project, pid)
    pdf = report.project_status_pdf(db, pid, proj.name if proj else pid)
    return Response(pdf, media_type="application/pdf",
                    headers={"Content-Disposition": 'attachment; filename="status-report.pdf"'})
