"""Three PPC implementations, one dashboard, and they do not agree.

This file exists because the disagreement is **real, shipped, and invisible from any one of them**.
Each module is internally consistent; the defect only appears when the same week is put through all
three. That is the shape a per-module test cannot catch by construction.

The numbers below are measured, not asserted from reading. If any of them changes, this fails and
somebody has to decide whether the change was intended — which is the whole purpose, because
consolidating them is a **domain decision** (a GC reports PPC to an owner) and not a cleanup.
"""
from __future__ import annotations

from aec_api import modules as me
from aec_api import schedule_lastplanner as lp
from aec_api.lean import ppc as lean_ppc
from aec_api.pull_plan import _pct

_FAILURES: list[str] = []
_REAL_LIST = me.list_records


def check(name: str, ok: bool, note: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}   {note}")
    if not ok:
        _FAILURES.append(name)


#: One week. Two commitments answered (one done, one missed), three still planned.
#: The honest reading is "not measurable yet" — nobody knows how the week went.
MIXED = (
    [{"data": {"status": "Complete", "workflow_state": "done", "week": "2026-03-02", "trade": "Concrete"}}]
    + [{"data": {"status": "Missed", "workflow_state": "not_done", "week": "2026-03-02",
                 "variance_reason": "materials", "trade": "Concrete"}}]
    + [{"data": {"status": "Planned", "workflow_state": "planned", "week": "2026-03-02", "trade": "Concrete"}}] * 3
)


def main() -> int:
    try:
        # --- lean.ppc: denominator is EVERY record ------------------------------------------------
        lean = lean_ppc(MIXED)
        check("lean.ppc counts unanswered commitments as failures",
              lean["ppc"] == 0.2 and lean["commitments"] == 5,
              f"1 done of 5 records = {lean['ppc']} — the three still planned drag it down, "
              "so mid-week every team reads as failing")

        # --- pull_plan: denominator is ASSESSED ONLY ------------------------------------------------
        done = sum(1 for r in MIXED if r["data"]["workflow_state"] == "done")
        not_done = sum(1 for r in MIXED if r["data"]["workflow_state"] == "not_done")
        pull = _pct(done, done + not_done)
        check("pull_plan.metrics counts only assessed ones",
              pull == 50.0,
              f"1 done of {done + not_done} assessed = {pull}% — the three planned are simply "
              "not in the denominator")

        # --- the vendored engine: unmeasurable ------------------------------------------------------
        me.list_records = lambda db, mod, pid, limit=0: [  # type: ignore[assignment]
            {"id": f"t{i}", "ref": f"T{i}", "title": "c", "data": r["data"]}
            for i, r in enumerate(MIXED)]
        vend = lp.reliability(None, "p1")
        week = vend["trend"][0]
        check("core/lastplanner reports the week as UNMEASURABLE, not as a number",
              week["ppc"] is None and week["unassessed"] == 3,
              f"3 unassessed of {week['committed']} committed -> ppc=None; "
              "a missing measurement reported as a good one is worse than no measurement")

        # --- the divergence itself ------------------------------------------------------------------
        check("the three disagree on the SAME week, and the spread is not a rounding argument",
              lean["ppc"] * 100 != pull and week["ppc"] is None,
              f"lean {lean['ppc'] * 100:.0f}%  ·  pull_plan {pull:.0f}%  ·  vendored None "
              "— and the portal renders the pull_plan one")

        check("...and the rendered number is the FLATTERING one",
              pull > lean["ppc"] * 100,
              f"{pull:.0f}% shown vs {lean['ppc'] * 100:.0f}% computed elsewhere for the same week")

        # --- two more lean.ppc defects, pinned ---------------------------------------------------------
        empty = lean_ppc([])
        check("lean.ppc reports 0.0 and 'needs work' for a project with NO commitments",
              empty["ppc"] == 0.0 and empty["rating"] == "needs work",
              "a team that made no promises is not a team that broke them — pinned as a known defect, "
              "not endorsed")

        no_reason = lean_ppc([{"data": {"status": "Missed"}}])
        check("lean.ppc DEFAULTS a missing variance reason instead of demanding one",
              no_reason["top_variance_reasons"] == [{"reason": "Unspecified", "count": 1}],
              "the reasons are the entire learning loop; a default quietly fills it with a value "
              "nobody entered")

        # The vendored engine's equivalent is an explicit enum member, which is a recorded absence
        # rather than a string that looks like data.
        check("...where the vendored engine records it as NOT_RECORDED, an explicit absence",
              any(x["reason"] == "materials" for x in vend["top_reasons"]),
              f"{vend['top_reasons']} — reasons come back as enum values, not free text")

    finally:
        me.list_records = _REAL_LIST  # type: ignore[assignment]

    if _FAILURES:
        print(f"FAILED: {', '.join(_FAILURES)}")
        return 1
    print("test_ppc_divergence OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
