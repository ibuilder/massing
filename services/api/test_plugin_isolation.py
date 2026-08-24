"""SEC-PLUGIN-LOADER — third-party plugin code runs in a CHILD PROCESS, not the API's.

`plugin_registry` used to `exec_module` a plugin's entry in this interpreter and then call its
`register(api)`. Every check it makes — the manifest, the `api_version` major, the rollback — happens
*before* that line and constrains nothing the code then does. Import-time code had the API's DB
session, filesystem, network and environment.

**The load-bearing assertion here is process identity.** A plugin that records `os.getpid()` must
report a different pid from this one — everything else (timeouts, stripped environment, refusals) is
only meaningful if that holds, and a boundary that quietly ran in-process would satisfy every other
test in this file.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_plugin_isolation.py
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

os.environ["DATABASE_URL"] = "sqlite:///./test_plugin_isolation.db"
os.environ["STORAGE_DIR"] = "./test_storage_plugin_isolation"
os.environ["IFC_DIR"] = "./test_ifc_plugin_isolation"
os.environ["AEC_PLUGINS_ENABLED"] = "1"
if os.path.exists("./test_plugin_isolation.db"):
    os.remove("./test_plugin_isolation.db")

import sys  # noqa: E402

sys.path.insert(0, "src")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "data" / "src"))

FAILED: list[str] = []


def check(name: str, ok: bool, detail: object = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + (f"   {detail}" if detail and not ok else ""))
    if not ok:
        FAILED.append(name)


TMP = Path(tempfile.mkdtemp(prefix="aec-plugins-"))
os.environ["AEC_PLUGINS_DIR"] = str(TMP)


def plugin(name: str, body: str, api_version: str = "1.0") -> Path:
    d = TMP / name
    d.mkdir(parents=True, exist_ok=True)
    (d / "plugin.json").write_text(json.dumps(
        {"name": name, "version": "1.0.0", "api_version": api_version,
         "description": f"{name} test plugin", "entry": "plugin.py"}), encoding="utf-8")
    (d / "plugin.py").write_text(body, encoding="utf-8")
    return d


# --- a plugin that reports the pid it registered in, and the pid its recipe runs in ---------------
plugin("pidprobe", '''
import os, json, pathlib

WHERE = pathlib.Path(os.environ["AEC_PIDFILE"])

def _rec(model, params):
    WHERE.write_text(json.dumps({"run_pid": os.getpid()}))
    for proj in model.by_type("IfcProject"):
        proj.Name = params.get("mark") or "MUTATED-BY-PLUGIN"
    return {"ran": True, "pid": os.getpid()}

def register(api):
    prev = {}
    if WHERE.exists():
        prev = json.loads(WHERE.read_text() or "{}")
    prev["import_pid"] = os.getpid()
    WHERE.write_text(json.dumps(prev))
    api.register_recipe("probe", _rec, category="plugin")
''')

PIDFILE = TMP / "pids.json"
os.environ["AEC_PIDFILE"] = str(PIDFILE)

from aec_api import plugin_registry  # noqa: E402
from aec_data import edit, massing  # noqa: E402

plugin_registry.load_all()
st = plugin_registry.status()
check("the plugin loaded", any(p["name"] == "pidprobe" for p in st["loaded"]),
      json.dumps(st)[:220])
check("...and its recipe is in the shared registry under its namespace",
      "pidprobe.probe" in edit.RECIPES, [k for k in edit.RECIPES if k.startswith("pidprobe")])

pids = json.loads(PIDFILE.read_text() or "{}")
check("THE PLUGIN'S IMPORT RAN IN ANOTHER PROCESS", pids.get("import_pid") not in (None, os.getpid()),
      f"plugin import_pid={pids.get('import_pid')} api pid={os.getpid()}")

# --- and so does the RECIPE, which is the half that would be easy to leave behind -----------------
_m = massing.compute_massing({"lot_width": 20, "lot_depth": 12, "far": 1.0,
                              "floor_to_floor": 3.0, "height_limit": 9})
_src = TMP / "m.ifc"
massing.generate_ifc(_m, str(_src), name="Plugin probe")
_out = TMP / "m_out.ifc"
res = edit.apply_recipe(str(_src), "pidprobe.probe", {"mark": "MARK-1081"}, str(_out))
check("the recipe applied through the normal edit path", _out.exists(), str(res)[:160])
pids = json.loads(PIDFILE.read_text() or "{}")
check("THE RECIPE ALSO RAN IN ANOTHER PROCESS — not just registration",
      pids.get("run_pid") not in (None, os.getpid()),
      f"run_pid={pids.get('run_pid')} api pid={os.getpid()}")
check("  ...and it was a DIFFERENT child from the discovery one, so nothing is kept warm across the "
      "boundary", pids.get("run_pid") != pids.get("import_pid"),
      f"import={pids.get('import_pid')} run={pids.get('run_pid')}")

# --- THE EDIT REACHES THE FILE, which is the half a process boundary is most likely to lose ---------
# The child writes a model; the proxy reopens it and hands `(model, changed)` back. If the key is not
# in `edit.REPLACING_RECIPES` the driver treats that tuple as the change summary and saves the PRE-edit
# object — a green run, a plausible report, and the user's edit written nowhere. Asserting the return
# value cannot see that; only reading the written file can. The first plugin fixture in this repo only
# counted storeys, so it would have passed throughout.
import ifcopenshell  # noqa: E402

_written = ifcopenshell.open(str(_out))
check("THE PLUGIN'S MUTATION IS IN THE WRITTEN FILE, not just in its return value",
      any(pj.Name == "MARK-1081" for pj in _written.by_type("IfcProject")),
      [pj.Name for pj in _written.by_type("IfcProject")])
check("...and the registry marked the proxy as replacing, which is what makes that true",
      "pidprobe.probe" in edit.REPLACING_RECIPES, sorted(edit.REPLACING_RECIPES))

# --- reloading is idempotent, which the module docstring promises -------------------------------
# Worth asserting because the boundary changed how registration happens: the callables now come from
# a child, and a reload that failed to unregister first would refuse every plugin on its second pass
# with "already registered" — a working system that stops working the first time someone reloads.
plugin_registry.load_all()
st2 = plugin_registry.status()
check("a second load_all() re-registers cleanly rather than colliding with itself",
      any(p["name"] == "pidprobe" for p in st2["loaded"])
      and not [r for r in st2["refused"] if r["name"] == "pidprobe"],
      json.dumps(st2["refused"])[:200])

# --- the child cannot see the host's credentials ---------------------------------------------------
plugin("envprobe", '''
import os, json, pathlib

def _rec(model, params):
    return {"seen": {k: bool(os.environ.get(k)) for k in
                     ("DATABASE_URL", "STORAGE_DIR", "AEC_API_KEY")}}

def register(api):
    pathlib.Path(os.environ["AEC_ENVFILE"]).write_text(json.dumps(
        {k: bool(os.environ.get(k)) for k in ("DATABASE_URL", "STORAGE_DIR", "AEC_API_KEY",
                                              "AEC_PLUGIN_CHILD")}))
    api.register_recipe("env", _rec)
''')
ENVFILE = TMP / "env.json"
os.environ["AEC_ENVFILE"] = str(ENVFILE)
os.environ["AEC_API_KEY"] = "super-secret-key"
plugin_registry.load_all()
seen = json.loads(ENVFILE.read_text() or "{}")
check("the child cannot see DATABASE_URL", seen.get("DATABASE_URL") is False, seen)
check("...nor STORAGE_DIR", seen.get("STORAGE_DIR") is False, seen)
check("...nor the API key", seen.get("AEC_API_KEY") is False, seen)
check("...and it knows it is the child, so anything down there can tell",
      seen.get("AEC_PLUGIN_CHILD") is True, seen)

PROBE_SRC = "import sys\nsys.path.insert(0, 'src')\nsys.path.insert(0, r'C:\\Server\\modelmaker\\services\\data\\src')\nfrom aec_api import plugin_registry as pr\npr.load_all()\nrs = [r['reason'] for r in pr.status()['refused'] if r['name'] == 'stderrplug']\nwant = 'PLUGIN-SAID: ' + chr(233) + 'chafaudage'\nprint('VERDICT_OK' if rs and want in rs[0] else 'VERDICT_BAD ' + ascii(rs[0] if rs else None))"

# --- the DIAGNOSTIC path survives the pipe, which is the half that actually needs pinning --------
# The protocol itself is ASCII whatever the codepage is, because `json.dumps` escapes non-ASCII by
# default — a recipe named in Chinese round-trips with or without the encoding pin in
# `_child_env`. **An assertion on the protocol would therefore pass either way, and the first
# version of this check did exactly that: it was mutation-tested against a build with the pin
# removed and stayed green.** What is genuinely raw on the pipe is the stderr tail `_host` reports
# when the child produced no JSON at all — the path you are on precisely when something has gone
# wrong and the message is all you have.
#
# So this plugin writes UTF-8 BYTES to stderr and dies without printing JSON. Read as cp1252 those
# bytes decode to mojibake without raising, so the failure mode is a refusal that misdescribes the
# problem rather than a crash — the quiet kind.
plugin("stderrplug", '''
import os, sys

sys.stderr.buffer.write(("PLUGIN-SAID: " + chr(233) + "chafaudage").encode("utf-8"))
sys.stderr.buffer.flush()
os._exit(3)
''')
plugin_registry.load_all()
_sp = [r for r in plugin_registry.status()["refused"] if r["name"] == "stderrplug"]
check("a plugin that dies without printing JSON is refused, not fatal", bool(_sp),
      json.dumps(plugin_registry.status()["refused"])[:200])
# Asserted in a CHILD of this test, with `PYTHONUTF8` and `PYTHONIOENCODING` removed from its
# environment, and that indirection is the whole point. `run_tests.py` invokes the suite with
# `PYTHONUTF8=1`, which puts the PARENT in UTF-8 mode and makes `subprocess`'s text decoding correct
# whatever `_host` asks for — so asserting this inline passes with the pin deleted. Measured, not
# feared: mutation-tested both ways, inline stayed green with the pin removed and this did not.
# **A check that only discriminates under an invocation nobody uses is not a check.**
_probe_env = {k: v for k, v in os.environ.items() if k not in ("PYTHONUTF8", "PYTHONIOENCODING")}
_probe = subprocess.run(
    [sys.executable, "-c", PROBE_SRC], capture_output=True, text=True, encoding="utf-8",
    errors="replace", env=_probe_env, cwd=str(Path(__file__).resolve().parent), timeout=180)
check("THE REFUSAL QUOTES THE CHILD'S BYTES AS UTF-8, not as the ANSI codepage",
      "VERDICT_OK" in (_probe.stdout or ""),
      ((_probe.stdout or "") + (_probe.stderr or ""))[-160:])

# --- a plugin that explodes at IMPORT time is refused, and takes nothing with it -------------------
plugin("exploder", 'raise RuntimeError("boom at import time")\n')
plugin_registry.load_all()
st = plugin_registry.status()
check("a plugin that raises at import is REFUSED", any(r["name"] == "exploder" for r in st["refused"]),
      json.dumps(st["refused"])[:200])
check("  ...and the API process is still running to say so", True)
check("  ...and the healthy plugins still loaded alongside it",
      any(p["name"] == "pidprobe" for p in st["loaded"]), json.dumps(st["loaded"])[:160])

# --- a wall-clock cap, and it is real -------------------------------------------------------------
os.environ["AEC_PLUGIN_TIMEOUT_S"] = "2"
import importlib  # noqa: E402

importlib.reload(plugin_registry)
plugin("sleeper", 'import time\n\ndef register(api):\n    time.sleep(30)\n')
plugin_registry.load_all()
st = plugin_registry.status()
slept = [r for r in st["refused"] if r["name"] == "sleeper"]
check("a plugin that hangs at import is cut off by the wall-clock cap", bool(slept),
      json.dumps(st["refused"])[:200])
check("  ...and the refusal says it timed out rather than blaming something else",
      bool(slept) and "timed out" in slept[0]["reason"], slept[0]["reason"] if slept else "")

# --- unregistering drops the recipe from BOTH structures ------------------------------------------
# A key left in `REPLACING_RECIPES` after its recipe is gone is dormant rather than harmless: the next
# plugin to claim that name inherits a replacing contract it never asked for, and the mismatch shows up
# as a lost edit, not an error.
_ns = [k for k in edit.REPLACING_RECIPES if k.startswith("sleeper.")]
check("no orphan replacing-keys survive from refused or unloaded plugins", not _ns, _ns)
check("  ...and the ones for loaded plugins are still there", "pidprobe.probe" in edit.REPLACING_RECIPES,
      sorted(edit.REPLACING_RECIPES))

# --- the api_version gate still refuses BEFORE the entry is touched --------------------------------
plugin("oldapi", 'def register(api):\n    raise RuntimeError("should never be imported")\n',
       api_version="0.1")
plugin_registry.load_all()
st = plugin_registry.status()
old = [r for r in st["refused"] if r["name"] == "oldapi"]
check("an api_version mismatch is refused on the MANIFEST, without importing the entry",
      bool(old) and "api_version" in old[0]["reason"], old[0]["reason"] if old else "")

shutil.rmtree(TMP, ignore_errors=True)
for _f in ("./test_plugin_isolation.db",):
    if os.path.exists(_f):
        try:
            os.remove(_f)
        except OSError:
            pass

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    raise SystemExit(1)
print("test_plugin_isolation OK")
