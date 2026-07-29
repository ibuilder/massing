"""R22-CLASSIFY-AI — classification coverage + code proposals for an imported model (project-scoped).

Reads the project's source IFC for the classifications it actually declares, proposes codes for the
rest with their evidence, and turns an explicit list of accepted GUIDs into `set_classification` edit
recipe steps. It never writes: the plan is returned for the caller to apply through the ordinary
authoring path, so a classification always has an author.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import classify_assist as ca
from ..db import get_db
from ..deps import open_source_ifc
from ..rbac import require_role

router = APIRouter()


def _elements(model) -> list[dict]:
    """Index-shaped records straight off the model, so the engine takes the same shape whether it is
    fed the property index or a freshly opened file."""
    import ifcopenshell.util.element as ue

    out = []
    seen: set[int] = set()
    for kls in ("IfcBuildingElement", "IfcElement"):
        try:
            found = model.by_type(kls)
        except RuntimeError:                # class absent from this schema
            continue
        for el in found:
            if el.id() in seen:
                continue
            seen.add(el.id())
            if el.is_a("IfcOpeningElement"):
                # A void is not a thing to classify or price, and `qto.py` skips openings at both of
                # its call sites — so counting them here would make this denominator disagree with
                # the takeoff's. "12% classified" has to mean 12% of what actually gets priced,
                # otherwise the coverage figure and the estimate describe different models.
                #
                # (`ifc_loader.physical_elements` does NOT filter them; the convention lives at the
                # call sites. Following the convention rather than changing the shared helper, which
                # would silently move every existing quantity.)
                continue
            try:
                t = ue.get_type(el)
            except Exception:               # noqa: BLE001 — a broken type relation is not fatal here
                t = None
            out.append({"guid": el.GlobalId, "ifc_class": el.is_a(),
                        "name": getattr(el, "Name", None),
                        "type_name": getattr(t, "Name", None) if t is not None else None})
    return out


@router.get("/projects/{pid}/classify/coverage")
def classify_coverage(pid: str, system: str = Query("masterformat"),
                      db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """How much of the model actually carries a classification code, and what the rest would need.

    **The percentage counts only what the model declares.** Derived codes are proposals and do not
    raise it. A low figure on a client's model is the true starting point of a cost exercise — the
    alternative is the implicit 100% you get from a class map that silently returns its default
    bucket for every unmapped class."""
    try:
        ca.systems()
        model = open_source_ifc(db, pid)
        rows = ca.propose(_elements(model), system, ca.read_declared(model))
    except ca.ClassifyError as e:
        raise HTTPException(422, str(e)) from e
    return {k: v for k, v in rows.items() if k != "rows"}


@router.get("/projects/{pid}/classify/proposals")
def classify_proposals(pid: str, system: str = Query("masterformat"),
                       basis: str | None = Query(None, description="declared|keyword|class_map|unmapped"),
                       limit: int = Query(2000, ge=1, le=20000),
                       db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """One row per element: its code and the evidence for it.

    `basis` says what kind of claim each row is. `class_map` rows are true of the element's CLASS and
    therefore identical for every element of that class — including the ones they are wrong for — so
    they are worth reviewing as a group rather than one at a time. `unmapped` rows have no code at
    all; those are the ones an estimate would silently price in the default bucket."""
    if basis is not None and basis not in ca.BASES:
        raise HTTPException(422, f"unknown basis {basis!r}; known: {', '.join(ca.BASES)}")
    try:
        model = open_source_ifc(db, pid)
        result = ca.propose(_elements(model), system, ca.read_declared(model))
    except ca.ClassifyError as e:
        raise HTTPException(422, str(e)) from e
    rows = result["rows"]
    if basis:
        rows = [r for r in rows if r["basis"] == basis]
    truncated = len(rows) > limit
    return {**{k: v for k, v in result.items() if k != "rows"},
            "rows": rows[:limit], "returned": min(len(rows), limit),
            "matching": len(rows), "truncated": truncated,
            # Say what was cut. A page that stops at the limit and does not mention it reads as the
            # whole set, and the whole set is exactly what a coverage exercise needs to know.
            "truncation_note": (f"{len(rows) - limit} further row(s) matched and are not shown; "
                                "raise ?limit= or filter by ?basis=") if truncated else None}


@router.post("/projects/{pid}/classify/plan")
def classify_plan(pid: str, accept: list[str] = Body(..., embed=True),
                  system: str = Body("masterformat", embed=True),
                  edition: str | None = Body(None, embed=True),
                  db: Session = Depends(get_db), _: str = Depends(require_role("editor"))):
    """Turn an explicit list of accepted GUIDs into `set_classification` recipe steps.

    Returns a plan; it does not apply it. Accepting a proposal is a deliberate act with an author,
    and a classification that appeared on elements because somebody opened a report is
    indistinguishable a week later from one a quantity surveyor decided. Anything that cannot be
    applied comes back in `skipped` **with a reason** rather than being dropped — a plan that
    silently covers 40 of the 60 elements somebody ticked is worse than one that refuses, because
    the other 20 look done."""
    if not accept:
        raise HTTPException(422, "accept must list at least one GlobalId")
    try:
        model = open_source_ifc(db, pid)
        result = ca.propose(_elements(model), system, ca.read_declared(model))
        return ca.apply_plan(result["rows"], accept, system, edition=edition)
    except ca.ClassifyError as e:
        raise HTTPException(422, str(e)) from e
