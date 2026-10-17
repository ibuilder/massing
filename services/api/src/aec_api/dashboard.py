"""Role-tailored dashboard (GC portal). Aggregates records across all modules into a
per-party view: KPIs, "ball-in-your-court" action items (records the acting party can move
through the workflow right now), per-module status counts, and a cost snapshot."""
from __future__ import annotations

from collections import Counter
from datetime import date
from typing import Any

from sqlalchemy.orm import Session

from . import cost, workflow_config
from . import modules as me
from .timeutil import utc_today


def _overdue(rec: dict, terminal: set[str]) -> bool:
    """Whether this record is past its due date AND still somebody's work.

    DASH-TERMINAL. `terminal` used to be the literal `("closed", "answered", "verified", "done")`,
    applied to all 139 modules, and it was wrong in both directions. Measured against the modules'
    own workflows:

    * A state terminal in its own module and absent from that tuple was handed to `active_records`
      as a SQL exclusion, so the record was LOADED as active and then passed this test: **finished
      work counted toward the portal's headline `overdue` KPI.** Same shape as CO-REJECTED and
      EXPIRY-UNDATED -- a figure inflated by work nobody owes.

      **The bound matters and the first draft of this note got it wrong in the flattering
      direction.** Structurally there are 74 such (module, state) pairs, but the overdue loop runs
      only where `_due_field_name(mod)` finds a due field, and that is **16 of 139 modules** -- so
      69 of those pairs never reach this KPI. Measured exposure is **5 pairs**: a `superseded`
      `decision`, a `cleared` `due_diligence`, a **`void` `rfi`**, an `accepted` `risk`, an
      `approved` `selection`. The voided RFI is the sharpest, because `rfi.RFI_WITHDRAWN` exists
      precisely to say *"a voided RFI was retracted: it carries no cost or schedule exposure"* --
      and this KPI counted it late. *A severity asserted over the wrong population is still wrong
      when the defect is real.*
    * `answered` is in that tuple and is NOT terminal in `rfi`, its only declarer: the workflow has
      `answered -> closed | accept [GC]` and `answered -> open | reopen [GC]`, and `rfi.COURT` says
      the ball is with *"GC (accept)"*. So an answered-but-unaccepted RFI counted as finished here
      while `rfi.CLOSED_STATES == ("closed", "void")` counted it open -- **three places in the tree
      answering one question two ways.**

    The set is now this record's own module's, derived by `workflow_config.terminal_states` from the
    workflow in force.
    """
    due = rec["data"].get("due_date")
    try:
        return bool(due) and date.fromisoformat(str(due)[:10]) < utc_today() \
            and rec["workflow_state"] not in terminal
    except (TypeError, ValueError):
        return False


def build(db: Session, pid: str, party: str | None) -> dict[str, Any]:
    by_module: list[dict] = []
    action_items: list[dict] = []
    #: How many records are ACTUALLY in this party's court, across every module. Counted from the
    #: state counts, never from `action_items`, which is capped — see the note at the return.
    action_total = 0
    overdue = 0
    # DASH-TERMINAL. These two sets were hardcoded here and applied to every module:
    #   open_states     = {open, submitted, draft, issued, scheduled, investigating,
    #                      applied, agenda, proposed, pending}
    #   terminal_states = {closed, answered, verified, done}
    # Both were wrong in both directions, and the two directions are NOT the same size.
    # `overdue` is the smaller: only 16 of 139 modules carry a due-date field, so only those are
    # scanned, and 5 (module, state) pairs there are finished work the KPI counted as late
    # (`decision.superseded`, `due_diligence.cleared`, `rfi.void`, `risk.accepted`,
    # `selection.approved`) plus `rfi.answered`, live work it called finished.
    # The open KPIs are the large one: **140 (module, state) pairs are LIVE in their module and in
    # NEITHER set**, so no KPI counted them -- 76 of 139 modules have at least one. Five of the six
    # headline open KPIs undercounted by name: `pending_change_orders` missed `approved` CORs,
    # `open_issues` missed `resolved`/`assigned`, `open_quality` missed `dispositioned` NCRs and
    # `corrected` deficiencies, `open_safety` missed `assigned`/`corrected` observations,
    # `open_punchlist` missed `ready`.
    #
    # Resolved per module from the workflow IN FORCE, so a project that overrode its workflow gets
    # its own answer. `live` is the COMPLEMENT of `terminal` rather than a second allowlist,
    # because a second allowlist is exactly the half that went stale: a state is live or it is
    # finished, and there is no third set to forget.
    wf_cfg = workflow_config.load(pid)
    counts = Counter()
    #: What each open KPI below counted, so the response can state it rather than implying a
    #: hardcoded list. Per module, from its own workflow.
    basis: dict[str, dict[str, list[str]]] = {}

    ACTION_CAP = 300          # bound the action-item collection (output is sliced to 100 anyway)
    # DASH-UNION (PERF-4): ONE UNION-ALL round-trip replaces the per-module GROUP BY (~124 queries).
    all_counts = me.state_counts_all(db, pid)
    for key, mod in me.REGISTRY.items():
        states = all_counts.get(key, {})
        total = sum(states.values())
        if not total:
            continue
        eff = workflow_config.effective(mod, pid, wf_cfg)
        terminal_states = set(workflow_config.terminal_states(eff))
        # OPEN IS THE COMPLEMENT OVER THE OBSERVED STATES, not the declared live ones -- and that
        # distinction is a defect this item shipped and `test_trunc_counted` caught. `states` comes
        # from `state_counts_all`, which reports what the DATA holds, while a DECLARED live set
        # reports what the module declares. Those are not the same: a record can sit in a state the
        # workflow no longer declares (written before a workflow change, or by an import), and under
        # a declared set such a state is in neither half -- so it vanished from every open KPI,
        # which is the exact shape this item exists to fix, re-introduced one layer along. The
        # `workflow_config.live_states` helper that did this is DELETED; see the note on
        # `terminal_states` for why there is no companion to it.
        #
        # Terminal-ness is the thing the workflow can actually answer ("no transition leaves here"),
        # so that stays declared and everything else observed is live. It also fails in the safe
        # direction: an unrecognised state shows up as work rather than disappearing. A module with
        # no workflow at all then has nothing terminal, so all of it is open -- which is the right
        # answer and not merely the convenient one.
        open_states = {s for s in states if s not in terminal_states}
        basis[key] = {"open": sorted(open_states), "terminal": sorted(terminal_states)}
        by_module.append({"key": key, "name": mod["name"], "section": mod.get("section"),
                          "count": total, "by_state": states})
        counts["total"] += total
        counts[f"open:{key}"] += sum(n for s, n in states.items() if s in open_states)

        # overdue: only modules that actually carry a due-date field need their JSON loaded — at
        # scale this avoids reading the `data` blob for the entire non-terminal tail of every module.
        if me._due_field_name(mod):
            for r in me.active_records(db, key, pid, terminal_states):
                if _overdue(r, terminal_states):
                    overdue += 1

        # action items: query only the states where this party has a move AND that are "open", with
        # lean columns (no JSON) and a cap — not the whole active tail. `available_actions` needs
        # only workflow_state, which is an indexed column.
        # The actionable STATES are derived for every module, outside the cap — `states` already
        # holds this party's per-state counts from the single UNION-ALL above, so the true total
        # costs no query. Deriving it inside the cap is what made the count a page length.
        actionable = {s for s in states
                      if s in open_states and me.available_actions(mod, s, party)}
        action_total += sum(states[s] for s in actionable)
        if actionable and len(action_items) < ACTION_CAP:
            need = ACTION_CAP - len(action_items)
            for r in me.active_records(db, key, pid, terminal_states, with_data=False,
                                       states=actionable, limit=need):
                action_items.append({
                    "module": key, "module_name": mod["name"], "id": r["id"], "ref": r["ref"],
                    "title": r["title"], "state": r["workflow_state"],
                    "actions": [a["action"] for a in me.available_actions(mod, r["workflow_state"], party)],
                })

    def open_count(key):
        return counts.get(f"open:{key}", 0)

    kpis = {
        "total_records": counts["total"],
        # The TRUE total, not the length of a capped collection. This KPI predates
        # `action_item_count` and carried the identical defect.
        "my_action_items": action_total,
        "overdue": overdue,
        "open_rfis": open_count("rfi"),
        "pending_change_orders": open_count("cor"),
        "open_issues": open_count("issue") + open_count("coordination_issue"),
        "open_quality": open_count("ncr") + open_count("deficiency") + open_count("inspection"),
        "open_safety": open_count("incident") + open_count("observation"),
        "open_punchlist": open_count("punchlist"),
    }

    try:
        cost_snapshot = cost.summary(db, pid)
    except Exception:
        cost_snapshot = None

    by_module.sort(key=lambda m: (-m["count"], m["name"]))
    action_items.sort(key=lambda a: a["module"])
    return {"party": party or "GC", "kpis": kpis, "cost": cost_snapshot,
            # DASH-TERMINAL. Which states each module counts as open and which as finished,
            # resolved from the workflow IN FORCE for this project. On the wire because the client
            # cannot derive it -- an override replaces the transitions, and terminal-ness is a
            # property of those. Only the modules that contributed a record are listed, so this is
            # the same population `by_module` is over.
            "kpi_basis": basis,
            # `action_items` is a page; `action_item_count` is how many are actually in this
            # party's court. The dashboard renders the first 20 of the page, so without the total
            # a user with 340 open items and one with 100 saw the same screen.
            #
            # **AND THE FIRST VERSION OF THIS FIELD WAS `len(action_items)`, WHICH IS ITSELF A PAGE
            # LENGTH.** Collection stops at `ACTION_CAP`, so the count could never exceed 300 and
            # the 340-item user in the sentence above read exactly `300` — a cap presented as a
            # total, which is the defect TRUNC-COUNTED existed to remove, shipped inside the change
            # that removed it. Found by review. *A field added to disclose a cap is the easiest
            # place in the codebase to re-introduce one, because nobody audits the fix.*
            "action_items": action_items[:100], "action_item_count": action_total,
            "by_module": by_module}
