"""MASTER-BUILDER brief — the software embodiment of the Master Builder Protocol: one synthesis that
holds the whole project in view at once. It runs the 8 protocol steps (place → program/HBU → feasibility
→ regulatory → design-integration → delivery → risk → handover) over the project's *own* data, grounds
the whole thing in **place** (the jurisdiction that decides which code governs and what the loads are),
and reports a readiness status + the concrete gaps per step by reading signals the platform already
produces — not by re-deriving them.

Design (per the build-doctrine): this is a *synthesis over the single sources of truth*, never a new
authority. Every probe is guarded so a missing module or engine degrades a step to a gap, never a 500.
Honest status: the brief reports what is *present* in the project, not that any step is correct, complete,
or approvable — that still needs licensed judgment, a plan check, and committed underwriting.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

# The 8 steps of the protocol, each with the module/engine signals that evidence it and the tool a gap
# points to. Kept declarative so the protocol reads the same here as in the skill.
_PROTOCOL: list[dict[str, Any]] = [
    {"key": "place", "n": 1, "title": "Place & context",
     "why": "Location decides which code governs, who approves, and what the loads are.",
     "link": "/models/georeferencing"},
    {"key": "program", "n": 2, "title": "Program & highest-and-best-use",
     "why": "Name what the asset actually is, and confirm it's the right use here — legally, physically, financially.",
     "link": "/quantities/disciplines"},
    {"key": "feasibility", "n": 3, "title": "Feasibility & the money",
     "why": "Does it pencil? Sources & uses, development budget, and returns are the spine every decision hangs from.",
     "link": "/proforma"},
    {"key": "regulatory", "n": 4, "title": "Regulatory path",
     "why": "Zoning → building code, fire, energy, accessibility, structural loads, MEP — sequenced with a timeline.",
     "link": "/golden-thread"},
    {"key": "design", "n": 5, "title": "Design integration",
     "why": "Architecture, structure, envelope, MEP resolved as one system — clashes are cheapest to fix in the model.",
     "link": "/clash/metrics"},
    {"key": "delivery", "n": 6, "title": "Delivery strategy",
     "why": "How to buy, build, sequence, and control it: delivery method, estimate, schedule, procurement, long-leads.",
     "link": "/schedule/cpm"},
    {"key": "risk", "n": 7, "title": "Risk",
     "why": "Name the risks, then allocate each to whoever can best carry it, and mitigate what remains.",
     "link": "/risk-board"},
    {"key": "handover", "n": 8, "title": "Handover & life",
     "why": "A building is a 50-year cash-flow and carbon liability — commissioning, close-out, operations, disposition.",
     "link": "/fca/index"},
]

_STATUS_SCORE = {"ready": 1.0, "partial": 0.5, "gap": 0.0}


def _count(db: Session, key: str, pid: str) -> int:
    """Guarded module-record count — a missing/absent module reads as zero, never raises."""
    try:
        from . import modules as me
        if key not in me.TABLES:
            return 0
        return len(me.list_records(db, key, pid, limit=100_000))
    except Exception:                                    # noqa: BLE001 — degrade to zero, never 500
        return 0


def _step(present: list[tuple[str, str]], missing: list[str]) -> str:
    """A step is ready when nothing's missing, partial when some evidence exists, gap when none does."""
    if present and not missing:
        return "ready"
    return "partial" if present else "gap"


def brief(db: Session, pid: str) -> dict[str, Any]:
    """Run the Master Builder Protocol over the project. Returns the per-step readiness + gaps, grounded
    in the project's jurisdiction, plus an overall readiness score."""
    from .models import Project

    project = db.get(Project, pid)
    if project is None:
        raise KeyError(pid)
    jurisdiction = (getattr(project, "jurisdiction", None) or "").strip()
    has_model = bool(getattr(project, "source_ifc", None))

    findings: dict[str, dict] = {}          # step key -> {present:[(label,detail)], missing:[label]}
    for s in _PROTOCOL:
        findings[s["key"]] = {"present": [], "missing": []}

    def add(step: str, ok: bool, label: str, detail: str = "") -> None:
        (findings[step]["present"].append((label, detail)) if ok
         else findings[step]["missing"].append(label))

    # 1 — place & context: the jurisdiction that resolves code editions + hazards, and a georeferenced model
    add("place", bool(jurisdiction), f"Jurisdiction set ({jurisdiction})" if jurisdiction else
        "Jurisdiction (AHJ / state) so code editions + loads resolve", jurisdiction)
    add("place", has_model, "Source IFC model present", "")

    # 2 — program & HBU: a model that carries the program (spaces/quantities)
    add("program", has_model, "Model defines the program (spaces / quantities)", "")

    # 3 — feasibility & money: a development budget / cost basis exists (does it pencil?)
    budget_n = _count(db, "budget", pid) + _count(db, "project_budget", pid)
    add("feasibility", budget_n > 0, "Development budget / cost basis", f"{budget_n} budget line(s)" if budget_n else "")

    # 4 — regulatory path: the compliance-evidence ledger (golden thread) carries requirements
    ce_n = _count(db, "compliance_evidence", pid)
    add("regulatory", ce_n > 0, "Compliance-evidence ledger (golden thread)", f"{ce_n} requirement(s)" if ce_n else "")
    add("regulatory", bool(jurisdiction), "Adopted code editions resolvable (needs jurisdiction)", "")

    # 5 — design integration: clash coordination has run (coordination issues tracked)
    ci_n = _count(db, "coordination_issue", pid)
    add("design", ci_n >= 0 and has_model, "Model available to coordinate", "")
    if ci_n > 0:
        add("design", True, "Clash coordination tracked", f"{ci_n} coordination issue(s)")

    # 6 — delivery strategy: a schedule + bid packages exist
    sched_n = _count(db, "schedule_activity", pid)
    pkg_n = _count(db, "bid_package", pid)
    add("delivery", sched_n > 0, "Construction schedule (activities)", f"{sched_n} activit(y/ies)" if sched_n else "")
    add("delivery", pkg_n > 0, "Bid packages / procurement scope", f"{pkg_n} package(s)" if pkg_n else "")

    # 7 — risk: the unified risk board surfaces at least one signal (guarded engine call)
    risk_n = None
    try:
        from . import risk_board
        risk_n = int(risk_board.board(db, pid).get("count", 0))
    except Exception:                                    # noqa: BLE001 — engine unavailable → treat as unknown
        risk_n = None
    add("risk", bool(risk_n), "Risks identified on the risk board",
        f"{risk_n} signal(s)" if risk_n else ("none surfaced yet" if risk_n == 0 else ""))

    # 8 — handover & life: a facility-condition / asset basis for the operating life
    fca_n = _count(db, "fca_element", pid) + _count(db, "asset_register", pid)
    signed = None
    try:
        from . import golden_thread
        signed = int(golden_thread.summary(db, pid).get("signed_off", 0))
    except Exception:                                    # noqa: BLE001
        signed = None
    add("handover", fca_n > 0, "Asset / facility-condition basis for operations",
        f"{fca_n} asset/element(s)" if fca_n else "")
    if signed:
        add("handover", True, "Requirements signed off (thread closing)", f"{signed} signed off")

    steps = []
    for s in _PROTOCOL:
        f = findings[s["key"]]
        status = _step(f["present"], f["missing"])
        steps.append({
            "n": s["n"], "key": s["key"], "title": s["title"], "why": s["why"], "link": s["link"],
            "status": status,
            "findings": [{"label": lbl, "detail": det} for lbl, det in f["present"]],
            "gaps": list(f["missing"]),
        })

    ready = sum(1 for s in steps if s["status"] == "ready")
    gaps = sum(1 for s in steps if s["status"] == "gap")
    readiness_pct = round(100.0 * sum(_STATUS_SCORE[s["status"]] for s in steps) / len(steps), 1)
    return {
        "project": getattr(project, "name", None), "jurisdiction": jurisdiction or None,
        "grounded_in_place": bool(jurisdiction),
        "reframe_prompt": "Name what this asset actually is, stripped of marketing — the real use drives "
                          "the comps, the tenants, and the buyer.",
        "readiness_pct": readiness_pct, "ready_steps": ready, "gap_steps": gaps, "step_count": len(steps),
        "steps": steps,
        "disclaimer": "A project-readiness synthesis over the data on hand — not a substitute for licensed "
                      "engineering/architectural judgment, an AHJ plan check, or committed underwriting. "
                      "Labels reflect what is present in the project, not that any step is correct, complete, "
                      "or approvable.",
        "note": "The Master Builder Protocol, run over this project's own data and grounded in its "
                "jurisdiction. Each step links to the tool that closes its gap.",
    }
