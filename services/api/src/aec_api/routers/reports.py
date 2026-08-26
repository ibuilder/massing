"""Report Center endpoints — catalog + per-report PDF / Excel export."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy.orm import Session

from .. import reports
from ..db import get_db
from ..rbac import current_user, require_role
from .exports import _xlsx_response

router = APIRouter()


@router.get("/reports")
def report_catalog(_: str = Depends(current_user)):
    """The available reports (id, name, group) for the Reports panel."""
    return {"reports": reports.catalog()}


@router.get("/projects/{pid}/reports/catalog")
def project_report_catalog(pid: str, db: Session = Depends(get_db),
                           user: str = Depends(require_role("viewer"))):
    """Every report available in THIS project — built-in and saved — in one list.

    R22-REPORT-BUILDER item 5. `reports.REPORTS` and the saved-view layer were two registries that
    knew nothing about each other, rendered in different panels. The entry's worry was that growing
    the module query surface would ship *"a second way to make a report, sitting beside the one users
    already have"*, and asked for them to be unified **or** for the separation to be a deliberate,
    recorded decision.

    **The decision is: they stay separate implementations behind ONE surface**, because they are not
    the same kind of thing and pretending otherwise would cost more than it buys.

    * A built-in report is **code** — Earned Value, the WIP schedule, a tri-approach appraisal. These
      compute things no query builder expresses; folding them into saved views would mean either a
      query language that can do EVM (it cannot) or 56 rows of config that secretly dispatch to
      Python (a registry with extra steps).
    * A saved view is **data** — a user's query, authored without an engineering ticket, and the
      whole point of R22-REPORT-BUILDER is that it needs no code to exist.

    What was genuinely wrong was never the two implementations; it was that a user asking *"what
    reports do I have here?"* got two unrelated answers from two panels. This route is the one answer.
    `kind` is explicit rather than inferred, because the two differ in what a caller may do with them
    — a built-in renders to PDF at a fixed path, a saved view is replayed against its module — and a
    UI that guesses that from the shape of an id will guess wrong.
    """
    out = [{"kind": "built_in", "id": r["id"], "name": r["name"], "group": r.get("group"),
            "module": None, "scope": "project", "owner": None}
           for r in reports.catalog()]
    from sqlalchemy import or_

    from ..models import SavedView
    rows = (db.query(SavedView)
            .filter(SavedView.project_id == pid,
                    or_(SavedView.user == user, SavedView.scope == "project"))
            .order_by(SavedView.created_at).all())
    out += [{"kind": "saved_view", "id": v.id, "name": v.name,
             "group": "Saved views", "module": v.module,
             "scope": v.scope or "private", "owner": v.user, "mine": v.user == user}
            for v in rows]
    return {"reports": out, "built_in": sum(1 for r in out if r["kind"] == "built_in"),
            "saved": sum(1 for r in out if r["kind"] == "saved_view")}


@router.get("/projects/{pid}/reports/{report}.pdf")
def report_pdf(pid: str, report: str, db: Session = Depends(get_db),
               _: str = Depends(require_role("viewer"))):
    try:
        rep = reports.build(db, pid, report)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return Response(reports.to_pdf(rep), media_type="application/pdf",
                    headers={"Content-Disposition": f'inline; filename="{report}.pdf"'})


@router.get("/projects/{pid}/reports/{report}.xlsx")
def report_xlsx(pid: str, report: str, db: Session = Depends(get_db),
                _: str = Depends(require_role("viewer"))):
    try:
        rep = reports.build(db, pid, report)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return _xlsx_response(reports.to_sheets(rep), f"{report}.xlsx")
