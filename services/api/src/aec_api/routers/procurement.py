"""Materials procure-to-pay endpoints — quote leveling, 3-way match, RFQ-dispatch status."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from .. import procurement, procurement_bridge
from ..db import get_db
from ..rbac import current_user, require_role

router = APIRouter()


@router.post("/projects/{pid}/procurement/level-quotes")
def level_quotes(pid: str, quotes: list[dict] = Body(..., embed=True), record: bool = False,
                 db: Session = Depends(get_db), actor: str = Depends(require_role("viewer"))):
    """Level competing material quotes into an apples-to-apples grid + low price per line + best supplier.
    Body: {quotes:[{supplier, lines:[{item, qty, unit, unit_price}]}]}. With `record=true` (editor),
    every priced line is also written to the price-observation ledger (source="quote")."""
    out = procurement.level_quotes(quotes)
    if record:
        # recording writes records — editor, not viewer (mirrors require_role incl. the RBAC-off bypass)
        from fastapi import HTTPException

        from .. import rbac
        if rbac.RBAC_ON:
            role = rbac.role_for(db, pid, actor)
            if role is None or rbac.ROLE_ORDER.get(role, -1) < rbac.ROLE_ORDER["editor"]:
                raise HTTPException(403, f"record=true requires editor on project "
                                         f"(user {actor!r} has {role or 'no'} role)")
        out["recorded_observations"] = procurement.record_quote_observations(db, pid, quotes, actor)
    return out


@router.post("/projects/{pid}/procurement/buyout-packages")
def buyout_packages(pid: str, payload: dict = Body(default={}),
                    _: str = Depends(require_role("viewer"))):
    """PROCURE-LEVEL: group QTO line items into buyout packages (each with an RFQ scope to send out).
    Body: {qto_lines:[{item, qty, unit, trade?/csi?/material_class?, unit_price?, cost?}], by?}."""
    return procurement.buyout_packages(payload.get("qto_lines") or [], payload.get("by") or "trade")


@router.post("/projects/{pid}/procurement/level")
def level(pid: str, payload: dict = Body(...), _: str = Depends(require_role("viewer"))):
    """PROCURE-LEVEL: score returned quotes for one buyout package against its RFQ scope on a normalized
    basis — price (extended over scope qty), coverage completeness, and lead time → a composite [0,1] score
    ranking the suppliers, with each one's scope gaps. Body: {scope:[{item, qty, unit}],
    quotes:[{supplier, lead_time_days?, lines:[{item, qty, unit, unit_price}]}], weights?}."""
    return procurement.score_quotes(payload.get("scope") or [], payload.get("quotes") or [],
                                    payload.get("weights"))


@router.get("/projects/{pid}/procurement/price-history")
def price_history(pid: str, material: str | None = None, db: Session = Depends(get_db),
                  _: str = Depends(require_role("viewer"))):
    """PROC-LOOP: the price-observation ledger per material — min/median/avg/max, the latest
    observation, vendors seen, latest-vs-median drift, and a spark series."""
    return procurement.price_history(db, pid, material)


@router.post("/projects/{pid}/procurement/material-request/suggest")
def material_request_suggest(pid: str, payload: dict = Body(default={}),
                             db: Session = Depends(get_db),
                             actor: str = Depends(require_role("editor"))):
    """PROC-LOOP: turn a model selection into per-class material-request suggestions from the QTO
    takeoff (volume → m3, area → m2, else count). Body: `{q: "<QUERY-DSL>"}` and/or
    `{guids: [...]}`; omit both to suggest over the whole model. `create=true` also creates
    `material_request` records (state `requested`) keyed to the GUIDs."""
    from fastapi import HTTPException

    from aec_data import qto  # type: ignore

    from .. import modules as me
    from .. import query_dsl
    from ..deps import source_ifc_path

    guids: set[str] | None = set(payload.get("guids") or []) or None
    q = payload.get("q")
    if q is not None:                                 # an explicit empty selector is a 422, not "whole model"
        from .properties import _INDEX, _ensure_loaded
        try:
            _ensure_loaded(pid)
        except Exception:                             # noqa: BLE001 — no index → selector matches nothing
            pass
        try:
            sel = set(query_dsl.select(_INDEX.get(pid), str(q), limit=20000)["guids"])
        except query_dsl.QueryError as e:
            raise HTTPException(422, f"bad selector: {e}")
        guids = (guids & sel) if guids else sel
    rows = qto.takeoff_file(source_ifc_path(db, pid))
    suggestions = procurement.suggest_material_requests(rows, guids)
    created = []
    if payload.get("create") and "material_request" in me.TABLES:
        for s in suggestions[:50]:
            rec = me.create_record(db, "material_request", pid, {"data": {
                "material": s["material"], "qty": s["qty"], "unit": s["unit"],
                "needed_by": payload.get("needed_by"),
                "guids": " ".join(g for g in s["guids"][:200] if g)}}, actor, None)
            created.append(rec["id"])
    return {"suggestions": suggestions, "created": created}


@router.get("/projects/{pid}/procurement/three-way-match")
def three_way_match(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Reconcile each PO (commitment) against its deliveries and invoices — flags over-billing,
    pay-before-receipt, and un-invoiced deliveries."""
    return procurement.three_way_match(db, pid)


@router.get("/procurement/rfq-status")
def rfq_status(_: str = Depends(current_user)):
    """Whether RFQ dispatch to suppliers is configured (else quote leveling + 3-way match still work)."""
    return procurement_bridge.status()
