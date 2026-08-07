"""R39-THROTTLE-SHARED — one counter, shared across worker processes, for every rate limit.

**Two limiters existed and only one of them could count.** `main.py` has the opt-in per-IP limiter
(`AEC_RATE_LIMIT_RPM`); it already had a Redis INCR+EXPIRE path *and* a boot guard that refuses to
start a multi-worker production deployment without a shared store. `throttle.py` has the always-on
per-endpoint limiter, and it kept `_HITS` as a plain in-process `dict` with **no Redis path and no
guard at all**. Its own docstring said "good enough for a single/few-worker deployment" — true when
it was written, and untrue since **R39-WORKER-SPLIT (v0.3.869) made a second writer process the
supported deployment**. An item can become urgent without being edited.

**The guard is the part worth recording.** A boot guard covering `AEC_RATE_LIMIT_RPM` reads, to
anyone checking, as "rate limiting is protected against the multi-worker mistake". It is not: it
covers the opt-in limiter and says nothing about the always-on one — which is the one guarding
`POST /auth/stepup` at 10/min, the AI paths at 30/min, and the e-sign webhook at 60/min. **A generic
gate hides a missing one**; the specific gate has to name its own subject.

So the counter lives here, once, and both limiters call it. `main.py` had the working implementation
and this is that code extracted, not a second one written beside it — two rate counters would be two
things to get the fail-open policy and the eviction policy right in.

**Fail-open on Redis trouble, deliberately.** A limiter that 500s when Redis hiccups converts a cache
outage into an API outage; every error path here falls back to the in-process count, which is the
pre-existing behaviour rather than no limit at all.
"""
from __future__ import annotations

import os

#: Set once at import. Read through a function rather than inlined at each call site so a test can
#: reconfigure it, and so `configured()` has exactly one answer for the boot guard to consult.
_REDIS_URL = os.environ.get("AEC_REDIS_URL", "").strip()

#: namespace -> { key -> [window, count] }. The in-process fallback, and the only counter when no
#: Redis is configured.
_LOCAL: dict[str, dict[str, list[int]]] = {}

_MAX_KEYS = 10_000

_client = None
_client_tried = False


def configured() -> bool:
    """Whether a shared counter is actually available.

    Used by the boot guard. Deliberately reports the URL being SET rather than the client being
    reachable: at boot a transient connection failure would otherwise be read as "no shared store"
    and refuse a correctly-configured deployment. Live reachability belongs on `/health`, not in a
    start-up predicate — the same split already recorded for the other boot guards.
    """
    return bool(_REDIS_URL)


def _redis():
    global _client, _client_tried
    if _client_tried:
        return _client
    _client_tried = True
    if _REDIS_URL:
        try:                                    # lazy: redis is a dependency only when a URL is set
            import redis.asyncio as _aioredis
            _client = _aioredis.from_url(_REDIS_URL, socket_timeout=0.25,
                                         socket_connect_timeout=0.25)
        except Exception:                       # noqa: BLE001 — not installed / bad URL → in-process
            _client = None
    return _client


def local_count(namespace: str, key: str, window: int) -> int:
    """Increment and return the in-process count for (namespace, key, window)."""
    ns = _LOCAL.setdefault(namespace, {})
    rec = ns.get(key)
    if not rec or rec[0] != window:
        rec = [window, 0]
        # Evict the OLDEST entries (dict insertion order), never `clear()`. A bulk clear resets every
        # active counter at once, so a scanner churning through keys can wipe the limiter's state for
        # everyone it was legitimately throttling. `throttle.py` did exactly that before this.
        while len(ns) > _MAX_KEYS:
            ns.pop(next(iter(ns)), None)
        ns[key] = rec
    rec[1] += 1
    return rec[1]


def redis_key(namespace: str, key: str, window: int) -> str:
    """The shared-store key for one counter.

    A separate function so it can be asserted without a Redis server. It was inline, and a mutation
    that removed the delimiters SURVIVED the whole suite — because the only code path that built a
    key was the one that never runs when no Redis is configured. **A branch nothing can enter is a
    branch nothing can test**, so the part worth checking was lifted out of it.

    Delimited on every join: `f"{a}:{b}"` and not `f"{a}{b}"`. Bare concatenation collides —
    namespace "rl" with key "x:1" is otherwise the same string as namespace "rlx" with key "1", and
    two limiters sharing one counter is a cap that silently tightens for one caller and loosens for
    another.
    """
    return f"{namespace}:{key}:{window}"


async def count(namespace: str, key: str, window: int) -> int:
    """Hits for (namespace, key, window). Shared via Redis when configured, else in-process."""
    r = _redis()
    if r is not None:
        try:
            k = redis_key(namespace, key, window)
            async with r.pipeline(transaction=True) as pipe:
                pipe.incr(k)
                pipe.expire(k, 65)              # auto-drop one window after it closes
                n, _ = await pipe.execute()
            return int(n)
        except Exception:                       # noqa: BLE001 — a Redis hiccup must not break requests
            pass
    return local_count(namespace, key, window)
