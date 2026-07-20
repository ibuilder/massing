"""Bidding endpoints (preconstruction): bid leveling — tabulate the bid_submission records by
their bid_package and compute low/high/avg/spread + flag the low bidder."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends
from sqlalchemy.orm import Session

from .. import bid_leveling
from .. import itb as itb_engine
from .. import modules as me
from ..db import get_db
from ..rbac import require_role
from ..throttle import rate_limited

router = APIRouter()


@router.get("/projects/{pid}/bidding/itb")
def itb_summary(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """ITB tracking — invited vs responded vs bonded per bid package + coverage gaps."""
    return itb_engine.itb(db, pid)


@router.get("/projects/{pid}/bidding/scope-gap")
def scope_gap_analysis(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """SCOPE-GAP — does every element in the model land in a bid package? Maps the model's takeoff (by
    NCS discipline) against the defined `bid_package` records and flags **gaps** — disciplines present in
    the model with no covering package, i.e. quantities not in any bid (with sample GUIDs to highlight) —
    plus packages whose discipline has no model elements. Distinct from the ITB bid-response coverage.
    409 without a source IFC."""
    from aec_data.qto import takeoff_file  # type: ignore

    from .. import scope_gap
    from ..deps import source_ifc_path as _src

    rows = takeoff_file(_src(db, pid), force_geometry=False)   # 409 if no source IFC; class-only is enough
    return scope_gap.analyze(db, pid, rows)


@router.post("/projects/{pid}/bidding/packages/{rid}/invite")
def invite_bidders(pid: str, rid: str, companies: list[str] = Body(..., embed=True),
                   db: Session = Depends(get_db), user: str = Depends(require_role("editor"))):
    """Invite companies to bid on a package — records the invitee list + invited count on the
    bid_package record (outbound ITB)."""
    rec = me.get_record(db, "bid_package", pid, rid)
    existing = (rec.get("data") or {}).get("invited_companies") or []
    merged = sorted(set(existing) | {c.strip() for c in companies if c.strip()})
    me.update_record(db, "bid_package", pid, rid,
                     {"invited_companies": merged, "bidders_invited": len(merged)}, user, None)
    return {"package": rid, "invited_companies": merged, "bidders_invited": len(merged)}


def _amt(rec: dict) -> float | None:
    v = (rec.get("data") or {}).get("amount")
    try:
        return float(v) if v not in (None, "") else None
    except (TypeError, ValueError):
        return None


@router.get("/projects/{pid}/bids/leveling")
def leveling(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Bid tabulation by package: each package's submissions, low/high/avg/spread, low-bidder flag."""
    packages = me.list_records(db, "bid_package", pid, limit=1_000_000)
    subs = me.list_records(db, "bid_submission", pid, limit=1_000_000)
    by_pkg: dict[str, list[dict]] = {}
    for s in subs:
        by_pkg.setdefault((s.get("data") or {}).get("package"), []).append(s)

    out = []
    for p in packages:
        sl = by_pkg.get(p["id"], [])
        amts = [a for a in (_amt(x) for x in sl) if a is not None]
        low = min(amts) if amts else None
        bids = [{"ref": x.get("ref"), "bidder": (x.get("data") or {}).get("bidder"),
                 "amount": _amt(x), "status": x.get("workflow_state"),
                 "is_low": low is not None and _amt(x) == low} for x in sl]
        out.append({"package": p.get("title") or p.get("ref"), "package_ref": p.get("ref"),
                    "bid_count": len(sl), "low": low, "high": max(amts) if amts else None,
                    "avg": round(sum(amts) / len(amts), 2) if amts else None,
                    "spread": round(max(amts) - low, 2) if len(amts) > 1 else 0.0,
                    "bids": sorted(bids, key=lambda b: (b["amount"] is None, b["amount"] or 0))})
    return {"packages": out, "package_count": len(packages), "bid_count": len(subs)}


_level_throttle = rate_limited("draft", 30)   # AI scope-normalization is an LLM call when enabled


@router.get("/projects/{pid}/bids/leveling/{package_rid}")
async def leveling_detail(pid: str, package_rid: str, db: Session = Depends(get_db),
                          _: str = Depends(require_role("viewer")), __: None = Depends(_level_throttle)):
    """Deep bid leveling for ONE package: base-bid stats + outliers, an apples-to-apples scope matrix
    (who includes/excludes each item), scope-gap detection, and a scope-adjusted low-bid recommendation.
    AI canonicalizes free-text scope phrases when an API key is set; deterministic otherwise."""
    from starlette.concurrency import run_in_threadpool
    subs = [s for s in me.list_records(db, "bid_submission", pid, limit=1_000_000)
            if (s.get("data") or {}).get("package") == package_rid]
    result = await run_in_threadpool(bid_leveling.level, subs)
    pkg = next((p for p in me.list_records(db, "bid_package", pid, limit=1_000_000)
                if p["id"] == package_rid), None)
    result["package"] = (pkg or {}).get("title") or (pkg or {}).get("ref") or package_rid
    return result
