"""DESKTOP-CONVERT-KILL — the Python converter runs in a child process that can be KILLED.

`from_ifc.convert`'s deadline is COOPERATIVE: it is checked between elements and every 4,096
entities, which bounds a model that overran because it had a lot in it. Two costs sit outside every
checkpoint and no in-process mechanism can reach them -- `ifcopenshell.open`, one call whose time
scales with file size and which is paid in full before the first check, and any single
`create_shape` that never returns. DESKTOP-CONVERT-TIMEOUT stayed open for exactly those two.

**The filed blocker did not hold, and that is worth recording rather than quietly routing around.**
The entry said process isolation needed `multiprocessing`, which under PyInstaller re-execs the
frozen executable unless `freeze_support()` is wired -- net-new machinery for a frozen app with no
pattern in this tree to copy. But `desktop_entry.py` is a three-line launcher and is the `Analysis`
script for BOTH `sidecar.spec` and `desktop.spec`, so an argv sentinel re-entering `sys.executable`
serves frozen and unfrozen alike and needs no `multiprocessing` at all. *A blocker recorded as a
property of the platform turned out to be a property of one approach to it.*

**The hang arms use a stub child that SELF-EXITS.** A stub that slept for ever would turn the
mutation "drop `timeout=` from `subprocess.run`" into a HANG rather than a failure, and a hang is
reported as nothing -- the run just stops. Learned the same way in `test_fragconvert_timeout.py`
section 4. Make a check FAIL; do not settle for it not passing.
"""
from __future__ import annotations

import ast
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, "src")
sys.path.insert(0, os.path.join("..", "data", "src"))

_fails = 0


def check(label: str, ok: bool, detail: str = "") -> None:
    global _fails
    print(("PASS  " if ok else "FAIL  ") + label + ("" if ok else f"   -- {detail}"))
    if not ok:
        _fails += 1


import aec_api.fragconvert as fc  # noqa: E402
from aec_api.fragconvert_child import SENTINEL  # noqa: E402

# --- 1. THE FROZEN ENTRY POINT DISPATCHES BEFORE IT BOOTS A SERVER --------------------------------
#: `sys.executable` is the BUNDLE when frozen, so the child is this same program re-run. If the
#: sentinel branch sat after `from aec_api.desktop import main`, every conversion would import
#: FastAPI, the router tree and the module catalog into a process whose only job is one file -- and
#: on a `main()` that starts serving, the child would never return at all. Ordering is the contract.
_ENTRY = Path("desktop_entry.py")
_tree = ast.parse(_ENTRY.read_text(encoding="utf-8"))


def _first_desktop_import_line(tree: ast.AST) -> int | None:
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith("aec_api.desktop"):
            return node.lineno
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.startswith("aec_api.desktop"):
                    return node.lineno
    return None


def _sentinel_compare_line(tree: ast.AST) -> int | None:
    """Where the entry point tests argv against the sentinel -- by NAME, not by string literal.

    Matching the literal `"--ifc-convert-child"` here would pass on an entry point that had drifted
    to its own hardcoded copy while `fragconvert_child.SENTINEL` said something else -- the two
    processes would then never meet, and this check would call that correct.
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Compare) and any(
                isinstance(c, ast.Name) and c.id == "SENTINEL" for c in node.comparators):
            return node.lineno
    return None


#: And it must get that name FROM `fragconvert_child`, not define its own. Checking the comparison
#: alone would pass on an entry point that had `SENTINEL = "--convert"` at the top of its own file:
#: the name matches, the value does not, and the parent would spawn a child that never dispatches.
_imports_sentinel = any(
    isinstance(n, ast.ImportFrom) and (n.module or "").endswith("fragconvert_child")
    and any(a.name == "SENTINEL" for a in n.names) for n in ast.walk(_tree))
check("the entry point imports the sentinel from fragconvert_child rather than redefining it",
      _imports_sentinel and SENTINEL.startswith("--"),
      f"desktop_entry.py does not import SENTINEL from fragconvert_child (sentinel is {SENTINEL!r})")

_dispatch, _boot = _sentinel_compare_line(_tree), _first_desktop_import_line(_tree)
check("the frozen entry point tests argv against the SHARED sentinel name",
      _dispatch is not None,
      "desktop_entry.py does not compare anything to `SENTINEL`; a hardcoded copy of the string "
      "would let the two sides drift apart with nothing to notice")
check("  ...and it does so BEFORE importing aec_api.desktop",
      _dispatch is not None and _boot is not None and _dispatch < _boot,
      f"sentinel compared at line {_dispatch}, aec_api.desktop imported at line {_boot} -- a "
      f"converter child would boot the whole server, and on a serving main() never return")

#: Both PyInstaller specs must analyse THAT file, or the sentinel exists in a launcher the shipped
#: binary does not use. Derived from the specs rather than asserted about "the entry point".
for _spec in ("desktop.spec", "sidecar.spec"):
    _txt = Path(_spec).read_text(encoding="utf-8")
    check(f"  ...and {_spec} builds from desktop_entry.py, so the sentinel is in the shipped binary",
          '["desktop_entry.py"]' in _txt.replace("'", '"'),
          f"{_spec} analyses a different script; the dispatch above would not be in that bundle")

# --- 2. NO IN-PROCESS FALLBACK --------------------------------------------------------------------
#: A fallback would mean that whenever spawning failed -- for a reason nobody reports, since it is
#: not an error anyone looks for -- the conversion silently returned to being uninterruptible. Same
#: shape as the advisory-lock degrade that nearly shipped in #575: a safety mechanism that turns
#: itself off is worse than one that was never there, because the reader believes it is on.
_SRC = Path("src/aec_api/fragconvert.py").read_text(encoding="utf-8")
_code = "\n".join(
    ln for ln in _SRC.splitlines() if not ln.lstrip().startswith(("#", "#:")))
check("`convert_ifc` does not call the converter in this process any more",
      "from aec_data.fragments.from_ifc import convert" not in _code,
      "fragconvert.py still imports the converter directly -- if that call is reachable, the "
      "uninterruptible path is still live and nothing here would say so")
check("  ...and the child is spawned with a timeout",
      "subprocess.run(" in _code and "timeout=timeout + _KILL_GRACE_S" in _code,
      "the spawn has no timeout= -- the child could not be killed, which is the whole item")

# --- 3. BEHAVIOURAL: it still converts, and a hang is now KILLED -----------------------------------
_TMP = tempfile.mkdtemp(prefix="killgate_")
from aec_data import massing  # noqa: E402

_src, _dst = Path(_TMP) / "k.ifc", Path(_TMP) / "k.frag"
massing.generate_blank_ifc(str(_src), name="KillGate", storeys=1, storey_height=3.0, ground_size=8.0)

_real_have = fc.have_converter
fc.have_converter = lambda: False                  # force the PYTHON branch regardless of this host
try:
    check("the Python path still converts, through a child process",
          fc.convert_ifc(_src, _dst, timeout=600) == fc.PYTHON and _dst.stat().st_size > 0,
          "the child produced no fragment")

    _coop: BaseException | None = None
    try:
        fc.convert_ifc(_src, _dst, timeout=0)
    except BaseException as e:                     # noqa: BLE001
        _coop = e
    check("  ...and the child's own COOPERATIVE deadline still refuses, as TimeoutError",
          isinstance(_coop, TimeoutError) and "killed" not in str(_coop),
          f"raised {type(_coop).__name__ if _coop else 'nothing'}: {_coop!s:.80} -- the ordinary "
          f"overrun should come back from the child's checkpoint, not from the kill")
finally:
    fc.have_converter = _real_have

#: THE ARM THIS ITEM EXISTS FOR. A child that never reaches a checkpoint -- the parse, or one
#: `create_shape` -- is killed by the parent. `_HANG_S` is far longer than the budget, and the stub
#: EXITS BY ITSELF so that removing `timeout=` makes this FAIL rather than hang.
#: The stub takes its sleep from argv so the two arms can ask for different ones. `_HANG_S` has to
#: be far clear of the 2 s budget plus the 5 s grace, or "killed at ~7 s" stops being
#: distinguishable from "the stub finished on its own" on a loaded runner -- and the arm would then
#: pass for the wrong reason. The self-exit probe below needs no such margin: it is asking whether
#: `sleep(x); sys.exit(0)` returns at all, which is true of every x. Review asked for `_HANG_S`
#: itself to be shortened; that would have bought the same ~25 s back by NARROWING the margin the
#: kill arm depends on, so the sleep is parameterised instead. *Make the cheap check cheap without
#: making the expensive one weaker.*
_HANG_S = 25
_hang = Path(_TMP) / "hangs.py"
_hang.write_text("import sys, time\ntime.sleep(float(sys.argv[1]))\nsys.exit(0)\n", encoding="utf-8")
_real_argv = fc._child_argv
fc._child_argv = lambda: [sys.executable, str(_hang), str(_HANG_S)]
try:
    _t0 = time.monotonic()
    _killed: BaseException | None = None
    try:
        fc._py_convert_in_child(str(_src), str(_dst), timeout=2)
    except BaseException as e:                     # noqa: BLE001
        _killed = e
    _wall = time.monotonic() - _t0
    check("a child that reaches NO checkpoint is KILLED -- the parse and a hung create_shape",
          isinstance(_killed, TimeoutError) and "killed" in str(_killed),
          f"raised {type(_killed).__name__ if _killed else 'nothing'} after {_wall:.1f}s: "
          f"{_killed!s:.100}")
    check(f"  ...at roughly the budget plus its grace, not at the stub's {_HANG_S}s",
          _wall < fc._KILL_GRACE_S + 8,
          f"took {_wall:.1f}s, so it waited the hang out rather than killing it")
finally:
    fc._child_argv = _real_argv

#: The stub's self-exit is load-bearing, so prove it rather than trusting the comment: a stub that
#: outlived the assertion would make the arm above pass for the wrong reason on a slow runner.
_p = subprocess.run([sys.executable, str(_hang), "0.2"], timeout=60)
check("  ...and the hang stub does exit on its own, so the mutation FAILS rather than hanging",
      _p.returncode == 0,
      "the stub did not self-exit; dropping `timeout=` from the spawn would stop this file dead "
      "instead of reporting a failure, and a hang is reported as nothing")

print()
print("test_fragconvert_kill " + ("OK" if not _fails else f"FAILED - {_fails}"))
raise SystemExit(1 if _fails else 0)
