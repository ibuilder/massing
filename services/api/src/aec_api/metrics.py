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


def observe(method: str, route: str, status: int, dur: float) -> None:
    global _hist_inf, _hist_sum
    with _lock:
        _req_total[(method, route, str(status))] = _req_total.get((method, route, str(status)), 0) + 1
        cls = f"{status // 100}xx"
        _class_total[cls] = _class_total.get(cls, 0) + 1
        _lat_sum[(method, route)] = _lat_sum.get((method, route), 0.0) + dur
        _lat_count[(method, route)] = _lat_count.get((method, route), 0) + 1
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
    out += ["# HELP http_requests_in_flight In-flight HTTP requests.",
            "# TYPE http_requests_in_flight gauge",
            f"http_requests_in_flight {inflight}",
            "# HELP process_uptime_seconds Seconds since the process started.",
            "# TYPE process_uptime_seconds gauge",
            f"process_uptime_seconds {time.time() - _start:.1f}"]
    return "\n".join(out) + "\n"
