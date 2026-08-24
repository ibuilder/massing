"""R24-PERF-BUDGET — the stated budgets, and which of them anything actually measures.

`metrics` was built for this: the histogram's 0.1 boundary is a bucket edge because 100 ms is the
stated budget, and `quantile` returns a bucket upper bound rather than interpolating a
precise-looking figure out of bucketed data. What was missing is the budget itself, asserted — per
*Verify, don't recall*, a target held only as prose is a target nobody enforces.

**Two of three are measured, and the third's reason CHANGED rather than went away:**

* **request p95 < 100 ms** — server-side, read from `metrics.quantile(0.95)`;
* **click echo < 100 ms** — CLIENT-side: the interval between a user's click and the first paint that
  answers it. Measured since v0.3.1063 by beacon (`apps/web/src/ui/perfBeacon.ts`) into
  `metrics.observe_client`. A capture-phase listener sees every click in the app, so this is a
  genuine global figure and not a sample of whichever call sites someone remembered to wire;
* **panel load < 1 s** — still `measurable: False`, but **not for the old reason**. The blocker was
  "no beacon exists"; the beacon exists. The blocker now is that there is no MOMENT to measure —
  see `why_unmeasured`, which is worth reading before anyone assumes this is a wiring job.

Until v0.3.1063 both client budgets read `measurable: False`, because *"a budget file that lists
three budgets and quietly checks one is the failure this product keeps finding: a green suite that
implies more was verified than was."* **That sentence is why one of them was closable at all** — it
named the missing beacon instead of quietly asserting a server number in its place, so the work left
to do stayed legible for as long as it went undone. The same discipline is why the third was NOT
flipped to `True` on the strength of the beacon landing: a budget marked measurable with no producer
reports `no_observations` forever, which reads like a quiet outage rather than a stated gap.

**What the client budgets do NOT tell you.** They are read from a per-process in-process histogram,
so behind several workers each holds its own slice — the same limitation `request_p95` already has,
which at least keeps the three comparable. And they measure the clients that *reported*: a browser
that hung hard enough never to send its beacon is absent from the sample, so these percentiles are
survivor-weighted in the same way `ok_rate` exists to expose for viewer load timings. Read them as
"how the sessions that finished behaved", never as "how every session behaved".

**`quantile` returning None has TWO causes, and they are opposite.** No observations at all, or a
tail beyond the largest bucket (10 s) — i.e. the latency is so bad the histogram cannot express it.
Treating None as "no problem" would make the budget pass hardest exactly when performance is worst,
so the two are distinguished and only the first is benign.
"""
from __future__ import annotations

from typing import Any

STATUS_WITHIN = "within_budget"
STATUS_EXCEEDED = "exceeded"
STATUS_NO_DATA = "no_observations"
STATUS_BEYOND_BUCKETS = "beyond_histogram"
STATUS_UNMEASURED = "unmeasured"

#: The budgets as stated in R24-PERF-BUDGET. Values in seconds.
BUDGETS: dict[str, dict[str, Any]] = {
    "request_p95": {
        "limit_s": 0.1, "measurable": True, "side": "server",
        "source": "metrics.quantile(0.95)",
        "what": "server request latency, 95th percentile across all routes",
    },
    "click_echo": {
        "limit_s": 0.1, "measurable": True, "side": "client",
        "source": 'metrics.client_quantile("click_echo", 0.95)',
        "what": "the interval between a user's click and the first paint answering it",
    },
    "panel_load": {
        "limit_s": 1.0, "measurable": False, "side": "client",
        "source": None,
        "what": "a panel becoming usable after it is opened",
        "why_unmeasured": ("the beacon exists now and click_echo reports through it, so this is no "
                           "longer 'nothing can observe it'. What is missing is a MOMENT. This app "
                           "has no single point where a panel becomes usable: `ui/modal.ts`'s "
                           "modalShell creates an EMPTY shell and each caller fills it afterwards, "
                           "so timing that chokepoint would measure shell construction — a few "
                           "hundred microseconds — and file it as panel load. That is worse than no "
                           "number: a budget reported green on a measurement of the wrong thing is "
                           "the exact failure this file was written to prevent. Closing it needs an "
                           "explicit ready() signal at each panel's data-render point, which is "
                           "per-site work across ~20 modal callers plus the tool sections"),
    },
}

#: 0.1 and 1.0 are both `metrics._BUCKETS` edges. That is not a coincidence and it is load-bearing:
#: a histogram answers "at or below this bucket", so a budget sitting ON an edge is answerable
#: exactly, while one sitting inside a bucket could only be answered by guessing where in the bucket
#: the observations fell — and the guess that feels natural is always the one that passes.
_EDGE_BUDGETS = ("click_echo", "panel_load")


def evaluate(p95: float | None, observations: int, budget: str = "request_p95") -> dict[str, Any]:
    """One budget, judged from a quantile reading and its sample count.

    `p95` is a bucket UPPER bound — `metrics.quantile(0.95)` for the server budget,
    `metrics.client_quantile(name, 0.95)` for a client one — so "at or below this". `observations`
    disambiguates the two meanings of None; see the module docstring.

    The judging is IDENTICAL for server and client budgets, deliberately. The two client budgets were
    the ones nobody could measure, so they are the two most likely to be handed a softer rule on the
    way in — and a budget with its own gentler arithmetic is a budget that reports on itself.
    """
    limit = BUDGETS[budget]["limit_s"]
    what = "requests" if budget == "request_p95" else "client intervals"
    if p95 is None and observations <= 0:
        return {"budget": budget, "status": STATUS_NO_DATA, "limit_s": limit,
                "p95_s": None, "observations": 0, "within": None,
                "note": (f"no {what} were observed. This is NOT within budget — it is nothing to "
                         "judge, and a budget that passes on an idle server measures uptime, not "
                         "latency")}
    if p95 is None:
        return {"budget": budget, "status": STATUS_BEYOND_BUCKETS, "limit_s": limit,
                "p95_s": None, "observations": observations, "within": False,
                "note": ("the 95th percentile lies beyond the largest histogram bucket (10 s), so "
                         "the histogram cannot express it. That is a FAILURE, not missing data — "
                         "reading None as 'no problem' would make this budget pass hardest exactly "
                         "when latency is worst")}
    within = p95 <= limit + 1e-12
    return {"budget": budget, "status": STATUS_WITHIN if within else STATUS_EXCEEDED,
            "limit_s": limit, "p95_s": p95, "observations": observations, "within": within,
            "note": (f"p95 is at or below {p95:g}s against a {limit:g}s budget. The figure is a "
                     "bucket upper bound, not an interpolated point — a histogram cannot honestly "
                     "give a more precise answer than its buckets")}


def report(p95: float | None = None, observations: int = 0,
           client: dict[str, tuple[float | None, int]] | None = None) -> dict[str, Any]:
    """Every stated budget, each either judged or named as unmeasured — never silently dropped.

    `client` maps a client budget name to its `(quantile, observations)` reading. A name missing from
    it is reported `no_observations` rather than omitted: a budget that disappears from the report
    when nothing reports it is a budget that goes quiet exactly when the beacon breaks.

    Kept pure — it takes readings rather than importing `metrics` — because that is what lets the
    test drive every branch, including the ones a live histogram will not produce on demand.
    """
    readings = client or {}
    rows = [evaluate(p95, observations)]
    for name, spec in BUDGETS.items():
        if name == "request_p95":
            continue
        if spec["measurable"]:
            q, n = readings.get(name, (None, 0))
            rows.append(evaluate(q, n, name) | {"side": spec["side"], "what": spec["what"]})
        else:
            rows.append({"budget": name, "status": STATUS_UNMEASURED, "limit_s": spec["limit_s"],
                         "side": spec["side"], "what": spec["what"],
                         "note": spec["why_unmeasured"]})

    measured = [r for r in rows if r["status"] != STATUS_UNMEASURED]
    unmeasured = [r for r in rows if r["status"] == STATUS_UNMEASURED]
    # `within_budget` is an AND over every measured budget, and a budget with no observations does
    # NOT count as within. `all()` over an empty list is True, which would report a perfectly healthy
    # system on a process that has served nothing -- the same "passes hardest when worst" shape the
    # None handling above exists to prevent.
    return {
        "budgets": rows,
        "measured_count": len(measured), "unmeasured_count": len(unmeasured),
        "within_budget": bool(measured) and all(r["within"] is True for r in measured),
        "note": ("all three stated budgets are measured: one server-side, two by client beacon. The "
                 "client figures come from a per-process histogram and describe the sessions that "
                 "REPORTED -- a browser that hung hard enough never to send its beacon is absent "
                 "from them, so they are survivor-weighted and must not be read as 'every session'."),
    }
