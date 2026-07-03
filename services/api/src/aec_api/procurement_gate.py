"""Procurement compliance gate — can a subcontractor bid or bill yet, and who needs a nudge.

The discipline that keeps a GC out of trouble: a sub shouldn't be invited to bid without an approved
prequalification and current insurance, and shouldn't be paid without an executed subcontract, current
insurance, and (collected at payment) a lien waiver. This engine reads the COI, prequalification,
subcontract and lien-waiver records to answer, per vendor, "can bid / can bill" with the specific
blockers — and produces the outbound nudge list of expiring or missing compliance documents. It never
moves money (that stays behind the flagged licensed-rail bridge); it gates on paperwork."""
from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from . import modules as me


def _d(rec: dict) -> dict:
    return rec.get("data") or {}


def _date(v) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10]) if v else None
    except ValueError:
        return None


def _vendor(rec: dict, *keys: str) -> str:
    d = _d(rec)
    for k in keys:
        v = (d.get(k) or "").strip()
        if v:
            return v
    return ""


def _coi_status(cois: list[dict], vendor: str, today: date) -> dict:
    latest = None
    for c in cois:
        if _vendor(c, "vendor") == vendor:
            exp = _date(_d(c).get("expires"))
            if latest is None or (exp and (_date(_d(latest).get("expires")) or date.min) < exp):
                latest = c
    if latest is None:
        return {"status": "missing", "expires": None}
    exp = _date(_d(latest).get("expires"))
    active = latest.get("workflow_state") in ("active", "open") and (exp is None or exp >= today)
    expiring = exp is not None and today <= exp <= today + timedelta(days=30)
    return {"status": "active" if active else "expired", "expires": exp.isoformat() if exp else None,
            "expiring_soon": expiring}


def gate(db, pid: str, vendor: str) -> dict[str, Any]:
    """Compliance readiness for one vendor: can they be invited to bid, and can they be paid."""
    today = date.today()
    cois = me.list_records(db, "coi", pid, limit=10000)
    prequals = me.list_records(db, "prequalification", pid, limit=10000)
    subs = me.list_records(db, "subcontract", pid, limit=10000)
    waivers = me.list_records(db, "lien_waiver", pid, limit=10000)

    coi = _coi_status(cois, vendor, today)
    pq = next((p for p in prequals if _vendor(p, "company") == vendor), None)
    pq_ok = bool(pq and pq.get("workflow_state") == "approved"
                 and (not _date(_d(pq).get("expires")) or _date(_d(pq).get("expires")) >= today))
    sub = next((s for s in subs if _vendor(s, "vendor", "vendor_company") == vendor), None)
    sub_executed = bool(sub and sub.get("workflow_state") == "executed")
    waiver = next((w for w in waivers if _vendor(w, "vendor") == vendor
                   and w.get("workflow_state") in ("received", "closed")), None)

    bid_blockers = []
    if not pq_ok:
        bid_blockers.append("no approved prequalification")
    if coi["status"] != "active":
        bid_blockers.append(f"insurance {coi['status']}")
    bill_blockers = []
    if not sub_executed:
        bill_blockers.append("no executed subcontract")
    if coi["status"] != "active":
        bill_blockers.append(f"insurance {coi['status']}")
    return {
        "vendor": vendor,
        "coi": coi,
        "prequal": {"status": "approved" if pq_ok else (pq.get("workflow_state") if pq else "missing")},
        "subcontract": {"executed": sub_executed},
        "waiver_on_file": waiver is not None,
        "can_bid": not bid_blockers, "bid_blockers": bid_blockers,
        "can_bill": not bill_blockers, "bill_blockers": bill_blockers,
        "note": "Bid gate = approved prequal + active insurance. Bill gate = executed subcontract + "
                "active insurance (lien waiver is collected at payment).",
    }


def compliance_feed(db, pid: str, within_days: int = 30) -> dict[str, Any]:
    """The outbound nudge list: every vendor with an expiring/expired/missing COI or an open bill
    gate, so the GC can chase the paperwork before it blocks a bid or a pay app."""
    vendors: set[str] = set()
    for key, keys in (("subcontract", ("vendor", "vendor_company")), ("coi", ("vendor",)),
                      ("prequalification", ("company",))):
        for r in me.list_records(db, key, pid, limit=10000):
            v = _vendor(r, *keys)
            if v:
                vendors.add(v)
    rows = []
    for v in sorted(vendors):
        g = gate(db, pid, v)
        issues = []
        if g["coi"]["status"] == "missing":
            issues.append("COI missing")
        elif g["coi"]["status"] == "expired":
            issues.append(f"COI expired ({g['coi']['expires']})")
        elif g["coi"].get("expiring_soon"):
            issues.append(f"COI expiring {g['coi']['expires']}")
        if g["prequal"]["status"] != "approved":
            issues.append("prequal not approved")
        if issues:
            rows.append({"vendor": v, "issues": issues, "can_bid": g["can_bid"], "can_bill": g["can_bill"]})
    return {"within_days": within_days, "vendors_flagged": len(rows), "vendors": rows,
            "note": "Vendors needing a compliance nudge (expiring/expired/missing COI or unapproved "
                    "prequal). Send before it blocks a bid invitation or pay application."}
