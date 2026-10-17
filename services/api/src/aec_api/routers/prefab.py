"""R23-PREFAB-KIT — the prefabrication-kit register (project-scoped).

Joins the `prefab_kit` records to the model index (scope + BOM), the pull-plan task they install
under, and the delivery that has to land first. `POST .../freeze` is the one write: it records the
GlobalId list a released kit is fabricated against.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from .. import model_events, model_index, rbac
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


def _model_version(pid: str) -> int | None:
    """The project's published model version, or None when it cannot be read.

    PREFAB-FREEZE-RACE. Half of `scope_version`, and the half that moves without anybody touching
    the kit. `model_events.current` already fails open to an in-process view, so a None here means
    the registry itself was unreadable — which must not become "version 0", because a token saying
    *no model published* would then match one saying *could not tell* and the precondition would
    pass across a republish it could not see. An absent reading is absent."""
    try:
        v = model_events.current(pid).get("version")
    except Exception:                       # noqa: BLE001 — a precondition input, never a 500
        return None
    return v if isinstance(v, int) else None


def _modified_iso(rec: dict) -> str | None:
    """A record's `modified_at` in the exact shape `modules.update_record` compares against.

    It normalises with `isoformat()` and falls back to `str()`, so this has to do the same or the
    optimistic lock refuses every write — a precondition that always fails is not a safer one, it
    is an outage that looks like diligence.

    `None` means "I have no pre-image", and `update_record` then skips its comparison rather than
    refusing. Unreachable for a register row, because `create_record` stamps `modified_at` at
    insert — and `scope_version` falls back to `created_at` anyway, so the token still covers such a
    record even where this lock would not."""
    cur = rec.get("modified_at")
    if hasattr(cur, "isoformat"):
        return cur.isoformat()
    return str(cur) if cur else None


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
                       today=as_of, model_version=_model_version(pid))


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
                     today=as_of, model_version=_model_version(pid))


@router.post("/projects/{pid}/prefab/kits/{rid}/freeze")
def prefab_freeze(pid: str, rid: str, if_scope_version: str | None = None,
                  db: Session = Depends(get_db),
                  actor: str = Depends(require_role("editor"))):
    """Freeze the kit's scope: resolve the selector once and write the GlobalId list onto the record.

    This is what makes a released kit a document rather than a query. From here the shop builds the
    frozen list; the selector is only the record of how that list was arrived at, and any later
    divergence between the two is reported by the register instead of silently changing what is being
    fabricated.

    Refuses to freeze an empty, erroring or truncated result — a released kit with nothing frozen is
    precisely the failure this whole mechanism exists to prevent, and it would be indistinguishable
    from a correctly released one on every screen.

    **`if_scope_version` is MANDATORY, and the mandate is the point.** PREFAB-FREEZE-RACE: this
    route resolves the selector at write time, so without a precondition a model republished or a
    selector edited between the confirmation and the POST writes a list the person never saw. PR
    #524 shipped the DETECTION half — the client compares the count it confirmed against the count
    written and says when they differ — and detection arrives after the record a shop fabricates
    from already holds the wrong list.

    Mandatory rather than opt-in, which is the opposite of `modules.update_record`'s
    `expected_modified_at`, deliberately: that mechanism serves 139 registers and many callers, so
    opting in is the only shape available to it, and the measured consequence is that *one of five
    web call sites passes it*. This route has one caller and one write, and an optional precondition
    here would leave the defect exactly as it is for anybody who omits it.

    **It is enforced HERE and the OpenAPI document therefore calls it optional, which is a real
    discrepancy and is named rather than papered over.** Declaring it `Query(...)` would mark it
    required in the schema and hand the refusal to FastAPI's validator, which answers **422** — the
    code this route already uses for "the scope itself cannot be frozen". A forgotten token would
    then arrive wearing the costume of `FREEZE_NO_MATCH` and the client would tell somebody to
    narrow a selector that is fine. So the three refusals get one code each — **400** you did not
    state what you were shown, **409** what you were shown has moved, **422** the scope cannot be
    frozen — and the cost is a `required: false` in a generated document. The cost is small because
    the only consumer is `api/prefab.ts`, whose `prefabFreeze(pid, rid, scopeVersion)` takes the
    token as a positional `string`: TypeScript refuses the call that the schema would permit. A
    generated client built from the document alone would be told it may omit the parameter, learn
    otherwise from one 400, and the 400 says exactly what to send.

    Three codes, three conditions, every message a module-level literal — no text in any response
    here derives from a caught exception (py/stack-trace-exposure)."""
    if not (if_scope_version or "").strip():
        raise HTTPException(400, pk.FREEZE_NO_SCOPE_VERSION)
    kit = me.get_record(db, "prefab_kit", pid, rid)
    # The precondition comes FIRST. Answering "the selector matches no elements" about a kit whose
    # selector has been edited since the reader saw it is a true sentence about a different kit, and
    # it reads as a verdict on the one they were looking at.
    if pk.scope_version(kit, _model_version(pid)) != if_scope_version:
        raise HTTPException(409, pk.FREEZE_STALE_SCOPE)
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
    # Re-check the MODEL half after resolving. `kit` has not been re-read, so the record half of the
    # token is unchanged here by construction — that half is closed below by `expected_modified_at`,
    # atomically, rather than by a second comparison.
    #
    # **What this catches is NOT "the resolve returned something different", and the first draft of
    # this comment said it was.** `model_index.load` rebinds `_INDEX[pid]` to a NEW dict, so the
    # `idx` captured above is a stable snapshot: a republish mid-request cannot change what
    # `resolve()` just returned. What it changes is what that answer is ABOUT. The list would be
    # internally consistent and derived from a superseded model, and `drift()` would then compare it
    # against the current one — a frozen scope that reads as drifted the instant it is written.
    # *A guard whose stated reason is wrong is a guard the next reader deletes.*
    #
    # And this NARROWS the window rather than closing it, said plainly because a narrowing described
    # as a closure is the overstatement this codebase keeps catching: a republish after THIS read is
    # still unguarded. The only closure is a lock around read-resolve-write. `pid_lock.mutating(pid)`
    # exists for it and is NOT taken here, because it would add a wait-timeout failure mode to the
    # one write this item exists to make trustworthy, and the writers it serialises against are the
    # authoring routes rather than every path that can re-ingest a model. The remaining window is
    # microseconds inside one request; the window this item is about is the minutes a person spends
    # reading a confirmation dialog, and the token closes that one completely.
    if pk.scope_version(kit, _model_version(pid)) != if_scope_version:
        raise HTTPException(409, pk.FREEZE_STALE_SCOPE)
    me.update_record(db, "prefab_kit", pid, rid,
                     {"frozen_guids": frozen["frozen_guids"]}, actor,
                     rbac.party_role_for(db, pid, actor),
                     # The record half, closed atomically instead of checked. `update_record`
                     # compares this INSIDE its retry, so a kit edited between the token check above
                     # and this write is refused rather than overwritten. Its own 409 carries a dict
                     # detail, which `httpCore.json` cannot surface as a sentence — the client's
                     # recovery is the same for both (re-read, re-confirm), so the status is what it
                     # acts on.
                     expected_modified_at=_modified_iso(kit))
    return {"ref": kit.get("ref"), "matched": frozen["matched"],
            "selector": frozen["selector"], "frozen": len(frozen["guids"]),
            # The token the NEXT write must echo. A client that re-froze from the version it sent
            # would be refused by the check above — the write bumped `modified_at` — so handing the
            # new one back saves a read that would otherwise be mandatory.
            "scope_version": pk.scope_version(
                me.get_record(db, "prefab_kit", pid, rid), _model_version(pid)),
            "note": "the kit now has a written scope; releasing it hands the shop THIS list"}
