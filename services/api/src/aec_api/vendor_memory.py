"""R22-PROCURE-DEPTH ③ — what a trade partner's record with YOUR firm actually is, across projects.

Two of the entry's three parts already exist and were verified before this was written:
`prequalification.py` scores EMR / bonding / capacity into a traceable Q-score with COI-expiry
tracking, and `clause_playbook.py` holds the clause-position playbook and its deviation register.
The third — **vendor scorecards persisting across projects** — did not: `prequalification.score_project`
takes a single `project_id`, so a sub is prequalified on job B from the form they filled in, with no
reference to what they actually did on job A.

That is the differentiator, and it is a *reach* problem rather than a modelling one. The history is
already recorded, keyed by vendor, in six registers: `subcontract`, `commitment`, `sub_invoice`,
`coi`, `lien_waiver` and `warranty`. Nothing had ever read them across projects.

**The Q-score and the history are reported side by side and never blended.** A single composite
number would hide which half came from a form the sub filled in themselves and which half came from
what they did — and those two deserve very different trust. Same rule as the option card's
`declared` vs `derived`.

**A vendor with no history scores nothing, not well.** `no_history` is a distinct verdict from
`clear`. A sub who has never worked for you is an unknown, and an unknown that renders as a clean
record is the single most expensive mistake this module could make — it is the prequalification
equivalent of "0 open NCRs" on a building nobody inspected.

**What this deliberately CANNOT tell you, stated because its absence is invisible.** Quality and
schedule performance are not attributable to a vendor: `ncr` and `inspection` carry no vendor field
(checked — their only near-match is `subject`), and no schedule activity binds one. So this reports
COMMERCIAL and COMPLIANCE history only. A vendor with a spotless record here may still have generated
every NCR on the job, and `attributable` says so rather than letting a clean-looking scorecard imply
a quality record it never examined.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import modules as me

#: Registers that carry a `vendor` field, and are therefore attributable across projects.
VENDOR_MODULES = ("subcontract", "commitment", "sub_invoice", "coi", "lien_waiver", "warranty")

#: Registers that record performance but carry NO vendor, so nothing here can speak to them.
NOT_ATTRIBUTABLE = ("ncr", "inspection")

VERDICT_NO_HISTORY = "no_history"
VERDICT_CLEAR = "clear"
VERDICT_WATCH = "watch"

_WHY = {
    VERDICT_NO_HISTORY: ("this vendor has no recorded history with the firm — an unknown, NOT a "
                         "clean record"),
    VERDICT_CLEAR: "history exists and shows no lapsed insurance or unwaived billing",
    VERDICT_WATCH: "history exists and something is outstanding — see `flags`",
}


def _num(v: Any) -> float:
    if v in (None, ""):
        return 0.0
    try:
        return float(str(v).replace(",", "").replace("$", "").strip())
    except (TypeError, ValueError):
        return 0.0


def _norm(s: Any) -> str:
    return " ".join(str(s or "").split()).strip()


def _date(v: Any) -> date | None:
    s = _norm(v)
    if not s:
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(s[:10], fmt).date()
        except ValueError:
            continue
    return None


def _rows(db: Session, key: str, project_ids: set[str] | None) -> list[tuple[str, dict]]:
    """`(project_id, data)` for a module across the caller's projects.

    Same tenant scoping as `benchmarking._rows` — `project_ids=None` means unrestricted (RBAC off or
    admin), otherwise the roll-up cannot see another tenant's vendors.
    """
    t = me.TABLES.get(key)
    if t is None:
        return []
    stmt = select(t.c.project_id, t.c.data)
    if project_ids is not None:
        stmt = stmt.where(t.c.project_id.in_(project_ids))
    return [(pid, d or {}) for pid, d in db.execute(stmt).all()]


def gather(db: Session, project_ids: set[str] | None = None) -> dict[str, dict[str, Any]]:
    """Every vendor-bearing record, bucketed by normalised vendor name."""
    by_vendor: dict[str, dict[str, Any]] = {}
    for key in VENDOR_MODULES:
        for pid, d in _rows(db, key, project_ids):
            name = _norm(d.get("vendor")) or _norm(d.get("vendor_company"))
            if not name:
                continue
            v = by_vendor.setdefault(name.lower(), {"vendor": name, "projects": set(),
                                                    "records": {k: [] for k in VENDOR_MODULES}})
            v["projects"].add(pid)
            v["records"][key].append(d)
    return by_vendor


def vendor_record(entry: dict[str, Any], today: date | None = None) -> dict[str, Any]:
    """One vendor's cross-project commercial and compliance history. Pure — no session."""
    today = today or date.today()
    recs = entry["records"]

    subcontract_value = sum(_num(d.get("value")) for d in recs["subcontract"])
    committed = sum(_num(d.get("amount")) for d in recs["commitment"])
    spent = sum(_num(d.get("spent")) for d in recs["commitment"])
    invoiced = sum(_num(d.get("amount")) for d in recs["sub_invoice"])
    waived = sum(_num(d.get("amount")) for d in recs["lien_waiver"])

    # Insurance: a certificate whose expiry has passed is a lapse. A certificate with no expiry
    # recorded is NOT a lapse and NOT compliance — it is unknown, and counted separately so a missing
    # date cannot quietly read as cover.
    expired = [d for d in recs["coi"] if (e := _date(d.get("expires"))) and e < today]
    no_expiry = [d for d in recs["coi"] if not _date(d.get("expires"))]

    flags: list[str] = []
    if expired:
        flags.append(f"{len(expired)} certificate(s) of insurance expired")
    if no_expiry:
        flags.append(f"{len(no_expiry)} certificate(s) with no expiry recorded — cover is unknown")
    # Billing not covered by a lien waiver is an exposure, but only meaningful if they have billed.
    if invoiced > 0 and waived + 0.01 < invoiced:
        flags.append(f"{round(invoiced - waived, 2)} invoiced beyond the lien waivers on file")
    warranties_live = [d for d in recs["warranty"]
                       if (e := _date(d.get("expires"))) and e >= today]

    has_history = any(recs[k] for k in VENDOR_MODULES)
    verdict = (VERDICT_NO_HISTORY if not has_history
               else VERDICT_WATCH if flags else VERDICT_CLEAR)

    return {
        "vendor": entry["vendor"],
        "verdict": verdict, "verdict_note": _WHY[verdict],
        "project_count": len(entry["projects"]),
        "subcontract_value": round(subcontract_value, 2),
        "committed": round(committed, 2), "spent": round(spent, 2),
        "invoiced": round(invoiced, 2), "lien_waivers_value": round(waived, 2),
        "coi_expired": len(expired), "coi_missing_expiry": len(no_expiry),
        "warranties_live": len(warranties_live),
        "record_counts": {k: len(recs[k]) for k in VENDOR_MODULES},
        "flags": flags,
        "trades": sorted({_norm(d.get("trade")) for d in recs["subcontract"] if _norm(d.get("trade"))}),
    }


def vendor_memory(db: Session, project_ids: set[str] | None = None,
                  today: date | None = None) -> dict[str, Any]:
    """Every trade partner's record across the caller's projects, ranked by exposure."""
    gathered = gather(db, project_ids)
    vendors = [vendor_record(v, today) for v in gathered.values()]
    vendors.sort(key=lambda v: (-v["project_count"], -v["subcontract_value"], v["vendor"]))
    repeat = [v for v in vendors if v["project_count"] > 1]

    return {
        "vendors": vendors,
        "vendor_count": len(vendors),
        # The whole point of persistence: a partner you have used more than once has a record worth
        # consulting before the next award.
        "repeat_vendors": len(repeat),
        "watch_count": sum(1 for v in vendors if v["verdict"] == VERDICT_WATCH),
        "verdict_meanings": _WHY,
        "attributable": {
            "from": list(VENDOR_MODULES),
            "not_from": list(NOT_ATTRIBUTABLE),
            "note": ("commercial and compliance history only. `ncr` and `inspection` carry no vendor "
                     "field, and no schedule activity binds one, so QUALITY and SCHEDULE performance "
                     "are not attributable to a vendor here. A clean record below is not a clean "
                     "quality record — it is silence on the subject"),
        },
        "note": ("A vendor with no recorded history is `no_history`, never `clear`. This is the "
                 "firm's own experience, kept separate from the self-reported prequalification "
                 "Q-score so the two are never mistaken for one another."),
        "message": (None if vendors else
                    "No vendor history yet — subcontracts, commitments, invoices, COIs, lien waivers "
                    "and warranties are what build it."),
    }
