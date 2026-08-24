"""PERF-THREADS ③ — concurrent IFC parses are capped, and the cap is observed rather than declared.

**The risk is not unbounded threads.** Starlette/anyio's pool is 40, not unlimited — the report that
raised this said otherwise, and that correction is the reason the fix is shaped the way it is. The real
problem is what those threads each hold: an IFC parse materialises a whole model, hundreds of MB for a
large one, so forty concurrent parses is an out-of-memory kill rather than a slow response.

So the cap is small and **specific to model work**, not a change to the general thread pool. Every
other route that goes off the event loop is cheap and stays unthrottled — capping those would trade a
real OOM for an invented queue.

What is asserted here is the property that matters and is easy to get wrong: **peak observed
concurrency**, measured by the fake parser itself, never exceeds the cap. A semaphore that is acquired
and released around the wrong statement, or leaked on an exception, passes a "does it still work" test
and fails this one.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_ifc_parse_gate.py
"""
from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

os.environ["AEC_IFC_PARSE_SLOTS"] = "3"          # must be set BEFORE the module is imported
sys.path.insert(0, "src")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data" / "src"))

import ifcopenshell  # noqa: E402

from aec_data import ifc_loader  # noqa: E402

FAILED: list[str] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + (f"   {detail}" if detail and not ok else ""))
    if not ok:
        FAILED.append(name)


check("the cap is read from the environment", ifc_loader.parse_slots() == 3, ifc_loader.parse_slots())


class Probe:
    """Stands in for `ifcopenshell.open`, recording how many callers are inside it at once."""

    def __init__(self, hold: float = 0.05, fail_every: int = 0) -> None:
        self.live = 0
        self.peak = 0
        self.calls = 0
        self.hold = hold
        self.fail_every = fail_every
        self._lock = threading.Lock()

    def __call__(self, path: str):
        with self._lock:
            self.live += 1
            self.calls += 1
            self.peak = max(self.peak, self.live)
            n = self.calls
        try:
            time.sleep(self.hold)
            if self.fail_every and n % self.fail_every == 0:
                raise RuntimeError("parser blew up")
            return object()                      # a stand-in model; nothing here inspects it
        finally:
            with self._lock:
                self.live -= 1


def run_parallel(n: int, target) -> list[BaseException | None]:
    """Fire `n` threads at `target` and collect what each raised."""
    out: list[BaseException | None] = [None] * n
    def one(i: int) -> None:
        try:
            target(f"/nonexistent/model-{i}.ifc")
        except BaseException as e:               # noqa: BLE001 — the point is to record it
            out[i] = e
    ts = [threading.Thread(target=one, args=(i,)) for i in range(n)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=30)
    return out


# The pre-flight scan reads the file; these paths do not exist, so stub it out — what is under test is
# the gate around the PARSE, not the truncation screen in front of it.
ifc_loader.scan_unterminated_string = lambda _p: False           # type: ignore[attr-defined]
import aec_data.schema_diag as _sd  # noqa: E402

_sd.scan_unterminated_string = lambda _p: False                  # type: ignore[assignment]

# --- the load-bearing assertion ------------------------------------------------------------------
probe = Probe()
ifcopenshell.open = probe                                        # type: ignore[assignment]
errs = run_parallel(12, ifc_loader._open_uncached)
check("all twelve parses ran", probe.calls == 12, probe.calls)
check("no parse raised", not any(errs), [type(e).__name__ for e in errs if e])
check("PEAK CONCURRENCY NEVER EXCEEDED THE CAP", probe.peak <= 3, f"peak={probe.peak}, cap=3")
# The twin: without it, a gate that let exactly ONE through would also pass the line above, and a cap
# of one is a different bug — it serialises every model read in the process.
check("...and the cap was actually REACHED, so this is not a cap of one",
      probe.peak == 3, f"peak={probe.peak}")

# --- a failing parse must not leak its slot -------------------------------------------------------
# `with` releases on the exception path; a hand-rolled acquire/release around the wrong statement does
# not. A leaked slot is invisible until the Nth failure, when the process stops parsing anything at
# all — the worst kind of bug to find in production.
probe2 = Probe(fail_every=2)
ifcopenshell.open = probe2                                       # type: ignore[assignment]
errs2 = run_parallel(8, ifc_loader._open_uncached)
raised = sum(1 for e in errs2 if e is not None)
check("half the parses failed, as arranged", raised == 4, raised)
check("...and the survivors still ran, so no slot was leaked", probe2.calls == 8, probe2.calls)

probe3 = Probe()
ifcopenshell.open = probe3                                       # type: ignore[assignment]
run_parallel(6, ifc_loader._open_uncached)
check("AFTER FOUR FAILURES the gate still admits the full cap", probe3.peak == 3,
      f"peak={probe3.peak} — a leaked slot would show here as a lower peak")

# --- the cheap refusal is NOT gated ---------------------------------------------------------------
# A truncated file is refused by a read, not a parse. Making that queue behind three real parses would
# put the cheapest answer on the slowest path.
_sd.scan_unterminated_string = lambda _p: True                   # type: ignore[assignment]
slow = Probe(hold=0.4)
ifcopenshell.open = slow                                         # type: ignore[assignment]

blockers = [threading.Thread(target=lambda: ifc_loader._open_uncached("/x/hold.ifc")) for _ in range(3)]
_sd.scan_unterminated_string = lambda _p: False                  # type: ignore[assignment]
for b in blockers:
    b.start()
time.sleep(0.05)                                                 # let them take all three slots
_sd.scan_unterminated_string = lambda _p: True                   # type: ignore[assignment]
t0 = time.time()
try:
    ifc_loader._open_uncached("/x/truncated.ifc")
    refused = False
except ifc_loader.UnreadableIfc:
    refused = True
elapsed = time.time() - t0
for b in blockers:
    b.join(timeout=10)
check("a truncated file is refused", refused)
check("...WITHOUT waiting for a parse slot", elapsed < 0.2, f"{elapsed:.2f}s while 3 slots were held")

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    raise SystemExit(1)
print("test_ifc_parse_gate OK")
