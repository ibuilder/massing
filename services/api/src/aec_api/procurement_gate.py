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

# PREQUAL-LAPSE. The warning horizon, shared by the COI and the prequalification so the two
# compliance documents on one gate cannot answer "expiring soon" against different windows. It was
# a literal `30` inside the COI branch and nowhere else, because the prequal had no branch.
WARN_DAYS = 30


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


def _coi_status(cois: list[dict], vendor: str, today: date, warn_days: int = WARN_DAYS) -> dict:
    latest = None
    for c in cois:
        if _vendor(c, "vendor") == vendor:
            exp = _date(_d(c).get("expires"))
            if latest is None or (exp and (_date(_d(latest).get("expires")) or date.min) < exp):
                latest = c
    # PREQUAL-LAPSE. `expiring_soon` is present on EVERY branch. It used to be absent from the
    # `missing` one, so a consumer reading `coi.expiring_soon` got `undefined` for a vendor with no
    # certificate at all -- a falsy value that reads as "not expiring soon" and is really "there is
    # nothing to expire". A key that exists on some branches is a key no caller can read safely.
    if latest is None:
        return {"status": "missing", "expires": None, "expiring_soon": False}
    exp = _date(_d(latest).get("expires"))
    active = latest.get("workflow_state") in ("active", "open") and (exp is None or exp >= today)
    expiring = exp is not None and today <= exp <= today + timedelta(days=warn_days)
    return {"status": "active" if active else "expired", "expires": exp.isoformat() if exp else None,
            "expiring_soon": expiring}


def gate(db, pid: str, vendor: str, warn_days: int = WARN_DAYS) -> dict[str, Any]:
    """Compliance readiness for one vendor: can they be invited to bid, and can they be paid.

    `warn_days` is the horizon the WARNINGS are computed against, and it is a parameter because
    `compliance_feed` below accepts one from the caller. It used to be a literal 30 inside the COI
    branch, so the feed's `within_days` -- validated and clamped to 1..365 by its route -- reached
    nothing: a caller asking for a 7-day nudge window got a 30-day one back, labelled 7. *A
    parameter accepted, validated, echoed and ignored is worse than an absent one, because the echo
    is what makes it look answered.* Blockers do not take a horizon: expired is expired.
    """
    today = date.today()
    cois = me.list_records(db, "coi", pid, limit=10000)
    prequals = me.list_records(db, "prequalification", pid, limit=10000)
    subs = me.list_records(db, "subcontract", pid, limit=10000)
    waivers = me.list_records(db, "lien_waiver", pid, limit=10000)

    coi = _coi_status(cois, vendor, today, warn_days)
    # ONE VENDOR CAN HAVE SEVERAL RECORDS, and the question is existential — this module's own
    # docstring says a sub may not bid "without AN approved prequalification". `next()` over the
    # unfiltered list answered a different question: `list_records` orders by `created_at` ascending,
    # so it judged the vendor on their OLDEST record. A sub who was rejected, remediated and approved
    # was reported `can_bid: False` with "no approved prequalification" while holding exactly that —
    # a false blocker whose message sends someone to redo work they have already done.
    #
    # A later rejection cannot revoke an earlier approval here, and that is the workflow's design
    # rather than an assumption: `prequalification` declares only `invited -> submitted`,
    # `submitted -> approved` and `submitted -> rejected`. There is NO transition out of `approved`,
    # so a rejection is a fact about one submission, and an approval lapses only by its `expires`
    # date — which is why the date check below is the thing that ends it.
    #
    # The fallback is the NEWEST record (the list is oldest-first) rather than the first, so when
    # nothing qualifies, `prequal.status` reports where the vendor actually stands today.
    def _pq_live(p: dict) -> bool:
        exp = _date(_d(p).get("expires"))
        return p.get("workflow_state") == "approved" and (not exp or exp >= today)

    v_pqs = [p for p in prequals if _vendor(p, "company") == vendor]
    pq = next((p for p in v_pqs if _pq_live(p)), v_pqs[-1] if v_pqs else None)
    pq_ok = bool(pq and _pq_live(pq))
    v_subs = [x for x in subs if _vendor(x, "vendor", "vendor_company") == vendor]
    sub = next((x for x in v_subs if x.get("workflow_state") == "executed"),
               v_subs[-1] if v_subs else None)
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

    # PREQUAL-LAPSE — the prequal's own expiry, reported with the same shape as the COI's.
    pq_exp = _date(_d(pq).get("expires")) if pq else None
    pq_block = {
        "status": "approved" if pq_ok else (pq.get("workflow_state") if pq else "missing"),
        "expires": pq_exp.isoformat() if pq_exp else None,
        # `pq_ok` is required: a prequal that has ALREADY lapsed is a blocker, not a warning, and
        # `_pq_live` has already refused it above. "Expiring soon" is only ever said about
        # something currently valid.
        "expiring_soon": bool(pq_ok and pq_exp is not None
                              and today <= pq_exp <= today + timedelta(days=warn_days)),
    }
    bid_warnings, bill_warnings = [], []
    if coi.get("expiring_soon"):
        bid_warnings.append(f"insurance expires {coi['expires']}")
        bill_warnings.append(f"insurance expires {coi['expires']}")
    if pq_block["expiring_soon"]:
        bid_warnings.append(f"prequalification lapses {pq_block['expires']}")
    return {
        "vendor": vendor,
        "coi": coi,
        "prequal": pq_block,
        "subcontract": {"executed": sub_executed},
        "waiver_on_file": waiver is not None,
        "can_bid": not bid_blockers, "bid_blockers": bid_blockers,
        "can_bill": not bill_blockers, "bill_blockers": bill_blockers,
        # PREQUAL-LAPSE. A document that is still valid today is NOT a blocker, so the verdict is
        # unchanged -- a gate that refused a vendor whose paperwork is current would be wrong. The
        # warnings are the state between "fine" and "blocked", which this gate had no way to say:
        # `can_bid: True` with `bid_blockers: []` was returned for a vendor whose approval dies in
        # ten days, and the approval's date is the only thing that ends it.
        "bid_warnings": bid_warnings,
        "bill_warnings": bill_warnings,
        "warn_days": warn_days,
        "note": "Bid gate = approved prequal + active insurance. Bill gate = executed subcontract + "
                "active insurance (lien waiver is collected at payment). Blockers refuse today; "
                f"warnings are documents still valid that lapse within {warn_days} days -- an "
                "approved prequalification has no transition out of `approved`, so its date is the "
                "only thing that ends it.",
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
        g = gate(db, pid, v, warn_days=within_days)
        issues = []
        if g["coi"]["status"] == "missing":
            issues.append("COI missing")
        elif g["coi"]["status"] == "expired":
            issues.append(f"COI expired ({g['coi']['expires']})")
        elif g["coi"].get("expiring_soon"):
            issues.append(f"COI expiring {g['coi']['expires']}")
        if g["prequal"]["status"] != "approved":
            issues.append("prequal not approved")
        elif g["prequal"]["expiring_soon"]:
            # PREQUAL-LAPSE. This list is the OUTBOUND NUDGE list, and a lapsing approval is the
            # one thing it can still be sent in time to prevent. Before this it could only report
            # `prequal not approved`, which becomes true after the approval has already died --
            # i.e. after `can_bid` has flipped and the sub has been dropped from the invitation.
            # A nudge list that only names what has already happened is a report, not a nudge.
            issues.append(f"prequal lapses {g['prequal']['expires']}")
        if issues:
            rows.append({"vendor": v, "issues": issues, "can_bid": g["can_bid"], "can_bill": g["can_bill"]})
    return {"within_days": within_days, "vendors_flagged": len(rows), "vendors": rows,
            "warn_days": within_days,
            "note": "Vendors needing a compliance nudge: an expiring, expired or missing COI, an "
                    "unapproved prequalification, or an approved one LAPSING within "
                    f"{within_days} days. Send before it blocks a bid invitation or pay "
                    "application. An already-expired document is reported whatever the window: "
                    "`within_days` bounds the WARNINGS, not the blockers."}
