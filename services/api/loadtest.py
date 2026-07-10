"""Load/stress harness — drives the heavy read paths against a scale-seeded DB (see seed_scale.py)
and reports per-endpoint latency + a small concurrency throughput test, so we can see what breaks
(or crawls) at mega-project volume and prove fixes before/after.

    DATABASE_URL=sqlite:///./_scale.db AEC_TRUST_XUSER=1 PYTHONPATH=src \
        ./.venv/Scripts/python.exe loadtest.py

Each endpoint runs in a worker thread with a wall-clock guard so a pathological N+1 can't hang the
run — it's reported as TIMEOUT(>Ns) instead. Exit code is non-zero if anything errors or times out.
"""
from __future__ import annotations

import concurrent.futures as cf
import os
import statistics
import sys
import time

os.environ.setdefault("DATABASE_URL", "sqlite:///./_scale.db")
os.environ.setdefault("AEC_TRUST_XUSER", "1")

from fastapi.testclient import TestClient  # noqa: E402
from aec_api.main import app               # noqa: E402

HDR = {"X-User": "loadtest"}
GUARD_S = 45  # per-call wall-clock guard


def _pid() -> str:
    with open(os.environ.get("AEC_SCALE_PID_FILE", "_scale_pid.txt")) as fh:
        return fh.read().strip()


def timed(client: TestClient, method: str, url: str) -> tuple[float, int, int]:
    """(elapsed_ms, status, response_bytes) for one call."""
    t0 = time.time()
    r = client.request(method, url, headers=HDR)
    return (time.time() - t0) * 1000, r.status_code, len(r.content)


def guarded(client: TestClient, label: str, url: str) -> dict:
    with cf.ThreadPoolExecutor(max_workers=1) as ex:
        fut = ex.submit(timed, client, "GET", url)
        try:
            ms, status, nbytes = fut.result(timeout=GUARD_S)
            return {"label": label, "url": url, "ms": ms, "status": status, "bytes": nbytes}
        except cf.TimeoutError:
            return {"label": label, "url": url, "ms": None, "status": "TIMEOUT", "bytes": 0}


def main() -> int:
    pid = _pid()
    with TestClient(app) as client:
        P = f"/projects/{pid}"
        # (label, url) — the heavy read paths a mega project hammers
        calls = [
            ("list rfi p1 (limit 200)",      f"{P}/modules/rfi?limit=200"),
            ("list rfi p1 (limit 1000)",     f"{P}/modules/rfi?limit=1000"),
            ("list rfi deep offset",         f"{P}/modules/rfi?limit=1000&offset=9000"),
            ("list rfi clamp (limit 1e6)",   f"{P}/modules/rfi?limit=1000000"),
            ("list direct_cost 1000",        f"{P}/modules/direct_cost?limit=1000"),
            ("search rfi q=concrete",        f"{P}/modules/rfi?q=concrete&limit=200"),
            ("search direct_cost q=steel",   f"{P}/modules/direct_cost?q=steel&limit=200"),
            ("filter rfi by state",          f"{P}/modules/rfi?state=open&limit=1000"),
            ("board rfi",                    f"{P}/modules/rfi/board"),
            ("count via views/alerts",       f"{P}/views/alerts"),
            ("dashboard",                    f"{P}/dashboard"),
            ("cost summary",                 f"{P}/cost/summary"),
            ("cost g703",                    f"{P}/cost/g703"),
            ("cost traceability",            f"{P}/cost/traceability"),
            ("wip",                          f"{P}/wip"),
            ("evm",                          f"{P}/evm"),
            ("safety metrics",               f"{P}/safety/metrics"),
            ("my-work",                      f"{P}/my-work"),
            ("due-feed",                     f"{P}/due-feed?days=7"),
            ("bcf export coordination(8k)",  f"{P}/modules/coordination_issue/bcf/export"),
            ("csv export rfi",               f"{P}/modules/rfi/export.csv"),
        ]
        print(f"{'endpoint':32s} {'ms':>9s}  {'status':>7s}  {'KB':>8s}")
        print("-" * 62)
        bad = 0
        for label, url in calls:
            r = guarded(client, label, url)
            ms = f"{r['ms']:.0f}" if r["ms"] is not None else f">{GUARD_S}s"
            kb = f"{r['bytes']/1024:.0f}" if r["bytes"] else "-"
            flag = ""
            if r["status"] == "TIMEOUT":
                flag = "  <-- TIMEOUT"; bad += 1
            elif isinstance(r["status"], int) and r["status"] >= 400:
                flag = f"  <-- HTTP {r['status']}"; bad += 1
            elif r["ms"] and r["ms"] > 1000:
                flag = "  <-- SLOW"
            print(f"{label:32s} {ms:>9s}  {str(r['status']):>7s}  {kb:>8s}{flag}")

        # concurrency: 40 list requests, 8 workers — throughput + tail latency under contention
        print("\nconcurrency: 40x list rfi (limit=200), 8 workers")
        url = f"{P}/modules/rfi?limit=200"
        t0 = time.time()
        with cf.ThreadPoolExecutor(max_workers=8) as ex:
            res = list(ex.map(lambda _: timed(client, "GET", url), range(40)))
        wall = time.time() - t0
        lat = sorted(x[0] for x in res)
        errs = sum(1 for x in res if x[1] >= 400)
        print(f"  wall={wall:.2f}s  throughput={40/wall:.1f} req/s  "
              f"p50={statistics.median(lat):.0f}ms  p95={lat[int(0.95*len(lat))-1]:.0f}ms  errors={errs}")
        bad += errs
    print(f"\n{'FAIL' if bad else 'OK'}: {bad} problem call(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
