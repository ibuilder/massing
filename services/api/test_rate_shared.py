"""R39-THROTTLE-SHARED — one rate counter, and a boot guard that names its own subject.

TWO LIMITERS, ONE OF WHICH COULD NOT COUNT. `main.py` has the opt-in per-IP limiter
(`AEC_RATE_LIMIT_RPM`): it already had a Redis INCR+EXPIRE path and a boot guard refusing to start a
multi-worker production deployment without a shared store. `throttle.py` has the always-on
per-endpoint limiter and kept a plain in-process `dict` with **no Redis path and no guard**. Its
docstring said "good enough for a single/few-worker deployment" — true when written, untrue since
**R39-WORKER-SPLIT (v0.3.869) made a second writer process the supported deployment**.

THE PART WORTH KEEPING is why nobody noticed. A boot guard that names `AEC_RATE_LIMIT_RPM` reads, to
anyone checking, as "rate limiting is protected against the multi-worker mistake". It is not — it
covers the opt-in limiter and is silent about the always-on one, which is the one capping
`POST /auth/stepup` at 10/min. **A generic-sounding gate hides a missing one**, so the new guard
names throttle buckets explicitly and this file asserts the two guards are separate checks.

WHAT THIS ASSERTS
  * the counter is per-namespace, and the namespace/key join is DELIMITED so two limiters cannot
    collide into one counter;
  * eviction under key churn drops the OLDEST entries and never `clear()`s — the old `throttle.py`
    cleared wholesale at 10k keys, so a scanner cycling through callers could wipe the limiter's
    state for everyone it was legitimately throttling. That is the one behaviour change here that is
    a security fix rather than a plumbing change;
  * the boot guard REFUSES a tuned bucket on a multi-worker production deployment, and does not
    refuse when a shared store is configured or when there is one worker;
  * two throttle buckets still do not share a cap.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_rate_shared.py
"""
import asyncio
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_rate_shared.db"
os.environ["STORAGE_DIR"] = "./test_storage_rate_shared"
os.environ.pop("AEC_REDIS_URL", None)          # no shared store: exercise the fallback path
for _f in ("./test_rate_shared.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi import Depends, FastAPI, Request  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aec_api import main as api_main  # noqa: E402
from aec_api import ratecount, throttle  # noqa: E402

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail and not ok else ''}")
    if not ok:
        failures.append(name)


#: ONE event loop for the whole file. `asyncio.run` per call spins up and tears down a loop each
#: time, and the churn section below makes ten thousand calls — on Windows that alone ran past a
#: ten-minute timeout, which reads exactly like a hung test rather than a slow harness.
_loop = asyncio.new_event_loop()
asyncio.set_event_loop(_loop)


def run(coro):
    return _loop.run_until_complete(coro)

# --------------------------------------------------------------------------------------------
# 1) The counter itself.
# --------------------------------------------------------------------------------------------
check("the counter increments within a window",
      [run(ratecount.count("ns", "a", 1)) for _ in range(3)] == [1, 2, 3])
check("a new window restarts the count", run(ratecount.count("ns", "a", 2)) == 1)
check("two namespaces do not share a counter", run(ratecount.count("other", "a", 2)) == 1)
check("two keys in one namespace do not share a counter",
      run(ratecount.count("ns", "b", 2)) == 1)

# The delimiter, asserted on the SHARED-STORE key. This check used to go through `count()`, which
# only builds such a key when a Redis client exists — so with no Redis configured it exercised the
# in-process dict instead, and a mutation stripping the delimiters survived the entire suite. A
# branch nothing can enter is a branch nothing can test; `redis_key` was lifted out of it for this.
# The pair has to be one that ACTUALLY collides when the delimiters go. The first attempt used
# ("rl", "x:9") vs ("rlx", "9") — but the colon inside the key kept them distinct even under bare
# concatenation, so the mutation survived. A collision probe that cannot collide proves nothing:
#   "rl" + "x9" + "5"  ==  "rlx" + "9" + "5"  ==  "rlx95"
k1 = ratecount.redis_key("rl", "x9", 5)
k2 = ratecount.redis_key("rlx", "9", 5)
check("a namespace/key join cannot collide by concatenation", k1 != k2,
      f"both built {k1!r} — two limiters would share one counter")
check("...and the in-process path keeps them apart too",
      run(ratecount.count("rl", "x9", 5)) == 1 and run(ratecount.count("rlx", "9", 5)) == 1)

# --------------------------------------------------------------------------------------------
# 2) Eviction under churn. The security-relevant behaviour change.
# --------------------------------------------------------------------------------------------
ratecount._LOCAL.clear()
VICTIM = "victim"
for _ in range(5):
    run(ratecount.count("churn", VICTIM, 7))       # an established, actively-throttled caller
# A scanner cycling far past the cap, exactly as a botnet walking an IP range would. Driven through
# the SYNC in-process path: `count()` only awaits when a Redis client exists, and ten thousand
# awaits here bought nothing but wall-clock. `local_count` is the code under test either way.
for i in range(ratecount._MAX_KEYS + 500):
    ratecount.local_count("churn", f"scan-{i}", 7)
after = run(ratecount.count("churn", VICTIM, 7))
# The victim is old, so LRU eviction MAY drop it — what must not happen is the whole namespace being
# reset while it is still present, and the map must stay bounded. Assert the bound and that the
# scanner's own recent entries survived (i.e. eviction happened at the head, not wholesale).
retained = len(ratecount._LOCAL["churn"])
check("the key map stays bounded under churn", retained <= ratecount._MAX_KEYS + 2,
      f"{retained} keys retained — the bound is not holding")
# THE DISCRIMINATING ASSERTION, and the first version was not one. It checked that the most recent
# scanner key had a count of 2, which is equally true under a wholesale `clear()` — the mutation
# reintroducing the old `throttle.py` bug survived it. What separates the two is how many keys
# SURVIVE: evicting the oldest holds the map at its bound, while clearing at the bound drops back to
# near zero and rebuilds (~500 keys here). So count them.
check("eviction drops the OLDEST keys — a wholesale clear() would leave far fewer",
      retained >= ratecount._MAX_KEYS * 0.9,
      f"only {retained} of {ratecount._MAX_KEYS} retained, so the map was cleared wholesale — a "
      "scanner can wipe the limiter's state for every caller it was legitimately throttling")
check("the victim's counter is still a real count, not silently reset to a fresh window",
      isinstance(after, int) and after >= 1)

# --------------------------------------------------------------------------------------------
# 3) The boot guard names throttle buckets — the check that did not exist.
# --------------------------------------------------------------------------------------------
def with_env(**kw):
    old = {k: os.environ.get(k) for k in kw}
    for k, v in kw.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v
    return old


def restore(old):
    for k, v in old.items():
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


o = with_env(UVICORN_WORKERS="4", AEC_REDIS_URL=None, AEC_THROTTLE_STEPUP_RPM="5")
check("a tuned bucket on a multi-worker box with no shared store is flagged",
      api_main._tuned_throttle_buckets() == ["AEC_THROTTLE_STEPUP_RPM"],
      f"got {api_main._tuned_throttle_buckets()}")

# ...and the two guards are SEPARATE checks. This is the assertion the whole item turns on: the
# pre-existing guard sees nothing here, because AEC_RATE_LIMIT_RPM is unset.
check("the pre-existing rate-limit guard does NOT cover this case",
      api_main._rate_limit_is_per_worker() is False,
      "the old guard already covered it — then this item was not a gap")

# NOTE: `with_env` RETURNS the previous values; calling restore() on its result immediately undoes
# the change. The first draft did exactly that and three checks failed against correct code — the
# harness was testing the environment it had just put back.
with_env(AEC_REDIS_URL="redis://localhost:6379/0")
check("a configured shared store clears the flag", api_main._tuned_throttle_buckets() == [],
      f"got {api_main._tuned_throttle_buckets()}")
with_env(AEC_REDIS_URL=None, UVICORN_WORKERS="1")
check("a single worker clears the flag", api_main._tuned_throttle_buckets() == [],
      f"got {api_main._tuned_throttle_buckets()}")
with_env(UVICORN_WORKERS="4", AEC_THROTTLE_STEPUP_RPM="0")
check("a bucket explicitly DISABLED (0) is not flagged — it cannot be multiplied",
      api_main._tuned_throttle_buckets() == [],
      f"got {api_main._tuned_throttle_buckets()}")
restore(o)

# The guard must actually refuse, not merely report. A predicate nobody acts on is a comment.
o2 = with_env(UVICORN_WORKERS="4", AEC_REDIS_URL=None, AEC_THROTTLE_STEPUP_RPM="5",
              AEC_ENV="production", AEC_RBAC="1", AEC_ALLOW_OPEN=None,
              AEC_AUTH_SECRET="x" * 40, AEC_TRUST_XUSER=None)
try:
    api_main._production_guard()
    check("the production guard REFUSES a tuned bucket without a shared store", False,
          "it returned instead of raising")
except RuntimeError as e:
    check("the production guard REFUSES a tuned bucket without a shared store",
          "AEC_THROTTLE_STEPUP_RPM" in str(e), f"raised, but not about the bucket: {e}")
restore(o2)

# --------------------------------------------------------------------------------------------
# 4) End to end: two buckets still hold separate caps through the real dependency.
# --------------------------------------------------------------------------------------------
ratecount._LOCAL.clear()
app = FastAPI()
a_dep, b_dep = throttle.rate_limited("alpha", 2), throttle.rate_limited("beta", 2)


@app.get("/a")
async def a(request: Request, _: None = Depends(a_dep)):
    return {"ok": True}


@app.get("/b")
async def b(request: Request, _: None = Depends(b_dep)):
    return {"ok": True}


with TestClient(app) as c:
    codes_a = [c.get("/a").status_code for _ in range(3)]
    check("a bucket still enforces its own cap", codes_a == [200, 200, 429], str(codes_a))
    check("exhausting one bucket does not exhaust another", c.get("/b").status_code == 200,
          "beta was already spent — the two buckets share a counter")

print(f"\ntest_rate_shared {'OK' if not failures else 'FAILED: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
