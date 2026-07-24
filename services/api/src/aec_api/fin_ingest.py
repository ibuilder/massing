"""FIN-INGEST — actuals reconciliation + import lineage (R19).

Two thin, deterministic layers over machinery that already ships:

- **reconcile(db, pid)** — the budget↔actuals two-way match on the cost-code spine, reusing
  `margin.by_cost_code` (budget / committed / actual / billed): rows split into **matched**
  (both sides present), **budget_only** (a control number with no cost hitting it — scope not
  started, or actuals coded elsewhere), **actuals_only** (cost with no budget line — the classic
  miscoding/scope-gap flag), plus the **uncoded** actual records that carry no cost code at all
  (each with its ref, so they can be fixed). Unmatched is surfaced BOTH ways, never netted.

- **import lineage** — every module import batch is audit-logged (`modules.import`) with the
  source filename, module, row counts, and actor; `import_history(db, pid)` reads it back. The
  period lock (fin_gov) applies to imports automatically because `do_import` posts through
  `modules.create_record` — locked-month rows land in the batch's error list, they don't sneak in.
"""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from . import margin
from . import modules as me
from .models import AuditLog

IMPORT_ACTION = "module.import"      # matches the existing import-route audit action

# actual-cost modules whose rows should carry a cost code (the uncoded scan)
_ACTUAL_MODULES = ("direct_cost", "sub_invoice")


def reconcile(db: Session, pid: str) -> dict[str, Any]:
    rows = margin.by_cost_code(db, pid).get("rows", [])
    matched, budget_only, actuals_only = [], [], []
    for r in rows:
        has_budget = (r.get("budget") or 0) > 0.005
        has_actual = (r.get("actual") or 0) > 0.005 or (r.get("committed") or 0) > 0.005
        slim = {"cost_code": r.get("cost_code"),
                "budget": r.get("budget"), "committed": r.get("committed"),
                "actual": r.get("actual"), "variance": r.get("variance")}
        if has_budget and has_actual:
            matched.append(slim)
        elif has_budget:
            budget_only.append(slim)
        elif has_actual:
            actuals_only.append(slim)
    uncoded: list[dict] = []
    for key in _ACTUAL_MODULES:
        for rec in me.list_records(db, key, pid, limit=100_000):
            d = rec.get("data") or {}
            if not d.get("cost_code") and (d.get("amount") or 0):
                uncoded.append({"module": key, "ref": rec.get("ref"),
                                "amount": d.get("amount"), "vendor": d.get("vendor")})
    # highest-value gaps first — the review order that matters
    actuals_only.sort(key=lambda r: -(r.get("actual") or 0))
    budget_only.sort(key=lambda r: -(r.get("budget") or 0))
    uncoded.sort(key=lambda r: -(r.get("amount") or 0))
    return {
        "matched": matched,
        "budget_only": budget_only,
        "actuals_only": actuals_only,
        "uncoded": uncoded[:200],
        "counts": {"matched": len(matched), "budget_only": len(budget_only),
                   "actuals_only": len(actuals_only), "uncoded": len(uncoded)},
        "fully_reconciled": not actuals_only and not uncoded,
    }


def import_history(db: Session, pid: str, limit: int = 100) -> list[dict[str, Any]]:
    """The project's import batches, newest first — the data-lineage answer to 'where did these
    numbers come from'."""
    q = (db.query(AuditLog).filter(AuditLog.action == IMPORT_ACTION)
         .order_by(AuditLog.ts.desc()).limit(max(1, min(int(limit), 500))))
    out = []
    for row in q.all():
        d = row.detail or {}
        if d.get("project_id") != pid:
            continue
        out.append({"ts": row.ts.isoformat() if row.ts else None, "actor": row.actor,
                    "module": d.get("module"), "filename": d.get("filename"),
                    "imported": d.get("imported"), "error_count": d.get("error_count")})
    return out
