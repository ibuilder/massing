"""
The geometry-slot semaphore — the mechanism for PERF-THREADS.

`geom_workers()` answers "how many processes should ONE pass use". It cannot answer "how many passes
should run at once", and that second number is what thrashes a server: eight concurrent requests each
starting a cpu-1 iterator asks for 8x(cpu-1) processes on a machine that has cpu.

All 13 sites are wired via `bounded_iterator`, which is what made this a one-line change per site
rather than thirteen restructures: the slot has to span the iterator's **consumption**, not its
construction, so the wrapper owns the lifetime instead of every differently-shaped loop.

The safety argument, which is why wiring was reasonable at all: release is deterministic on both
normal endings (`initialize()` False, `next()` False) and on exceptions, with `__del__` only as a
backstop for an early `break`. And if the backstop ever misses, `geometry_slot` acquires with a
timeout and proceeds anyway — so a leaked slot degrades to the unbounded behaviour we already had,
never to a deadlock. The tests below assert every one of those paths.
"""
import sys
import threading
import time

sys.path.insert(0, "src")
sys.path.insert(0, "../data/src")

from aec_data import geomconf  # noqa: E402

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


# --- sizing ---------------------------------------------------------------------------------------
check("at least one slot always exists", geomconf.geom_slots() >= 1,
      "zero slots would mean nothing renders at all")

import os  # noqa: E402

os.environ["AEC_GEOM_SLOTS"] = "3"
check("the slot count is tunable", geomconf.geom_slots() == 3)
os.environ["AEC_GEOM_SLOTS"] = "not-a-number"
check("a garbage override falls back rather than crashing", geomconf.geom_slots() >= 1)
del os.environ["AEC_GEOM_SLOTS"]

# --- re-entrancy: the deadlock this is designed to avoid ---------------------------------------------
geomconf._SLOTS = threading.BoundedSemaphore(1)
geomconf._depth = threading.local()

entered = []
with geomconf.geometry_slot():
    entered.append("outer")
    with geomconf.geometry_slot():          # would deadlock on a plain semaphore with 1 slot
        entered.append("inner")
check("a nested pass on the same thread does NOT deadlock", entered == ["outer", "inner"],
      "nothing nests today; this makes it safe when something does")
check("the slot is fully released after nesting unwinds", geomconf._SLOTS.acquire(timeout=1))
geomconf._SLOTS.release()

# --- the slot actually excludes across threads -----------------------------------------------------
# Event-driven, not sleep-driven. A `sleep(0.2)` that has to land inside a window flakes both ways
# under the parallel gate — and a concurrency test that fails intermittently teaches people to
# re-run it rather than read it.
geomconf._SLOTS = threading.BoundedSemaphore(1)
order = []
a_in, release_a, b_in = threading.Event(), threading.Event(), threading.Event()


def worker(name):
    with geomconf.geometry_slot():
        order.append(f"{name}-in")
        (a_in if name == "a" else b_in).set()
        if name == "a":
            release_a.wait(5.0)
        order.append(f"{name}-out")


ta = threading.Thread(target=worker, args=("a",)); ta.start()
check("the first thread enters", a_in.wait(5.0))
tb = threading.Thread(target=worker, args=("b",)); tb.start()
check("a second thread WAITS while the slot is held", not b_in.wait(0.5), f"saw {order}")
release_a.set()
check("...and proceeds once it is released", b_in.wait(5.0))
ta.join(5); tb.join(5)
check("both ran in order", order == ["a-in", "a-out", "b-in", "b-out"], f"saw {order}")

# --- a timeout proceeds; it does not fail the request -------------------------------------------------
geomconf._SLOTS = threading.BoundedSemaphore(1)
geomconf._WAIT_S = 0.3
blocked, hogging = threading.Event(), threading.Event()
done = []


def hog():
    with geomconf.geometry_slot():
        hogging.set()               # signal that the slot is REALLY taken, do not guess with sleep
        blocked.wait(5.0)


th = threading.Thread(target=hog); th.start()
check("the hog holds the only slot", hogging.wait(5.0))
t0 = time.time()
with geomconf.geometry_slot():          # cannot get a slot; must proceed anyway
    done.append(time.time() - t0)
check("a pass that cannot get a slot RUNS anyway", len(done) == 1,
      "the semaphore is a fairness guard, not a gate on whether a user gets their drawing")
check("...after waiting, not immediately", done and done[0] >= 0.25, f"waited {done[0]:.2f}s")
blocked.set(); th.join(3)

# --- and a timed-out pass must not over-release the semaphore -----------------------------------------
check("a timed-out pass does not release a slot it never held",
      geomconf._SLOTS.acquire(timeout=1),
      "over-releasing a BoundedSemaphore raises, and would do so far from the cause")
geomconf._SLOTS.release()

# --- the wrapper: does the slot span CONSUMPTION and get released every way a read ends? ------------
geomconf._SLOTS = threading.BoundedSemaphore(1)
geomconf._depth = threading.local()
geomconf._WAIT_S = 0.2


class FakeIt:
    """Stands in for an ifcopenshell iterator. `n` shapes, then next() -> False."""

    def __init__(self, n=2, init=True, raise_on=None):
        self.n, self.init_ok, self.raise_on, self.i = n, init, raise_on, 0

    def initialize(self):
        if self.raise_on == "initialize":
            raise RuntimeError("boom")
        return self.init_ok

    def get(self):
        return f"shape{self.i}"

    def next(self):
        if self.raise_on == "next":
            raise RuntimeError("boom")
        self.i += 1
        return self.i < self.n

    def some_other_method(self):
        return "passthrough"


class FakeGeom:
    def __init__(self, it): self._it = it
    def iterator(self, settings, model, workers=None): return self._it


def free_slots():
    """How many slots are currently takeable."""
    got = []
    while geomconf._SLOTS.acquire(blocking=False):
        got.append(1)
    for _ in got:
        geomconf._SLOTS.release()
    return len(got)


# exhausting the iterator releases
it = geomconf.bounded_iterator(FakeGeom(FakeIt(n=2)), None, None)
check("the wrapper holds a slot while reading", free_slots() == 0)
it.initialize()
while it.next():
    pass
check("exhausting the read RELEASES the slot", free_slots() == 1)

# initialize() False releases immediately — nothing to iterate
it = geomconf.bounded_iterator(FakeGeom(FakeIt(init=False)), None, None)
it.initialize()
check("initialize()==False releases at once", free_slots() == 1,
      "a model with no geometry must not hold a slot for nothing")

# an exception mid-read releases
it = geomconf.bounded_iterator(FakeGeom(FakeIt(raise_on="next")), None, None)
it.initialize()
try:
    it.next()
except RuntimeError:
    pass
check("an exception during the read releases the slot", free_slots() == 1,
      "a failed render must not permanently consume capacity")

# early break relies on the GC backstop
import gc  # noqa: E402

it = geomconf.bounded_iterator(FakeGeom(FakeIt(n=99)), None, None)
it.initialize(); it.next()
check("an unfinished read still holds its slot", free_slots() == 0)
del it
gc.collect()
check("dropping an unfinished reader releases it (GC backstop)", free_slots() == 1)

# double release must never happen — it would raise on a BoundedSemaphore
it = geomconf.bounded_iterator(FakeGeom(FakeIt(n=1)), None, None)
it.initialize()
it.next()          # exhausts -> releases
it._finish()       # explicit second finish
del it; gc.collect()
check("release is idempotent — no double-release", free_slots() == 1,
      "over-releasing a BoundedSemaphore raises, far from the cause")

# unknown attributes pass through to the real iterator
it = geomconf.bounded_iterator(FakeGeom(FakeIt()), None, None)
check("unknown methods forward to the wrapped iterator", it.some_other_method() == "passthrough")
del it; gc.collect()

# nested: an inner pass must NOT take a second slot.
#
# The first version of this test used BoundedSemaphore(1) and asserted `free_slots() == 0` inside the
# outer slot — which is true whether or not the inner call took anything, because the outer already
# holds the only slot. It passed with the re-entrancy guard removed entirely. A test that cannot fail
# is not evidence, and this file is the last place that should have contained one.
#
# With TWO slots the assertion has teeth: outer takes one, so a guarded inner leaves exactly one free
# and an unguarded inner leaves zero.
geomconf._SLOTS = threading.BoundedSemaphore(2)
geomconf._depth = threading.local()
with geomconf.geometry_slot():
    check("  (baseline) the outer slot is held, one remains", free_slots() == 1)
    inner = geomconf.bounded_iterator(FakeGeom(FakeIt()), None, None)
    check("a pass inside an existing slot does not take a SECOND", free_slots() == 1,
          "an unguarded inner call would leave 0 free here")
    del inner
gc.collect()
check("both slots are free once the outer unwinds", free_slots() == 2)

# and the wrapper's own depth tracking must guard a wrapper INSIDE a wrapper
geomconf._SLOTS = threading.BoundedSemaphore(2)
geomconf._depth = threading.local()
outer = geomconf.bounded_iterator(FakeGeom(FakeIt()), None, None)
check("  (baseline) the wrapper took one slot", free_slots() == 1)
nested = geomconf.bounded_iterator(FakeGeom(FakeIt()), None, None)
check("a wrapper created inside a wrapper takes no second slot", free_slots() == 1,
      "bounded_iterator READ _depth without ever SETTING it — the guard covered geometry_slot only")
del nested, outer
gc.collect()
check("both slots return after the wrappers are dropped", free_slots() == 2)

# --- the leak the review caught: a constructor that raises must not eat a slot forever -------------
geomconf._SLOTS = threading.BoundedSemaphore(1)
geomconf._depth = threading.local()


class ExplodingGeom:
    def iterator(self, settings, model, workers=None):
        raise RuntimeError("iterator construction failed")


try:
    geomconf.bounded_iterator(ExplodingGeom(), None, None)
except RuntimeError:
    pass
check("a failed iterator construction RELEASES its slot", free_slots() == 1,
      "the slot is taken before the constructor runs; with no wrapper built, __del__ never fires")

# --- sizing: the formula that silently collapsed to 1 ------------------------------------------------
import multiprocessing  # noqa: E402

# run_tests.py exports AEC_GEOM_WORKERS=1, so geom_workers() short-circuits on the override and the
# formula below was NEVER evaluated by the gate — the invariant check could not fail. Clear it here.
_saved_env = os.environ.pop("AEC_GEOM_WORKERS", None)
real_cpu = multiprocessing.cpu_count
try:
    for cpu in (1, 2, 3, 4, 8, 16, 32):
        multiprocessing.cpu_count = lambda c=cpu: c
        sl = geomconf.geom_slots()
        if cpu >= 2:
            check(f"cpu={cpu}: more than one pass may run (got {sl})", sl > 1,
                  "min(4, cpu//2) still gave 1 on 2- and 3-core hosts — the worse-than-nothing state")
        # a LONE pass must still get the machine; this is the regression the slot-count divisor caused
        geomconf._INFLIGHT[0] = 1
        check(f"cpu={cpu}: a lone render still gets ~the box ({geomconf.geom_workers()})",
              geomconf.geom_workers() >= max(1, cpu - 1))
        # and concurrent passes must divide it rather than multiply past it
        geomconf._INFLIGHT[0] = sl
        wk = geomconf.geom_workers()
        check(f"cpu={cpu}: {sl} concurrent x {wk} workers = {sl*wk} stays near {cpu}", sl * wk <= cpu + 1)
finally:
    multiprocessing.cpu_count = real_cpu
    geomconf._INFLIGHT[0] = 0
    if _saved_env is not None:
        os.environ["AEC_GEOM_WORKERS"] = _saved_env

# --- #5: a cross-thread drop must not poison the creating thread's re-entrancy marker ------------
geomconf._SLOTS = threading.BoundedSemaphore(2)
geomconf._depth = threading.local()
geomconf._INFLIGHT[0] = 0

holder = {}


def make_on_other_thread():
    holder["it"] = geomconf.bounded_iterator(FakeGeom(FakeIt(n=99)), None, None)
    holder["depth_after_create"] = getattr(geomconf._depth, "n", 0)


t = threading.Thread(target=make_on_other_thread); t.start(); t.join(5)
check("the creating thread marked itself in-pass", holder["depth_after_create"] == 1)

# Drop it from THIS thread — i.e. what the garbage collector does. The old code decremented the
# collector's thread-local, leaving the creator permanently at 1 and silently unable to ever take a
# slot again — the bound switching itself off for a pooled worker, forever, invisibly.
del holder["it"]
gc.collect()
check("a cross-thread drop still releases the slot", free_slots() == 2)

depth_seen = {}


def check_depth_on_creator():
    depth_seen["n"] = getattr(geomconf._depth, "n", 0)


t2 = threading.Thread(target=check_depth_on_creator); t2.start(); t2.join(5)
check("a fresh thread is not left marked in-pass", depth_seen["n"] == 0,
      "the collector must not decrement somebody else's thread-local")
check("in-flight returns to zero", geomconf._INFLIGHT[0] == 0)

# --- #6: special methods resolve on the TYPE, so a forwarding __getattr__ never sees them ---------
geomconf._SLOTS = threading.BoundedSemaphore(2)
geomconf._depth = threading.local()


class IterableIt(FakeIt):
    def __iter__(self):
        return iter(["s0", "s1"])


it = geomconf.bounded_iterator(FakeGeom(IterableIt()), None, None)
check("the wrapper is iterable, as a drop-in must be", list(it) == ["s0", "s1"],
      "`for shape in ...` is the first idiom people reach for; __getattr__ does not cover it")
del it
gc.collect()

print()
if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_geom_slots OK")
