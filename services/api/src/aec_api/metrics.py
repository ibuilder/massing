"""Lightweight in-process metrics (Prometheus text exposition) — stdlib only, no deps.

A middleware records per-request counts and latencies keyed by (method, route-template, status)
and an in-flight gauge; `/metrics` renders them in the Prometheus 0.0.4 text format. Route
*templates* (e.g. /projects/{pid}/members) are used, not raw paths, to keep label cardinality
bounded. Counters are per-process: with multiple uvicorn workers each exposes its own slice
(fine for dev / single-worker; use a multiprocess collector if you scale workers and scrape one)."""
from __future__ import annotations

import threading
import time

_lock = threading.Lock()
_req_total: dict[tuple[str, str, str], int] = {}
_lat_sum: dict[tuple[str, str], float] = {}
_lat_count: dict[tuple[str, str], int] = {}
_inflight = 0
_start = time.time()


_class_total: dict[str, int] = {}                # "2xx"/"3xx"/"4xx"/"5xx" — one-label alert feed

#: Latency histogram buckets, seconds. R24-PERF-BUDGET asserts a p95, and the `_sum`/`_count`
#: summary below **cannot answer that** — sum/count yields a MEAN, and a mean hides exactly the tail
#: a budget is about. Buckets are cumulative (Prometheus convention), unlabelled by route so the
#: cardinality stays flat: this is one global latency shape, which is what a budget is written
#: against. The 0.1 boundary is deliberately a bucket edge because 100 ms is the stated budget.
_BUCKETS: tuple[float, ...] = (0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0)
_hist: dict[float, int] = dict.fromkeys(_BUCKETS, 0)
_hist_inf = 0
_hist_sum = 0.0


#: Routes counted, but kept OUT of the latency histogram `request_p95` is read from.
#:
#: The client beacon posts on every click. Those are tiny, fast, same-datacentre writes, and there
#: are up to two per second per open tab — so folding them into the histogram would pull the server
#: p95 DOWN and make `request_p95` pass more easily the more the browser reported. **The instrument
#: would have been flattering the thing it measures**, in the direction nobody checks, and the effect
#: grows with adoption.
#:
#: They stay in `http_requests_total`, where an operator can see the volume: the goal is to keep
#: telemetry out of a budget written about user-facing latency, not to hide it.
_HIST_EXCLUDED: frozenset[str] = frozenset({"/metrics/client"})


def observe(method: str, route: str, status: int, dur: float) -> None:
    global _hist_inf, _hist_sum
    with _lock:
        _req_total[(method, route, str(status))] = _req_total.get((method, route, str(status)), 0) + 1
        cls = f"{status // 100}xx"
        _class_total[cls] = _class_total.get(cls, 0) + 1
        _lat_sum[(method, route)] = _lat_sum.get((method, route), 0.0) + dur
        _lat_count[(method, route)] = _lat_count.get((method, route), 0) + 1
        if route in _HIST_EXCLUDED:
            return
        for b in _BUCKETS:
            if dur <= b:
                _hist[b] += 1
        _hist_inf += 1
        _hist_sum += dur


def quantile(q: float) -> float | None:
    """Interpolation-free quantile from the cumulative buckets, or None with no observations.

    Returns the bucket UPPER BOUND containing the qth observation — i.e. "p95 is at or below this",
    which is the only honest answer a histogram can give. It deliberately does not interpolate a
    precise-looking figure out of bucketed data; `+Inf` observations return None rather than a
    fabricated ceiling. Used by the perf-budget test, so it must not flatter the tail.
    """
    with _lock:
        total = _hist_inf
        snap = dict(_hist)
    if total <= 0:
        return None
    target = q * total
    for b in _BUCKETS:
        if snap[b] >= target:
            return b
    return None  # the qth observation is beyond the largest bucket


#: CLIENT-side observations, one histogram per budget name. R24-PERF-BUDGET states three budgets and
#: two of them are things only a browser can see — the interval between a click and the paint that
#: answers it, and a panel becoming usable. Those arrive by beacon and land here.
#:
#: **A separate family, not the request histogram.** Folding paint intervals into
#: `_hist` would silently corrupt `request_p95`, which is the one budget that was honest all along —
#: a fast server would start failing its own budget because a slow laptop repainted slowly.
#:
#: **The buckets are deliberately the same tuple.** Both client budgets land exactly on an existing
#: edge — `0.1` for click echo, `1.0` for panel load — so "at or below the bucket" answers the budget
#: question without interpolating, which is the same property that made `_BUCKETS` right for the
#: server budget. A bucket set that straddled a budget would force a guess at the boundary and the
#: guess would always be the direction that passes.
#:
#: Per-process, exactly like the counters above, and for the same reason. With multiple workers each
#: exposes its own slice. That is a real limitation and it is the SAME limitation `request_p95`
#: already has, so the three budgets remain comparable with each other; it is stated in the budget
#: report rather than left for a reader to infer.
_client_hist: dict[str, dict[float, int]] = {}
_client_inf: dict[str, int] = {}
_client_sum: dict[str, float] = {}


def observe_client(budget: str, dur: float) -> None:
    """Record one client-side interval, in seconds, against a named budget.

    Callers must clamp before calling: these numbers come from a browser and are attacker-controlled.
    An unclamped value poisons the very percentile the budget is read from, which is a quiet way to
    make the instrument lie rather than break.
    """
    with _lock:
        h = _client_hist.setdefault(budget, dict.fromkeys(_BUCKETS, 0))
        for b in _BUCKETS:
            if dur <= b:
                h[b] += 1
        _client_inf[budget] = _client_inf.get(budget, 0) + 1
        _client_sum[budget] = _client_sum.get(budget, 0.0) + dur


def client_quantile(budget: str, q: float) -> float | None:
    """The qth quantile for one client budget, with `quantile`'s exact semantics.

    Returns the bucket UPPER bound, or None for BOTH "nothing observed" and "beyond the largest
    bucket". Those two are opposite in meaning and the caller distinguishes them with
    `client_count` -- see `perf_budget`, where reading None as "no problem" would make a budget pass
    hardest exactly when the client is slowest.
    """
    with _lock:
        total = _client_inf.get(budget, 0)
        snap = dict(_client_hist.get(budget) or {})
    if total <= 0 or not snap:
        return None
    target = q * total
    for b in _BUCKETS:
        if snap[b] >= target:
            return b
    return None


def client_count(budget: str) -> int:
    """How many observations back a client budget — the disambiguator for a None quantile."""
    with _lock:
        return _client_inf.get(budget, 0)


def inflight(delta: int) -> None:
    global _inflight
    with _lock:
        _inflight += delta


def _esc(v: str) -> str:
    return v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def render_queue(stats: dict | None, worker_inline: bool) -> list[str]:
    """JOB-STALL-VISIBLE — Prometheus lines for the job queue. `stats=None` means it could not be read.

    Three deliberate choices, each guarding against a metric that reads as reassuring when it is not:

    **`aec_jobs_stats_ok` is always emitted.** It is the gauge that says whether the other gauges mean
    anything. Without it, a database the scrape cannot reach and a perfectly empty queue produce the
    same output — no queue series at all — and the second reading is the one an operator will make.

    **`aec_jobs_oldest_queued_seconds` is OMITTED when nothing is queued, never zero.** Zero says "the
    oldest job is brand new"; the truth is "there is no oldest job". An alert written as
    `aec_jobs_oldest_queued_seconds > 600` then simply does not fire on an empty queue, which is the
    Prometheus idiom for an absent measurement, and a `0` would have made the metric useless for the
    one thing it exists to detect.

    **Age, not depth, is the alarm.** Depth is wrong in both directions: a deep queue draining quickly
    is healthy, and a single job wedged for six hours — the exact shape of a missing worker after
    JOB-WORKER-SPLIT — never crosses a depth threshold at all. Depth is still exported, because it is
    the right thing to *scale* on; it is just not the right thing to *page* on.
    """
    out = ["# HELP aec_jobs_stats_ok 1 if the queue could be read; 0 means the values below are absent.",
           "# TYPE aec_jobs_stats_ok gauge",
           f"aec_jobs_stats_ok {1 if stats else 0}",
           "# HELP aec_jobs_worker_inline 1 if THIS process runs the job worker (AEC_JOB_WORKER).",
           "# TYPE aec_jobs_worker_inline gauge",
           f"aec_jobs_worker_inline {1 if worker_inline else 0}"]
    if not stats:
        return out
    out += ["# HELP aec_jobs_by_state Job rows by state. Scale on `queued`; do not page on it.",
            "# TYPE aec_jobs_by_state gauge"]
    for st in ("queued", "running", "done", "error"):
        out.append(f'aec_jobs_by_state{{state="{st}"}} {int(stats.get(st, 0))}')
    age = stats.get("oldest_queued_seconds")
    if age is not None:
        out += ["# HELP aec_jobs_oldest_queued_seconds Age of the head of the queue. THIS is the stall "
                "alarm; absent when nothing is queued.",
                "# TYPE aec_jobs_oldest_queued_seconds gauge",
                f"aec_jobs_oldest_queued_seconds {float(age):.3f}"]
    return out


def render() -> str:
    with _lock:
        req = dict(_req_total); lat_s = dict(_lat_sum); lat_c = dict(_lat_count); inflight = _inflight
        cls = dict(_class_total)
    out = [
        "# HELP http_responses_by_class_total Responses by status class (alert on 4xx/5xx rate).",
        "# TYPE http_responses_by_class_total counter",
    ]
    for k in sorted(cls):
        out.append(f'http_responses_by_class_total{{class="{k}"}} {cls[k]}')
    out += [
        "# HELP http_requests_total Total HTTP requests by method, route and status.",
        "# TYPE http_requests_total counter",
    ]
    for (m, r, s), c in sorted(req.items()):
        out.append(f'http_requests_total{{method="{_esc(m)}",route="{_esc(r)}",status="{s}"}} {c}')
    out += ["# HELP http_request_duration_seconds Request latency by method and route.",
            "# TYPE http_request_duration_seconds summary"]
    for (m, r), total in sorted(lat_s.items()):
        lbl = f'method="{_esc(m)}",route="{_esc(r)}"'
        out.append(f'http_request_duration_seconds_sum{{{lbl}}} {total:.6f}')
        out.append(f'http_request_duration_seconds_count{{{lbl}}} {lat_c[(m, r)]}')
    with _lock:
        hsnap = dict(_hist); hinf = _hist_inf; hsum = _hist_sum
    out += ["# HELP http_request_duration_seconds_hist Global request latency histogram. Use this "
            "for p95 — the summary above gives a mean, which hides the tail a budget is about.",
            "# TYPE http_request_duration_seconds_hist histogram"]
    for b in _BUCKETS:
        out.append(f'http_request_duration_seconds_hist_bucket{{le="{b}"}} {hsnap[b]}')
    out += [f'http_request_duration_seconds_hist_bucket{{le="+Inf"}} {hinf}',
            f"http_request_duration_seconds_hist_sum {hsum:.6f}",
            f"http_request_duration_seconds_hist_count {hinf}"]
    # Client-side budgets, one histogram per name. Rendered even when empty is NOT the choice here:
    # a budget with no observations is omitted, so a dashboard shows nothing rather than a flat zero
    # line that reads like "fast". The budget report says `no_observations` in words for the same
    # reason.
    with _lock:
        cnames = sorted(_client_hist)
        csnap = {k: dict(_client_hist[k]) for k in cnames}
        cinf = dict(_client_inf); csum = dict(_client_sum)
    if cnames:
        out += ["# HELP client_interval_seconds_hist Client-side budget intervals, by budget name "
                "(R24-PERF-BUDGET). Reported by browser beacon; per-process like the server "
                "histogram above.",
                "# TYPE client_interval_seconds_hist histogram"]
        for name in cnames:
            for b in _BUCKETS:
                out.append(f'client_interval_seconds_hist_bucket{{budget="{_esc(name)}",le="{b}"}} '
                           f'{csnap[name][b]}')
            out += [f'client_interval_seconds_hist_bucket{{budget="{_esc(name)}",le="+Inf"}} '
                    f'{cinf.get(name, 0)}',
                    f'client_interval_seconds_hist_sum{{budget="{_esc(name)}"}} '
                    f'{csum.get(name, 0.0):.6f}',
                    f'client_interval_seconds_hist_count{{budget="{_esc(name)}"}} '
                    f'{cinf.get(name, 0)}']
    out += ["# HELP http_requests_in_flight In-flight HTTP requests.",
            "# TYPE http_requests_in_flight gauge",
            f"http_requests_in_flight {inflight}",
            "# HELP process_uptime_seconds Seconds since the process started.",
            "# TYPE process_uptime_seconds gauge",
            f"process_uptime_seconds {time.time() - _start:.1f}"]
    return "\n".join(out) + "\n"
