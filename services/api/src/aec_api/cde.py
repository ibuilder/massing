"""ISO 19650 information management — CDE container discipline + the requirements register.

ISO 19650 organizes project information into *containers* that move through a Common Data Environment
in four states — Work in Progress → Shared → Published → Archived — each carrying a suitability/status
code (S0/S1…S4 shared, A published-for-construction, CR/AB record) and a revision, with review→approve
gates between states. This engine is read-side: it reports the container-state distribution, the
suitability spread, the CDE-discipline metrics (revision control, approval-status coverage, metadata
completeness) that feed the BIM KPI scorecard, and the requirements register (OIR/AIR/PIR/EIR/BEP/
MIDP/TIDP) with coverage of the core documents a compliant appointment needs."""
from __future__ import annotations

from typing import Any

from . import modules as me

# ISO 19650 CDE states, in order.
STATES = ("wip", "shared", "published", "archived")
# The requirement types a well-formed appointment should have on file (for coverage scoring).
CORE_REQS = ("EIR", "BEP", "AIR")


def _d(rec: dict) -> dict:
    return rec.get("data") or {}


def _pct(n: int, d: int) -> float | None:
    return round(100 * n / d, 1) if d else None


def status(db, pid: str) -> dict[str, Any]:
    """CDE container rollup: state distribution, suitability spread, and the three CDE-discipline
    metrics (revision control, approval-status coverage, metadata completeness)."""
    containers = me.list_records(db, "information_container", pid, limit=100000)
    total = len(containers)
    by_state: dict[str, int] = {s: 0 for s in STATES}
    by_suitability: dict[str, int] = {}
    has_revision = past_wip = complete = 0
    for c in containers:
        d = _d(c)
        st = c.get("workflow_state") or "wip"
        by_state[st] = by_state.get(st, 0) + 1
        suit = (d.get("suitability_code") or "").split(" - ")[0] or "(none)"
        by_suitability[suit] = by_suitability.get(suit, 0) + 1
        if (d.get("revision") or "").strip():
            has_revision += 1
        if st != "wip":
            past_wip += 1
        # metadata completeness: the fields a container needs to be findable/auditable
        if all((d.get(f) or "").strip() for f in ("info_type", "discipline", "originator",
                                                  "suitability_code", "revision")):
            complete += 1
    return {
        "total": total, "by_state": by_state, "by_suitability": by_suitability,
        "discipline": {
            "revision_control_pct": _pct(has_revision, total),
            "approval_status_pct": _pct(past_wip, total),      # share ever advanced past WIP
            "metadata_completeness_pct": _pct(complete, total),
            "published": by_state.get("published", 0),
            "archived": by_state.get("archived", 0),
        },
        "note": "CDE states per ISO 19650: WIP -> Shared -> Published -> Archived. Metadata "
                "completeness = containers with type, discipline, originator, suitability and "
                "revision all set.",
    }


def requirements(db, pid: str) -> dict[str, Any]:
    """The information-requirements register (OIR/AIR/PIR/EIR/BEP/MIDP/TIDP), grouped by type with
    issued/draft/superseded counts and coverage of the core documents (EIR, BEP, AIR)."""
    reqs = me.list_records(db, "info_requirement", pid, limit=10000)
    by_type: dict[str, dict[str, int]] = {}
    present: set[str] = set()
    for r in reqs:
        d = _d(r)
        code = (d.get("req_type") or "Other").split(" - ")[0]
        present.add(code)
        bucket = by_type.setdefault(code, {"total": 0, "issued": 0, "draft": 0, "superseded": 0})
        bucket["total"] += 1
        st = r.get("workflow_state") or "draft"
        if st in bucket:
            bucket[st] += 1
    missing_core = [c for c in CORE_REQS if c not in present]
    return {
        "total": len(reqs), "by_type": by_type,
        "core_coverage": {"required": list(CORE_REQS), "missing": missing_core,
                          "complete": not missing_core},
        "note": "A compliant appointment carries at least an EIR, a BEP, and (for the operational "
                "phase) an AIR. Missing core requirements are flagged.",
    }


def scorecard_inputs(db, pid: str) -> dict[str, Any]:
    """Compact CDE-discipline signals for the BIM KPI scorecard (C3). Kept here so the KPI engine
    has one import for everything ISO 19650."""
    s = status(db, pid)
    r = requirements(db, pid)
    return {"cde": s["discipline"], "requirements_core_complete": r["core_coverage"]["complete"],
            "containers": s["total"], "requirements": r["total"]}
