"""R23-PREFAB-KIT — the prefabrication-kit register (project-scoped).

Joins the `prefab_kit` records to the model index (scope + BOM), the pull-plan task they install
under, and the delivery that has to land first. `POST .../freeze` is the one write: it records the
GlobalId list a released kit is fabricated against.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import model_index, rbac
from .. import modules as me
from .. import prefab_kit as pk
from ..db import get_db
from ..rbac import require_role

router = APIRouter()


def _index(pid: str):
    """The project's property index, or None. None is a first-class answer here — a kit register with
    no model still lists its kits and says that nothing about their scope can be checked, which is
    more useful than a 409 that hides the records."""
    try:
        model_index.ensure_loaded(pid)
    except Exception:                       # noqa: BLE001 — no model uploaded is not an error here
        return None
    return model_index.get_index(pid)


def _by_id(db: Session, key: str, pid: str) -> dict[str, dict]:
    if key not in me.TABLES:
        return {}
    return {str(r.get("id")): r for r in me.list_records(db, key, pid, limit=100000)}


@router.get("/projects/{pid}/prefab/kits")
def prefab_register(pid: str, as_of: str | None = None, limit: int = Query(500, ge=1, le=2000),
                    db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Every prefab kit on the project, worst first, each with its scope, BOM, scope drift and the
    specific things blocking it.

    Kits sort by the severity of their worst blocker rather than by date: a kit whose released scope
    has **drifted** from what the selector now matches outranks one that is merely late, because a
    late kit is a known problem and a drifted one is an unknown wrong one."""
    if "prefab_kit" not in me.TABLES:
        raise HTTPException(404, "the prefab_kit module is not installed")
    kits = me.list_records(db, "prefab_kit", pid, limit=limit)
    return pk.register(kits, _index(pid),
                       tasks_by_id=_by_id(db, "pull_plan_task", pid),
                       deliveries_by_id=_by_id(db, "delivery", pid),
                       today=as_of)


@router.get("/projects/{pid}/prefab/kits/{rid}")
def prefab_kit_detail(pid: str, rid: str, as_of: str | None = None,
                      db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """One kit, fully resolved."""
    kit = me.get_record(db, "prefab_kit", pid, rid)
    d = kit.get("data") or {}
    tasks = _by_id(db, "pull_plan_task", pid)
    dels = _by_id(db, "delivery", pid)
    return pk.assess(kit, _index(pid),
                     pull_task=tasks.get(str(d.get("pull_task") or "")),
                     delivery=dels.get(str(d.get("delivery") or "")),
                     today=as_of)


@router.post("/projects/{pid}/prefab/kits/{rid}/freeze")
def prefab_freeze(pid: str, rid: str, db: Session = Depends(get_db),
                  actor: str = Depends(require_role("editor"))):
    """Freeze the kit's scope: resolve the selector once and write the GlobalId list onto the record.

    This is what makes a released kit a document rather than a query. From here the shop builds the
    frozen list; the selector is only the record of how that list was arrived at, and any later
    divergence between the two is reported by the register instead of silently changing what is being
    fabricated.

    Refuses to freeze an empty, erroring or truncated result — a released kit with nothing frozen is
    precisely the failure this whole mechanism exists to prevent, and it would be indistinguishable
    from a correctly released one on every screen."""
    kit = me.get_record(db, "prefab_kit", pid, rid)
    idx = _index(pid)
    # Ask WHY it cannot be frozen and answer with that constant, rather than calling `freeze()` and
    # stringifying whatever it raised. `str(e)` on a caught exception is the py/stack-trace-exposure
    # sink; every string that can reach the response below is a module-level literal.
    blocker = pk.freeze_blocker(kit, idx)
    if blocker:
        raise HTTPException(422, blocker)
    try:
        frozen = pk.freeze(kit, idx)
    except ValueError:                       # deliberately unbound — a fixed literal, never `e`
        raise HTTPException(422, pk.FREEZE_FAILED) from None
    me.update_record(db, "prefab_kit", pid, rid,
                     {"frozen_guids": frozen["frozen_guids"]}, actor,
                     rbac.party_role_for(db, pid, actor))
    return {"ref": kit.get("ref"), "matched": frozen["matched"],
            "selector": frozen["selector"], "frozen": len(frozen["guids"]),
            "note": "the kit now has a written scope; releasing it hands the shop THIS list"}
