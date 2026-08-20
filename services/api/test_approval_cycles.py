"""R22-ENTITLEMENT — the review cycle, and the number the argument is actually about.

A permit that took seven months prompts one question, and it is never "how long". It is **whose court
did it sit in.** An agency that held three rounds for 40 days and an applicant who took 55 to answer
them produce identical elapsed time, a completely different conversation, and a different remedy.
Before this, the only recoverable duration was `applied_date → issued_date`: one number for a
back-and-forth, because `permit` has a single `under_review` state and a third round is
indistinguishable from a first.

**The assertion that carries this file is the split** — `days_with_agency` vs `days_with_applicant`
on rounds whose elapsed time is identical. If those two ever collapse into one number, the module has
stopped answering the only question it exists for.

**The refusal that carries it is the open round.** A round the agency still holds has no
comments-received date. Scoring that absence as zero would report a submission held ninety days as
instantaneous — the most flattering possible lie about the party you are about to argue with — so
open rounds are counted and named, never scored.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_approval_cycles.py
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, "src")

from aec_api import approval_cycles as ac  # noqa: E402

_FAILURES: list[str] = []


def check(name: str, ok: bool, note: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}   {note}")
    if not ok:
        _FAILURES.append(name)


def rnd(n, sub, got=None, resp=None, *, comments=None, agency="City", outcome=None, ref=None):
    return {"ref": ref or f"RC-{n:03d}", "workflow_state": "closed",
            "data": {"round": n, "submitted_date": sub, "comments_received_date": got,
                     "response_sent_date": resp, "comment_count": comments,
                     "agency": agency, "outcome": outcome, "permit": "PRM-001"}}


#: Two applications with IDENTICAL total elapsed time (2026-01-01 → 2026-03-02, 60 days) and opposite
#: causes. This pair is the whole point of the module.
AGENCY_SLOW = [rnd(1, "2026-01-01", "2026-02-20", "2026-02-25", comments=12),
               rnd(2, "2026-02-25", "2026-03-01", "2026-03-02", comments=1)]
APPLICANT_SLOW = [rnd(1, "2026-01-01", "2026-01-06", "2026-02-25", comments=12),
                  rnd(2, "2026-02-25", "2026-03-01", "2026-03-02", comments=1)]


def main() -> int:
    slow_agency = ac.cycles(AGENCY_SLOW)
    slow_us = ac.cycles(APPLICANT_SLOW)

    # ================= THE SPLIT =================
    check("two applications with the SAME elapsed time are told apart by whose court held it",
          slow_agency["days_with_agency"] == 54 and slow_agency["days_with_applicant"] == 6
          and slow_us["days_with_agency"] == 9 and slow_us["days_with_applicant"] == 51,
          f"agency-slow {slow_agency['days_with_agency']}d/{slow_agency['days_with_applicant']}d vs "
          f"applicant-slow {slow_us['days_with_agency']}d/{slow_us['days_with_applicant']}d — "
          "both ran 2026-01-01 to 2026-03-02")

    check("...and the elapsed total really IS the same — the control",
          (slow_agency["days_with_agency"] + slow_agency["days_with_applicant"])
          == (slow_us["days_with_agency"] + slow_us["days_with_applicant"]) == 60,
          "without this the split could be an artefact of one dataset simply being longer")

    check("the share is stated as a percentage, which is what an argument quotes",
          slow_agency["agency_share_pct"] == 90.0 and slow_us["agency_share_pct"] == 15.0,
          f"{slow_agency['agency_share_pct']}% vs {slow_us['agency_share_pct']}%")

    check("rounds are counted, so a three-round permit cannot look like a one-round permit",
          slow_agency["rounds"] == 2 and slow_agency["rounds_closed"] == 2,
          "`permit` has ONE under_review state; the round count is the thing it could not hold")

    # ================= THE OPEN ROUND =================
    open_now = ac.cycles([rnd(1, "2026-01-01", "2026-01-20", "2026-01-25"),
                          rnd(2, "2026-01-25")])          # still with the agency
    check("a round the agency still holds is NAMED, not scored as zero",
          open_now["rounds_open"] == 1
          and open_now["open_detail"][0]["held_by"] == ac.WITH_AGENCY,
          f"{open_now['open_detail']} — scoring it zero would report a submission held for months "
          "as instantaneous, which flatters exactly the party you are arguing with")

    check("...and the open round contributes NOTHING to the agency total",
          open_now["days_with_agency"] == 19,
          f"{open_now['days_with_agency']}d — round 1 only. An open leg is unmeasurable, not 0")

    with_us = ac.cycles([rnd(1, "2026-01-01", "2026-01-20")])   # comments in, no response yet
    check("a round WE still hold is named too, and against us",
          with_us["rounds_open"] == 1
          and with_us["open_detail"][0]["held_by"] == ac.WITH_APPLICANT,
          "the refusal has to be symmetrical or it is advocacy rather than measurement")

    check("...and a share nobody can compute is None, never 0",
          with_us["days_with_applicant"] is None and with_us["agency_share_pct"] is None,
          f"agency={with_us['days_with_agency']} applicant={with_us['days_with_applicant']} — "
          "a share of an unknown total is not a share")

    # ================= ORDER IS REPORTED, NOT IMPOSED =================
    jumbled = ac.cycles([rnd(1, "2026-03-01", "2026-03-10", "2026-03-12"),
                         rnd(2, "2026-01-01", "2026-01-10", "2026-01-12")])
    check("a round numbered later but dated earlier is REPORTED, not silently sorted",
          len(jumbled["rounds_out_of_order"]) == 1
          and "round 2" in jumbled["rounds_out_of_order"][0],
          f"{jumbled['rounds_out_of_order']} — that means a mis-keyed date or rounds that are not "
          "what they look like, and sorting destroys the only evidence of it")

    check("...and a correctly ordered set reports nothing — the twin",
          ac.cycles(AGENCY_SLOW)["rounds_out_of_order"] == [],
          "a check that always fires is not a check")

    # ================= REFUSALS =================
    none = ac.cycles([])
    check("no rounds is refused with counts as None, never 0",
          none["available"] is False and none["rounds"] is None
          and none["status"] == ac.STATUS_NO_ROUNDS,
          "'nobody submitted' and 'the agency was instantaneous' must not render alike")

    undated = ac.cycles([{"data": {"round": 1, "agency": "City"}}])
    check("a round with no submitted date cannot start a clock, and says so",
          undated["available"] is False and undated["status"] == ac.STATUS_UNDATED
          and undated["rounds_undated"] == 1,
          undated["reason"][:70])

    mixed = ac.cycles(AGENCY_SLOW + [{"data": {"round": 3, "agency": "City"}}])
    check("...and ONE undated round does not discard the rounds that are dated",
          mixed["available"] is True and mixed["rounds"] == 2 and mixed["rounds_undated"] == 1,
          f"rounds={mixed['rounds']} undated={mixed['rounds_undated']} — a single bad record must "
          "not take out the report")

    # ================= the axis is stated =================
    check("the day basis is on the response, not left in the arithmetic",
          slow_agency["days_basis"] == "calendar" and "weekend" in slow_agency["note"],
          "construction durations here are WORKING days; a statutory review clock is not, and "
          "mixing the two silently is how a delay analysis produces a confident wrong number")

    check("comments are totalled, because the count is what a resubmittal is scoped from",
          slow_agency["total_comments"] == 13, f"{slow_agency['total_comments']}")

    check("the result survives json.dumps — a route has to return it",
          bool(json.dumps(slow_agency)) and bool(json.dumps(none)))

    # ================= filtering to one application =================
    two_apps = AGENCY_SLOW + [{**rnd(1, "2026-05-01", "2026-05-10", "2026-05-11"),
                               "data": {**rnd(1, "2026-05-01", "2026-05-10", "2026-05-11")["data"],
                                        "permit": "PRM-999"}}]
    one = ac.cycles(two_apps, application="PRM-001")
    check("filtering to one application excludes the other's rounds",
          one["rounds"] == 2 and ac.cycles(two_apps)["rounds"] == 3,
          f"{one['rounds']} of {ac.cycles(two_apps)['rounds']} — mixing two applications' rounds "
          "would average an agency's behaviour across permits it never saw together")

    if _FAILURES:
        print(f"FAILED: {', '.join(_FAILURES)}")
        return 1
    print("approval_cycles: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
