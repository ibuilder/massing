"""Lightweight per-endpoint rate limiting for expensive operations (AI review, file conversion).

The global middleware in main.py caps *all* requests per IP but is opt-in (off by default) and one
flat number. Some endpoints are far costlier than a normal read — an AI review calls an LLM, a convert
shells out / hits a paid cloud translation — so they get their own, always-on, much lower per-caller
cap regardless of the global limiter. In-process sliding window keyed by (bucket, caller); good enough
for a single/few-worker deployment and, unlike the global limiter, protects even when AEC_RATE_LIMIT_RPM
is unset. Defaults are generous enough for tests/interactive use; tune or disable per bucket via env
(AEC_THROTTLE_<BUCKET>_RPM; 0 disables)."""
from __future__ import annotations

import os
import time

from fastapi import HTTPException, Request

# bucket -> { caller -> [window_minute, count] }
_HITS: dict[str, dict[str, list[int]]] = {}


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
    429 with a Retry-After header when exceeded."""
    def _dep(request: Request) -> None:
        limit = _limit(bucket, default_rpm)
        if limit <= 0:
            return
        win = int(time.time() // 60)
        who = _caller(request)
        b = _HITS.setdefault(bucket, {})
        rec = b.get(who)
        if not rec or rec[0] != win:
            rec = [win, 0]
            if len(b) > 10_000:                 # bound memory: drop stale windows wholesale
                b.clear()
            b[who] = rec
        rec[1] += 1
        if rec[1] > limit:
            raise HTTPException(429, f"rate limit exceeded for {bucket} (max {limit}/min)",
                                headers={"Retry-After": "60"})
    return _dep
