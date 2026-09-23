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

import logging
import subprocess
import time
from pathlib import Path

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
    add_data_src_to_path()
    from aec_data.fragments.from_ifc import convert as _py_convert  # type: ignore

    #: The deadline is computed HERE, from the caller's `timeout`, rather than passing the duration
    #: down: the callee would then restart the clock, and the time already spent authoring the source
    #: IFC before this call would be free. `edit_preview` builds a one-element model first.
    result = _py_convert(src, deadline=time.monotonic() + timeout)
    if result.failed:
        # Named, not swallowed: geometry IfcOpenShell could not build is a fact about the model that
        # a user can act on, and a converter that quietly returns fewer elements is the failure mode
        # this codebase keeps finding.
        _log.warning("python fragment conversion: %d element(s) had unbuildable geometry: %s",
                     len(result.failed), ", ".join(result.failed[:10]))
    Path(dst).write_bytes(result.data)
    return PYTHON
