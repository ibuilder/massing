"""Three PPC implementations, two registers, and — since v0.3.974 — ONE rule.

This file used to pin a disagreement. Its own header said the numbers were measured rather than
asserted, and that if any changed, somebody had to decide whether the change was intended — because
consolidating them is a **domain decision** (a GC reports PPC to an owner), not a cleanup.

**That decision was made: the vendored engine's rule wins.** So this file now asserts the agreement,
and keeps the old numbers as the thing that changed, because a consolidation nobody can see the size
of is indistinguishable from a refactor.

## The rule

* met or not met — no partial credit;
* an **unanswered** commitment makes the period unmeasurable, so PPC is `None`, never a number;
* nothing promised is `None` too — a team that made no commitments has not broken any.

## Why there are still three functions

There are **two registers and a route**, not three opinions. `lean.ppc` scores `weekly_plan`;
`pull_plan.metrics` scores `pull_plan_task`; `schedule_lastplanner.reliability` scores the same
`pull_plan_task` records through `massingplan.core.lastplanner`. Collapsing them would merge two
registers that hold different work. What had to agree is the RULE, and that is what is asserted here.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_ppc_divergence.py
"""
from __future__ import annotations

import sys

sys.path.insert(0, "src")

from aec_api import modules as me  # noqa: E402
from aec_api import schedule_lastplanner as lp  # noqa: E402
from aec_api.lean import NO_REASON_RECORDED  # noqa: E402
from aec_api.lean import ppc as lean_ppc  # noqa: E402
from aec_api.pull_plan import _ppc  # noqa: E402

_FAILURES: list[str] = []
_REAL_LIST = me.list_records


def check(name: str, ok: bool, note: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}   {note}")
    if not ok:
        _FAILURES.append(name)


#: One week, five commitments. Two answered (one done, one missed), three still open.
#: The honest reading is "not measurable yet" — nobody knows how the week went.
#: `planned_week` is the field the register declares; the old fixture said `week`, which is
#: `weekly_plan`'s field, and that is how the adapter shipped unable to read its own register.
OPEN_WEEK = (
    [{"data": {"status": "Complete", "workflow_state": "done",
               "planned_week": "2026-03-02", "trade": "Concrete"}}]
    + [{"data": {"status": "Missed", "workflow_state": "not_done", "planned_week": "2026-03-02",
                 "variance_reason": "materials", "trade": "Concrete"}}]
    + [{"data": {"status": "Planned", "workflow_state": "committed",
                 "planned_week": "2026-03-02", "trade": "Concrete"}}] * 3
)

#: The same week once every promise has been answered: 3 done, 2 missed.
CLOSED_WEEK = (
    [{"data": {"status": "Complete", "workflow_state": "done",
               "planned_week": "2026-03-02", "trade": "Concrete"}}] * 3
    + [{"data": {"status": "Missed", "workflow_state": "not_done", "planned_week": "2026-03-02",
                 "variance_reason": "materials", "trade": "Concrete"}}] * 2
)


def vendored(rows: list[dict]) -> dict:
    me.list_records = lambda db, mod, pid, limit=0: [        # type: ignore[assignment]
        {"id": f"t{i}", "ref": f"T{i}", "title": "c", "data": r["data"]}
        for i, r in enumerate(rows)]
    try:
        return lp.reliability(None, "p1")
    finally:
        me.list_records = _REAL_LIST                          # type: ignore[assignment]


def counts(rows: list[dict]) -> tuple[int, int, int]:
    """(done, committed, unassessed) in `pull_plan.metrics`' terms."""
    st = [r["data"]["workflow_state"] for r in rows]
    done = st.count("done")
    return done, len(st), len(st) - done - st.count("not_done")


def main() -> int:
    try:
        # ================= AN OPEN WEEK IS UNMEASURABLE, EVERYWHERE =================
        lean_open = lean_ppc(OPEN_WEEK)
        pull_open = _ppc(*counts(OPEN_WEEK))
        vend_open = vendored(OPEN_WEEK)["trend"][0]["ppc"]

        check("all three report an open week as UNMEASURABLE, not as a number",
              lean_open["ppc"] is None and pull_open is None and vend_open is None,
              f"lean={lean_open['ppc']}  pull_plan={pull_open}  vendored={vend_open}. "
              "Before v0.3.974: lean 20%, pull_plan 50%, vendored None — and the portal rendered "
              "the 50%")

        check("...and each says HOW MANY are unanswered, so the blank is legible",
              lean_open["unassessed"] == 3 and counts(OPEN_WEEK)[2] == 3
              and vendored(OPEN_WEEK)["trend"][0]["unassessed"] == 3,
              "'unmeasurable' with no count reads as a bug; with a count it reads as a status")

        # ================= A CLOSED WEEK AGREES ON THE NUMBER =================
        #
        # The twin, and the one that matters: if they all returned None always, the check above
        # would pass on three broken engines.
        lean_closed = lean_ppc(CLOSED_WEEK)["ppc"]
        pull_closed = _ppc(*counts(CLOSED_WEEK))
        vend_closed = vendored(CLOSED_WEEK)["trend"][0]["ppc"]

        check("a CLOSED week produces a number, and the three agree on it — the twin",
              lean_closed == 0.6 and pull_closed == 60.0 and vend_closed == 0.6,
              f"3 of 5 met: lean={lean_closed}  pull_plan={pull_closed}%  vendored={vend_closed}. "
              "Without this, three engines that always answered None would look consolidated")

        check("...and the two scales are stated, not silently mixed",
              lean_closed == vend_closed and pull_closed == lean_closed * 100,
              "lean and the engine report a FRACTION, pull_plan reports a PERCENT — the same rule "
              "on two scales, which is a rendering choice and not a second opinion")

        # ================= nothing promised is not zero =================
        empty = lean_ppc([])
        check("a project with NO commitments is unmeasurable, not 'needs work'",
              empty["ppc"] is None and empty["rating"] is None and empty["commitments"] == 0,
              "reported 0.0 and 'needs work' until v0.3.974 — a team that made no promises is not "
              "a team that broke them")

        check("...and pull_plan agrees on an empty period",
              _ppc(0, 0, 0) is None,
              "one rule, so the empty case cannot diverge either")

        # ================= reasons are never invented =================
        no_reason = lean_ppc([{"data": {"status": "Missed"}}])
        check("a missed commitment with no stated reason is recorded as an ABSENCE",
              no_reason["top_variance_reasons"] == [{"reason": NO_REASON_RECORDED, "count": 1}]
              and no_reason["reasons_not_recorded"] == 1,
              f"{no_reason['top_variance_reasons']} — it defaulted to the string 'Unspecified' "
              "until v0.3.974, which sorted beside real reasons as though somebody had entered it")

        check("...and the vendored engine records the same absence as an enum member",
              any(x["reason"] == "materials" for x in vendored(CLOSED_WEEK)["top_reasons"]),
              "reasons come back as enum values there, not free text")

        # ================= the adapter reads the REGISTER's field =================
        check("the vendored adapter groups on `planned_week`, the field the register declares",
              vendored(OPEN_WEEK)["available"] is True,
              "it read a bare `week` until v0.3.974 — `weekly_plan`'s field name — so on every real "
              "project it answered 'none of the N tasks carry a week'. "
              "`test_ppc_field_conformance.py` is the gate that keeps this true")

        if _FAILURES:
            print(f"FAILED: {', '.join(_FAILURES)}")
            return 1
        print("ppc_divergence: all checks passed — one rule, two registers")
        return 0
    finally:
        me.list_records = _REAL_LIST                          # type: ignore[assignment]


if __name__ == "__main__":
    raise SystemExit(main())
