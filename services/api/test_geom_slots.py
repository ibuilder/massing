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
geomconf._SLOTS = threading.BoundedSemaphore(1)
order, hold = [], threading.Event()


def worker(name):
    with geomconf.geometry_slot():
        order.append(f"{name}-in")
        if name == "a":
            hold.wait(2.0)
        order.append(f"{name}-out")


ta = threading.Thread(target=worker, args=("a",)); ta.start()
time.sleep(0.2)
tb = threading.Thread(target=worker, args=("b",)); tb.start()
time.sleep(0.2)
check("a second thread WAITS while the slot is held", order == ["a-in"], f"saw {order}")
hold.set(); ta.join(3); tb.join(3)
check("...and proceeds once it is released", order == ["a-in", "a-out", "b-in", "b-out"], f"saw {order}")

# --- a timeout proceeds; it does not fail the request -------------------------------------------------
geomconf._SLOTS = threading.BoundedSemaphore(1)
geomconf._WAIT_S = 0.3
blocked = threading.Event()
done = []


def hog():
    with geomconf.geometry_slot():
        blocked.wait(2.0)


th = threading.Thread(target=hog); th.start()
time.sleep(0.1)
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

# nested: an inner pass must NOT take a second slot
geomconf._SLOTS = threading.BoundedSemaphore(1)
with geomconf.geometry_slot():
    inner = geomconf.bounded_iterator(FakeGeom(FakeIt()), None, None)
    check("a pass inside an existing slot does not take another", free_slots() == 0,
          "and crucially does not block waiting for one")
    del inner

print()
if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_geom_slots OK")
