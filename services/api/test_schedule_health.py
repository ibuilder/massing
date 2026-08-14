"""R45-SCHED-REACH ① — the DCMA 14-point adapter.

`massingplan/core/health.py` implements the checks and is 634 lines of vendored engine that nothing
in this application could call until `aec_api/schedule_health.py` existed. These assertions are about
the **adapter**, not the checks: the engine has its own correctness upstream, and re-testing its
arithmetic here would fork the contract by pinning behaviour we do not own.

What the adapter owes the caller is narrower and entirely ours:

* a real schedule reaches the engine at all (the reachability this whole item is about),
* a schedule that is *bad* is reported as bad — without this, every assertion below passes on an
  adapter that returns a hardcoded grade A,
* the three states never collapse: **no activities**, **a loop**, and **assessed** are different
  answers, and neither of the first two is a grade of F,
* the optional baseline/resource arguments are actually wired, rather than accepted and dropped.
"""
from __future__ import annotations

from datetime import date

from aec_api.schedule_health import health

_FAILURES: list[str] = []


def check(name: str, ok: bool, note: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}   {note}")
    if not ok:
        _FAILURES.append(name)


def act(id_: str, days: int, preds: str = "", **data: object) -> dict:
    """`duration`, NOT `duration_days`.

    `schedule_engine._duration_days` reads `data["duration"]` and falls back to `finish - start`,
    then to **1**. This fixture said `duration_days` for its first several releases, so every activity
    arrived as a 1-day task and the CPLI check reported a *3-day* critical path for 5+10+15 days of
    work. Nothing failed — the assertions are about structure — but the suite was exercising a
    schedule nobody had described. `test_duration_is_actually_read` below is the guard.
    """
    return {"id": id_, "ref": id_.upper(), "title": f"Activity {id_}",
            "data": {"duration": days, "predecessors": preds, **data}}


#: A well-formed chain: every activity linked, FS, no lags, no constraints.
CLEAN = [act("a", 5), act("b", 10, "a"), act("c", 15, "b")]

#: The same three activities with nothing joining them. Check 1 (Logic) counts dangling activities.
DANGLING = [act("a", 5), act("b", 10), act("c", 15)]


def main() -> int:
    # --- the guard the fixture needed and did not have -------------------------------------------
    #
    # `schedule_engine._duration_days` reads `data["duration"]`; anything else falls through to a
    # 1-day default. This fixture said `duration_days` for several releases and every assertion below
    # still passed, because they are about structure. A suite exercising a schedule nobody described
    # is worse than a missing one: it reports coverage it does not have.
    r = health(CLEAN)
    cpli = next(c for c in r["checks"] if c["number"] == 13)
    check("the fixture's durations are actually read — not silently defaulted to 1 day",
          "30-day" in cpli["detail"],
          f"{cpli['detail'][:52]} (5+10+15; a 3-day path means the key was wrong)")

    # --- the reachability this item exists for -------------------------------------------------
    check("a real schedule reaches the vendored engine and comes back assessed",
          r["available"] and r["assessed"] > 0,
          f"grade {r['grade']}, {r['assessed']} assessed / {r['skipped']} skipped")

    check("the engine ran all fourteen checks, not a subset the adapter chose",
          len(r["checks"]) == 14, f"{len(r['checks'])} checks")

    # --- the twin: it can say something is WRONG ------------------------------------------------
    #
    # Without this, every other assertion here is satisfied by an adapter that returns a canned
    # grade A. A quality score that cannot report poor quality is not a quality score.
    bad = health(DANGLING)
    check("...and a schedule with dangling logic is reported as failing",
          bad["available"] and bad["failed"] > 0 and bad["score"] < r["score"],
          f"grade {bad['grade']}, score {bad['score']} vs {r['score']} clean, "
          f"{bad['failed']} failed")

    logic = next(c for c in bad["checks"] if c["number"] == 1)
    check("...and it names WHICH check failed and who offended",
          logic["status"] == "fail" and logic["offender_count"] > 0,
          f"check 1 Logic: {logic['status']}, {logic['offender_count']} offender(s)")

    # --- the honesty rule: skipped is not passed -------------------------------------------------
    #
    # The engine excludes skipped checks from the denominator, and its own docstring says why: a tool
    # that scores 14/14 because four checks could not run is worse than one that does not score.
    # Asserted here because the adapter is what surfaces the numbers a reader trusts.
    assessed = [c for c in r["checks"] if c["status"] != "skipped"]
    skipped = [c for c in r["checks"] if c["status"] == "skipped"]
    check("skipped checks are excluded from the score, not counted as passes",
          r["score"] == 100.0 and len(skipped) == 4 and len(assessed) == 10,
          f"100.0 over {len(assessed)} runnable, NOT {100.0 * len(assessed) / 14:.1f} over 14")

    check("...and every skipped check says what was missing",
          all(c["detail"].lower().startswith("skipped") for c in skipped),
          f"{len(skipped)} skipped, each with a reason")

    # --- the optional arguments are wired, not decoration ----------------------------------------
    #
    # An adapter that accepts `baseline_finish` and drops it would pass every assertion above. The
    # observable difference is check 14 moving from skipped to run.
    b14 = next(c for c in r["checks"] if c["number"] == 14)
    with_baseline = health(CLEAN, baseline_finish={"a": date(2026, 1, 5), "b": date(2026, 1, 20),
                                                   "c": date(2026, 2, 10)})
    b14_after = next(c for c in with_baseline["checks"] if c["number"] == 14)
    check("passing baseline_finish actually reaches the engine — check 14 stops being skipped",
          b14["status"] == "skipped" and b14_after["status"] != "skipped",
          f"check 14: {b14['status']} -> {b14_after['status']}")

    res = health(CLEAN, resourced_activity_ids=["a", "b", "c"])
    r10, r10_after = (next(c for c in x["checks"] if c["number"] == 10) for x in (r, res))
    check("...and so does resourced_activity_ids — check 10 stops being skipped",
          r10["status"] == "skipped" and r10_after["status"] != "skipped",
          f"check 10: {r10['status']} -> {r10_after['status']}")

    # --- the three states stay distinct ----------------------------------------------------------
    empty = health([])
    check("no activities is UNAVAILABLE, not a grade of F",
          empty["available"] is False and empty["grade"] is None and empty["score"] is None,
          f"grade={empty['grade']!r} score={empty['score']!r} — an unplanned project is not a bad one")

    check("...and it says so in words a caller can show",
          bool(empty.get("reason")), empty.get("reason", ""))

    cyc = health([act("a", 5, "c"), act("b", 10, "a"), act("c", 15, "b")])
    check("a cyclic network is UNAVAILABLE with its cycle, not a grade",
          cyc["available"] is False and cyc["grade"] is None and bool(cyc.get("cycle")),
          f"cycle={cyc.get('cycle')} — no dates were computed, so no check could read one")

    # The shape twin. Callers branch on `available`, but anything that reads `checks` or `failed`
    # without branching must not explode — that is why the unavailable shape carries every key.
    check("every unavailable shape carries the full key set, so a caller need not special-case it",
          all(set(x) >= set(r) - {"activity_count", "relationship_count", "data_date", "optimisable"}
              for x in (empty, cyc))
          and all(k in x for x in (empty, cyc) for k in ("checks", "failed", "assessed", "skipped")),
          "checks/failed/assessed/skipped present and empty on both")

    # --- the layering contract -------------------------------------------------------------------
    #
    # The dependency runs ONE WAY: the adapter knows both vocabularies, the engine knows only its own.
    #
    # The first version of this asserted it by grepping the adapter's own source for "sqlalchemy" —
    # and failed, because the docstring explaining the rule contains the word. A source-grep gate
    # reading its own documentation is a shape this repo has now hit six separate times, and it was
    # the weaker check anyway: it scanned the file that is *allowed* to know both sides.
    #
    # The invariant worth asserting is directional and lives at the other end — nothing under
    # `massingplan.core` may import `aec_api`. That is checkable by import, not by grep, and it is
    # what would actually break a re-sync.
    from pathlib import Path

    core = Path(__file__).resolve().parent / "src" / "massingplan" / "core"
    leaks = [p.name for p in core.glob("*.py")
             if "aec_api" in p.read_text(encoding="utf-8")]
    check("the dependency is one-way — no vendored module imports the application",
          not leaks, f"{len(list(core.glob('*.py')))} vendored modules, none reach back"
                     if not leaks else f"LEAKED: {', '.join(leaks)}")

    # ...and the other end, asserted by import rather than by reading a docstring: the adapter really
    # does pull the engine in. If someone reimplemented the checks locally this would still pass the
    # behavioural assertions above while the whole point of the item — reaching vendored code —
    # quietly evaporated.
    import ast

    import aec_api.schedule_health as mod

    tree = ast.parse(Path(mod.__file__).read_text(encoding="utf-8"))
    engine_imports = sorted(
        n.module for n in ast.walk(tree)
        if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("massingplan.")
    )
    check("...and the adapter reaches the vendored engine rather than reimplementing it",
          any(m == "massingplan.core.health" for m in engine_imports),
          f"imports {', '.join(engine_imports)}")

    if _FAILURES:
        print(f"FAILED: {', '.join(_FAILURES)}")
        return 1
    print("test_schedule_health OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
