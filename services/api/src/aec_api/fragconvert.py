"""Which IFC->Fragments converter this install can use — asked and answered ONCE.

There are two, and they are not interchangeable in availability:

* **Node** (`services/converter/src/cli.mjs`), which uses the same `@thatopen/fragments` importer and
  web-ifc WASM as the browser. Present in a source checkout and in the API container image.
* **Python** (`aec_data.fragments`), which tessellates with IfcOpenShell. Present wherever the
  backend runs, including the packaged desktop app.

**The desktop app has no Node runtime**, so before this existed `GET /projects/{pid}/model.frag` was
404 forever there: the branch that converts was skipped by its own `.exists()` guard and publish
reported success with `"reconverted": false` (DESKTOP-FRAGMENTS). The API image is unaffected — it
copies `node` and the converter in — which is why this never showed up in the deployed product.

**Node stays the default where it exists, deliberately.** It is the same code path the browser
runs, so a model converted server-side and a model converted in a future browser-side path agree by
construction. Python is the fallback that makes the desktop app work at all, and
`services/api/test_fragments_python.py` measures the two against each other rather than assuming
they agree: same elements, same entity index, same up-axis, and the reference reader accepts both.
"""
from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from pathlib import Path

from . import fragconvert_child
from .apppaths import add_data_src_to_path, converter_cli, have_converter

_log = logging.getLogger("aec.fragconvert")

#: Which converter a given call used, for the caller to report rather than guess.
NODE = "node"
PYTHON = "python"


def available() -> bool:
    """Can this install convert IFC to Fragments at all? True wherever the backend runs.

    Kept distinct from `apppaths.have_converter`, which answers the narrower question "is the NODE
    converter present" and is still the right question for the RVT bridge, which has no Python path.
    """
    return True


def convert_ifc(src: str | Path, dst: str | Path, *, timeout: int = 600) -> str:
    """Convert `src` (.ifc) to `dst` (.frag). Returns which converter ran: `NODE` or `PYTHON`.

    **`timeout` binds BOTH paths now, by different mechanisms and to different depths.** Node gets a
    real one: `subprocess.run` kills a child that overruns. The Python path calls IfcOpenShell in the
    caller's own process, where nothing can interrupt it from outside, so it gets a COOPERATIVE
    deadline instead — `from_ifc.convert` checks the clock between elements and raises.

    *It is enforced at phase boundaries and within the two loops — which is narrower than "the
    parameter is honoured", and the difference is worth stating.* The per-element and per-entity
    loops are bounded, so a model that overran because it had a lot in it is refused. **Two costs
    sit outside every checkpoint**: `ifcopenshell.open`, one call whose time scales with file size
    and which is therefore paid in full before the first check; and any single `create_shape` that
    never returns, after which the loop never reaches the next check. Both need the killable child
    process DESKTOP-CONVERT-TIMEOUT is filed for, and the entry stays open for them.
    **Deliberately not marked closed on the strength of the narrower fix**, because "the parameter
    is honoured" is exactly the reading that made the old asymmetry invisible.

    **Both paths raise `TimeoutError`.** Node's own is `subprocess.TimeoutExpired`, which is a
    `SubprocessError` and not a `TimeoutError`, so a caller distinguishing "too slow" from "broke"
    would have had to know which converter ran — a fact this function exists to hide. Nothing caught
    the old type (checked across the tree); `aec_data.sandbox` already raises `TimeoutError` for a
    budget overrun, so this is the house spelling rather than a new one.

    Raises on failure. It does NOT promise `dst` is untouched afterwards: the Node path streams and
    can leave a truncated file behind, and only the Python path writes in one go. So a raise means
    "do not use `dst`", not "`dst` does not exist" — both callers convert into a temporary directory
    and publish only on success, which is what actually keeps a truncated `.frag` out of storage. A
    truncated one fails in a viewer with no clue where it came from.
    """
    src, dst = str(src), str(dst)
    if have_converter():
        try:
            subprocess.run(["node", str(converter_cli()), src, dst],
                           check=True, capture_output=True, timeout=timeout)
        except subprocess.TimeoutExpired as e:
            raise TimeoutError(f"IFC->Fragments conversion exceeded {timeout}s (node)") from e
        return NODE
    #: The budget starts when THIS FUNCTION is entered, which is the same instant the Node path's
    #: `subprocess.run(timeout=...)` starts its own — so the two branches measure the same interval,
    #: which is the point of computing it here rather than handing the duration down.
    #:
    #: **What it does NOT cover: anything the caller did first.** `edit_preview` authors a
    #: one-element IFC before it calls this, and that time is outside the budget. A first draft of
    #: this comment claimed the opposite — that computing the deadline here is what stops the
    #: authoring being "free" — which is wrong: `monotonic()` is read below, after the caller has
    #: already done that work, so handing the duration down instead would differ only by the import
    #: on the line above. Raised in review. *This change exists to state timeout scope accurately,
    #: which makes a wrong scope claim in its own rationale the worst place to leave one.*
    _py_convert_in_child(src, dst, timeout=timeout)
    return PYTHON


#: Grace the child gets to hit its own cooperative deadline before the parent kills it. The child is
#: given the caller's FULL budget, so in the ordinary overrun it raises `TimeoutError` at `timeout`
#: and names which phase it was in; the kill exists for the two costs no checkpoint can see. That
#: makes the outer bound `timeout + _KILL_GRACE_S` rather than `timeout` -- stated here because the
#: alternative, shortening the child's deadline to keep the bound at exactly `timeout`, would change
#: when the cooperative error fires and make the two branches disagree about what the parameter
#: means. *A backstop that pre-empts the thing it backs up is not a backstop.*
_KILL_GRACE_S = 5


def _child_argv() -> list[str]:
    """How to re-enter this program as the converter child, frozen or not.

    **`sys.executable` is the bundle when frozen**, so `-m` is meaningless there -- PyInstaller does
    not ship a module runner. `desktop_entry.py` dispatches on the sentinel before it imports the
    server, which is what makes the same executable serve as both. Unfrozen, `sys.executable` is the
    interpreter and `-m` works normally.
    """
    if getattr(sys, "frozen", False):
        return [sys.executable, fragconvert_child.SENTINEL]
    return [sys.executable, "-m", "aec_api.fragconvert_child"]


def _py_convert_in_child(src: str, dst: str, *, timeout: int) -> None:
    """Run the Python converter in a killable child. Raises `TimeoutError` if it overran.

    **There is no in-process fallback, deliberately.** Falling back would mean that whenever
    spawning failed -- a reason nobody would see, since it is not an error anyone reports -- the
    conversion would silently go back to being uninterruptible, which is the exact defect this
    exists to remove. It is the same shape as the advisory-lock degrade that nearly shipped in #575:
    a safety mechanism that quietly turns itself off is worse than one that was never there, because
    the reader believes it is on.
    """
    #: The child must import the SAME code this process did. `services/api` and `services/data/src`
    #: are on `sys.path` here through `add_data_src_to_path()` and the launcher, neither of which a
    #: bare child inherits -- `PYTHONPATH` is how a subprocess gets told.
    add_data_src_to_path()
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(p for p in sys.path if p)
    env["PYTHONUTF8"] = "1"

    try:
        proc = subprocess.run([*_child_argv(), src, dst, str(timeout)],
                              capture_output=True, timeout=timeout + _KILL_GRACE_S, env=env)
    except subprocess.TimeoutExpired as e:
        raise TimeoutError(
            f"IFC->Fragments conversion exceeded {timeout}s and was killed (python); it did not "
            f"reach its own deadline check, so it was inside `ifcopenshell.open` or a single "
            f"`create_shape`") from e

    if proc.returncode == 2:                           # the child's own cooperative deadline
        raise TimeoutError(f"IFC->Fragments conversion exceeded {timeout}s (python)")
    if proc.returncode != 0:
        raise RuntimeError(
            f"IFC->Fragments conversion failed (python, rc={proc.returncode}): "
            f"{proc.stderr.decode('utf-8', 'replace')[-2000:]}")

    try:
        report = json.loads(proc.stdout.decode("utf-8", "replace").strip().splitlines()[-1])
    except (ValueError, IndexError):
        report = {}
    failed, total = report.get("failed") or [], report.get("failed_total", 0)
    if total:
        # Named, not swallowed: geometry IfcOpenShell could not build is a fact about the model that
        # a user can act on, and a converter that quietly returns fewer elements is the failure mode
        # this codebase keeps finding.
        _log.warning("python fragment conversion: %d element(s) had unbuildable geometry: %s",
                     total, ", ".join(failed[:10]))
