"""ISO 19650 information management — CDE container discipline + the requirements register.

ISO 19650 organizes project information into *containers* that move through a Common Data Environment
in four states — Work in Progress → Shared → Published → Archived — each carrying a suitability/status
code (S0/S1…S4 shared, A published-for-construction, CR/AB record) and a revision, with review→approve
gates between states. This engine is read-side: it reports the container-state distribution, the
suitability spread, the CDE-discipline metrics (revision control, approval-status coverage, metadata
completeness) that feed the BIM KPI scorecard, and the requirements register (OIR/AIR/PIR/EIR/BEP/
MIDP/TIDP) with coverage of the core documents a compliant appointment needs."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from . import modules as me
from .timeutil import utc_today

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
    by_state: dict[str, int] = dict.fromkeys(STATES, 0)
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


# ISO 19650 flow-down tiers — lower = more upstream (organizational intent → task delivery)
_TIER = {"OIR": 0, "PIR": 1, "AIR": 1, "EIR": 2, "BEP": 2, "MIDP": 3, "TIDP": 4}


def cascade(db, pid: str) -> dict[str, Any]:
    """The information-requirement flow-down (ISO 19650): OIR → PIR/AIR → EIR → MIDP/TIDP, linked by
    each record's `derives_from`. Returns the requirements as tiered nodes, the parent→children edges,
    and cascade health — which non-top requirements don't trace up to a higher-level one (a broken
    flow-down) and any links that point the wrong way (to an equal-or-lower tier)."""
    reqs = me.list_records(db, "info_requirement", pid, limit=10000)
    nodes: dict[str, dict] = {}
    for r in reqs:
        d = _d(r)
        code = (d.get("req_type") or "Other").split(" - ")[0]
        nodes[r["id"]] = {"id": r["id"], "ref": r.get("ref"), "title": r.get("title"), "type": code,
                          "tier": _TIER.get(code, 9), "state": r.get("workflow_state"),
                          "derives_from": d.get("derives_from") or None}
    children: dict[str, list[str]] = {}
    orphans, misdirected, roots = [], [], []
    for n in nodes.values():
        p = n["derives_from"]
        if p and p in nodes:
            children.setdefault(p, []).append(n["id"])
            if nodes[p]["tier"] >= n["tier"] and n["tier"] != 9:
                misdirected.append({"id": n["id"], "ref": n["ref"], "type": n["type"],
                                    "parent_type": nodes[p]["type"]})
        else:
            # OIRs sit at the top of the cascade (legitimately unlinked); everything else should trace up
            (roots if n["tier"] == 0 else orphans).append(
                {"id": n["id"], "ref": n["ref"], "type": n["type"], "title": n["title"]})
    linked = sum(1 for n in nodes.values() if n["derives_from"] in nodes)
    return {
        "total": len(nodes), "linked": linked, "coverage_pct": _pct(linked, len(nodes)),
        "nodes": sorted(nodes.values(), key=lambda x: (x["tier"], x["ref"] or "")),
        "children": children, "roots": roots, "orphans": orphans, "misdirected": misdirected,
        "note": "ISO 19650 flow-down: OIR → PIR/AIR → EIR → MIDP/TIDP. Each requirement should derive "
                "from a higher-level one; orphans don't trace up to organizational intent.",
    }


_LOIN_FIELDS = ("loin_geometry", "loin_information", "loin_documentation")


def delivery_plan(db, pid: str, today: date | None = None) -> dict[str, Any]:
    """The MIDP/TIDP delivery view (ISO 19650): information requirements laid out against their
    programme dates, so every exchange is tied to a milestone. Returns each requirement with its due
    date + status (overdue / due-soon / scheduled / issued), a per-milestone (due-month) roll-up, and
    the summary the plan lives on — overdue count, next deliverable, and LOIN-specification coverage
    (share of requirements that state a Level of Information Need, per EN 17412)."""
    today = today or utc_today()
    reqs = me.list_records(db, "info_requirement", pid, limit=10000)
    items, months, overdue, upcoming, loin_set = [], {}, 0, 0, 0
    for r in reqs:
        d = _d(r)
        issued = (r.get("workflow_state") or "draft") == "issued"
        raw = d.get("due_date")
        due = None
        if raw:
            try:
                due = datetime.fromisoformat(str(raw)[:10]).date()
            except ValueError:
                due = None
        if issued:
            status = "issued"
        elif due and due < today:
            status = "overdue"; overdue += 1
        elif due and (due - today).days <= 30:
            status = "due_soon"; upcoming += 1
        else:
            status = "scheduled"
        has_loin = any(d.get(f) and d.get(f) != "Not required" for f in _LOIN_FIELDS)
        if has_loin:
            loin_set += 1
        items.append({"id": r["id"], "ref": r.get("ref"), "title": r.get("title"),
                      "type": (d.get("req_type") or "Other").split(" - ")[0],
                      "due_date": due.isoformat() if due else None, "status": status, "has_loin": has_loin,
                      "loin": {f: d.get(f) for f in _LOIN_FIELDS if d.get(f)}})
        if due:
            key = due.strftime("%Y-%m")
            m = months.setdefault(key, {"month": key, "total": 0, "issued": 0, "overdue": 0})
            m["total"] += 1
            m["issued"] += 1 if issued else 0
            m["overdue"] += 1 if status == "overdue" else 0
    items.sort(key=lambda x: (x["due_date"] or "9999", x["ref"] or ""))
    nxt = next((i for i in items if i["status"] in ("overdue", "due_soon", "scheduled") and i["due_date"]), None)
    return {
        "total": len(items), "overdue": overdue, "due_soon": upcoming,
        "loin_coverage_pct": _pct(loin_set, len(items)),
        "next_deliverable": nxt,
        "by_month": [months[k] for k in sorted(months)],
        "items": items,
        "note": "MIDP/TIDP: each information requirement mapped to its programme date. Overdue = past "
                "due and not issued; LOIN coverage = requirements that state a Level of Information Need.",
    }


def exchange_acceptance(db, pid: str) -> dict[str, Any]:
    """ISO 19650-6 information-exchange acceptance: each container that has left WIP (i.e. been
    exchanged) is reviewed against the four acceptance criteria — completeness, suitability,
    authorization, traceability — and the ones not yet acceptable are flagged before the next decision
    point. Authorization = published/archived (approved for use), vs merely shared for information."""
    containers = me.list_records(db, "information_container", pid, limit=100000)
    reviewed = [c for c in containers if (c.get("workflow_state") or "wip") != "wip"]
    crit = {"completeness": 0, "suitability": 0, "authorization": 0, "traceability": 0}
    nonconforming = []
    for c in reviewed:
        d = _d(c)
        st = c.get("workflow_state")
        checks = {
            "completeness": all((d.get(f) or "").strip() for f in ("info_type", "discipline", "originator")),
            "suitability": bool((d.get("suitability_code") or "").strip()),
            "authorization": st in ("published", "archived"),
            "traceability": bool((d.get("revision") or "").strip()),
        }
        for k, ok in checks.items():
            crit[k] += 1 if ok else 0
        failed = [k for k, ok in checks.items() if not ok]
        if failed:
            nonconforming.append({"id": c["id"], "ref": c.get("ref"), "title": c.get("title"),
                                  "state": st, "failed": failed})
    n = len(reviewed)
    return {
        "reviewed": n, "accepted": n - len(nonconforming), "nonconforming_count": len(nonconforming),
        "acceptable": n > 0 and not nonconforming,
        "criteria_pct": {k: _pct(v, n) for k, v in crit.items()},
        "nonconforming": nonconforming[:50],
        "note": "ISO 19650-6 exchange acceptance: each shared/published container reviewed against "
                "completeness, suitability, authorization and traceability before the next decision point.",
    }


def scorecard_inputs(db, pid: str) -> dict[str, Any]:
    """Compact CDE-discipline signals for the BIM KPI scorecard (C3). Kept here so the KPI engine
    has one import for everything ISO 19650."""
    s = status(db, pid)
    r = requirements(db, pid)
    return {"cde": s["discipline"], "requirements_core_complete": r["core_coverage"]["complete"],
            "containers": s["total"], "requirements": r["total"]}
