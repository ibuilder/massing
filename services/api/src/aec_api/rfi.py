"""RFI log analytics — the RFI register: ball-in-court (workflow state), overdue (date-required passed
while still awaiting a response), response turnaround, and cost/schedule-impact exposure. Pure read-side
aggregation over the rfi module; no writes. Mirrors the submittals/quality register engines."""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

# states where the ball is with the consultant/designer (awaiting an answer)
AWAITING_RESPONSE = ("draft", "open")
CLOSED_STATES = ("closed", "void")
#: RFI states that are a WITHDRAWN question, not an answered one. A voided RFI was retracted: it
#: carries no cost or schedule exposure and it never received a response. `open_count`,
#: `overdue_count` and `ball_in_court` already honoured this (void is in CLOSED_STATES and has its
#: own court); the exposure counts and the turnaround average did not.
RFI_WITHDRAWN = ("void",)
# workflow_state -> whose court the ball is in
COURT = {"draft": "GC (submit)", "open": "Consultant", "answered": "GC (accept)",
         "closed": "Closed", "void": "Void"}


def _parse(s: Any) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s)[:10]).date()
    except ValueError:
        return None


def _d(r: dict) -> dict:
    return r.get("data") or r


def register(rfis: list[dict], as_of: date | None = None) -> dict[str, Any]:
    today = as_of or date.today()
    by_state, by_discipline, by_priority, ball_in_court = {}, {}, {}, {}
    overdue = cost_impacted = schedule_impacted = voided = 0
    response_days: list[int] = []
    withdrawn_refs: list[str | None] = []
    rows = []
    for r in rfis:
        d = _d(r)
        st = r.get("workflow_state") or "draft"
        by_state[st] = by_state.get(st, 0) + 1
        court = COURT.get(st, st)
        ball_in_court[court] = ball_in_court.get(court, 0) + 1
        disc = (d.get("discipline") or "(unassigned)").strip() or "(unassigned)"
        by_discipline[disc] = by_discipline.get(disc, 0) + 1
        pri = (d.get("priority") or "(none)").strip() or "(none)"
        by_priority[pri] = by_priority.get(pri, 0) + 1
        due = _parse(d.get("due_date"))
        is_overdue = bool(due and due < today and st in AWAITING_RESPONSE)
        if is_overdue:
            overdue += 1
        # Measured before the fix on a register holding one live RFI with no impact and one VOIDED
        # RFI marked cost_impact/schedule_impact "Yes": both exposure counts read 1, sourced
        # entirely from the withdrawn question. A retracted RFI is not exposure the job is carrying.
        withdrawn = st in RFI_WITHDRAWN
        if withdrawn:
            voided += 1
            withdrawn_refs.append(r.get("ref"))
        if not withdrawn and (d.get("cost_impact") or "None") in ("Yes", "Possible"):
            cost_impacted += 1
        if not withdrawn and (d.get("schedule_impact") or "None") in ("Yes", "Possible"):
            schedule_impacted += 1
        created = _parse(r.get("created_at"))
        # Answered/closed RFIs have a response; approximate turnaround created -> last update.
        # A module row's timestamp column is `modified_at`; this read `updated_at`, which no module
        # row carries, so every turnaround was None and `avg_response_days` could never compute —
        # a DEAD metric rather than a slow one, and the refusal filter below would have been
        # vacuous without fixing it first. A withdrawn RFI never got a response, so it is not a
        # turnaround sample either.
        resolved = (_parse(r.get("modified_at"))
                    if st not in AWAITING_RESPONSE and not withdrawn else None)
        days = (resolved - created).days if created and resolved else None
        if days is not None and days >= 0:
            response_days.append(days)
        rows.append({
            "ref": r.get("ref"), "subject": d.get("subject"), "discipline": disc,
            "priority": pri, "state": st, "ball_in_court": court,
            "due_date": d.get("due_date"), "overdue": is_overdue,
            "cost_impact": d.get("cost_impact") or "None",
            "schedule_impact": d.get("schedule_impact") or "None",
            "answered": bool((d.get("answer") or "").strip()),
        })
    open_count = sum(v for k, v in by_state.items() if k not in CLOSED_STATES)
    avg_response = round(sum(response_days) / len(response_days), 1) if response_days else None
    return {
        "rfi_count": len(rows), "open_count": open_count,
        "closed_count": len(rows) - open_count, "overdue_count": overdue,
        "cost_impacted_count": cost_impacted, "schedule_impacted_count": schedule_impacted,
        "avg_response_days": avg_response,
        # `voided_count` is a SUBSET of `closed_count`, not a third bucket beside it — stated so the
        # response reconciles: open_count + closed_count == rfi_count, and voided_count <=
        # closed_count. The exposure counts and the turnaround average are taken over the
        # rfi_count - voided_count RFIs that were not withdrawn.
        "voided_count": voided,
        "withdrawn_excluded": [x for x in withdrawn_refs if x],
        "ball_in_court": ball_in_court, "by_state": by_state,
        "by_discipline": dict(sorted(by_discipline.items())),
        "by_priority": dict(sorted(by_priority.items())),
        "rows": sorted(rows, key=lambda r: (not r["overdue"], r.get("ref") or "")),
    }


def rfi_register(db, pid: str) -> dict[str, Any]:
    from . import modules as me
    rfis = me.list_records(db, "rfi", pid, limit=100000) if "rfi" in me.TABLES else []
    return register(rfis)
