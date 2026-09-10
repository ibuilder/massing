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

    Raises on failure. It does NOT promise `dst` is untouched afterwards: the Node path streams and
    can leave a truncated file behind, and only the Python path writes in one go. So a raise means
    "do not use `dst`", not "`dst` does not exist" — both callers convert into a temporary directory
    and publish only on success, which is what actually keeps a truncated `.frag` out of storage. A
    truncated one fails in a viewer with no clue where it came from.
    """
    src, dst = str(src), str(dst)
    if have_converter():
        subprocess.run(["node", str(converter_cli()), src, dst],
                       check=True, capture_output=True, timeout=timeout)
        return NODE
    add_data_src_to_path()
    from aec_data.fragments.from_ifc import convert as _py_convert  # type: ignore

    result = _py_convert(src)
    if result.failed:
        # Named, not swallowed: geometry IfcOpenShell could not build is a fact about the model that
        # a user can act on, and a converter that quietly returns fewer elements is the failure mode
        # this codebase keeps finding.
        _log.warning("python fragment conversion: %d element(s) had unbuildable geometry: %s",
                     len(result.failed), ", ".join(result.failed[:10]))
    Path(dst).write_bytes(result.data)
    return PYTHON
