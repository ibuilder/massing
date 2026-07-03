"""Design-phase spine — the architect/engineer project lifecycle as explicit, gated phases.

The platform generates a massing model and jumps into the GC portal; the classic design lifecycle
(Schematic Design → Design Development → Construction Documents → Construction Administration) was
implicit. This makes it first-class: the eight **RIBA Plan of Work 2020** stages mapped to the **AIA**
design phases, each a `project_phase` record with a deliverables checklist, an A/E design-fee %, an
ISO-19650 information status, and a formal **gate** the Architect + Owner sign off before the project
advances. `seed_phases()` lays the eight stages on a project (called from generate); `lifecycle()`
aggregates them with the itemized soft-cost / A/E-fee allocation for the "Project Lifecycle" view.

Definitions are the canonical spine (RICS/RIBA/AIA-grounded); a deployment can edit the seeded records."""
from __future__ import annotations

from . import modules as me
from . import soft_costs

# The eight RIBA 2020 stages mapped to AIA phases. `fee_pct` is the A/E design-fee share drawn in that
# stage (sums to 100 across SD/DD/CD/Bid/CA; pre-design + handover/use carry no design fee). `iso`
# is the dominant ISO-19650 information status for the stage's deliverables.
PHASES: list[dict] = [
    {"order": 0, "riba": "0 Strategic Definition", "aia": "Pre-Design / Feasibility",
     "fee_pct": 0, "iso": "S0 (WIP)",
     "deliverables": ["Business case", "Site + zoning feasibility", "Test fit", "Order-of-magnitude proforma"]},
    {"order": 1, "riba": "1 Preparation & Briefing", "aia": "Pre-Design / Programming",
     "fee_pct": 0, "iso": "S0 (WIP)",
     "deliverables": ["Project brief / program", "EIR (Exchange Information Requirements)", "BEP", "Feasibility studies"]},
    {"order": 2, "riba": "2 Concept Design", "aia": "Schematic Design (SD)",
     "fee_pct": soft_costs.AE_PHASE_SPLIT["SD"] * 100, "iso": "S1 (Shared)",
     "deliverables": ["Massing + concept model", "Design narrative", "Outline specs", "SD estimate (Class 4)"]},
    {"order": 3, "riba": "3 Spatial Coordination", "aia": "Design Development (DD)",
     "fee_pct": soft_costs.AE_PHASE_SPLIT["DD"] * 100, "iso": "S1 (Shared)",
     "deliverables": ["Coordinated architecture + structure + MEP", "Developed specs", "DD estimate (Class 3)", "Clash-free model"]},
    {"order": 4, "riba": "4 Technical Design", "aia": "Construction Documents (CD)",
     "fee_pct": soft_costs.AE_PHASE_SPLIT["CD"] * 100, "iso": "S2 (Published)",
     "deliverables": ["Construction drawings", "Project manual / specifications", "IDS-validated model", "CD estimate (Class 2)"]},
    {"order": 5, "riba": "5 Manufacturing & Construction", "aia": "Bidding + Construction Administration (CA)",
     "fee_pct": (soft_costs.AE_PHASE_SPLIT["Bid"] + soft_costs.AE_PHASE_SPLIT["CA"]) * 100, "iso": "A (Published for construction)",
     "deliverables": ["Bid / award", "RFIs + submittals", "ASIs / bulletins / change orders", "Site observation reports"]},
    {"order": 6, "riba": "6 Handover", "aia": "Substantial Completion / Closeout",
     "fee_pct": 0, "iso": "AS (As-built)",
     "deliverables": ["Punch list + architect sign-off", "G704 substantial completion", "As-built / record model", "COBie + O&M turnover"]},
    {"order": 7, "riba": "7 Use", "aia": "Post-Occupancy / Operations",
     "fee_pct": 0, "iso": "AM (Asset information model)",
     "deliverables": ["Warranty tracking", "Commissioning close-out", "Post-occupancy evaluation", "Operations & maintenance"]},
]

_KEY = "project_phase"


def is_available() -> bool:
    return _KEY in me.TABLES


def seed_phases(db, pid: str, actor: str = "system") -> dict:
    """Create the eight design-phase records on a project (idempotent — skips if any exist).
    Stage 0 starts active; the rest are 'active' too (a phase is a container, gates advance them)."""
    if not is_available():
        return {"seeded": False, "reason": "project_phase module not loaded"}
    if me.list_records(db, _KEY, pid, limit=1):
        return {"seeded": False, "reason": "already seeded"}
    n = 0
    for ph in PHASES:
        me.create_record(db, _KEY, pid, {"data": {
            "subject": f"{ph['riba']} — {ph['aia']}",
            "riba_stage": ph["riba"], "aia_phase": ph["aia"], "order": ph["order"],
            "design_fee_pct": ph["fee_pct"], "iso_status": ph["iso"],
            "deliverables": "\n".join(ph["deliverables"]),
        }}, actor, "GC")
        n += 1
    return {"seeded": True, "phases": n}


def _order(rec: dict) -> int:
    try:
        return int(rec.get("data", {}).get("order", 99))
    except (TypeError, ValueError):
        return 99


def lifecycle(db, pid: str, hard_cost: float = 0.0, soft_cost_pct: float = 25.0) -> dict:
    """The project's design phases + gate states + the phase-allocated A/E design fee (from the itemized
    soft costs), for the Project Lifecycle view. `current_stage` = the lowest-order phase not yet
    approved (the one the team is working in)."""
    recs = sorted(me.list_records(db, _KEY, pid, limit=50), key=_order) if is_available() else []
    ae = soft_costs.itemize(hard_cost, soft_cost_pct)["ae_schedule"] if hard_cost else []
    ae_by_phase = {x["phase"]: x for x in ae}
    # map an AIA phase label to the AE-split bucket for the fee amount
    aia_to_bucket = {"Schematic Design (SD)": "SD", "Design Development (DD)": "DD",
                     "Construction Documents (CD)": "CD"}
    phases = []
    current = None
    for r in recs:
        d = r.get("data", {})
        state = r.get("workflow_state")
        bucket = aia_to_bucket.get(d.get("aia_phase", ""))
        fee_amt = ae_by_phase.get(bucket, {}).get("amount", 0) if bucket else 0
        # RIBA 5 carries Bid + CA
        if str(d.get("order")) == "5":
            fee_amt = ae_by_phase.get("Bid", {}).get("amount", 0) + ae_by_phase.get("CA", {}).get("amount", 0)
        phases.append({"id": r["id"], "ref": r.get("ref"), "order": _order(r), "state": state,
                       "riba_stage": d.get("riba_stage"), "aia_phase": d.get("aia_phase"),
                       "design_fee_pct": d.get("design_fee_pct"), "iso_status": d.get("iso_status"),
                       "deliverables": (d.get("deliverables") or "").split("\n") if d.get("deliverables") else [],
                       "design_fee_amount": fee_amt, "signed_by": d.get("signed_by")})
        if current is None and state != "approved":
            current = {"id": r["id"], "riba_stage": d.get("riba_stage"), "aia_phase": d.get("aia_phase")}
    return {"phases": phases, "current_stage": current, "seeded": bool(recs),
            "ae_schedule": ae, "count": len(phases)}
