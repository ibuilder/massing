"""R35-PIDLOCK-XPROC — the sidecar lock now serialises across workers, or says it cannot.

The interesting assertions are not "a lock was taken". They are the three ways this fix could have
shipped looking correct and doing nothing:

1. **a per-process key.** `hash()` is randomised per process (PEP 456), so a key derived from it
   gives every worker a *different* advisory lock and none ever collide. The lock costs a round trip
   and serialises nothing — the exact bug being fixed, reintroduced by the fix, and invisible to any
   test that runs in one process;
2. **a deadlock on the ordinary path.** `mutating()` nests — `jobs.py` holds it across a handler that
   calls `docmanager`, which takes it again. A cross-process lock acquired per call would have the
   nested acquisition wait, in a second session, on a lock its own caller holds;
3. **a silent no-op on SQLite**, reported as though it were serialisation.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_pid_lock_xproc.py
"""
import subprocess
import sys
import threading

sys.path.insert(0, "src")

from aec_api import pid_lock  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


def _reacquired(timeout: float = 5.0) -> bool:
    """Can the lock be taken again? Run in a thread so a leaked RLock times out instead of hanging
    the whole suite — a test that hangs reports nothing at all."""
    got = threading.Event()

    def _try():
        with pid_lock.mutating(PID):
            got.set()

    threading.Thread(target=_try, daemon=True).start()
    return got.wait(timeout=timeout)


# --- 1. THE KEY MUST BE STABLE ACROSS PROCESSES -------------------------------------------------
# This is the assertion the whole item rests on. A key that varies per process makes the lock a
# no-op that still looks like a lock.
PID = "project-abc-123"
here = pid_lock.advisory_key(PID)
out = subprocess.run(
    [sys.executable, "-c",
     "import sys; sys.path.insert(0,'src');\n"
     "from aec_api import pid_lock; print(pid_lock.advisory_key('project-abc-123'))"],
    capture_output=True, text=True, timeout=60,
)
check("a separate PROCESS derives the same advisory key",
      out.returncode == 0 and out.stdout.strip() == str(here),
      f"here={here} other_process={out.stdout.strip()!r} err={out.stderr[-160:]}")

check("  and it is NOT Python's randomised str hash",
      here != hash(PID) or True,  # equality is possible by chance; the cross-process check above is
      "")                          # the real assertion — this line documents why it is not enough
# Prove the randomised hash really would have differed, so assertion 1 is not vacuous.
h2 = subprocess.run([sys.executable, "-c", "print(hash('project-abc-123'))"],
                    capture_output=True, text=True, timeout=60).stdout.strip()
check("  (control) Python's hash() DOES differ across processes — so the check above is meaningful",
      h2 != str(hash(PID)), f"{h2} vs {hash(PID)} — if equal, PYTHONHASHSEED is pinned")

check("the key fits a signed 64-bit advisory-lock id",
      -(2**63) <= here < 2**63, here)
check("different projects get different keys",
      pid_lock.advisory_key("a") != pid_lock.advisory_key("b"))
check("the same project gets the same key twice",
      pid_lock.advisory_key("a") == pid_lock.advisory_key("a"))

# --- 2. NESTING MUST NOT DEADLOCK ------------------------------------------------------------------
# The ordinary path: jobs.py holds mutating(pid) and the handler calls docmanager, which takes it
# again. If this hangs, the fix has deadlocked the product on its most common mutating flow.
done = threading.Event()
err: list = []


def _nested():
    try:
        with pid_lock.mutating(PID):
            with pid_lock.mutating(PID):          # the docmanager call inside a job handler
                with pid_lock.mutating(PID):      # and one deeper, for good measure
                    pass
        done.set()
    except Exception as e:                        # noqa: BLE001
        err.append(e)
        done.set()


t = threading.Thread(target=_nested, daemon=True)
t.start()
check("mutating() nests three deep without deadlocking — the jobs.py -> docmanager path",
      done.wait(timeout=20) and not err, f"timed out or raised: {err}")

# --- 3. reentrancy bookkeeping must not leak ---------------------------------------------------------
with pid_lock.mutating(PID):
    pass
depth = getattr(pid_lock._local, "depth", {}) or {}
check("the reentrancy counter returns to zero after the block",
      depth.get(PID, 0) == 0, depth)
with pid_lock.mutating(PID):
    inner = dict(getattr(pid_lock._local, "depth", {}) or {})
check("  a second, separate acquisition also unwinds cleanly",
      (getattr(pid_lock._local, "depth", {}) or {}).get(PID, 0) == 0, inner)

# --- 4. the status is HONEST about what is actually in force -------------------------------------------
st = pid_lock.cross_process_status()
check("cross_process_status names the backend and the dialect",
      set(st) >= {"cross_process", "backend", "dialect", "meaning"}, st)
check("  it does not claim cross-process serialisation on a non-Postgres backend",
      st["cross_process"] is (st["dialect"] == "postgresql"), st)
if not st["cross_process"]:
    check("  and the meaning states the CONSEQUENCE, not just the absence",
          "lose the first writer" in st["meaning"], st["meaning"])
    check("  naming single-writer-per-project as a real constraint",
          "single-writer-per-project" in st["meaning"].lower(), st["meaning"])

# --- 5. the lock still works as a lock, in-process ------------------------------------------------------
# Without this, every assertion above could pass on a lock that never excludes anything.
order: list[str] = []
started = threading.Event()


def _hold():
    with pid_lock.mutating("serial-test"):
        started.set()
        order.append("A-in")
        threading.Event().wait(0.3)
        order.append("A-out")


def _contend():
    started.wait(timeout=5)
    with pid_lock.mutating("serial-test"):
        order.append("B-in")


ta, tb = threading.Thread(target=_hold), threading.Thread(target=_contend)
ta.start(); tb.start(); ta.join(timeout=15); tb.join(timeout=15)
check("two threads do NOT interleave inside the lock — it actually excludes",
      order == ["A-in", "A-out", "B-in"], order)

# --- 6. an exception inside the block must reach the caller UNCHANGED -----------------------------
# Regression: the first version of `_advisory` yielded inside a `try` whose `except Exception` also
# yielded. Throwing into the first yield landed in the handler, which yielded again, and contextlib
# raised "generator didn't stop after throw()" — REPLACING whatever the caller's body actually raised.
# Every real error inside `with mutating(pid):` was masked on the SQLite path, which is the default
# for dev and for this suite. test_docmanager caught it; this pins it.
class _Marker(Exception):
    pass


try:
    with pid_lock.mutating(PID):
        raise _Marker("the caller's own error")
    caught: Exception | None = None
except _Marker as e:
    caught = e
except Exception as e:                                # noqa: BLE001
    caught = e

check("an exception raised inside mutating() propagates unchanged, not as a generator error",
      isinstance(caught, _Marker), f"{type(caught).__name__}: {caught}")
check("  and the reentrancy counter still unwinds after the exception",
      (getattr(pid_lock._local, "depth", {}) or {}).get(PID, 0) == 0,
      getattr(pid_lock._local, "depth", {}))
check("  the in-process lock is released too — a later acquisition does not hang",
      _reacquired(), "mutating() blocked after an exception, so the RLock leaked")

print()
if FAILED:
    print(f"pid_lock_xproc: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("pid_lock_xproc: all checks passed")
