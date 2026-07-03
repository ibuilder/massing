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


def observe(method: str, route: str, status: int, dur: float) -> None:
    with _lock:
        _req_total[(method, route, str(status))] = _req_total.get((method, route, str(status)), 0) + 1
        cls = f"{status // 100}xx"
        _class_total[cls] = _class_total.get(cls, 0) + 1
        _lat_sum[(method, route)] = _lat_sum.get((method, route), 0.0) + dur
        _lat_count[(method, route)] = _lat_count.get((method, route), 0) + 1


def inflight(delta: int) -> None:
    global _inflight
    with _lock:
        _inflight += delta


def _esc(v: str) -> str:
    return v.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


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
    out += ["# HELP http_requests_in_flight In-flight HTTP requests.",
            "# TYPE http_requests_in_flight gauge",
            f"http_requests_in_flight {inflight}",
            "# HELP process_uptime_seconds Seconds since the process started.",
            "# TYPE process_uptime_seconds gauge",
            f"process_uptime_seconds {time.time() - _start:.1f}"]
    return "\n".join(out) + "\n"
