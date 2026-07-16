"""RFI-0 — the **decision-readiness audit**: the proactive inverse of the RFI.

Every RFI is a decision someone had to make without the information they needed. This scans the model for the
**information gaps a builder would otherwise have to ask about** — a failed code check, an element that
should carry a detail/keynote but doesn't, unnamed/orphaned/duplicate data, an unresolved clash — and returns
them as one ranked *resolve-before-issue* list. It composes checks that already ship (the approvability
pre-flight, the detail-rule validator, model-hygiene, clash coordination) rather than adding new analysis, so
it stays consistent with each tool. Findings round-trip to BCF. A pre-check assist — not a promise of zero
RFIs.
"""
from __future__ import annotations

from typing import Any

_SEV_ORDER = {"high": 0, "medium": 1, "low": 2}


def decision_readiness(db, pid: str, model) -> dict[str, Any]:
    """Aggregate the shipped checks into a ranked list of information gaps + a readiness verdict."""
    gaps: list[dict] = []

    # 1. code / permit readiness — the approvability pre-flight's failed checks
    try:
        from . import codecheck
        ap = codecheck.approvability(model)
        for c in ap.get("checks", []):
            if c.get("status") == "fail":
                gaps.append({"category": "code", "severity": "high", "title": c["check"],
                             "detail": c.get("detail", ""), "citation": c.get("citation"),
                             "count": len(c.get("guids") or []) or None, "guids": (c.get("guids") or [])[:20],
                             "fix": "resolve the code check before issuing for permit"})
    except Exception:  # noqa: BLE001
        pass

    # 2. missing detail / keynote — the Track-D detail-rule validator
    try:
        from aec_data import rules  # type: ignore
        vr = rules.validate_rules(model)
        by_missing: dict[str, list[str]] = {}
        for e in (vr.get("elements") or []):
            by_missing.setdefault(str(e.get("missing") or "detail"), []).append(e.get("guid"))
        for missing, gs in by_missing.items():
            gaps.append({"category": "detail", "severity": "high",
                         "title": f"Missing detail / keynote: {missing}",
                         "detail": f"{len(gs)} element(s) match a detailing rule but lack their {missing} "
                                   "keynote/detail (a builder would ask how it's built)",
                         "count": len(gs), "guids": [g for g in gs if g][:20],
                         "fix": "run Auto-detail or attach the detail + keynote"})
    except Exception:  # noqa: BLE001
        pass

    # 3. model-data gaps — the model-hygiene checks that block confident construction
    try:
        from . import model_qa
        q = model_qa.model_qa(model)
        titles = {"orphaned_elements": "Elements not placed in any level",
                  "unenclosed_spaces": "Rooms not enclosed (no space boundary)",
                  "blank_names": "Unnamed elements (no mark/tag)",
                  "duplicate_guids": "Duplicate GlobalIds (copy without new GUID)"}
        for key, title in titles.items():
            c = q.get("checks", {}).get(key) or {}
            if c.get("count"):
                sample = c.get("sample") or []
                guids = [s.get("guid") for s in sample if isinstance(s, dict) and s.get("guid")]
                gaps.append({"category": "data", "severity": "medium", "title": title,
                             "detail": f"{c['count']} element(s)", "count": c["count"],
                             "guids": guids[:20], "fix": "fix the data before hand-off"})
    except Exception:  # noqa: BLE001
        pass

    # 4. coordination — open clashes are unresolved build questions
    try:
        from . import clash_intel
        cm = clash_intel.metrics(db, pid)
        if cm.get("open"):
            gaps.append({"category": "coordination", "severity": "high", "title": "Open clashes",
                         "detail": f"{cm['open']} of {cm.get('total_issues', 0)} clash issue(s) still open",
                         "count": cm["open"], "guids": [],
                         "fix": "resolve or formally accept each clash"})
    except Exception:  # noqa: BLE001
        pass

    # 5. missing dimensions — elements a builder / estimator can't size, order, or take off without a
    # dimension the drawings should carry. The proactive inverse of the classic "what size is this?" RFI.
    try:
        import ifcopenshell.util.element as _ue
        dim_gaps: dict[str, list[str]] = {}
        for d in list(model.by_type("IfcDoor")) + list(model.by_type("IfcWindow")):
            if not getattr(d, "OverallWidth", None) or not getattr(d, "OverallHeight", None):
                dim_gaps.setdefault(f"{d.is_a()[3:].lower()}s with no overall width/height", []).append(d.GlobalId)
        for sp in model.by_type("IfcSpace"):
            q = _ue.get_psets(sp).get("Qto_SpaceBaseQuantities") or {}
            if not (q.get("NetFloorArea") or q.get("GrossFloorArea")):
                dim_gaps.setdefault("rooms with no floor area (no finishes/occupancy takeoff)", []).append(sp.GlobalId)
        for title, gs in dim_gaps.items():
            gaps.append({"category": "dimensions", "severity": "medium",
                         "title": f"Missing dimension: {title}",
                         "detail": f"{len(gs)} element(s) can't be sized / ordered / taken off without it",
                         "count": len(gs), "guids": gs[:20],
                         "fix": "add the missing dimension (size attribute / base quantity) before issuing"})
    except Exception:  # noqa: BLE001
        pass

    gaps.sort(key=lambda g: (_SEV_ORDER.get(g["severity"], 3), -(g.get("count") or 0)))
    by_cat: dict[str, int] = {}
    for g in gaps:
        by_cat[g["category"]] = by_cat.get(g["category"], 0) + 1
    high = sum(1 for g in gaps if g["severity"] == "high")
    return {
        "gaps": gaps,
        "total_gaps": len(gaps),
        "high_severity": high,
        "by_category": by_cat,
        "ready": len(gaps) == 0,
        "summary": (f"{len(gaps)} information gap(s) a builder would have to ask about "
                    f"({high} high-severity)") if gaps else "No obvious information gaps — decision-ready.",
        "disclaimer": "A decision-readiness / RFI-prevention pre-check — flags where the model lacks the "
                      "information needed to build, so it's resolved before issuing. NOT a guarantee of zero "
                      "RFIs; confirm with the AHJ and the trades.",
    }
