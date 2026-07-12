"""Disposition & valuation endpoints — auto-fill a listing from the project, the tri-approach
appraisal, the RESO export seam (bridge to WPRealWise / MLS), and a signed, read-only public listing
link for sharing a 3D tour / fact sheet without a session."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Query, Request
from sqlalchemy.orm import Session

from .. import (
    capital,
    comps,
    distwaterfall,
    leasemgmt,
    marketing,
    rbac,
    re_bridge,
    rentroll,
    securities_bridge,
    signing,
)
from .. import modules as me
from ..db import get_db
from ..models import Project

router = APIRouter()


def _investors(db: Session, pid: str) -> list[dict]:
    return me.list_records(db, "investor", pid, limit=100000) if "investor" in me.TABLES else []


@router.get("/projects/{pid}/cap-table")
def cap_table(pid: str, db: Session = Depends(get_db), _: str = Depends(rbac.require_role("viewer"))):
    """Investor cap table — ownership by commitment + contributed/distributed/unreturned totals."""
    return capital.cap_table(_investors(db, pid))


def _allocate(db: Session, pid: str, amount: float, kind: str, persist: bool, user: str) -> dict:
    """Allocate pro-rata; when persist=True, post each allocation to the investor's contributed
    (call) or distributed (distribution) running total so the cap table tracks over time."""
    result = capital.allocate(_investors(db, pid), amount, kind=kind)
    if persist:
        field = "contributed" if kind == "call" else "distributed"
        for a in result["allocations"]:
            if not a.get("id"):
                continue
            rec = me.get_record(db, "investor", pid, a["id"])
            cur = float((rec.get("data") or {}).get(field) or 0.0)
            me.update_record(db, "investor", pid, a["id"], {field: round(cur + a["amount"], 2)}, user, None)
        result["persisted"] = True
    return result


@router.post("/projects/{pid}/capital-call")
def capital_call(pid: str, amount: float = Body(..., embed=True), persist: bool = Body(False, embed=True),
                 db: Session = Depends(get_db), user: str = Depends(rbac.require_role("editor"))):
    """Allocate a capital call pro-rata by commitment. persist=true posts it to each investor's
    contributed total; otherwise it's a preview."""
    return _allocate(db, pid, amount, "call", persist, user)


@router.post("/projects/{pid}/distribution")
def distribution(pid: str, amount: float = Body(..., embed=True), persist: bool = Body(False, embed=True),
                 db: Session = Depends(get_db), user: str = Depends(rbac.require_role("editor"))):
    """Allocate a distribution pro-rata by commitment. persist=true posts it to each investor's
    distributed total; otherwise it's a preview."""
    return _allocate(db, pid, amount, "distribution", persist, user)


@router.post("/projects/{pid}/waterfall")
def waterfall_scenario(pid: str, body: dict = Body(default={}), db: Session = Depends(get_db),
                       _: str = Depends(rbac.require_role("viewer"))):
    """Run a distribution / equity-waterfall scenario over the cap table. Body: {distributable:[..],
    dates:[..]} or {exit_amount, contribution_date, exit_date}; optional pref_rate/tiers/style/clawback.
    Returns LP/GP totals, IRR/EM, period splits, and the per-investor allocation."""
    return distwaterfall.scenario(db, pid, body)


def _statement_pdf(db: Session, pid: str, iid: str) -> tuple[bytes, str]:
    """Build an investor's capital-account statement PDF. Returns (pdf_bytes, ref). 404 if missing."""
    rec = me.get_record(db, "investor", pid, iid)            # 404 if missing
    ct = capital.cap_table(_investors(db, pid))
    row = next((r for r in ct["rows"] if r["ref"] == rec.get("ref")), None)
    if not row:
        raise HTTPException(404, "investor not in cap table")
    row["entity_type"] = (rec.get("data") or {}).get("entity_type")
    p = db.get(Project, pid)
    return capital.statement_pdf(row, ct, p.name if p else pid), str(rec.get("ref"))


def _pdf_response(pdf: bytes, ref: str):
    from fastapi.responses import Response as _Resp
    return _Resp(pdf, media_type="application/pdf",
                 headers={"Content-Disposition": f'inline; filename="statement_{ref}.pdf"'})


@router.get("/projects/{pid}/investors/{iid}/statement.pdf")
def investor_statement(pid: str, iid: str, db: Session = Depends(get_db),
                       _: str = Depends(rbac.require_role("viewer"))):
    """A one-page investor capital-account statement PDF."""
    pdf, ref = _statement_pdf(db, pid, iid)
    return _pdf_response(pdf, ref)


@router.post("/projects/{pid}/investors/{iid}/share")
def investor_statement_share(pid: str, iid: str, ttl: int = Query(30 * 24 * 3600, ge=60),
                             db: Session = Depends(get_db), _: str = Depends(rbac.require_role("viewer"))):
    """Mint a signed, expiring link to an investor's statement PDF — the investor opens it with no
    session (the LP-portal share). Default TTL 30 days. The signature authorizes exactly that path."""
    me.get_record(db, "investor", pid, iid)                  # 404 if missing
    path = f"/projects/{pid}/investors/{iid}/statement.public.pdf"
    return signing.sign_path(path, ttl=ttl)


@router.get("/projects/{pid}/investors/{iid}/statement.public.pdf")
def investor_statement_public(pid: str, iid: str, request: Request, db: Session = Depends(get_db)):
    """Read-only investor statement behind a valid signed link (HMAC) — no session required.
    Publishes only this investor's own capital-account statement."""
    qp = request.query_params
    if not signing.verify_path(request.url.path, qp.get("sig"), qp.get("exp")):
        raise HTTPException(403, "a valid signed link is required")
    pdf, ref = _statement_pdf(db, pid, iid)
    return _pdf_response(pdf, ref)


@router.get("/projects/{pid}/rent-roll")
def get_rent_roll(pid: str, db: Session = Depends(get_db),
                  _: str = Depends(rbac.require_role("viewer"))):
    """Operating rent roll — occupancy, WALT, lease-expiration schedule + in-place income from the
    `lease` module (the hold phase). Feeds the appraisal income approach (`/appraisal?rentroll=1`)."""
    return rentroll.rent_roll(db, pid)


@router.get("/projects/{pid}/leases/management")
def lease_management(pid: str, years: int = 5, recoverable_opex: float | None = None,
                     db: Session = Depends(get_db), _: str = Depends(rbac.require_role("viewer"))):
    """Lease-management depth — renewal/expiration pipeline, forward rent-escalation schedule, and
    CAM/expense-recovery reconciliation (pass ?recoverable_opex= for the recovery ratio + gap)."""
    return leasemgmt.lease_management(db, pid, years, recoverable_opex)


@router.get("/projects/{pid}/listings/autofill")
def listing_autofill(pid: str, db: Session = Depends(get_db),
                     _: str = Depends(rbac.require_role("viewer"))):
    """Pre-populated listing fields from the project's proforma + model (the off-plan advantage)."""
    return {"data": marketing.autofill_listing(db, pid)}


@router.post("/projects/{pid}/comparables/import")
def import_comparables(pid: str, body: dict = Body(...), db: Session = Depends(get_db),
                       user: str = Depends(rbac.require_role("editor"))):
    """Bulk-import comparables from CSV (`{csv}`) or a RESO array (`{reso|rows}`) into the `comparable`
    module — feeds the sales-comparison appraisal. Forgiving header mapping; rows without an address
    are skipped. Returns the created count + the parsed rows."""
    parsed = comps.parse(body)
    created = []
    for data in parsed:
        rec = me.create_record(db, "comparable", pid, {"data": data}, user, None)
        created.append({"id": rec.get("id"), "ref": rec.get("ref"), "address": data.get("address")})
    return {"imported": len(created), "rows": created}


@router.get("/projects/{pid}/appraisal")
def get_appraisal(pid: str, request: Request, db: Session = Depends(get_db),
                  _: str = Depends(rbac.require_role("viewer"))):
    """Tri-approach valuation. Saved overrides (project.dev_property.appraisal) merge with any query
    overrides (query wins): depreciation_pct, land_value, replacement_cost_new, stabilized_noi,
    cap_rate, subject_sqft, weight_income, weight_cost, weight_sales."""
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    saved = (p.dev_property or {}).get("appraisal") or {}
    overrides = dict(saved)
    qp = request.query_params
    for k in ("depreciation_pct", "land_value", "replacement_cost_new", "stabilized_noi",
              "cap_rate", "subject_sqft", "subject_units"):
        if qp.get(k) not in (None, ""):
            try:
                overrides[k] = float(qp[k])
            except ValueError:
                pass
    weights = {}
    for wk, qk in (("income", "weight_income"), ("cost", "weight_cost"),
                   ("sales_comparison", "weight_sales")):
        if qp.get(qk) not in (None, ""):
            try:
                weights[wk] = float(qp[qk])
            except ValueError:
                pass
    if weights or saved.get("weights"):
        overrides["weights"] = {**(saved.get("weights") or {}), **weights}
    # income approach can value off the *actual* rent roll's in-place income instead of the proforma
    if qp.get("rentroll") == "1":
        overrides["stabilized_noi"] = rentroll.rent_roll(db, pid).get("in_place_gross_income", 0.0)
    return marketing.compute_appraisal(db, pid, overrides)


@router.post("/projects/{pid}/appraisal")
def save_appraisal(pid: str, overrides: dict = Body(...), db: Session = Depends(get_db),
                   _: str = Depends(rbac.require_role("editor"))):
    """Persist appraisal overrides (depreciation, land value, weights, …) on the project."""
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    p.dev_property = {**(p.dev_property or {}), "appraisal": overrides}
    db.commit()
    return marketing.compute_appraisal(db, pid, overrides)


@router.get("/projects/{pid}/listings/{lid}/reso")
def listing_reso(pid: str, lid: str, db: Session = Depends(get_db),
                 _: str = Depends(rbac.require_role("viewer"))):
    """The RESO Data Dictionary payload for a listing — the shape a bridge POSTs to WPRealWise / MLS."""
    rec = me.get_record(db, "listing", pid, lid)
    return {"reso": marketing.to_reso(rec)}


@router.get("/re-syndication/status")
def re_syndication_status(_: str = Depends(rbac.current_user)):
    """Whether the WPRealWise / MLS syndication bridge is configured (off unless REALWISE_URL+key set)."""
    return re_bridge.status()


@router.post("/projects/{pid}/listings/{lid}/syndicate")
def listing_syndicate(pid: str, lid: str, db: Session = Depends(get_db),
                      _: str = Depends(rbac.require_role("editor"))):
    """Push a listing (RESO-serialized) into WPRealWise / an MLS. Requires the bridge to be configured;
    422 with an actionable message otherwise. The RESO export endpoint works regardless."""
    rec = me.get_record(db, "listing", pid, lid)                 # 404 if missing
    reso = marketing.to_reso(rec)
    try:
        return re_bridge.syndicate(reso, rec.get("ref"))
    except (RuntimeError, NotImplementedError) as e:
        raise HTTPException(422, str(e))


def _syndication_package(db: Session, pid: str) -> dict:
    """Build the neutral syndication package from the cap table. Always available offline."""
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    ct = capital.cap_table(_investors(db, pid))
    disclosures = (p.dev_property or {}).get("offering") or {}
    return securities_bridge.syndication_payload(p.name, ct, disclosures)


@router.get("/projects/{pid}/securities/package")
def securities_package(pid: str, db: Session = Depends(get_db),
                       _: str = Depends(rbac.require_role("viewer"))):
    """The syndication package (cap table → neutral investor-platform schema). This is the payload the
    capital-markets bridge pushes; it exports the same JSON regardless of whether the bridge is wired."""
    return _syndication_package(db, pid)


@router.get("/securities-syndication/status")
def securities_syndication_status(_: str = Depends(rbac.current_user)):
    """Whether the capital-markets syndication bridge is configured (off unless a platform URL+key set).
    This connector syncs the investor ledger only and never moves money."""
    return securities_bridge.status()


@router.post("/projects/{pid}/securities/syndicate")
def securities_syndicate(pid: str, db: Session = Depends(get_db),
                         _: str = Depends(rbac.require_role("admin"))):
    """Sync the cap table into the configured investor / digital-securities platform (positions only —
    no funds move). Requires the bridge to be configured; 422 with an actionable message otherwise. The
    package export endpoint works regardless."""
    package = _syndication_package(db, pid)
    try:
        return securities_bridge.syndicate(package, pid)
    except (RuntimeError, NotImplementedError) as e:
        raise HTTPException(422, str(e))


@router.post("/projects/{pid}/listings/{lid}/share")
def listing_share(pid: str, lid: str, ttl: int = Query(7 * 24 * 3600, ge=60),
                  db: Session = Depends(get_db), _: str = Depends(rbac.require_role("viewer"))):
    """Mint a signed, expiring URL to the public listing JSON (for a QR / shared link). The signature
    authorizes exactly that path until it expires — no session needed by the recipient."""
    me.get_record(db, "listing", pid, lid)                       # 404 if missing
    path = f"/projects/{pid}/listings/{lid}/public"
    return signing.sign_path(path, ttl=ttl)


@router.get("/projects/{pid}/listings/{lid}/public")
def listing_public(pid: str, lid: str, request: Request, db: Session = Depends(get_db)):
    """Read-only public listing — the only intentionally-anonymous surface. Requires a valid signed
    URL (HMAC) regardless of RBAC; publishes only listing-safe fields (no internal financials beyond
    what the owner put in the public description / asking price)."""
    qp = request.query_params
    if not signing.verify_path(request.url.path, qp.get("sig"), qp.get("exp")):
        raise HTTPException(403, "a valid signed link is required")
    rec = me.get_record(db, "listing", pid, lid)
    d = rec.get("data") or {}
    public_fields = ("address", "asset_type", "list_price", "city", "state", "zip_code",
                     "beds", "baths", "sqft", "num_units", "year_built", "price_psf",
                     "public_description", "virtual_tour_url", "highlights")
    return {
        "ref": rec.get("ref"),
        "status": rec.get("workflow_state"),
        "listing": {k: d.get(k) for k in public_fields if d.get(k) not in (None, "")},
    }
