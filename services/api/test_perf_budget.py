"""R24-PERF-BUDGET — the stated budget, asserted, and the two nobody can measure yet.

`metrics` was already built for this: the 0.1 histogram boundary is a bucket edge because 100 ms is
the budget, and `quantile` returns a bucket upper bound rather than interpolating a precise-looking
number out of bucketed data. What was missing is the assertion — per *Verify, don't recall*, a target
held only as prose is a target nobody enforces.

1. **the server budget is asserted against REAL traffic** — requests are driven through the app and
   the p95 read from the live histogram, not from a synthetic number;
2. **`quantile` returning None has two opposite causes** — no observations, or a tail beyond the
   largest bucket. Reading None as "no problem" would make the budget pass hardest exactly when
   latency is worst, so `beyond_histogram` is a FAILURE and `no_observations` is not a pass either;
3. **two of three are measured** — the client beacon (v0.3.1063) closed `click_echo`. `panel_load`
   stays unmeasured on purpose, and its REASON changed rather than vanished: the beacon exists, but
   the app has no single moment where a panel becomes usable, so there is nothing honest to time. What is asserted instead: the client budgets
   are judged by the SAME arithmetic as the server one, a slow client FAILS `within_budget`, and a
   measurable budget whose beacon reported nothing comes back `no_observations` rather than
   vanishing from the report. The `unmeasured` slot is kept and still tested against a temporary
   declaration, because the next budget stated before it can be measured needs it;
4. **the sink refuses rather than trusts.** The budget name is matched against `BUDGETS` (an
   unvalidated name would let a browser create unbounded histogram series in a long-lived process),
   implausible durations are DROPPED rather than clamped to the boundary — clamping files a hostile
   value in the slowest real bucket and quietly moves the p95 — and an anonymous caller is refused,
   because shifting a percentile an operator decides from is a way to make the instrument lie.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_perf_budget.py
"""
import os
import sys

sys.path.insert(0, "src")

os.environ["DATABASE_URL"] = "sqlite:///./test_perf_budget.db"
os.environ["STORAGE_DIR"] = "./test_storage_perf"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_perf_budget.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import metrics  # noqa: E402
from aec_api import perf_budget as pb  # noqa: E402
from aec_api.main import app  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


# --- 3. EVERY STATED BUDGET IS DECLARED, MEASURABLE OR NOT ------------------------------------------
check("all three stated budgets are declared",
      set(pb.BUDGETS) == {"request_p95", "click_echo", "panel_load"}, sorted(pb.BUDGETS))
check("  the stated limits are 100 ms / 100 ms / 1 s",
      [pb.BUDGETS[k]["limit_s"] for k in ("request_p95", "click_echo", "panel_load")]
      == [0.1, 0.1, 1.0], {k: v["limit_s"] for k, v in pb.BUDGETS.items()})
check("click_echo is measurable now — the beacon closed that one",
      pb.BUDGETS["click_echo"]["measurable"] is True)
check("  ...and names the beacon as its source, not a server reading",
      "client_quantile" in (pb.BUDGETS["click_echo"]["source"] or ""),
      pb.BUDGETS["click_echo"]["source"])
# panel_load stays False ON PURPOSE. Flipping it when the beacon landed would have been the easy
# half of the item and the dishonest one: a budget marked measurable with no producer reports
# `no_observations` for ever, which reads like an outage rather than the stated gap it is.
check("panel_load is still UNMEASURED — no producer, so not marked measurable",
      pb.BUDGETS["panel_load"]["measurable"] is False)
check("  ...and its reason names the MISSING MOMENT, not the missing beacon",
      "missing is a MOMENT" in pb.BUDGETS["panel_load"]["why_unmeasured"]
      and "modalShell" in pb.BUDGETS["panel_load"]["why_unmeasured"],
      pb.BUDGETS["panel_load"]["why_unmeasured"][:100])
check("  BOTH client budgets are histogram BUCKET EDGES, so neither reading is an interpolation",
      0.1 in metrics._BUCKETS and 1.0 in metrics._BUCKETS, metrics._BUCKETS)

# THE TWIN for the flip above. Every budget being measurable means the `unmeasured` path is no longer
# exercised by real data -- and an unexercised branch is one nobody notices deleting. It is kept
# because the NEXT budget somebody states before they can measure it needs the same slot, so it is
# asserted here against a temporary declaration rather than left to rot.
pb.BUDGETS["__probe__"] = {"limit_s": 1.0, "measurable": False, "side": "client", "source": None,
                           "what": "a probe", "why_unmeasured": "declared but not yet measurable"}
try:
    probe = pb.report(0.05, 10, {"click_echo": (0.05, 5)})
    probe_row = [b for b in probe["budgets"] if b["budget"] == "__probe__"]
    check("  a budget declared UNMEASURABLE is still named in the report, never dropped",
          len(probe_row) == 1 and probe_row[0]["status"] == pb.STATUS_UNMEASURED,
          [b["budget"] for b in probe["budgets"]])
    check("  ...and carries the stated reason rather than an empty slot",
          probe_row and "not yet measurable" in (probe_row[0]["note"] or ""))
finally:
    del pb.BUDGETS["__probe__"]

# The client budgets are judged by the SAME arithmetic as the server one. They were the two nobody
# could measure, which makes them the two most likely to be handed a softer rule on the way in.
check("a client budget over its limit is EXCEEDED, by the same code",
      pb.evaluate(0.25, 100, "click_echo")["status"] == pb.STATUS_EXCEEDED)
check("  and one exactly at the boundary is within it",
      pb.evaluate(0.1, 100, "click_echo")["within"] is True)
check("  a None client reading WITH observations is a failure, not missing data",
      pb.evaluate(None, 40, "click_echo")["within"] is False,
      pb.evaluate(None, 40, "click_echo"))

# --- 2. None HAS TWO OPPOSITE CAUSES ------------------------------------------------------------------
none_idle = pb.evaluate(None, observations=0)
check("None with NO observations is 'no_observations', not a pass",
      none_idle["status"] == pb.STATUS_NO_DATA and none_idle["within"] is None, none_idle)
check("  and says a budget passing on an idle server measures uptime, not latency",
      "measures uptime, not latency" in none_idle["note"])
none_slow = pb.evaluate(None, observations=500)
check("NONE WITH OBSERVATIONS IS A FAILURE — the tail is beyond the histogram",
      none_slow["status"] == pb.STATUS_BEYOND_BUCKETS and none_slow["within"] is False, none_slow)
check("  naming the trap: None read as 'no problem' passes hardest when latency is worst",
      "hardest exactly when latency is worst" in none_slow["note"])
check("a p95 over budget is EXCEEDED",
      pb.evaluate(0.25, 100)["status"] == pb.STATUS_EXCEEDED)
check("  and one at the boundary is within it",
      pb.evaluate(0.1, 100)["within"] is True, pb.evaluate(0.1, 100))

# --- 1. THE SERVER BUDGET, AGAINST REAL TRAFFIC --------------------------------------------------------
with TestClient(app) as c:
    c.headers.update({"X-User": "perf@test"})
    for _ in range(40):
        c.get("/health")
    for _ in range(10):
        c.get("/capabilities")

    obs = metrics._hist_inf
    p95 = metrics.quantile(0.95)

check("real traffic was observed by the histogram", obs >= 50, obs)
check("  quantile returns a reading rather than None", p95 is not None, p95)
verdict = pb.evaluate(p95, obs)
check("SERVER REQUEST p95 IS WITHIN THE 100 ms BUDGET",
      verdict["within"] is True, {"p95_s": p95, "limit_s": 0.1, "observations": obs})
check("  judged from the LIVE histogram, not a supplied number",
      verdict["p95_s"] == p95 and verdict["observations"] == obs, verdict)

rep = pb.report(p95, obs, {"click_echo": (0.05, 30)})
check("the report lists all three budgets", len(rep["budgets"]) == 3, len(rep["budgets"]))
check("  two measured, one still unmeasured — and the unmeasured one is NAMED",
      (rep["measured_count"], rep["unmeasured_count"]) == (2, 1)
      and [b["budget"] for b in rep["budgets"] if b["status"] == pb.STATUS_UNMEASURED]
      == ["panel_load"],
      [(b["budget"], b["status"]) for b in rep["budgets"]])
check("  with every budget within, within_budget is True", rep["within_budget"] is True, rep)

# `within_budget` is an AND across all three. Before the beacon it described one budget while
# reading like a verdict on the product; the whole point of measuring the other two is that a slow
# CLIENT can now fail it.
slow = pb.report(p95, obs, {"click_echo": (0.25, 30)})
check("A SLOW CLIENT FAILS within_budget — it is an AND across every MEASURED budget",
      slow["within_budget"] is False,
      [(b["budget"], b["status"]) for b in slow["budgets"]])
check("  and the server budget is still reported as within, so the failure is attributable",
      [b for b in slow["budgets"] if b["budget"] == "request_p95"][0]["within"] is True)

# A measurable budget with nothing reported must not vanish. A budget that disappears from the
# report when its beacon breaks is the same "green implies more than was tested" failure, arriving
# later and harder to spot -- the row is simply absent rather than wrong.
quiet = pb.report(p95, obs)
check("A MEASURABLE BUDGET WITH NO BEACON reports no_observations — it is not omitted",
      [b["status"] for b in quiet["budgets"] if b["budget"] == "click_echo"]
      == [pb.STATUS_NO_DATA],
      [(b["budget"], b["status"]) for b in quiet["budgets"]])
check("  ...and that is NOT within budget — silence is not a pass",
      quiet["within_budget"] is False, quiet["within_budget"])
check("  the report states the client figures are survivor-weighted",
      "survivor-weighted" in rep["note"], rep["note"][:120])


# --- 4. THE SINK: what it refuses -----------------------------------------------------------------
# The beacon is the only way these two budgets get numbers, so the sink is the only place a bad
# number can enter. Almost every check here is a refusal; the twin -- that a GOOD payload IS recorded
# and moves the histogram -- runs first, or the refusals would all pass on a route that accepts
# nothing at all.
from fastapi import HTTPException  # noqa: E402

from aec_api.main import record_client_interval  # noqa: E402

with TestClient(app) as c2:
    c2.headers.update({"X-User": "perf@test"})
    before = metrics.client_count("click_echo")
    r = c2.post("/metrics/client", json={"budget": "click_echo", "ms": 42})
    check("THE TWIN: a good beacon payload is recorded",
          r.status_code == 200 and r.json().get("recorded") is True,
          f"{r.status_code} {r.text[:100]}")
    check("  ...and it actually reached the histogram",
          metrics.client_count("click_echo") == before + 1,
          (before, metrics.client_count("click_echo")))

    # THE BEACON MUST NOT FLATTER THE SERVER BUDGET.
    #
    # The beacon posts on every click: tiny, fast, same-datacentre writes, up to two a second per open
    # tab. Counting them in the latency histogram would pull `request_p95` DOWN, so the server budget
    # would pass more easily the more the browser reported -- an instrument flattering the thing it
    # measures, in the direction nobody checks, with the bias GROWING as adoption grows. They are
    # excluded from the histogram and still counted in `http_requests_total`.
    hist_before = metrics._hist_inf
    for _ in range(25):
        c2.post("/metrics/client", json={"budget": "click_echo", "ms": 3})
    check("25 beacon posts do NOT enter the latency histogram request_p95 reads",
          metrics._hist_inf == hist_before, (hist_before, metrics._hist_inf))
    check("  ...but they ARE counted, so an operator can still see the volume",
          any(k[1] == "/metrics/client" and v >= 25 for k, v in metrics._req_total.items()),
          [(k, v) for k, v in metrics._req_total.items() if k[1] == "/metrics/client"])
    # The control: an ordinary route in the same client DOES reach the histogram, or the check above
    # passes on a histogram that stopped recording anything at all.
    hist_mid = metrics._hist_inf
    c2.get("/health")
    check("  CONTROL: an ordinary request still reaches the histogram",
          metrics._hist_inf > hist_mid, (hist_mid, metrics._hist_inf))

    r = c2.post("/metrics/client", json={"budget": "made_up", "ms": 42})
    check("an unknown budget name is refused 422 -- never used as a dict key",
          r.status_code == 422, f"{r.status_code} {r.text[:120]}")
    r = c2.post("/metrics/client", json={"budget": "request_p95", "ms": 42})
    check("  a SERVER budget cannot be beaconed either -- the client does not get to set it",
          r.status_code == 422, f"{r.status_code} {r.text[:120]}")
    r = c2.post("/metrics/client", json={"budget": "panel_load", "ms": 42})
    check("  a DECLARED-BUT-UNMEASURABLE budget is refused too -- no producer means no data, and a "
          "beacon slipping one in would make an unmeasured budget look measured",
          r.status_code == 422, f"{r.status_code} {r.text[:120]}")

    n_before = metrics.client_count("click_echo")
    for bad in (-1, 600_001, "42", True, None):
        r = c2.post("/metrics/client", json={"budget": "click_echo", "ms": bad})
        ok = r.status_code == 200 and r.json().get("recorded") is False
        check(f"  an implausible duration is DROPPED, not clamped: {bad!r}", ok,
              f"{r.status_code} {r.text[:90]}")
    check("  ...and none of them reached the histogram",
          metrics.client_count("click_echo") == n_before,
          (n_before, metrics.client_count("click_echo")))

# NaN and inf go through the handler directly: `json.dumps` emits bare `NaN`, which some stacks
# reject before the handler is reached -- and the thing under test is that the RANGE COMPARISON
# drops them, not that a parser did. A NaN reaching a bucket would sit in every cumulative count
# below it and quietly bend the percentile.
for bad in (float("nan"), float("inf")):
    # `_user` is a dependency-only parameter; calling the handler directly leaves it as its Depends
    # default, which the body never reads. What is under test here is the range comparison.
    out = record_client_interval({"budget": "click_echo", "ms": bad})
    check(f"  {bad!r} never reaches a bucket -- it fails the range comparison",
          out.get("recorded") is False, out)

# The anonymous refusal. This suite runs with RBAC off, so `current_user` never returns "anonymous"
# through the client -- the refusal is asserted on the DEPENDENCY the route declares.
#
# The first draft of this route took `Depends(current_user)` and hand-rolled the check in the body.
# That works and is invisible to the static walker in `test_global_authz`, which would have recorded
# a new platform-global mutating route carrying no authorising dependency -- the exact shape
# `require_identified` exists to stop, and one this repo has shipped twice before. So the assertion
# is that the route depends on the AUTHORISER, not merely that some code path returns an error.
from aec_api.rbac import require_identified  # noqa: E402

try:
    require_identified("anonymous")
    check("an anonymous caller is refused -- the histogram is not open to the internet", False,
          "no exception raised")
except HTTPException as e:
    check("an anonymous caller is refused -- the histogram is not open to the internet",
          e.status_code == 403, e.status_code)

_beacon = [r for r in app.routes
           if getattr(r, "path", None) == "/metrics/client" and "POST" in (getattr(r, "methods", None) or set())]
check("the beacon route exists exactly once", len(_beacon) == 1, len(_beacon))
if _beacon:
    _deps = repr(_beacon[0].dependant.dependencies)
    check("  ...and it depends on require_identified, not merely current_user",
          "require_identified" in _deps, _deps[:160])

# Stop the job worker before touching the file. Starting the app leaves a DAEMON thread polling the
# `jobs` table, and a daemon thread outlives the block that started it — so removing the database
# underneath it is what produced the CI failure below. Ordering alone now prevents it; this makes the
# thread stop rather than merely lose its race.
from aec_api import jobs as _jobs  # noqa: E402

_jobs.stop_worker()

# Cleanup LAST, after every TestClient has been closed.
#
# This used to sit above the section below, and section 4 was appended after it — so the second
# TestClient started an app against a database that had just been deleted, SQLite recreated the file
# empty, and the daemon job-worker thread that startup leaves polling hit "no such table: jobs".
# It passed locally and failed in CI, because whether the reaper's timer fires inside that window is
# a matter of timing. **Anything that starts the app must run before the file is removed.**
for _f in ("./test_perf_budget.db",):
    if os.path.exists(_f):
        try:
            os.remove(_f)
        except OSError:
            pass

print()
if FAILED:
    print(f"perf_budget: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("perf_budget: all checks passed")
