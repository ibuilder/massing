"""R22-ENTITLEMENT — the review cycle, and whose court the time sat in.

## What was missing, checked rather than assumed

Both registers for approval already existed: `entitlement` (application_type, agency, hearing_date,
public_process, conditions) and `permit` (applied → under_review → issued). `approval_conditions` and
`condition_checks` already carry conditions of approval into the model as constraints.

What neither register modelled is **rounds**. `permit` has a single `under_review` state, so a third
review round is indistinguishable from a first, and the only durations recoverable are
`applied_date → issued_date`: one number for a process that is actually a back-and-forth.

**That number cannot settle the argument the process generates.** When a permit takes seven months,
the question is never "how long" — it is *whose court did it sit in*. An agency that held three rounds
for forty days total and an applicant who took fifty-five days to answer them produce the same
elapsed time and completely different conversations, with completely different remedies. This computes
the split.

## What this is NOT, because two neighbours are close enough to confuse

`permit_timeline.estimate()` forecasts days-to-issue from **other** projects' public permit feeds — a
market prior for underwriting, computed before you apply. This measures **this** project's actual
rounds, after. Neither replaces the other, and the forecast is the more useful of the two right up
until the first round comes back.

`proforma/approval_risk` scores the *risk* of approval. It does not track a submittal.

And `jurisdiction_packs` — the closest name of all — is **data-requirement rule packs**: what a
submitted model must contain. Not a package of documents submitted to an authority. That is the fifth
naming collision this ring has produced, and the first that pointed the wrong way: a name that sounds
like the missing thing and is a different thing.

## The refusals, which are the design

**An open round is unmeasurable, not zero days.** A round sitting with the agency has no
`comments_received_date`, and treating that absence as zero would report an agency that has held a
submission for ninety days as instantaneous — the most flattering possible lie about the party you
are about to argue with. Open rounds are counted and named, never scored. This is the same rule
v0.3.974 settled for PPC, and for the same reason.

**Days are counted on the calendar, deliberately.** A review clock is calendar days: a statutory
"30-day review" does not pause for a weekend, and an applicant who sat on comments over Christmas
still sat on them. This is the opposite choice from `schedule_compare`, which counts working days
because a *construction* duration is worked. Stating which axis is in use is the point — mixing them
silently is how `eot.py` produced four identical numbers.

**Rounds out of order are reported, not sorted away.** Round 3 dated before round 2 means somebody
mis-keyed a date or the rounds are not what they appear to be, and quietly sorting hides the only
evidence of that.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

#: Every state a round can be in, and who is holding it. The register's workflow uses the first two.
WITH_AGENCY = "with_agency"
WITH_APPLICANT = "with_applicant"
CLOSED = "closed"

STATUS_OK = "measured"
STATUS_NO_ROUNDS = "no_rounds"
STATUS_UNDATED = "no_dated_rounds"


def _date(v: Any) -> date | None:
    if isinstance(v, date) and not isinstance(v, datetime):
        return v
    if isinstance(v, datetime):
        return v.date()
    if not isinstance(v, str) or not v.strip():
        return None
    try:
        return datetime.fromisoformat(v.strip()[:10]).date()
    except ValueError:
        return None


def _num(v: Any) -> float | None:
    if isinstance(v, bool) or v in (None, ""):
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    return None if f != f else f


def _round_no(data: dict) -> int | None:
    n = _num(data.get("round"))
    return int(n) if n is not None and n >= 1 else None


def _leg(start: date | None, end: date | None) -> int | None:
    """Calendar days between two dates, or None if either end is missing.

    `None` rather than 0 is the whole discipline of this module: a leg with no end date is a leg
    still running, and the one thing it is definitely not is instantaneous.
    """
    if start is None or end is None:
        return None
    return (end - start).days


def cycles(records: list[dict] | None, *, application: str | None = None) -> dict[str, Any]:
    """Review rounds for one application, split by which party held the clock.

    `application` filters to a single permit/entitlement reference; omitted, every round supplied is
    treated as belonging to one application, which is what a caller that has already filtered wants.
    """
    rows = [r for r in (records or []) if isinstance(r, dict)]
    if application:
        rows = [r for r in rows
                if str((r.get("data") or {}).get("permit") or "") == application
                or str((r.get("data") or {}).get("entitlement") or "") == application]
    if not rows:
        return _unavailable(STATUS_NO_ROUNDS,
                            "no review rounds recorded — an application nobody has submitted has no "
                            "review history, which is different from one that sailed through")

    rounds: list[dict[str, Any]] = []
    undated = 0
    for r in rows:
        d = r.get("data") or {}
        sub = _date(d.get("submitted_date"))
        got = _date(d.get("comments_received_date"))
        resp = _date(d.get("response_sent_date"))
        no = _round_no(d)
        if sub is None:
            undated += 1
            continue
        rounds.append({
            "ref": r.get("ref"),
            "round": no,
            "agency": d.get("agency") or "",
            "submitted": sub.isoformat(),
            "comments_received": got.isoformat() if got else None,
            "response_sent": resp.isoformat() if resp else None,
            "comment_count": _num(d.get("comment_count")),
            "outcome": d.get("outcome") or None,
            # The two legs. Agency holds it from submission until comments land; we hold it from
            # comments until we answer. Either can be open, and an open leg is None.
            "days_with_agency": _leg(sub, got),
            "days_with_applicant": _leg(got, resp),
            "open_with": (WITH_AGENCY if got is None else
                          WITH_APPLICANT if resp is None else None),
            "state": r.get("workflow_state"),
        })

    if not rounds:
        # `rounds_undated`, not `undated` — `_unavailable` merges extras by key, so a mismatched
        # name silently adds a stray field and leaves the real count at 0. Caught by the test
        # asserting the COUNT rather than just the status.
        return _unavailable(STATUS_UNDATED,
                            f"none of the {len(rows)} rounds carries a submitted date, so no clock "
                            "can be started", rounds_undated=undated)

    # Order is REPORTED, not imposed. A round numbered 3 whose submission predates round 2 means a
    # mis-keyed date or rounds that are not what they look like; sorting it away destroys the only
    # evidence that anything is wrong.
    numbered = [r for r in rounds if r["round"] is not None]
    out_of_order = [
        f"round {b['round']} ({b['submitted']}) precedes round {a['round']} ({a['submitted']})"
        for a, b in zip(numbered, numbered[1:], strict=False)
        if a["round"] is not None and b["round"] is not None
        and b["round"] > a["round"] and b["submitted"] < a["submitted"]
    ]

    closed = [r for r in rounds if r["open_with"] is None]
    agency_days = [r["days_with_agency"] for r in rounds if r["days_with_agency"] is not None]
    applicant_days = [r["days_with_applicant"] for r in rounds if r["days_with_applicant"] is not None]
    open_rounds = [r for r in rounds if r["open_with"] is not None]

    total_agency = sum(agency_days) if agency_days else None
    total_applicant = sum(applicant_days) if applicant_days else None
    return {
        "available": True,
        "status": STATUS_OK,
        "rounds": len(rounds),
        "rounds_closed": len(closed),
        # Counted and named. A report that scored these as zero would flatter whichever party is
        # currently holding the file, which is exactly the party the reader is arguing with.
        "rounds_open": len(open_rounds),
        "open_detail": [{"round": r["round"], "held_by": r["open_with"], "since":
                         r["comments_received"] or r["submitted"]} for r in open_rounds],
        "rounds_undated": undated,
        "days_with_agency": total_agency,
        "days_with_applicant": total_applicant,
        # The number the argument is actually about. `None` when either side has no closed leg —
        # a share of an unknown total is not a share.
        "agency_share_pct": (round(100 * total_agency / (total_agency + total_applicant), 1)
                             if total_agency is not None and total_applicant is not None
                             and (total_agency + total_applicant) > 0 else None),
        "mean_agency_turnaround_days": (round(sum(agency_days) / len(agency_days), 1)
                                        if agency_days else None),
        "mean_applicant_turnaround_days": (round(sum(applicant_days) / len(applicant_days), 1)
                                           if applicant_days else None),
        "total_comments": (sum(r["comment_count"] for r in rounds
                               if r["comment_count"] is not None) or None),
        "rounds_out_of_order": out_of_order,
        "detail": rounds,
        "days_basis": "calendar",
        "note": ("Days are CALENDAR days: a statutory review period does not pause for a weekend, and "
                 "an applicant who sat on comments over a holiday still sat on them. Construction "
                 "durations elsewhere in this system are working days — the axis is stated because "
                 "mixing the two silently is how a delay analysis produces a confident wrong number. "
                 "An open round is counted and named, never scored: a submission the agency has held "
                 "for ninety days is not zero days of agency time."),
    }


def for_project(db, project_id: str, application: str | None = None) -> dict[str, Any]:
    """Review cycles from the project's own `review_cycle` records."""
    from . import modules as me
    if "review_cycle" not in me.TABLES:
        return _unavailable(STATUS_NO_ROUNDS,
                            "the review_cycle register is not present in this deployment")
    rows = me.list_records(db, "review_cycle", project_id, limit=100000)
    out = cycles(rows, application=application)
    out["project_id"] = project_id
    return out


def _unavailable(status: str, reason: str, **extra: Any) -> dict[str, Any]:
    """Counts are `None`, never 0 — "nobody submitted" and "the agency was instant" are different."""
    out: dict[str, Any] = {
        "available": False, "status": status, "reason": reason,
        "rounds": None, "rounds_closed": None, "rounds_open": None, "open_detail": [],
        "rounds_undated": 0, "days_with_agency": None, "days_with_applicant": None,
        "agency_share_pct": None, "mean_agency_turnaround_days": None,
        "mean_applicant_turnaround_days": None, "total_comments": None,
        "rounds_out_of_order": [], "detail": [], "days_basis": None,
    }
    out.update({k: v for k, v in extra.items() if v is not None})
    return out
