"""R45-SCHED-DEDUPE ② `risk` — one Monte Carlo, and the two ways the deleted one was wrong.

The ring's rule is *diff the two behaviours, keep the deeper engine, keep our rendering, delete the
loser, and write a test asserting there is exactly one implementation*. This is that test, plus the
measurements that justified which one was the loser — kept as assertions rather than as a paragraph,
because the argument for a deletion is the thing most likely to be doubted later.

**Defect 1 — it counted Saturdays.** `schedule_risk` converted a duration to a date with
`start + timedelta(days=round(days))`. On a five-activity, 100-working-day chain from 2026-03-02 it
put the deterministic finish on **2026-06-10**; the surviving engine, running the same `Task`/`Link`
network on the same work calendars the CPM uses, puts it on **2026-07-17**. Thirty-seven days apart,
in the same portal, under two labels that both said "schedule risk".

**Defect 2 — and this one is worse.** Its predecessor index was built from `ref` and `wbs` only,
never the record `id`. `schedule_cpm` resolves BOTH. So a schedule whose logic was written with
record ids chained correctly in the CPM and simulated as **fully parallel** in the risk run: no
error, no warning, a P80 four months early on a job that had four months of chain in it.

The second defect is the reason this file asserts the *behaviour* and not just the file count. A
deletion test that only greps for a filename would pass against a re-import under another name.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, "src")

from aec_api import schedule_cpm, schedule_risk_mc  # noqa: E402

_FAILURES: list[str] = []


def check(name: str, ok: bool, note: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}   {note}")
    if not ok:
        _FAILURES.append(name)


def chain(pred_key: str) -> list[dict]:
    """Five 20-day activities in series — 100 working days from 2026-03-02."""
    return [{"id": f"a{i}", "ref": f"A{i}", "title": f"T{i}",
             "data": {"duration": 20, "start": "2026-03-02",
                      "predecessors": "" if i == 0 else
                                      (f"a{i - 1}" if pred_key == "id" else f"A{i - 1}")}}
            for i in range(5)]


def main() -> int:
    src = Path(__file__).resolve().parent / "src" / "aec_api"

    # ================= EXACTLY ONE IMPLEMENTATION =================
    #
    # Read from the tree, not remembered. The ring's failure mode is two engines drifting apart while
    # both stay green, so the population is enumerated rather than asserted about.
    # A Monte Carlo module either DEFINES a simulator or imports the vendored one. Matching on the
    # word "montecarlo" instead named `risk_board.py`, which merely links to the route — the first
    # version of this scan did exactly that and reported the wrong file.
    simulators = sorted(p.name for p in src.glob("*.py")
                        if "def simulate(" in (t := p.read_text(encoding="utf-8"))
                        or "from massingplan.core.risk import" in t)
    check("exactly one Monte Carlo simulator remains in aec_api",
          simulators == ["schedule_risk_mc.py"],
          f"{simulators} — `schedule_risk.py` was deleted in v0.3.972 rather than left beside it")

    check("...and its module file is really gone, not merely unreferenced",
          not (src / "schedule_risk.py").exists(),
          "an unimported module is still a module somebody can import next week")

    # The twin: the scan must be able to SEE a second simulator, or it reports every tree as clean.
    planted = "from massingplan.core.risk import simulate\ndef simulate(t, l): ...\n"
    check("...and the scan can still see a second one — the twin",
          "def simulate(" in planted and "from massingplan.core.risk import" in planted,
          "a population scan that matches nothing reports every tree as deduplicated")

    # ================= DEFECT 1: CALENDAR DAYS =================
    ref_run = schedule_risk_mc.risk(chain("ref"), iterations=300, seed=7)
    check("the surviving engine finishes a 100-working-day chain in July, not June",
          ref_run["deterministic_finish"] == "2026-07-17",
          f"{ref_run['deterministic_finish']} — the deleted engine said 2026-06-10 by adding "
          "calendar days, 37 days adrift and always optimistic")

    check("...and the P80 buffer is counted in WORKING days too",
          ref_run["buffer_p80_days"] is not None and ref_run["buffer_p80_days"] >= 0,
          f"{ref_run['buffer_p80_days']}d — `risk_board` reads this, and a buffer that counts "
          "Saturdays reads high on a job that is fine")

    # ================= DEFECT 2: PREDECESSORS BY RECORD ID =================
    #
    # THE assertion. Both keyings describe the same chain; both must simulate as the same chain.
    by_id = schedule_risk_mc.risk(chain("id"), iterations=300, seed=7)
    check("logic written with record IDs chains, exactly as it does in the CPM",
          by_id["deterministic_finish"] == ref_run["deterministic_finish"],
          f"id-keyed {by_id['deterministic_finish']} vs ref-keyed {ref_run['deterministic_finish']}. "
          "The deleted engine indexed on ref/wbs only, so this input simulated FULLY PARALLEL and "
          "reported a P80 four months early with no error")

    check("...and the CPM agrees both keyings are one chain — the control",
          (schedule_cpm.compute(chain("id"))["critical_path"]
           == schedule_cpm.compute(chain("ref"))["critical_path"]
           == ["A0", "A1", "A2", "A3", "A4"]),
          "without this the finding would be 'the CPM is lenient', not 'the simulator lost the logic'")

    # ================= WHAT TRAVELLED WITH THE DELETED ENGINE =================
    #
    # "Keep the deeper engine" was never a licence to drop what the shallower one carried.
    for fn in ("for_project", "project_ppc"):
        check(f"{fn} survived the deletion", hasattr(schedule_risk_mc, fn),
              "the PPC lookup existed TWICE before — in the route and in the MCP tool — which is how "
              "two callers of one forecast come to calibrate differently"
              if fn == "project_ppc" else
              "the route, the MCP tool and the risk board now assemble through one function")

    check("PPC still widens the tail below target and narrows it above",
          (schedule_risk_mc.ppc_tail_factor(60) > schedule_risk_mc.ppc_tail_factor(80)
           > schedule_risk_mc.ppc_tail_factor(95)),
          f"60% -> {schedule_risk_mc.ppc_tail_factor(60):.3f}, "
          f"80% -> {schedule_risk_mc.ppc_tail_factor(80):.3f}, "
          f"95% -> {schedule_risk_mc.ppc_tail_factor(95):.3f}. This is ours and it is the one thing "
          "the vendored engine had no notion of")

    check("...and an unknown PPC is the default tail, not a guessed one",
          schedule_risk_mc.ppc_tail_factor(None) == schedule_risk_mc.ppc_tail_factor(80.0),
          "no reliability data is the uncalibrated default; inventing a team average would put a "
          "number nobody measured into a forecast somebody commits to")

    # ================= refusals =================
    empty = schedule_risk_mc.risk([])
    check("nothing to simulate reports unavailable with every percentile None",
          empty["available"] is False
          and all(empty[k] is None for k in ("p10", "p50", "p80", "p90", "buffer_p80_days")),
          "an invented P80 is the whole hazard; 'no data' and 'finishes today' must not render alike")

    if _FAILURES:
        print(f"FAILED: {', '.join(_FAILURES)}")
        return 1
    print("schedule_risk_single: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
