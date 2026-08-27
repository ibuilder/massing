"""R35-DEAL-MEMORY reaches the underwriting screen — and refuses two of its three metrics.

## What was actually wrong

`deal_memory.comps` has been routed since the engine shipped. `deal_memory.beside()` — the last
function in that module, whose own docstring says it is *"the shape the underwriting screen wants"* —
had **no caller anywhere in the tree**: not a route, not the client, not a screen.

Nothing failed. `test_reachable.py` asks whether a MODULE is reachable, and `deal_memory` is: the
portfolio route imports it. So the item read as shipped while the half it exists for was dark. That
is `read_p6xml_all` again one ring over, and the lesson recorded there holds here: **a module can be
reachable and its whole reason for existing still be unreachable.**

## The refusals, which are the load-bearing part

`comps` reports three real metrics. The route offers exactly ONE of them, and the other two are
decisions rather than an unfinished job:

* **`cost_per_sf` — offered.** The proforma enters a hard cost and the project has a GFA, so the
  entered number can be put in the metric's own units. A unit conversion, not a claim.
* **`cost_variance_pct` — NOT offered.** The nearest thing a proforma enters is a contingency, and
  *"your contingency should cover this firm's historical overrun"* is an assertion the product would
  be making in an underwriting. Same shape as `/schedule/eot`, which is built and deliberately unwired
  for exactly this reason.
* **`schedule_variance_days` — NOT offered.** A variance is not a duration. Beside an entered
  `construction_months` it would be a category error wearing matching units, which is the most
  dangerous kind: both are numbers of time and the screen would look right.

And `no_gfa` is its own status rather than folded into `insufficient_history`. They are different
problems with different remedies — load a model vs close more projects — and answering the first with
the second sends somebody hunting for history they already have.

Run: cd services/api && PYTHONPATH=src:../data/src ./.venv/bin/python test_deal_memory_beside.py
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./_dm_beside.db")
os.environ.setdefault("STORAGE_DIR", "./_storage_dm_beside")

# `setdefault`, so `run_tests.py` keeps control of the per-test database it already assigns -- but
# then CHECKED, because setdefault also inherits whatever a developer happens to have exported. This
# file calls `Base.metadata.create_all` and commits fixture projects; against an inherited Postgres
# that is test schema and test rows in a real database, and the cleanup below only unlinks a local
# `.db` file. Refuse rather than proceed: a destructive test that silently retargets is worse than
# one that will not start.
_DB = os.environ["DATABASE_URL"]
if not _DB.startswith("sqlite:///"):
    raise SystemExit(f"refusing to run: DATABASE_URL is {_DB!r}, not a local sqlite file. This test "
                     "creates tables and commits fixtures; point it at a scratch sqlite path.")
os.environ.pop("AEC_RBAC", None)
for _f in ("./_dm_beside.db",):
    if os.path.exists(_f):
        os.remove(_f)

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from fastapi import HTTPException  # noqa: E402

from aec_api import cost as cost_engine  # noqa: E402
from aec_api import deal_memory as dm  # noqa: E402
from aec_api import energy  # noqa: E402
from aec_api.db import Base, SessionLocal, engine  # noqa: E402
from aec_api.models import Project  # noqa: E402
from aec_api.routers.operations import project_deal_memory_beside  # noqa: E402

Base.metadata.create_all(engine)

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAILED.append(name)


#: Six closed projects, all built, all with a GFA — one above `MIN_SAMPLES` so a distribution exists
#: at all. Costs chosen so the quartiles are easy to read: $/SF of 200,220,240,260,280,300.
BUILT = {f"built{i}": {"budget": 100.0, "actual": (200.0 + i * 20) * 1000.0} for i in range(6)}
GFA = {f"built{i}": 1000.0 for i in range(6)}
#: The deal being underwritten. No actual spend, so `comps` excludes it from its own comp set — the
#: property the route's comment relies on, asserted here rather than assumed.
LIVE = "underwriting"
GFA[LIVE] = 2000.0

with SessionLocal() as db:
    for pid in [*BUILT, LIVE]:
        db.add(Project(id=pid, name=pid))
    db.commit()

_real_summary, _real_gfa = cost_engine.summary, energy.project_gfa_sf
cost_engine.summary = lambda db, pid: BUILT.get(pid, {})            # noqa: E731 — focused seam
energy.project_gfa_sf = lambda db, pid: GFA.get(pid)                # noqa: E731


def call(pid: str, hard_cost: float):
    with SessionLocal() as db:
        return project_deal_memory_beside(pid, hard_cost, db=db, user="tester")


try:
    # ---- the comp set really is six, and excludes the deal on screen --------------------------------
    # Anti-vacuity, and the route's own stated assumption. If the live project counted, its $/SF would
    # be in the distribution it is being compared against — a number compared to itself, which is the
    # exact failure this whole module was written to avoid.
    with SessionLocal() as db:
        memory = dm.comps(db)
    m = memory["metrics"]["cost_per_sf"]
    check("the comp set is the six BUILT projects", m["status"] == "ok" and m["count"] == 6, str(m))
    check("...and the deal being underwritten is excluded from its own comps",
          LIVE in {e["id"] for e in memory["excluded"]}, str(memory["excluded_count"]))

    # ---- inside the range ---------------------------------------------------------------------------
    # 2000 SF at $250/SF = $500,000. The six landed 200…300, so p25–p75 straddles 250.
    out = call(LIVE, 500_000.0)
    check("a hard cost inside the firm's own range says so", out["status"] == "ok"
          and out["position"] == "within_iqr", f"{out.get('status')} {out.get('position')}")
    check("...reporting the ENTERED value in the metric's units, not the dollars",
          out["entered"] == 250.0, str(out.get("entered")))
    check("...and showing the division it did, so the number can be checked",
          out["gfa_sf"] == 2000.0 and out["hard_cost"] == 500_000.0,
          f"{out.get('gfa_sf')} / {out.get('hard_cost')}")
    check("...as a comparison rather than a verdict", "not a verdict" in (out.get("note") or ""),
          (out.get("note") or "")[:60])

    # ---- above the range ----------------------------------------------------------------------------
    high = call(LIVE, 2000.0 * 400.0)
    check("a hard cost above the firm's own history is reported as above",
          high["position"] == "above_p75", str(high.get("position")))
    low = call(LIVE, 2000.0 * 100.0)
    check("...and below as below", low["position"] == "below_p25", str(low.get("position")))

    # ---- no GFA is its OWN answer -------------------------------------------------------------------
    energy.project_gfa_sf = lambda db, pid: None                    # noqa: E731
    nogfa = call(LIVE, 500_000.0)
    check("a project with no GFA answers no_gfa", nogfa["status"] == "no_gfa", str(nogfa["status"]))
    check("...NOT insufficient_history — different problem, different remedy",
          nogfa["status"] != "insufficient_history" and "model" in (nogfa["note"] or ""),
          (nogfa.get("note") or "")[:70])
    energy.project_gfa_sf = lambda db, pid: GFA.get(pid)            # noqa: E731

    # ---- too little history is NOT a range ----------------------------------------------------------
    # Under the sample floor the engine emits no distribution, and the route must pass that through
    # rather than inventing quartiles from two projects. A range from too few is noise wearing a
    # dollar sign, and it would be on a screen next to somebody's underwriting.
    thin = dict(list(BUILT.items())[:2])
    cost_engine.summary = lambda db, pid: thin.get(pid, {})         # noqa: E731
    few = call(LIVE, 500_000.0)
    check("under the sample floor no range is offered", few["status"] == "insufficient_history",
          str(few["status"]))
    check("...and no median leaks out with it", few.get("median") is None, str(few.get("median")))
    cost_engine.summary = lambda db, pid: BUILT.get(pid, {})        # noqa: E731

    # ---- refusals -----------------------------------------------------------------------------------
    # NaN and inf pass BOTH halves of a `not x or x <= 0` guard -- `not nan` is False and every
    # comparison with nan is False -- so they reached the division and left as `null` under orjson: a
    # comparison with a missing number in it, which reads as "no history" rather than as bad input.
    for bad in (0.0, -5.0, float("nan"), float("inf"), float("-inf")):
        try:
            call(LIVE, bad)
            check(f"a hard cost of {bad} is refused", False, "no HTTPException raised")
        except HTTPException as e:
            check(f"a hard cost of {bad} is refused", e.status_code == 422, str(e.status_code))
    try:
        call("nosuchproject", 500_000.0)
        check("an unknown project is 404, not an empty comparison", False, "no HTTPException")
    except HTTPException as e:
        check("an unknown project is 404, not an empty comparison", e.status_code == 404,
              str(e.status_code))

    # ---- the two metrics NOT offered, asserted as a decision -----------------------------------------
    # The route answers about cost_per_sf and nothing else. Pinned so that wiring either of the other
    # two later is a deliberate act with this file failing first, rather than a quiet addition: both
    # would put a NEW claim in front of an underwriter.
    check("the route answers about cost_per_sf and only that", out["metric"] == "cost_per_sf",
          out["metric"])
    check("...and the two it refuses are still in the engine, available to a later decision",
          {"cost_variance_pct", "schedule_variance_days"} <= set(memory["metrics"]),
          str(sorted(memory["metrics"])))
finally:
    cost_engine.summary, energy.project_gfa_sf = _real_summary, _real_gfa
    engine.dispose()
    for _f in ("./_dm_beside.db",):
        if os.path.exists(_f):
            os.remove(_f)

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("DEAL MEMORY BESIDE OK - the underwriting screen can now reach `beside()`, which had no caller "
      "anywhere while the module it lives in counted as reachable. $/SF is offered because a hard "
      "cost and a GFA convert into it; a realised cost variance and a realised schedule variance are "
      "refused, because putting either beside a contingency or a duration would be the product "
      "asserting something rather than converting units.")
