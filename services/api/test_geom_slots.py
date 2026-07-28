"""
The geometry-slot semaphore — the mechanism for PERF-THREADS.

`geom_workers()` answers "how many processes should ONE pass use". It cannot answer "how many passes
should run at once", and that second number is what thrashes a server: eight concurrent requests each
starting a cpu-1 iterator asks for 8x(cpu-1) processes on a machine that has cpu.

**The mechanism ships here; the 13 call sites are NOT yet wired to it.** Wiring means the slot has to
be held for the iterator's *consumption*, not its creation, and every site has its own loop shape and
early returns. That is a real refactor with a lifetime question in it, not a mechanical edit, and a
half-wired concurrency guard reads as protection that is not there. These tests pin the primitive so
the wiring is the only thing left to get right.
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

print()
if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_geom_slots OK")
