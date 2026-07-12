"""Shared helpers for the report builders (record fetch + generic log table)."""
from __future__ import annotations

from sqlalchemy.orm import Session

from .. import modules as me
from ..reports_core import Report
from ..reports_core import money as _money


def _records(db: Session, key: str, pid: str) -> list[dict]:
    return me.list_records(db, key, pid, limit=100000) if key in me.TABLES else []


def _log(db: Session, pid: str, name: str, key: str, title: str, cols: list[tuple[str, str]]) -> Report:
    recs = _records(db, key, pid)
    r = Report(title, name)
    r.kpi("Records", len(recs))
    rows = []
    for rec in recs:
        d = rec.get("data") or {}
        row = [rec.get("ref", "")]
        for field, _ in cols:
            v = d.get(field, "")
            row.append(_money(v) if field in ("amount", "value") else str(v))
        row.append(rec.get("workflow_state", ""))
        rows.append(row)
    r.table(title, ["Ref"] + [label for _, label in cols] + ["Status"], rows)
    return r
