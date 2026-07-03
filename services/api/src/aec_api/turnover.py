"""Substantial completion (AIA G704) + record-model turnover.

The closeout modules tracked punch/commissioning/warranty/O&M, but nothing tied them into a signed
**substantial-completion** milestone or a locked **record (as-built) model**. This adds that final
step: the Architect signs off the punch list, a **G704 Certificate of Substantial Completion** is
issued with the punch list attached, the current model version is stamped as the **record model**, and
the turnover package captures it all.

No new tables — the state lives on the existing `completion_certificate` record's `data` (signatures +
`record_model_version` + punch metrics) and the model-version history. G704 requires a prepared punch
list to certify (substantial completion is certified *with* an outstanding punch list, per AIA)."""
from __future__ import annotations

from datetime import datetime, timezone

from . import closeout, versions
from . import modules as me

_CERT = "completion_certificate"


def readiness(db, pid: str) -> dict:
    """Punch-list rollup + latest model version — is the project ready for a G704 certification?
    Substantial completion is certified *with* a punch list of remaining items, so the gate is that a
    punch list has been prepared (not that it's 100% complete)."""
    punches = me.list_records(db, "punchlist", pid, limit=100000) if "punchlist" in me.TABLES else []
    roll = closeout.punch_rollup(punches)
    hist = versions.history(db, pid)
    latest = hist[0]["version"] if hist else None
    return {
        "punch": {"count": roll["punch_count"], "verified": roll["verified_count"],
                  "open": roll["open_count"], "complete_pct": roll["complete_pct"],
                  "overdue": roll["overdue_count"], "open_cost": roll["open_cost"]},
        "punch_list_prepared": roll["punch_count"] > 0,
        "latest_model_version": latest,
        "ready_for_substantial_completion": roll["punch_count"] > 0,
    }


def certify(db, pid: str, cert_rid: str, architect: str, owner: str | None = None,
            contractor: str | None = None, occupancy_date: str | None = None,
            actor: str = "system") -> dict:
    """Architect certifies substantial completion on a completion_certificate record: gate on a prepared
    punch list, record the Architect (certifying) + Owner/Contractor signatures, stamp the current model
    version as the record model, and issue the certificate. Returns the updated cert + readiness."""
    if not architect:
        raise ValueError("architect (certifying name) is required")
    r = readiness(db, pid)
    if not r["ready_for_substantial_completion"]:
        raise ValueError("No punch list has been prepared; a G704 certifies substantial completion "
                         "with the outstanding punch list attached.")
    rec = me.get_record(db, _CERT, pid, cert_rid)          # 404 if missing
    data = rec.get("data") or {}
    keep = [s for s in (data.get("signatures") or [])
            if s.get("party") not in ("Architect", "Owner", "Contractor")]
    today = datetime.now(timezone.utc).date().isoformat()
    keep.append({"party": "Architect", "name": architect, "method": "typed",
                 "signed_at": today, "certifies": True})
    if owner:
        keep.append({"party": "Owner", "name": owner, "method": "typed", "signed_at": today})
    if contractor:
        keep.append({"party": "Contractor", "name": contractor, "method": "typed", "signed_at": today})
    patch = {"signatures": keep, "type": "Substantial",
             "record_model_version": r["latest_model_version"],
             "punch_complete_pct": r["punch"]["complete_pct"], "punch_open": r["punch"]["open"],
             "certified_by": architect, "date": data.get("date") or today}
    if occupancy_date:
        patch["occupancy_date"] = occupancy_date
    out = me.update_record(db, _CERT, pid, cert_rid, patch, actor, "Architect")
    if rec.get("workflow_state") == "draft":               # architect sign-off issues the certificate
        try:
            out = me.transition(db, _CERT, pid, cert_rid, "issue", actor, "GC", "architect certified")
        except Exception:                                  # noqa: BLE001 — non-blocking; signatures stand
            pass
    return {"certificate": out, "readiness": r}


def package_status(db, pid: str) -> dict:
    """Turnover summary for the closeout package: substantial-completion cert (signed?), record model
    version, and punch readiness."""
    r = readiness(db, pid)
    certs = me.list_records(db, _CERT, pid, limit=1000) if _CERT in me.TABLES else []
    subs = [c for c in certs if (c.get("data") or {}).get("type") == "Substantial"]
    signed = None
    for c in subs:
        sigs = (c.get("data") or {}).get("signatures") or []
        if any(s.get("party") == "Architect" and s.get("certifies") for s in sigs):
            signed = {"ref": c.get("ref"), "record_model_version": (c.get("data") or {}).get("record_model_version"),
                      "signed_by": [s.get("party") for s in sigs]}
            break
    return {"readiness": r, "substantial_completion": signed,
            "record_model_locked": bool(signed and signed.get("record_model_version") is not None)}
