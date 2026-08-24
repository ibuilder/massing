"""SEC-PLUGIN-LOADER — the child process third-party plugin code actually runs in.

WHY A PROCESS AND NOT MORE VALIDATION
--------------------------------------
`plugin_registry` used to do `spec.loader.exec_module(mod)` in the API process and then call
`mod.register(PluginApi(...))`. Everything it checked — the manifest, the `api_version` major, the
rollback of a plugin that raises — happens **before** that line, and none of it constrains what the
code then does. Whatever the entry module runs at import time ran with the API's full privileges: its
DB session, its filesystem, its network, its environment.

Signing is the weaker alternative and was rejected in the entry: it answers *who wrote this*, not
*what it may do*. A denylist is weaker still — this codebase already learned from the snippet sandbox
that a denylist cannot see methods reached through an injected object.

So the boundary is a process. This module is what runs inside it.

TWO MODES, AND EXECUTION IS ONE OF THEM ON PURPOSE
---------------------------------------------------
    discover   import each plugin, call `register(api)` against a RECORDING api, print what it
               declared. No recipe body ever runs.
    run        execute ONE registered recipe against an IFC on disk, and write the result.

Sandboxing only `discover` would have been half a boundary and would have read like a whole one. A
plugin's recipe is `fn(model, params)` — an arbitrary callable — so if registration is isolated and
execution is not, the import-time code is contained and the code that does the actual work is not.
The entry's own words are "run registration in a separate process"; taking that literally would leave
the larger hole open, which is why `run` is here too.

WHAT THIS PROCESS DOES NOT HAVE
--------------------------------
The parent strips `DATABASE_URL`, `STORAGE_DIR`, `AEC_API_KEY` and the rest from the child's
environment (see `plugin_registry._child_env`). It talks to the parent over stdout as JSON and gets
its work from argv. It has no DB session and no storage handle because there is nothing in the
environment to build one from — not because it politely declines to.

WHAT IT COSTS, STATED PLAINLY
------------------------------
A model round-trip per recipe call. `edit.apply_recipes` opens a model once and runs a whole batch in
memory; a plugin recipe in that batch now writes the model, runs a process, and reads it back. That is
real, it is only paid when `AEC_PLUGINS_ENABLED=1` (off by default), and it is the price of the code
not being in this process. A boundary that was free would not be one.

**No memory cap.** `setrlimit` is POSIX-only and this repo has already refused a Windows-unavailable
memory cap once rather than ship a guard that silently does nothing on the platform it develops on. A
wall-clock timeout is portable and is enforced; memory is bounded only by the OS.
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path
from typing import Any


class RecordingApi:
    """The `PluginApi` shape, recording declarations instead of performing them.

    Deliberately NOT the real `PluginApi`: that one writes into `edit.RECIPES`, which is a live host
    structure and is exactly what a discovery pass must not touch. A recording double also means the
    child never imports `aec_data.edit`, so a plugin cannot reach the recipe table through it.
    """

    def __init__(self, plugin_name: str, api_version: str) -> None:
        self._name = plugin_name
        self.api_version = api_version
        self.recipes: list[dict[str, str]] = []

    def register_recipe(self, name: str, fn: Any, *, category: str = "plugin",
                        produces: str = "") -> str:
        key = f"{self._name}.{name}"
        if any(r["key"] == key for r in self.recipes):
            raise ValueError(f"duplicate recipe {key}")
        self.recipes.append({"key": key, "name": name, "category": category, "produces": produces})
        return key


def _load_entry(plugin_dir: Path, entry_name: str):
    """Import a plugin's entry module. **This is the dangerous line, and it is why we are here.**"""
    entry = plugin_dir / entry_name
    spec = importlib.util.spec_from_file_location(f"aec_plugin_{plugin_dir.name}", entry)
    if spec is None or spec.loader is None:
        raise ValueError(f"cannot load entry {entry.name}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    if not hasattr(mod, "register"):
        raise ValueError("entry module has no register(api) function")
    return mod


def discover(plugin_dir: Path, entry_name: str, api_version: str) -> dict[str, Any]:
    """What this plugin declares. No recipe body runs."""
    mod = _load_entry(plugin_dir, entry_name)
    api = RecordingApi(plugin_dir.name, api_version)
    mod.register(api)
    return {"ok": True, "recipes": api.recipes}


def run(plugin_dir: Path, entry_name: str, api_version: str, recipe: str,
        ifc_in: str, ifc_out: str, params: dict) -> dict[str, Any]:
    """Execute one recipe against an IFC on disk and write the result.

    The recipe is re-resolved by registering again in this process rather than trusting a name handed
    in: the child is the only place that ever holds the callable, so there is nothing to look it up in
    on the parent side. Registration is cheap next to opening a model.
    """
    import ifcopenshell  # imported here so `discover` does not pay for it

    mod = _load_entry(plugin_dir, entry_name)
    fns: dict[str, Any] = {}

    class _Collect(RecordingApi):
        def register_recipe(self, name, fn, *, category="plugin", produces=""):
            key = super().register_recipe(name, fn, category=category, produces=produces)
            fns[key] = fn
            return key

    mod.register(_Collect(plugin_dir.name, api_version))
    fn = fns.get(recipe)
    if fn is None:
        raise ValueError(f"{recipe} is not registered by this plugin")

    model = ifcopenshell.open(ifc_in)
    result = fn(model, params)
    # Core recipes may return either `changed` or `(model, changed)`; a plugin's may do the same, and
    # the second form is how a recipe that reopens the model hands the new one back.
    if isinstance(result, tuple) and len(result) == 2:
        model, changed = result
    else:
        changed = result
    model.write(ifc_out)
    return {"ok": True, "changed": changed}


def main(argv: list[str]) -> int:
    """`discover <dir> <entry> <api_version>` | `run <dir> <entry> <api_version> <recipe> <in> <out>`.

    Params for `run` arrive on **stdin**, not argv: a params dict can be large and can contain
    anything, and a command line is the wrong place for both.

    Every failure is printed as `{"ok": false, "error": ...}` and exits 1 — the parent must be able to
    tell a refusal from a crash, and a traceback on stderr is not a protocol.
    """
    try:
        mode = argv[1]
        d, entry, api_version = Path(argv[2]), argv[3], argv[4]
        if mode == "discover":
            out = discover(d, entry, api_version)
        elif mode == "run":
            params = json.loads(sys.stdin.read() or "{}")
            out = run(d, entry, api_version, argv[5], argv[6], argv[7], params)
        else:
            raise ValueError(f"unknown mode {mode}")
    except Exception as e:  # noqa: BLE001 — the whole point is that nothing escapes this process
        print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}))
        return 1
    print(json.dumps(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
