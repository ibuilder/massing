"""Change-order log analytics — the CO value pipeline (pending / approved / executed), reason mix,
schedule-day exposure, ball-in-court, plus the upstream change-event ROM pipeline (potential exposure
not yet a CO). Pure read-side aggregation over the cor / change_event modules; no writes."""
from __future__ import annotations

from typing import Any

# cor workflow_state -> whose court the ball is in
COR_COURT = {"draft": "GC (prepare)", "submitted": "Owner / Architect", "approved": "GC (execute)",
             "executed": "Executed", "rejected": "Rejected"}
COR_PENDING = ("draft", "submitted")
COR_FINAL = ("executed",)
#: The owner refused it: no money owed, no time claimed. A NAMED CONSTANT because that is the
#: invariant `services/api/test_refusal_readers.py` asserts for this whole class — *"a rule spelled
#: out inline in each reader is a rule with N places to rot"* — and `co_log` tested `"rejected"` as
#: a bare literal in two places that had come to disagree with each other: the money total counted
#: it and the schedule total did not.
COR_REFUSED = ("rejected",)


def _num(v: Any) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _d(r: dict) -> dict:
    return r.get("data") or r


def co_log(db, pid: str) -> dict[str, Any]:
    from . import modules as me
    cors = me.list_records(db, "cor", pid, limit=100000) if "cor" in me.TABLES else []
    ces = me.list_records(db, "change_event", pid, limit=100000) if "change_event" in me.TABLES else []

    by_state, by_reason, ball_in_court = {}, {}, {}
    total = pending = approved = executed = rejected = 0.0
    sched_days = rejected_days = 0.0
    rows = []
    for c in cors:
        d = _d(c)
        st = c.get("workflow_state") or "draft"
        by_state[st] = by_state.get(st, 0) + 1
        court = COR_COURT.get(st, st)
        ball_in_court[court] = ball_in_court.get(court, 0) + 1
        reason = (d.get("reason") or "(unspecified)").strip() or "(unspecified)"
        by_reason[reason] = by_reason.get(reason, 0) + 1
        amt = _num(d.get("amount"))
        total += amt
        if st in COR_PENDING:
            pending += amt
        elif st == "approved":
            approved += amt
        elif st == "executed":
            executed += amt
        elif st in COR_REFUSED:
            rejected += amt
        sd = _num(d.get("schedule_days"))
        # A REJECTED change order claims no time, so it is out of the schedule total — and it was
        # IN the money total two lines up. CO-REJECTED: the same refusal, two treatments, one
        # function. Both figures are now published with the refusal named beside them rather than
        # one of them silently resolved: the rejected days are counted separately so the exclusion
        # is as visible as the inclusion was, and `live_value` is the money figure that honours the
        # refusal the way this line already does.
        if st in COR_REFUSED:
            rejected_days += sd
        else:
            sched_days += sd
        rows.append({
            "ref": c.get("ref"), "subject": d.get("subject"), "state": st, "ball_in_court": court,
            "reason": reason, "amount": amt, "schedule_days": sd,
        })

    # upstream change-event ROM exposure (potential COs not yet executed)
    ce_open = ce_rom = 0.0
    ce_by_scope = {}
    for e in ces:
        d = _d(e)
        st = e.get("workflow_state") or "open"
        scope = (d.get("scope_status") or "Undetermined").strip() or "Undetermined"
        ce_by_scope[scope] = ce_by_scope.get(scope, 0) + 1
        if st != "closed":
            ce_open += 1
            ce_rom += _num(d.get("rom"))

    return {
        "co_count": len(rows),
        # EVERY COR raised, REJECTED ONES INCLUDED. That is a volume-of-change figure and a
        # legitimate one — it is also the number a report quotes as exposure, which it is not, and
        # it was printed beside `pending`/`approved`/`executed` with no fourth term to explain the
        # gap. Measured on a four-COR fixture: total $575,000, the three named states $175,000, and
        # a $400,000 residue that is the rejected COR and had no name on the screen. *A total whose
        # own parts do not sum to it leaves the reader to invent the difference.*
        "total_value": round(total, 2),
        # WHAT IS OR MAY BECOME MONEY — total minus rejected, and the headline a change-order
        # report wants. `test_refusal_readers.py`'s rule for the whole class: a refused record is
        # not exposure. Added rather than changing `total_value`, because the raised total answers a
        # real question and silently redefining it would move a figure in somebody's saved report.
        "live_value": round(total - rejected, 2),
        "pending_value": round(pending, 2),     # draft + submitted (awaiting approval)
        "approved_value": round(approved, 2),   # approved, not yet executed
        "executed_value": round(executed, 2),   # in the revised contract sum
        "rejected_value": round(rejected, 2),
        # Excludes rejected CORs, which claim no time. The excluded days are published rather than
        # dropped so the asymmetry with `total_value` is auditable from the response alone.
        "total_schedule_days": round(sched_days, 1),
        "rejected_schedule_days": round(rejected_days, 1),
        "by_state": by_state, "by_reason": dict(sorted(by_reason.items())),
        "ball_in_court": ball_in_court,
        "change_events_open": int(ce_open),
        "change_event_rom_exposure": round(ce_rom, 2),
        "change_events_by_scope": dict(sorted(ce_by_scope.items())),
        "rows": sorted(rows, key=lambda r: (r.get("ref") or "")),
    }
