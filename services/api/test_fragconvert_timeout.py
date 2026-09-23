"""DESKTOP-CONVERT-TIMEOUT — does `convert_ifc`'s `timeout` bind the PYTHON path, or only Node?

`fragconvert.convert_ifc` has always taken a `timeout`. It reached `subprocess.run` on the Node
path, where an overrunning child can be killed, and reached **nothing at all** on the Python path,
which calls IfcOpenShell in the caller's own process. `_publish` runs on a background worker and
does not care. **`edit_preview` is a synchronous route that passes `timeout=120`**, so a slow model
held a request worker past its own deadline instead of reaching the 503 that route is written to
return — and the parameter's presence is what made that invisible.

### What this gate asserts, and what it deliberately does not

The fix is a COOPERATIVE deadline: `from_ifc.convert` checks the clock between elements. So the
honest claim is bounded:

* a conversion that overruns because there is a lot to do **is refused** — asserted behaviourally;
* a conversion given room **still succeeds** — asserted, because a deadline that always fires is a
  converter that never converts, and that mutation passes the first check alone;
* a single element whose `create_shape` never returns is **still unbounded** — asserted only as
  prose here, because no in-process check can demonstrate the absence of a mechanism that does not
  exist. That is the residue DESKTOP-CONVERT-TIMEOUT stays open for.

*A partial fix asserted as a whole one is the shape of the defect this gate exists to close*, so the
docstring of `convert_ifc` and this file say the same bounded thing.

Run: `PYTHONPATH=src:../data/src python test_fragconvert_timeout.py`
"""
from __future__ import annotations

import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, "src")
sys.path.insert(0, "../data/src")

FAILED: list[str] = []


def check(label: str, ok: bool, detail: object = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   -- {detail}" if not ok and detail else ""))
    if not ok:
        FAILED.append(label)


from aec_data import edit, massing  # noqa: E402
from aec_data.fragments.from_ifc import convert  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

_TMP = tempfile.mkdtemp(prefix="fragtimeout_")
IFC = Path(_TMP) / "model.ifc"

#: Enough products that the geometry loop is entered several times -- a one-element model would
#: reach the first checkpoint and finish, so the deadline could be asserted on a population of one
#: and prove nothing about the loop.
massing.generate_blank_ifc(str(IFC), name="TimeoutGate", storeys=2, storey_height=3.0,
                           ground_size=20.0)
_m = open_model(str(IFC))
_st = _m.by_type("IfcBuildingStorey")[0].Name
edit.add_spaces(_m, rooms_per_storey=3, ceiling_height=3.0)
for _i in range(6):
    edit.add_wall(_m, [0, float(_i)], [8, float(_i)], 3.0, 0.2, _st)
_m.write(str(IFC))

_t0 = time.monotonic()
_ok = convert(str(IFC))
_baseline = time.monotonic() - _t0
check("the fixture converts at all, with geometry -- otherwise every timing below is measuring an "
      "empty loop",
      bool(_ok.data) and not _ok.failed, f"failed={_ok.failed}")
print(f"  baseline conversion: {_baseline * 1000:.0f} ms")

# --- 1. A DEADLINE ALREADY PAST IS REFUSED --------------------------------------------------------
#: `monotonic() - 1` rather than a short positive budget: a budget racing the machine is a flaky
#: test on a slow runner, and the question here is whether the clock is CONSULTED, which a deadline
#: in the past answers deterministically. The timing assertion below is what says it is consulted
#: EARLY rather than after all the work.
_t0 = time.monotonic()
_raised: BaseException | None = None
try:
    convert(str(IFC), deadline=time.monotonic() - 1)
except BaseException as e:                      # noqa: BLE001 -- the type is the assertion below
    _raised = e
_elapsed = time.monotonic() - _t0
check("a deadline already past raises TimeoutError rather than converting anyway",
      isinstance(_raised, TimeoutError),
      f"raised {type(_raised).__name__ if _raised else 'nothing'} — "
      f"`edit_preview` turns any exception into its 503, but a caller that wants to tell 'too slow' "
      f"from 'broken' cannot, and `subprocess.TimeoutExpired` is NOT a TimeoutError")
#: THE STAGE IS ASSERTED, NOT JUST THE TYPE, and this is what makes the check about WHERE the
#: checkpoints are rather than whether one exists somewhere. A deadline already past must be caught
#: at the FIRST one — right after the parse, before a single `create_shape`. Deleting the parse and
#: geometry checkpoints leaves the one in the entity-index loop, which still raises `TimeoutError`
#: and still says "deadline": a check accepting any stage passes that mutation while the converter
#: does all the work and complains afterwards. *Measured: that mutation passed the first draft of
#: this file.*
check("  ...and it stops at the FIRST checkpoint, before any geometry is built",
      isinstance(_raised, TimeoutError) and "deadline" in str(_raised) and "parse" in str(_raised),
      f"message: {_raised!s:.200} — expected the `parse` stage; another stage means the earliest "
      f"checkpoint is later than the parse and the work before it is unbounded")
#: A TIMING ASSERTION WAS TRIED HERE AND REMOVED. `elapsed < max(0.25, baseline * 0.9)` against a
#: 33 ms fixture is satisfied by doing the whole conversion, so it passed the same mutation: a
#: threshold generous enough not to flake on a slow runner is generous enough to measure nothing.
#: The stage name answers the same question deterministically and on any machine.

# --- 1b. AND THE GEOMETRY LOOP HAS ITS OWN CHECKPOINT ---------------------------------------------
#: Crossing the deadline DURING the loop, not before it, which the check above cannot reach. The
#: `progress` hook is made slow on purpose so the crossing is deterministic rather than a race with
#: the machine: ~50 ms per element against a ~150 ms budget stops a few products in, on any runner.
_seen: list[float] = []


def _slow(fraction: float) -> None:
    """Burn time inside the loop so a mid-loop deadline is reached by arithmetic, not by luck."""
    _seen.append(fraction)
    time.sleep(0.05)


_mid: BaseException | None = None
try:
    convert(str(IFC), progress=_slow, deadline=time.monotonic() + 0.15)
except BaseException as e:                      # noqa: BLE001
    _mid = e
check("a deadline crossed DURING the geometry loop stops the loop, naming that stage",
      isinstance(_mid, TimeoutError) and "geometry" in str(_mid),
      f"raised {type(_mid).__name__ if _mid else 'nothing'}: {_mid!s:.200}")
check("  ...and it stopped PARTWAY -- a checkpoint reached only after the last element is a "
      "checkpoint that bounds nothing",
      isinstance(_mid, TimeoutError) and 0 < len(_seen) < 12,
      f"the progress hook saw {len(_seen)} of the model's products before stopping")

# --- 2. AND IT IS NOT ALWAYS-RAISE ----------------------------------------------------------------
#: The positive control, and it is not optional: "raise when the deadline passed" and "raise" are
#: the same code until something proves otherwise, and the second is a converter that has stopped
#: converting. The mutation that deletes the `> deadline` comparison passes check 1 and fails here.
#: Compared STRUCTURALLY, not byte-for-byte. `metadata` embeds `"created": datetime.now(...)`, so
#: two conversions of one file are never identical bytes — the first draft of this check asserted
#: equality and failed on a correct converter, reporting "3137 bytes vs 3137". *An assertion that
#: fails on correct code is the same defect as one that passes on broken code, and costs a round.*
from aec_data.fragments import loads  # noqa: E402


def _shape(result):
    """What a conversion IS, minus the clock: meshes, their sizes, and the entity index."""
    m = loads(result.data)
    return (len(m.meshes), [(len(x.points), len(x.profiles)) for x in m.meshes],
            list(m.guids), list(m.guids_items), m.coordinates)


#: Caught rather than allowed to propagate: the always-raise mutation makes this call throw, and an
#: uncaught traceback exits non-zero without naming which contract broke. *A gate that dies is a
#: gate whose message is a stack trace.*
try:
    _far = convert(str(IFC), deadline=time.monotonic() + 600)
    _far_shape, _far_err = _shape(_far), None
except BaseException as e:                      # noqa: BLE001
    _far_shape, _far_err = None, e
check("a deadline with room still converts, to the same MODEL as no deadline at all",
      _far_err is None and _far_shape == _shape(_ok),
      f"raised {type(_far_err).__name__}: {_far_err!s:.120}" if _far_err else
      f"{_far_shape[0] if _far_shape else '?'} meshes vs {_shape(_ok)[0]} — a checkpoint must not "
      f"change the output")
check("...and `deadline=None` is the unbounded default, so existing callers are untouched",
      _shape(convert(str(IFC))) == _shape(_ok),
      "the default path changed behaviour")

# --- 3. THE ROUTE'S CONTRACT ----------------------------------------------------------------------
#: `convert_ifc` is what `edit_preview` calls, and the asymmetry lived THERE rather than in the
#: converter: the parameter was accepted and then reached only one of the two branches. Asserting on
#: `from_ifc.convert` alone would leave the wiring untested, which is how the original gap survived
#: a file whose docstring described it.
import aec_api.fragconvert as fc  # noqa: E402

_src = Path(_TMP) / "wire.ifc"
massing.generate_blank_ifc(str(_src), name="WireGate", storeys=1, storey_height=3.0, ground_size=8.0)
_dst = Path(_TMP) / "wire.frag"

_real_have = fc.have_converter
fc.have_converter = lambda: False               # force the PYTHON branch regardless of this host
try:
    _wired: BaseException | None = None
    try:
        fc.convert_ifc(_src, _dst, timeout=0)
    except BaseException as e:                  # noqa: BLE001
        _wired = e
    check("convert_ifc PASSES the budget to the Python path -- the parameter reaching only the Node "
          "branch is the whole defect, and the converter's own check cannot detect that",
          isinstance(_wired, TimeoutError),
          f"raised {type(_wired).__name__ if _wired else 'nothing'} with timeout=0")
    check("  ...and a generous budget on the same branch still writes the fragment",
          fc.convert_ifc(_src, _dst, timeout=600) == fc.PYTHON and _dst.stat().st_size > 0,
          "the Python branch stopped producing output")
finally:
    fc.have_converter = _real_have

print()
print("test_fragconvert_timeout " + ("FAILED - " + str(len(FAILED)) if FAILED else "OK"))
for f in FAILED:
    print("  - " + f)
sys.exit(1 if FAILED else 0)
