"""Invitation-to-bid (ITB) tracking — rolls up bid packages vs the submissions received: who was
invited, who responded, who provided a bid bond, the low bid, and coverage gaps (packages with no
bids). Complements bid leveling (the compare) with the outbound/solicitation side. Pure over dicts."""
from __future__ import annotations

from typing import Any


def _num(v: Any) -> float | None:
    try:
        f = float(v)
        return f
    except (TypeError, ValueError):
        return None


def _truthy(v: Any) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "y", "provided")


def summarize(packages: list[dict], submissions: list[dict]) -> dict[str, Any]:
    """packages: bid_package records; submissions: bid_submission records. Matches submissions to a
    package by the submission's `package` field == the package name or ref.

    ITB-DOUBLE. Five defects lived here, and every one of them pushed the same way -- toward a trade
    looking better covered than it is, on the screen that decides whether there are enough bidders
    to award.

    1. **Submissions were counted TWICE** whenever a package's name equalled its ref, which is the
       common case for a package referenced by its own name. The match was
       `subs_by_pkg.get(name) + subs_by_pkg.get(ref)`, two lookups concatenated with no dedupe.
       Measured: 5 submissions -> `responses: 10`, `bonded: 10`, `response_rate: 100.0` instead of
       50.0, and `coverage` flipping from "thin" to "covered". Matching is by submission IDENTITY
       now, so a package found under both keys counts each bid once.
    2. **An unknown denominator read as 0%.** `round(...) if invited else 0.0` gave a package with
       five bids and no recorded invite list `response_rate: 0.0` -- the same value as "nobody
       bid" -- on a row whose `coverage` said "covered". `None` now; unknown is not zero.
    3. **The headline rate divided across two populations.** `total_responses / total_invited`
       counted responses from every package against the invited count of only those that recorded
       one. Measured: 10 invited + 3 bids on Concrete, no invite count + 5 bids on Drywall, giving
       **80%** where Concrete alone is 30%. The same two-population ratio PRICE-MATCHED fixed in
       `pricing.reconcile`; it is computed over the RATED packages only, with the split stated.
    4. **The rate could exceed 100%**, which is what (1) and (3) look like together.
    5. **A submission matching no package vanished.** Three bids posted, `total_responses: 1`, and
       nothing in the response mentioned the other two -- a bid filed against a misspelled package
       name left no trace. Counted and reported now, because an unmatched bid is a bid somebody
       submitted and nobody is looking at.
    """
    # (idx, data) so a package found under BOTH its name and its ref counts each bid once.
    subs_by_pkg: dict[str, list[tuple[int, dict]]] = {}
    for i, sraw in enumerate(submissions):
        d = sraw.get("data") or sraw
        key = str(d.get("package") or "").strip().lower()
        subs_by_pkg.setdefault(key, []).append((i, d))
    rows = []
    total_invited = total_responses = total_bonded = no_bid_pkgs = 0
    rated_invited = rated_responses = rated_pkgs = unrated_pkgs = 0
    claimed: set[int] = set()
    for p in packages:
        d = p.get("data") or p
        name = d.get("name") or p.get("ref") or ""
        invited_list = d.get("invited_companies") or []
        invited = len(invited_list) if invited_list else int(_num(d.get("bidders_invited")) or 0)
        # A SET of keys is the whole of defect (1): `{"bp-003", "bp-003"}` is one key, where
        # `get(name) + get(ref)` was two lookups whose results were concatenated.
        #
        # No per-package dedupe beyond that, and the first draft of this fix had one -- an
        # `if i in seen: continue` inside the loop. **Mutating it away did not red the test**,
        # which is how it was caught: a submission carries exactly ONE `package` string, so it
        # sits in exactly one bucket, so within a single package the same index cannot arrive
        # twice. The guard could never fire. *A guard that cannot fire reads as the fix and
        # isn't one, and the mutation that proves the real fix is the one that removes the
        # mechanism, not the belt beside it.*
        keys = {str(name).strip().lower(), str(p.get("ref") or "").strip().lower()} - {""}
        matched = [(i, sd) for k in sorted(keys) for i, sd in subs_by_pkg.get(k, [])]
        subs = [sd for _, sd in matched]
        # Across packages it IS possible for one submission to be claimed twice -- package A's
        # name can equal package B's ref -- so this is a set over the whole loop, and
        # `total_responses` can exceed `submission_count` when that happens. The note below
        # reports unmatched bids; a bid claimed by two packages is a naming collision between
        # packages, which is a different fact and not one this summary invents an answer for.
        claimed |= {i for i, _ in matched}
        responses = len(subs)
        bonded = sum(1 for s in subs if _truthy(s.get("bond_provided")))
        amts = [a for s in subs if (a := _num(s.get("amount") or s.get("base_bid"))) is not None]
        low = min(amts) if amts else None
        total_invited += invited
        total_responses += responses
        total_bonded += bonded
        if invited:
            rated_pkgs += 1
            rated_invited += invited
            rated_responses += responses
        else:
            unrated_pkgs += 1
        if responses == 0:
            no_bid_pkgs += 1
        rows.append({
            "ref": p.get("ref"), "package": name, "trade": d.get("trade"),
            "budget": _num(d.get("budget")), "invited": invited, "responses": responses,
            "bonded": bonded, "low_bid": low, "due_date": d.get("due_date"),
            # `None`, not 0.0, when nobody recorded who was invited: a rate needs a denominator,
            # and the figure that reads as "nobody bid" is the dangerous one to fabricate.
            "response_rate": round(100 * responses / invited, 1) if invited else None,
            # Unchanged, and deliberately: coverage is about the ABSOLUTE number of bids in hand,
            # which is sound whether or not anybody recorded the invite list. What was wrong was
            # printing it beside a 0.0% rate, not the judgement itself.
            "coverage": "no bids" if responses == 0 else ("covered" if responses >= 3 else "thin"),
            "rate_basis": "invited" if invited else "no invite list recorded",
        })
    unmatched = [i for i in range(len(submissions)) if i not in claimed]
    return {
        "package_count": len(packages),
        "total_invited": total_invited,
        "total_responses": total_responses,
        "total_bonded": total_bonded,
        "packages_without_bids": no_bid_pkgs,
        # Over the packages that recorded an invite list, so the numerator and denominator are the
        # same population. `None` when none did -- there is no rate to report, which is not 0%.
        "overall_response_rate": (round(100 * rated_responses / rated_invited, 1)
                                  if rated_invited else None),
        "rated_packages": rated_pkgs,
        "unrated_packages": unrated_pkgs,
        "rated_responses": rated_responses,
        # Bids that matched no package. Submitted by somebody, looked at by nobody.
        "unmatched_submissions": len(unmatched),
        "submission_count": len(submissions),
        "coverage_note": _coverage_note(len(packages), rated_pkgs, unrated_pkgs, len(unmatched)),
        "rows": sorted(rows, key=lambda r: (r["coverage"] != "no bids", r["package"])),
    }


def _coverage_note(pkgs: int, rated: int, unrated: int, unmatched: int) -> str:
    """The engine's sentence about what the headline rate is over, and what is not in it."""
    if not pkgs:
        return "No bid packages yet."
    if not rated:
        head = (f"No invite list is recorded on any of the {pkgs} package(s), so there is no "
                "response rate to report -- which is not a rate of 0%.")
    else:
        head = f"The response rate is over the {rated} package(s) that record an invite list"
        head += (f"; {unrated} package(s) do not and are not in it." if unrated
                 else " -- every package records one.")
    if unmatched:
        head += (f" {unmatched} submission(s) name a package that does not exist here and are "
                 "counted in NO package above -- check the package name on them.")
    return head


def itb(db, pid: str) -> dict[str, Any]:
    from . import modules as me
    pkgs = me.list_records(db, "bid_package", pid, limit=100000) if "bid_package" in me.TABLES else []
    subs = me.list_records(db, "bid_submission", pid, limit=100000) if "bid_submission" in me.TABLES else []
    return summarize(pkgs, subs)
