"""Lightweight per-endpoint rate limiting for expensive operations (AI review, file conversion).

The global middleware in main.py caps *all* requests per IP but is opt-in (off by default) and one
flat number. Some endpoints are far costlier than a normal read — an AI review calls an LLM, a convert
shells out / hits a paid cloud translation — so they get their own, always-on, much lower per-caller
cap regardless of the global limiter. In-process sliding window keyed by (bucket, caller); good enough
for a single/few-worker deployment and, unlike the global limiter, protects even when AEC_RATE_LIMIT_RPM
is unset. Defaults are generous enough for tests/interactive use; tune or disable per bucket via env
(AEC_THROTTLE_<BUCKET>_RPM; 0 disables).

R39-THROTTLE-SHARED (2026-08-07). The count now goes through `ratecount`, so it is SHARED across
worker processes when `AEC_REDIS_URL` is set. Until then this kept its own in-process dict, and the
line above about "a single/few-worker deployment" had quietly stopped being true: R39-WORKER-SPLIT
(v0.3.869) made a second writer process the supported deployment, which multiplies every cap here by
the worker count. That matters most for the tightest buckets, which are the security-relevant ones —
`stepup` at 10/min guards a human step-up assertion.
"""
from __future__ import annotations

import os
import time

from fastapi import HTTPException, Request

from . import ratecount


def _limit(bucket: str, default: int) -> int:
    raw = os.environ.get(f"AEC_THROTTLE_{bucket.upper()}_RPM")
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _caller(request: Request) -> str:
    # Prefer the authenticated user (set by auth middleware/deps) so one abusive account behind a
    # shared NAT can't exhaust everyone; fall back to client IP for anonymous callers.
    user = getattr(request.state, "user", None)
    if isinstance(user, dict):
        who = user.get("username")
        if who:
            return f"u:{who}"
    return f"ip:{request.client.host if request.client else '?'}"


def rate_limited(bucket: str, default_rpm: int):
    """FastAPI dependency factory: allow at most N calls/minute to `bucket` per caller.

    `default_rpm` is the built-in cap; override with AEC_THROTTLE_<BUCKET>_RPM (0 disables). Raises
    429 with a Retry-After header when exceeded.

    ASYNC since R39-THROTTLE-SHARED, because the shared counter is an awaited Redis round-trip.
    FastAPI resolves sync and async dependencies alike, so no call site changes — but a caller that
    invoked `_dep(request)` directly would now get a coroutine, which is why `test_throttle` drives
    it through a real app rather than by hand.
    """
    async def _dep(request: Request) -> None:
        limit = _limit(bucket, default_rpm)
        if limit <= 0:
            return
        win = int(time.time() // 60)
        # The bucket is the NAMESPACE and the caller is the key, so two buckets can never share a
        # counter — under the old dict that separation was structural; under a flat Redis keyspace
        # it has to be spelled out.
        n = await ratecount.count(f"throttle:{bucket}", _caller(request), win)
        if n > limit:
            raise HTTPException(429, f"rate limit exceeded for {bucket} (max {limit}/min)",
                                headers={"Retry-After": "60"})
    return _dep
