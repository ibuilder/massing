"""R24-PERF-BUDGET — the stated budgets, and which of them anything actually measures.

`metrics` was built for this: the histogram's 0.1 boundary is a bucket edge because 100 ms is the
stated budget, and `quantile` returns a bucket upper bound rather than interpolating a
precise-looking figure out of bucketed data. What was missing is the budget itself, asserted — per
*Verify, don't recall*, a target held only as prose is a target nobody enforces.

**Three budgets are stated and only one is server-measurable**, and this module's job is to keep
that distinction visible:

* **request p95 < 100 ms** — server-side, real, read from `metrics.quantile(0.95)`;
* **click echo < 100 ms** — CLIENT-side. Nothing on the server can see the interval between a user's
  click and the first paint that answers it. It needs a browser beacon that does not exist yet;
* **panel load < 1 s** — client-side for the same reason: server time is one term in it.

A budget file that lists three budgets and quietly checks one is the failure this product keeps
finding: a green suite that implies more was verified than was. The unmeasurable two are reported as
`unmeasured` with the reason, so their absence is *stated* rather than inferred from silence.

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
        "limit_s": 0.1, "measurable": False, "side": "client",
        "source": None,
        "what": "the interval between a user's click and the first paint answering it",
        "why_unmeasured": ("nothing on the server can observe it — the click, the render and the "
                           "paint all happen in the browser. It needs a client beacon that does not "
                           "exist yet, and asserting it here would be a green check on something "
                           "never measured"),
    },
    "panel_load": {
        "limit_s": 1.0, "measurable": False, "side": "client",
        "source": None,
        "what": "a panel becoming usable after it is opened",
        "why_unmeasured": ("server response time is only one term in it; the rest is transfer, parse "
                           "and render. A server-side assertion would pass while a panel took four "
                           "seconds to become usable"),
    },
}


def evaluate(p95: float | None, observations: int) -> dict[str, Any]:
    """The server-measurable budget, judged from a quantile reading and its sample count.

    `p95` is `metrics.quantile(0.95)` — a bucket UPPER bound, so "at or below this". `observations`
    disambiguates the two meanings of None; see the module docstring.
    """
    limit = BUDGETS["request_p95"]["limit_s"]
    if p95 is None and observations <= 0:
        return {"budget": "request_p95", "status": STATUS_NO_DATA, "limit_s": limit,
                "p95_s": None, "observations": 0, "within": None,
                "note": ("no requests were observed. This is NOT within budget — it is nothing to "
                         "judge, and a budget that passes on an idle server measures uptime, not "
                         "latency")}
    if p95 is None:
        return {"budget": "request_p95", "status": STATUS_BEYOND_BUCKETS, "limit_s": limit,
                "p95_s": None, "observations": observations, "within": False,
                "note": ("the 95th percentile lies beyond the largest histogram bucket (10 s), so "
                         "the histogram cannot express it. That is a FAILURE, not missing data — "
                         "reading None as 'no problem' would make this budget pass hardest exactly "
                         "when latency is worst")}
    within = p95 <= limit + 1e-12
    return {"budget": "request_p95", "status": STATUS_WITHIN if within else STATUS_EXCEEDED,
            "limit_s": limit, "p95_s": p95, "observations": observations, "within": within,
            "note": (f"p95 is at or below {p95:g}s against a {limit:g}s budget. The figure is a "
                     "bucket upper bound, not an interpolated point — a histogram cannot honestly "
                     "give a more precise answer than its buckets")}


def report(p95: float | None = None, observations: int = 0) -> dict[str, Any]:
    """Every stated budget, with the unmeasurable ones named rather than omitted."""
    measured = evaluate(p95, observations)
    unmeasured = [{"budget": k, "status": STATUS_UNMEASURED, "limit_s": v["limit_s"],
                   "side": v["side"], "what": v["what"], "note": v["why_unmeasured"]}
                  for k, v in BUDGETS.items() if not v["measurable"]]
    return {
        "budgets": [measured, *unmeasured],
        "measured_count": 1, "unmeasured_count": len(unmeasured),
        "within_budget": measured["within"] is True,
        "note": ("two of the three stated budgets are CLIENT-side and unmeasured; they are listed "
                 "so a green result cannot be read as 'all three verified'. A budget file that "
                 "checks one of three and says nothing about the rest is how a suite comes to imply "
                 "more than it tested."),
    }
