"""glTF class colours must be the same in every process — the defect an in-process test cannot see.

`_class_colour` used `hash(cls)`. PEP 456 salts string hashing per process, so the same model exported
twice got **different colours per class** and any visual diff between two exports was meaningless. The
docstring asserted *stable*, *deterministic* and *"so exports colour the same"*, which is why nobody
checked: the comment claimed the property the code lacked.

Measured before the fix, `IfcWall` across three runs: green, magenta, green-cyan.

**Why this suite spawns a subprocess.** Within one interpreter `hash()` is perfectly consistent, so an
ordinary same-process assertion passes on the broken code. The bug lives entirely in the gap between
processes, and a test that cannot cross that gap is structurally unable to see it — which is how this
survived. Found by the Massing Security session while auditing every `hash()` in the tree after the
same defect class turned up in `pid_lock`.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_export_colour_stable.py
"""
import subprocess
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "../data/src")

from aec_data.gltf_export import _class_colour  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


CLASSES = ["IfcWall", "IfcSlab", "IfcColumn", "IfcBeam", "IfcReinforcingBar", "IfcDoor"]
here = {c: _class_colour(c) for c in CLASSES}

# --- 1. THE CROSS-PROCESS ASSERTION — the only one that can see the bug ---------------------------
prog = (
    "import sys,json; sys.path.insert(0,'src'); sys.path.insert(0,'../data/src')\n"
    "from aec_data.gltf_export import _class_colour\n"
    f"print(json.dumps({{c: _class_colour(c) for c in {CLASSES!r}}}))\n"
)
out = subprocess.run([sys.executable, "-c", prog], capture_output=True, text=True, timeout=120)
check("a separate process produced colours at all", out.returncode == 0, out.stderr[-200:])

import json  # noqa: E402

other = json.loads(out.stdout) if out.returncode == 0 else {}
check("EVERY class gets the same colour in another process", other == here,
      {c: (here[c], other.get(c)) for c in CLASSES if other.get(c) != here[c]})

# The control: prove `hash()` really would have differed, so the assertion above is not vacuous. If
# PYTHONHASHSEED is pinned in this environment the whole suite is meaningless and should say so.
h = subprocess.run([sys.executable, "-c", "print(hash('IfcWall'))"],
                   capture_output=True, text=True, timeout=60).stdout.strip()
check("(control) hash('IfcWall') DOES differ across processes — so the check above is meaningful",
      h != str(hash("IfcWall")),
      f"{h} == {hash('IfcWall')}: PYTHONHASHSEED is pinned, so this suite proves nothing")

# --- 2. the colours are still usable ----------------------------------------------------------------
check("every colour is RGBA in range with an opaque alpha",
      all(len(v) == 4 and all(0.0 <= x <= 1.0 for x in v) and v[3] == 1.0 for v in here.values()),
      here)
check("different classes get different colours — a single hue for everything is not a scheme",
      len({tuple(v) for v in here.values()}) >= len(CLASSES) - 1,
      {c: tuple(v) for c, v in here.items()})
check("the same class twice in one process is identical", _class_colour("IfcWall") == here["IfcWall"])
check("an unknown class still gets a colour rather than raising",
      len(_class_colour("IfcSomethingNobodyHasHeardOf")) == 4)

print()
if FAILED:
    print(f"export_colour_stable: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("export_colour_stable: all checks passed")
