"""PyInstaller entry point for the free single-project desktop .exe.

Thin launcher so the spec has a stable script to analyze; all logic lives in
aec_api.desktop (SQLite + local mode + serves the bundled SPA on 127.0.0.1:8765).

It also serves as the re-entry point for the IFC->Fragments converter CHILD PROCESS. The Python
converter runs IfcOpenShell in-process, where a parse or a single `create_shape` cannot be
interrupted; running it in a child makes it killable, which is the whole of DESKTOP-CONVERT-TIMEOUT.
`sys.executable` is this bundle when frozen, so the child is THIS program re-run with a sentinel.

**The branch is before the `aec_api.desktop` import on purpose, and that is load-bearing rather than
tidy.** Importing it pulls in FastAPI, the router tree and the module catalog, and would start a
server in a process whose only job is to convert one file. Keep the sentinel check first.

Using an argv sentinel rather than `multiprocessing` is what avoids `freeze_support()`: spawn would
re-exec this same frozen executable and need the guard wired, which is the net-new machinery the
roadmap entry was blocked on.
"""
import sys

from aec_api.fragconvert_child import SENTINEL

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == SENTINEL:
        from aec_api.fragconvert_child import main
        raise SystemExit(main(sys.argv[2:]))

    from aec_api.desktop import main as _serve
    _serve()
