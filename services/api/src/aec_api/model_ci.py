"""MODEL-CI — "Automate-lite": a pack of model checks that runs on demand (and can be wired to publish),
producing a pass / warn / fail report + a badge, stored as an artifact so every model carries a quality
gate. Each check is a thin adapter over an engine that already ships (RULE-LIB, data completeness, …),
so the pack grows by registering one function — the same shape as the job-kind and edit-recipe registries.

The report is stored as one JSON blob per project (`{pid}/model_ci_latest.json`) — no migration — and is
the thing a "✔ passing / ✖ failing" badge reads.
"""
from __future__ import annotations

import json
from collections.abc import Callable
from datetime import date

from sqlalchemy.orm import Session

from . import rule_library, storage

_KEY = "{pid}/model_ci_latest.json"

# status precedence: any fail → fail; else any warn → warn; else if everything skipped → skip; else pass
_RANK = {"fail": 0, "warn": 1, "pass": 2, "skip": 3}


def _rules_check(db: Session | None, pid: str, idx: dict | None) -> dict:
    """RULE-LIB gate: the project's rule library must pass. High-severity failures fail the build;
    medium/low failures warn."""
    rules = rule_library.load(pid) or rule_library.STARTER_RULES
    r = rule_library.run(idx, rules)
    if not r.get("model_scored"):
        return {"status": "skip", "summary": "no model loaded", "metrics": {}}
    fails = r.get("failing_rules", 0)
    by = r.get("by_severity", {})
    status = "fail" if by.get("high") else ("warn" if fails else "pass")
    return {"status": status,
            "summary": f"{fails}/{r['total_rules']} rules failing · {r.get('total_violations', 0)} violations",
            "metrics": {"failing_rules": fails, "violations": r.get("total_violations", 0), "by_severity": by}}


def _named_check(db: Session | None, pid: str, idx: dict | None) -> dict:
    """A cheap data-completeness gate: the share of elements that carry a name. <50% fails, <90% warns."""
    if not idx:
        return {"status": "skip", "summary": "no model loaded", "metrics": {}}
    total = len(idx)
    named = sum(1 for e in idx.values() if e.get("name"))
    pct = round(100 * named / total, 1) if total else 0.0
    status = "pass" if pct >= 90 else "warn" if pct >= 50 else "fail"
    return {"status": status, "summary": f"{pct}% of {total} elements named",
            "metrics": {"named_pct": pct, "named": named, "total": total}}


def _clash_check(db: Session | None, pid: str, idx: dict | None) -> dict:
    """MODEL-CI-2: the latest durable clash run (`clash_detect` job). Clashes are coordination work,
    not automatically defects — any clashes → warn, zero → pass, no run yet → skip."""
    if db is None:
        return {"status": "skip", "summary": "no db session", "metrics": {}}
    from .models import Job
    j = (db.query(Job).filter(Job.kind == "clash_detect", Job.project_id == pid, Job.state == "done")
         .order_by(Job.created_at.desc()).first())
    if not j or not isinstance(j.result, dict):
        return {"status": "skip", "summary": "no clash run yet", "metrics": {}}
    n = int(j.result.get("count") or 0)
    return {"status": "warn" if n else "pass", "summary": f"{n} clash(es) in the latest run",
            "metrics": {"count": n, "job_id": j.id}}


# (key, label, fn) — register a new check by appending one adapter over an existing engine.
CHECKS: list[tuple[str, str, Callable[[Session | None, str, dict | None], dict]]] = [
    ("rules", "Rule library", _rules_check),
    ("named", "Elements named", _named_check),
    ("clash", "Latest clash run", _clash_check),
]


def _overall(statuses: list[str]) -> str:
    if any(s == "fail" for s in statuses):
        return "fail"
    if any(s == "warn" for s in statuses):
        return "warn"
    if statuses and all(s == "skip" for s in statuses):
        return "skip"
    return "pass"


def run(db: Session | None, pid: str, idx: dict | None) -> dict:
    """Run the whole check pack over the model → per-check pass/warn/fail + an overall badge, persisted
    as the project's latest CI result. A check that raises is reported as a failure, never crashing the run."""
    results = []
    for key, label, fn in CHECKS:
        try:
            out = fn(db, pid, idx)
        except Exception as e:                        # noqa: BLE001 — a broken check fails, doesn't crash CI
            out = {"status": "fail", "summary": f"check error: {e}", "metrics": {}}
        results.append({"key": key, "label": label, **out})
    overall = _overall([r["status"] for r in results])
    report = {"overall": overall, "badge": overall.upper(), "ran_at": date.today().isoformat(),
              "total_checks": len(results),
              "passed": sum(1 for r in results if r["status"] == "pass"),
              "failed": sum(1 for r in results if r["status"] == "fail"),
              "warned": sum(1 for r in results if r["status"] == "warn"),
              "checks": results}
    storage.put(_KEY.format(pid=pid), json.dumps(report).encode("utf-8"))
    return report


def latest(pid: str) -> dict:
    """The project's last CI report (badge source), or a 'none' placeholder if it never ran."""
    try:
        return json.loads(storage.get(_KEY.format(pid=pid)))
    except Exception:                                 # noqa: BLE001 — never run
        return {"overall": "none", "badge": "NONE", "checks": [], "note": "No CI run yet."}
