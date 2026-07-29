"""R23-RECIPE-ARTIFACT — the edit-recipe log: read it, diff it, export it, replay it.

Its own router rather than more of `authoring.py`, which is already the app's largest write surface.
The capture side lives there (four call sites beside the existing `edit_history.push`); everything
read-only lives here.
"""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import recipe_log
from ..db import get_db
from ..rbac import require_role

router = APIRouter()


def _guard(fn, *a, **k):
    """Map an unreadable log to a 409 rather than a 500 — and say the file is intact.

    The alternative the module used to have was to report an EMPTY log, which is worse than an
    error: it reads as "this project has no history" and the next edit would have written that
    emptiness back."""
    try:
        return fn(*a, **k)
    except recipe_log.LogUnreadable as e:
        raise HTTPException(409, str(e)) from e



@router.get("/projects/{pid}/recipes/log")
def recipe_log_read(pid: str, limit: int = Query(200, ge=1, le=2000), offset: int = Query(0, ge=0),
                    recipe: str | None = None,
                    db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """The edit-recipe log, newest first — recipe, parameters, actor, time, and the source files it
    ran between.

    The parameters are the part that did not exist before: the audit log records an edit's *outputs*
    and the undo stack records *file paths*, so nothing kept what an edit was actually asked to do.
    Without the inputs there is no replay, no diff and no provenance trail worth the name."""
    return _guard(recipe_log.log, pid, limit=limit, offset=offset, recipe=recipe)


@router.get("/projects/{pid}/recipes/export")
def recipe_log_export(pid: str, db: Session = Depends(get_db),
                      _: str = Depends(require_role("viewer"))):
    """The whole log as a portable document, **oldest first** — the provenance artifact.

    Oldest-first because it is meant to be read as a sequence of operations, and because that is the
    order a replay needs. `/recipes/log` is newest-first because that is the order a person reads a
    history in. Both orders are stated in their payloads rather than left to be discovered."""
    return _guard(recipe_log.export, pid)


@router.get("/projects/{pid}/recipes/diff")
def recipe_log_diff(pid: str, a: int = Query(..., ge=0), b: int = Query(..., ge=0),
                    db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Compare two log entries by their index in the export (oldest-first) order.

    Only meaningful for two runs of the same recipe, and that is checked rather than assumed — the
    parameter names of `add_wall` and `set_pset` are not the same vocabulary, and a key-by-key
    comparison across them would report every field as changed and mean nothing."""
    entries = _guard(recipe_log.export, pid)["entries"]
    for i in (a, b):
        if i >= len(entries):
            raise HTTPException(404, f"entry {i} is outside the log ({len(entries)} entr(ies))")
    return recipe_log.diff(entries[a], entries[b])


@router.post("/projects/{pid}/recipes/replay-plan")
def recipe_replay_plan(pid: str, indices: list[int] | None = Body(None, embed=True),
                       db: Session = Depends(get_db), _: str = Depends(require_role("editor"))):
    """Ordered `{recipe, params}` steps to re-run the logged edits against another model.

    Returns a **plan**, and does not execute it. Re-running a sequence of authoring edits is exactly
    the kind of thing that should carry one author and one audit row, and a log that could re-run
    itself would carry neither — apply the steps through `POST /projects/{pid}/edit/batch`.

    Refuses if any selected entry had parameters elided for size. Replaying with the stored
    descriptor in place of the value would call the recipe with something that *resembles* the
    original argument and is not it, which is the one outcome a provenance feature must never
    produce. The refusal names the entries so the caller knows which edits cannot be reproduced."""
    entries = _guard(recipe_log.export, pid)["entries"]
    try:
        return recipe_log.replay_plan(entries, indices=indices)
    except recipe_log.ReplayError as e:
        raise HTTPException(422, str(e)) from e
