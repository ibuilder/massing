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


def _src(db: Session | None, pid: str) -> str | None:
    """The project's source IFC path, or None (no db / no accessible source) — checks skip on None."""
    if db is None:
        return None
    try:
        from .deps import source_ifc_path
        return source_ifc_path(db, pid)
    except Exception:                                 # noqa: BLE001 — no source IFC is a skip, not a crash
        return None


def _ids_check(db: Session | None, pid: str, idx: dict | None) -> dict:
    """MODEL-CI-3: validate against the project's **pinned IDS** (PUT /projects/{pid}/ids). The IDS is
    the information-delivery contract, so any failing specification fails the build. No pinned IDS →
    skip (an unpinned project hasn't signed up for the contract)."""
    import os
    import tempfile

    key = f"{pid}/ids/project.ids"                    # mirrors routers/analysis._ids_key
    if not storage.exists(key):
        return {"status": "skip", "summary": "no IDS pinned", "metrics": {}}
    ifc = _src(db, pid)
    if not ifc:
        return {"status": "skip", "summary": "no source IFC", "metrics": {}}
    from aec_data import validate  # type: ignore
    fd, ids_path = tempfile.mkstemp(suffix=".ids")    # temp dir, not the read-only /app tree
    try:
        with os.fdopen(fd, "wb") as fh:
            fh.write(storage.get(key))
        s = validate.validate_file(ifc, ids_path).get("summary", {})
    finally:
        try:
            os.unlink(ids_path)
        except OSError:
            pass
    failed = int(s.get("failed") or 0)
    return {"status": "fail" if failed else "pass",
            "summary": f"{s.get('passed', 0)}/{s.get('specifications', 0)} IDS specifications passing",
            "metrics": {"specifications": s.get("specifications", 0),
                        "passed": s.get("passed", 0), "failed": failed}}


def _qto_rollup(rows: list[dict]) -> dict:
    """Per-class {count, area, volume} headline quantities from takeoff rows."""
    out: dict[str, dict] = {}
    for r in rows:
        c = out.setdefault(r.get("ifc_class") or "?", {"count": 0, "area": 0.0, "volume": 0.0})
        c["count"] += 1
        c["area"] = round(c["area"] + float(r.get("area") or 0.0), 2)
        c["volume"] = round(c["volume"] + float(r.get("volume") or 0.0), 2)
    return out


def _qto_delta(prev: dict, cur: dict, threshold: float = 0.25) -> list[str]:
    """Human-readable notes for classes that appeared, vanished, or swung more than ``threshold``
    in count / area / volume between two rollups. Pure — unit-testable without an IFC."""
    notes = []
    for cls in sorted(set(prev) | set(cur)):
        p, c = prev.get(cls), cur.get(cls)
        if p is None:
            notes.append(f"{cls} appeared ({c['count']} elements)")
            continue
        if c is None:
            notes.append(f"{cls} vanished ({p['count']} elements before)")
            continue
        for m in ("count", "area", "volume"):
            pv, cv = float(p.get(m) or 0.0), float(c.get(m) or 0.0)
            if pv and abs(cv - pv) / pv > threshold:
                notes.append(f"{cls} {m} {pv:g} → {cv:g} ({(cv - pv) / pv:+.0%})")
                break                                 # one note per class is enough
    return notes


def _qto_delta_check(db: Session | None, pid: str, idx: dict | None) -> dict:
    """MODEL-CI-3: headline quantities vs the previous CI run — big unexplained swings are a review
    flag (warn), never a hard fail; quantities legitimately change as the model grows. The snapshot
    rides in this check's metrics inside the stored report, so no extra storage is needed."""
    ifc = _src(db, pid)
    if not ifc:
        return {"status": "skip", "summary": "no source IFC", "metrics": {}}
    from aec_data import qto  # type: ignore
    snap = _qto_rollup(qto.takeoff_file(ifc))         # mtime-cached — cheap on repeat runs
    prev = next(((c.get("metrics") or {}).get("snapshot")
                 for c in latest(pid).get("checks", []) if c.get("key") == "qto_delta"), None)
    if not prev:
        return {"status": "pass", "summary": f"baseline captured ({sum(v['count'] for v in snap.values())} elements)",
                "metrics": {"snapshot": snap}}
    notes = _qto_delta(prev, snap)
    return {"status": "warn" if notes else "pass",
            "summary": f"{len(notes)} class(es) moved >25% since the last run" if notes
                       else "quantities stable vs the last run",
            "metrics": {"snapshot": snap, "changes": notes[:20]}}


# (key, label, fn) — register a new check by appending one adapter over an existing engine.
CHECKS: list[tuple[str, str, Callable[[Session | None, str, dict | None], dict]]] = [
    ("rules", "Rule library", _rules_check),
    ("named", "Elements named", _named_check),
    ("clash", "Latest clash run", _clash_check),
    ("ids", "Pinned IDS contract", _ids_check),
    ("qto_delta", "Quantity drift", _qto_delta_check),
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
