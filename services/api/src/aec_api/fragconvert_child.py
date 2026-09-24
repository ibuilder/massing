"""The Python IFC->Fragments conversion, run in a CHILD PROCESS so it can be KILLED.

`from_ifc.convert` honours a COOPERATIVE deadline -- it checks the clock between elements and every
4,096 entities. That bounds a model that overran because it had a lot in it, and it cannot bound the
two costs that sit outside every checkpoint: `ifcopenshell.open`, one call whose time scales with
file size and which is paid in full before the first check, and any single `create_shape` that never
returns, after which the loop never reaches the next one. Nothing inside the process can interrupt
either. A separate process can be killed.

**Why an argv sentinel and not `multiprocessing`.** The desktop app is a PyInstaller bundle, where
`multiprocessing` spawn re-execs the frozen executable and needs `freeze_support()` wired at the
entry point; DESKTOP-CONVERT-TIMEOUT was filed on the strength of that being net-new machinery for a
frozen app with no pattern here to copy. It is avoidable. `desktop_entry.py` -- the `Analysis`
script for BOTH `sidecar.spec` and `desktop.spec` -- is a three-line launcher, so it can branch on
`sys.argv[1]` BEFORE importing the server and hand off to this module. `sys.executable` then means
"the bundle" when frozen and "the interpreter" when not, and one mechanism covers both.

Talks to its parent over argv and stdout only: no shared state, nothing to clean up if it is killed
mid-write. It writes the `.frag` itself rather than piping bytes back, because a model is tens of
megabytes and a pipe the parent is not draining while it waits would deadlock.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

#: The argv[0]-after-the-program marker `desktop_entry.py` dispatches on. Spelled once, imported by
#: both sides and by the gate, so the two can never drift apart silently -- which is the failure a
#: string repeated in three files invites.
SENTINEL = "--ifc-convert-child"


def main(argv: list[str]) -> int:
    """`argv` is `[src, dst, budget_seconds]`. Writes `dst`; prints one JSON line on stdout.

    Returns 0 on success, 2 on a cooperative timeout, 1 on anything else. The parent distinguishes
    "this converter gave up" from "this converter broke" by that code rather than by parsing text.
    """
    src, dst, budget = argv[0], argv[1], float(argv[2])

    from .apppaths import add_data_src_to_path
    add_data_src_to_path()
    from aec_data.fragments.from_ifc import convert  # type: ignore

    try:
        result = convert(src, deadline=time.monotonic() + budget)
    except TimeoutError as e:
        print(json.dumps({"timeout": str(e)}), flush=True)
        return 2
    Path(dst).write_bytes(result.data)
    #: `failed` is capped: it is one GlobalId per element IfcOpenShell refused, and a thoroughly
    #: broken model can name thousands. The parent logs the first ten either way, and an unbounded
    #: line here would be a second way for a bad model to become a resource problem.
    print(json.dumps({"failed": result.failed[:500], "failed_total": len(result.failed),
                      "elements": result.elements, "meshes": result.meshes}), flush=True)
    return 0


if __name__ == "__main__":                             # `python -m aec_api.fragconvert_child`
    raise SystemExit(main(sys.argv[1:]))
