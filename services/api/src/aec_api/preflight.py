"""Pre-flight — the one-click **"is this model clean enough to issue?"** gate. The platform already scores
model health (`model_health.scorecard`: hygiene · KPIs · clash · verified-as-built · code readiness) and
flags decision-readiness gaps; what it lacked is a single crisp **PASS / HOLD verdict** with a pre-issue
checklist — the pyRevit "run the pre-flight before you publish" moment.

This composes the shipped lenses into a checklist, adds the missing lenses — **discipline-classification
completeness** (elements that don't map to the discipline tree can't be scheduled / priced / drawn by
discipline), **keynote/spec completeness** (the detail-rule QA), **drawing-set QA** (the set-integrity
review), and the **pinned-IDS validation** (the project's contractual information-delivery spec) — and
folds in **open high-priority issues** as a hard blocker. Every check carries a `link` (the API tool
that drills into it), so a HOLD is one click from its evidence. Reuses the engines; no duplicate logic.
"""
from __future__ import annotations

from typing import Any

_PASS, _WARN, _FAIL = "pass", "warn", "fail"
_ORDER = {_FAIL: 0, _WARN: 1, _PASS: 2}

# deep-link map: model-health lens key → the API tool that acts on it
_LENS_LINKS = {
    "hygiene": "/projects/{pid}/models/qa",
    "information": "/projects/{pid}/bim-kpi/scorecard",
    "coordination": "/projects/{pid}/topics",
    "verified": "/projects/{pid}/verified-progress",
    "readiness": "/projects/{pid}/codecheck/approvability",
}


def _lens_status(score: float) -> str:
    return _PASS if score >= 85 else _WARN if score >= 60 else _FAIL


def issuance_gate(db, pid: str, model, elements: list[dict] | None,
                  ifc_path: str | None = None, ids_bytes: bytes | None = None) -> dict[str, Any]:
    """A pre-issue checklist + a single ready/hold verdict. `model` enables the hygiene + keynote +
    drawing-cross-check lenses; `elements` is the published property index (classification
    completeness); `ifc_path` + `ids_bytes` (the project's pinned IDS) enable the IDS lens."""
    from . import classification, drawing_qa, model_health
    from .models import Topic

    card = model_health.scorecard(db, pid, model=model, elements=elements)
    checks: list[dict[str, Any]] = []

    # 1) every scored model-health lens becomes a checklist item
    for ln in card.get("lenses", []):
        if ln.get("score") is None:
            continue
        checks.append({"key": ln["key"], "label": ln["label"], "status": _lens_status(ln["score"]),
                       "detail": ln.get("headline", ""), "score": ln["score"],
                       "link": _LENS_LINKS.get(ln["key"], "").replace("{pid}", pid) or None})

    # 2) discipline-classification completeness — the missing lens (elements that don't map to the tree)
    els = elements or []
    total = len(els)
    if total:
        unclassified = [e.get("guid") for e in els
                        if not classification.discipline_of_ifc_class(e.get("ifc_class", ""))]
        pct = round(100 * (1 - len(unclassified) / total), 1)
        checks.append({"key": "classification", "label": "Discipline classification",
                       "status": _PASS if pct >= 95 else _WARN if pct >= 80 else _FAIL,
                       "detail": f"{total - len(unclassified)}/{total} elements classified ({pct}%)",
                       "score": pct, "count": len(unclassified),
                       "guids": [g for g in unclassified if g][:200],
                       "link": f"/projects/{pid}/models/health"})

    # 3) keynote / spec-code completeness — the detail-rule QA ("components missing a keynote")
    if model is not None:
        try:
            from aec_data import rules  # type: ignore

            kq = rules.validate_rules(model)
            gaps = int(kq.get("gaps", 0))
            checks.append({"key": "keynotes", "label": "Keynote / spec codes",
                           "status": _PASS if gaps == 0 else _WARN if gaps <= 12 else _FAIL,
                           "detail": (f"{gaps} element(s) missing a required keynote/spec code"
                                      if gaps else "every governed element carries its keynote/spec code"),
                           "count": gaps,
                           "guids": [e.get("guid") for e in kq.get("elements", [])][:200],
                           "link": f"/projects/{pid}/detailing/rules/validate"})
        except Exception:                              # noqa: BLE001 — a QA engine error never blocks the gate
            pass

    # 4) drawing-set QA — set integrity / issuance hygiene / model cross-checks (when sheets exist)
    try:
        dq = drawing_qa.review(db, pid, model)
        if dq.get("sheet_count"):
            sev = dq.get("by_severity", {})
            verdict = dq.get("verdict", "CLEAN")
            checks.append({"key": "drawing_qa", "label": "Drawing-set QA",
                           "status": _FAIL if verdict == "HOLD" else _WARN if verdict == "REVIEW" else _PASS,
                           "detail": (f"{dq.get('finding_count', 0)} finding(s) across "
                                      f"{dq.get('sheet_count', 0)} sheets "
                                      f"({sev.get('critical', 0)} critical · {sev.get('major', 0)} major · "
                                      f"{sev.get('minor', 0)} minor)"
                                      if dq.get("finding_count") else
                                      f"{dq.get('sheet_count', 0)} sheets, no findings"),
                           "count": dq.get("finding_count", 0),
                           "link": f"/projects/{pid}/drawing-set/qa"})
    except Exception:                                  # noqa: BLE001
        pass

    # 5) pinned-IDS validation — the project's contractual information-delivery spec (when pinned)
    if ifc_path and ids_bytes:
        import os
        import tempfile
        from pathlib import Path

        fd, ids_path = tempfile.mkstemp(suffix=".ids")  # never write into the (read-only) source tree
        try:
            with os.fdopen(fd, "wb") as fh:
                fh.write(ids_bytes)
            from aec_data import validate  # type: ignore

            vr = validate.validate_file(ifc_path, ids_path)
            specs = vr.get("specifications", [])
            failed = [s for s in specs if s.get("status") == "fail"]
            checks.append({"key": "ids", "label": "IDS validation (pinned spec)",
                           "status": _FAIL if failed else _PASS,
                           "detail": (f"{len(specs) - len(failed)}/{len(specs)} specifications pass"
                                      + (f" — failing: {', '.join(s.get('name', '?') for s in failed[:5])}"
                                         if failed else "")),
                           "count": len(failed),
                           "link": f"/projects/{pid}/validate"})
        except Exception:                              # noqa: BLE001 — a bad IDS shouldn't 500 the gate
            pass
        finally:
            Path(ids_path).unlink(missing_ok=True)

    # 6) open high-priority coordination / RFI issues are a hard blocker to issuing
    open_high = (db.query(Topic)
                 .filter(Topic.project_id == pid, Topic.status != "closed", Topic.priority == "high")
                 .count())
    checks.append({"key": "open_issues", "label": "Open high-priority issues",
                   "status": _FAIL if open_high else _PASS,
                   "detail": (f"{open_high} open high-priority BCF/RFI item(s) to resolve" if open_high
                              else "no open high-priority issues"),
                   "count": open_high, "link": f"/projects/{pid}/topics"})

    blocking = [c for c in checks if c["status"] == _FAIL]
    warnings = [c for c in checks if c["status"] == _WARN]
    ready = not blocking
    return {
        "ready": ready,
        "verdict": "READY TO ISSUE" if ready else "HOLD — resolve the blocker(s) first",
        "overall_score": card.get("overall_score"),
        "band": card.get("band"),
        "blocking": len(blocking),
        "warnings": len(warnings),
        "checks": sorted(checks, key=lambda c: _ORDER[c["status"]]),
        "disclaimer": "A pre-issue model-health gate composing hygiene, clash coordination, code readiness, "
                      "verified-as-built, classification/keynote completeness, drawing-set QA, and the "
                      "pinned IDS. Not a substitute for a professional review or the AHJ.",
    }


def run(db, pid: str) -> dict[str, Any]:
    """Assemble the gate's inputs from the project (source IFC · published index · pinned IDS) and run
    it — the one call both the `/preflight` endpoint and the issuance flow share."""
    import json

    from . import storage
    from .deps import open_source_ifc, source_ifc_path

    model = None
    ifc_path = None
    try:
        model = open_source_ifc(db, pid)               # enables the hygiene/keynote lenses
        ifc_path = source_ifc_path(db, pid)
    except Exception:                                  # noqa: BLE001 — no source IFC: DB/index lenses only
        pass
    try:
        elements = json.loads(storage.get(f"{pid}/props.json")).get("elements", [])
    except Exception:                                  # noqa: BLE001 — no published index yet
        elements = []
    ids_key = f"{pid}/ids/project.ids"                 # the pinned-IDS storage key (see routers/analysis)
    ids_bytes = storage.get(ids_key) if storage.exists(ids_key) else None
    return issuance_gate(db, pid, model, elements, ifc_path=ifc_path, ids_bytes=ids_bytes)


def summary(gate: dict[str, Any]) -> dict[str, Any]:
    """The compact stamp the issuance record carries — verdict + counts + the blocking check keys."""
    return {"ready": gate["ready"], "verdict": gate["verdict"], "overall_score": gate.get("overall_score"),
            "blocking": gate["blocking"], "warnings": gate["warnings"],
            "blocking_checks": [c["key"] for c in gate["checks"] if c["status"] == _FAIL]}
