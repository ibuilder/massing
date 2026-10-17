"""Submittal register — the spec-section-organized submittal log: turnaround (received→returned),
ball-in-court (workflow state), and overdue flags (required-on-site passed, not yet closed). Pure.

SUBMITTAL-RETURNED. `CLOSED_STATES` was `("returned", "closed")`, written out by hand, and
`returned` is not a terminal state: the shipped `submittal` workflow gives it TWO outgoing
transitions, `close` and `revise_resubmit`. So a submittal the A/E sent back marked *"Revise &
Resubmit"* was counted as closed -- out of `open_count`, and **unable to be overdue at all**,
because `is_overdue` tests `st not in CLOSED_STATES`. Measured, one submittal six weeks past its
required-on-site date:

| | `Revise & Resubmit` | `Approved` |
|---|---|---|
| `open_count` | 0 | 0 |
| `overdue_count` | 0 | 0 |
| `avg_turnaround_days` | 9.0 | 9.0 |

The two rendered identically on every figure the screen prints, and a rejected submittal six weeks
late is the single most urgent row in a submittal log.

**The derivation agrees with the sibling register and disagrees with this one, which is the whole
argument for deriving it.** A state is terminal when no transition leaves it. Run against
`rfi/module.json` that reproduces `rfi.CLOSED_STATES == ("closed", "void")` exactly -- a list
written out by hand in another file, by somebody else, and right. Run against
`submittal/module.json` it returns `("closed",)` alone. *Two siblings hardcoded the same kind of
list; the rule tells which one drifted.* `services/api/test_submittals.py` asserts both halves of
that, rather than leaving it in this docstring.

And since WORKFLOW-DARK a project may REPLACE those transitions, so the set is resolved against the
workflow in force and published as `closed_states` with `workflow_overridden` beside it -- the same
contract `tm_summary` states for `accepted_states`.

### Two counts over populations the response did not state

* `overdue_count` can only count a submittal carrying a `required_on_site` date. Measured: 40
  submittals in A/E review with none recorded returns **`overdue_count: 0`**, which reads as
  *nothing is late*. `dated_count` is the population now, and EXPIRY-UNDATED is the same shape one
  register over.
* `avg_turnaround_days` averages the submittals carrying BOTH `date_received` and `date_returned`.
  Measured: **3.5 days over 2 of 40**. `turnaround_count` is that population.

Both reach further than the one screen: `projecthealth` turns `overdue_count` into a red/amber/green
tile, and `report_builders.construction` prints `Open` / `Overdue` / `Avg turnaround` as KPIs on an
exported register. *A count whose population is unstated gets quoted by whoever reads it next.*
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Any

#: The shipped `submittal` workflow's terminal state. Kept as the fallback for a caller with no
#: module in scope -- NOT the authority: `terminal_states` derives it from the workflow in force.
#: It used to read `("returned", "closed")`, which is the defect this module's docstring is about.
CLOSED_STATES = ("closed",)

#: Dispositions that send the submittal back. A `returned` row carrying one of these is not
#: progress -- it is work owed by the subcontractor, and the register's job is to say so.
RESUBMIT_DISPOSITIONS = ("Revise & Resubmit", "Rejected")


def _parse(s: Any) -> date | None:
    if not s:
        return None
    try:
        return datetime.fromisoformat(str(s)[:10]).date()
    except ValueError:
        return None


def terminal_states(mod: dict) -> list[str]:
    """The workflow's own definition of "nothing left to do": a state no transition leaves.

    Structural, not inferred from the order states are declared in -- COURT-SPLIT measured that
    order and found it alphabetical in at least one module, so reading a progression out of it is
    wrong. An outgoing edge is a fact about the graph.
    """
    wf = mod.get("workflow") or {}
    states = [str(s) for s in wf.get("states") or []]
    leaves = {str(t["from"]) for t in wf.get("transitions") or [] if t.get("from")}
    return sorted(s for s in states if s not in leaves)


def effective_closed(pid: str) -> tuple[list[str] | None, bool]:
    """This project's terminal submittal states, and whether its workflow is an override.

    `None` means the question could not be answered -- the module is not installed -- which is not
    the same answer as "no state is terminal" and must not be rendered as one.
    """
    from . import modules_registry, workflow_config
    mod = modules_registry.REGISTRY.get("submittal")
    if not mod:
        return None, False
    eff = workflow_config.effective(mod, pid)
    return terminal_states(eff), bool(eff.get("workflow_overridden"))


def _subs(n: int) -> str:
    return f"{n} submittal" if n == 1 else f"{n} submittals"


def _coverage_note(total: int, dated: int, turns: int, resubmit: int) -> str:
    """The engine's sentence about which submittals each count is over."""
    if not total:
        return "No submittals in the register."
    bits = []
    if dated < total:
        bits.append(f"overdue is over the {dated} of {total} carrying a required-on-site date "
                    f"({total - dated} {'has' if total - dated == 1 else 'have'} none, so "
                    f"{'it' if total - dated == 1 else 'they'} cannot be counted late)")
    if turns < total:
        bits.append(f"the average turnaround is over the {turns} of {total} carrying both a "
                    f"received and a returned date")
    if resubmit:
        bits.append(f"{_subs(resubmit)} came back marked for resubmittal and "
                    f"{'is' if resubmit == 1 else 'are'} still open")
    if not bits:
        return (f"All {_subs(total)} {'carries' if total == 1 else 'carry'} the dates both counts "
                "need, and none is awaiting resubmittal.")
    # NOT `str.capitalize()` -- that lowercases the rest of the string, so a disposition or a state
    # name reaching this sentence would be silently de-capitalised. ITB-DOUBLE's lesson one file
    # over: the inflection somebody forgets is the one nobody reads back.
    note = "; ".join(bits)
    return note[:1].upper() + note[1:] + "."


def register(submittals: list[dict], as_of: date | None = None,
             closed: list[str] | None = None, overridden: bool = False) -> dict[str, Any]:
    today = as_of or date.today()
    closed_set = tuple(closed) if closed is not None else CLOSED_STATES
    rows, by_status, by_section = [], {}, {}
    turnarounds, overdue, dated, resubmit = [], 0, 0, 0
    for s in submittals:
        d = s.get("data") or s
        st = s.get("workflow_state") or "draft"
        by_status[st] = by_status.get(st, 0) + 1
        section = (d.get("spec_section") or "(unassigned)").strip()
        by_section[section] = by_section.get(section, 0) + 1
        rec, ret = _parse(d.get("date_received")), _parse(d.get("date_returned"))
        ros = _parse(d.get("required_on_site"))
        turn = (ret - rec).days if rec and ret else None
        if turn is not None:
            turnarounds.append(turn)
        if ros:
            dated += 1
        is_closed = st in closed_set
        is_overdue = bool(ros and ros < today and not is_closed)
        if is_overdue:
            overdue += 1
        disp = d.get("disposition")
        # A row the A/E sent back, still not closed: the subcontractor owes a resubmittal. Flagged
        # whatever the state is called, because the disposition is what says it is coming back.
        needs_resubmit = bool(disp in RESUBMIT_DISPOSITIONS and not is_closed)
        if needs_resubmit:
            resubmit += 1
        rows.append({
            "ref": s.get("ref"), "title": d.get("title"), "spec_section": section,
            "type": d.get("type"), "responsible": d.get("responsible_contractor"),
            "disposition": disp, "status": st,
            "required_on_site": d.get("required_on_site"), "turnaround_days": turn,
            "overdue": is_overdue, "ball_in_court": st,
            # Whether this row COULD be overdue. `overdue: false` means two different things and
            # a register that cannot tell them apart reports an undated backlog as on time.
            "overdue_assessed": bool(ros),
            "needs_resubmittal": needs_resubmit,
            "closed": is_closed,
        })
    avg_turn = round(sum(turnarounds) / len(turnarounds), 1) if turnarounds else None
    return {
        "submittal_count": len(rows),
        "open_count": sum(1 for r in rows if not r["closed"]),
        "overdue_count": overdue,
        # The population `overdue_count` is over -- not every submittal can be late.
        "dated_count": dated,
        "undated_count": len(rows) - dated,
        "avg_turnaround_days": avg_turn,
        # ...and the population the average is over.
        "turnaround_count": len(turnarounds),
        # Open and sent back: counted as closed before this item, so invisible everywhere.
        "needs_resubmittal_count": resubmit,
        # Which states this register treats as done, and whether they are the shipped ones. Facts
        # the client cannot derive, which is why they are on the wire.
        "closed_states": list(closed_set),
        "workflow_overridden": overridden,
        "by_status": by_status,
        "by_section": dict(sorted(by_section.items())),
        "coverage_note": _coverage_note(len(rows), dated, len(turnarounds), resubmit),
        "rows": sorted(rows, key=lambda r: (r.get("spec_section") or "", r.get("ref") or "")),
    }


def submittal_register(db, pid: str) -> dict[str, Any]:
    from . import modules as me
    subs = me.list_records(db, "submittal", pid, limit=100000) if "submittal" in me.TABLES else []
    closed, overridden = effective_closed(pid)
    return register(subs, closed=closed, overridden=overridden)
