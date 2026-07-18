"""PLUGIN-REGISTRY — a versioned, manifest-gated plugin model for server-side authoring recipes.

The OpenAEC/Open CAD Studio lesson (§🧭 #6): make the FIRST third-party extension a template exercise,
not archaeology. A plugin is a directory with a `plugin.json` manifest and a Python entry module whose
`register(api)` adds **namespaced authoring recipes** (`<plugin>.<recipe>`) into the same GUID-stable
`aec_data.edit.RECIPES` registry the CAD command line, the AI bar, MCP `run_recipe`, and `POST /edit`
all dispatch — so a plugin recipe is instantly drivable from every authoring surface and shows up in
the authoring matrix automatically.

Three hard gates keep this safe and honest:
  1. **Opt-in**: plugins run arbitrary Python at load, so discovery is OFF unless `AEC_PLUGINS_ENABLED=1`
     (the same philosophy as the A1 execute-code sandbox — never on by default).
  2. **API-version gate**: the manifest must declare an `api_version` whose MAJOR matches
     `PLUGIN_API_VERSION`; a mismatch refuses the plugin with a clear reason instead of loading a module
     built against a different recipe contract.
  3. **Namespace + collision refusal**: recipes register as `<plugin>.<name>`; a key that already exists
     (core or another plugin) is refused, never silently overwritten.

`load_all()` is idempotent — reloading first unregisters everything the previous load registered, so a
changed plugin re-registers cleanly. Refusals are returned AND logged; a half-loaded plugin set is
visible, never silent."""
from __future__ import annotations

import importlib.util
import json
import logging
import os
from collections.abc import Callable
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

# The recipe-API contract version. MAJOR bumps when the register(api)/recipe calling convention
# (fn(model, params) -> changed, GUID-stable, guards-prechecked) changes incompatibly.
PLUGIN_API_VERSION = "1.0"

_STATE: dict[str, Any] = {"loaded": [], "refused": [], "registered_keys": []}


def _plugins_dir() -> Path:
    default = Path(__file__).resolve().parents[4] / "plugins"       # repo-root /plugins
    return Path(os.environ.get("AEC_PLUGINS_DIR") or default)


def enabled() -> bool:
    return os.environ.get("AEC_PLUGINS_ENABLED") == "1"


class PluginApi:
    """The facade handed to a plugin's `register(api)` — the ONLY supported extension surface.
    Everything registered is tracked so a reload can cleanly unregister it."""

    def __init__(self, plugin_name: str, registered: list[str]):
        self._name = plugin_name
        self._registered = registered
        self.api_version = PLUGIN_API_VERSION

    def register_recipe(self, name: str, fn: Callable[[Any, dict], Any], *,
                        category: str = "plugin", produces: str = "") -> str:
        """Add a GUID-stable authoring recipe as `<plugin>.<name>`. `fn(model, params)` receives the
        open ifcopenshell model + the params dict and returns a summary of what changed (same contract
        as every core recipe). Raises ValueError on a key collision — never overwrites."""
        from aec_data import edit  # type: ignore

        key = f"{self._name}.{name}"
        if key in edit.RECIPES:
            raise ValueError(f"recipe key {key!r} already registered")
        edit.RECIPES[key] = fn
        self._registered.append(key)
        try:                                             # surface it in the authoring matrix, categorized
            from . import authoring_matrix
            authoring_matrix._MAP.setdefault(key, (category, produces))
        except Exception:  # noqa: BLE001 — matrix categorization is cosmetic; the recipe still works
            pass
        return key


def _read_manifest(d: Path) -> dict:
    mf = d / "plugin.json"
    if not mf.exists():
        raise ValueError("no plugin.json manifest")
    data = json.loads(mf.read_text(encoding="utf-8"))
    for req in ("name", "version", "api_version"):
        if not data.get(req):
            raise ValueError(f"manifest missing required field {req!r}")
    if not str(data["name"]).replace("_", "").replace("-", "").isalnum():
        raise ValueError("plugin name must be alphanumeric (plus - or _)")
    return data


def _api_compatible(declared: str) -> bool:
    """MAJOR must match; a plugin built for 2.x must not load into a 1.x host (and vice-versa)."""
    try:
        return str(declared).split(".")[0] == PLUGIN_API_VERSION.split(".")[0]
    except Exception:  # noqa: BLE001 — an unparseable version is incompatible by definition
        return False


def _unregister_all() -> None:
    from aec_data import edit  # type: ignore

    for key in _STATE["registered_keys"]:
        edit.RECIPES.pop(key, None)
    _STATE["registered_keys"] = []


def load_all() -> dict[str, Any]:
    """Discover + load every plugin under the plugins dir. Idempotent (a reload replaces the previous
    registrations). Returns {enabled, dir, loaded:[…], refused:[{name, reason}]} — refusals are data,
    not exceptions, so one broken plugin never blocks the rest."""
    _unregister_all()
    _STATE["loaded"], _STATE["refused"] = [], []
    pdir = _plugins_dir()
    out = {"enabled": enabled(), "dir": str(pdir), "loaded": _STATE["loaded"], "refused": _STATE["refused"]}
    if not enabled():
        return out                                      # off by default — plugins execute code at load
    if not pdir.is_dir():
        return out
    for d in sorted(p for p in pdir.iterdir() if p.is_dir() and not p.name.startswith(("_", "."))):
        try:
            mf = _read_manifest(d)
        except (ValueError, json.JSONDecodeError) as e:
            _STATE["refused"].append({"name": d.name, "reason": f"bad manifest: {e}"})
            log.warning("plugin %s refused: bad manifest: %s", d.name, e)
            continue
        if not _api_compatible(mf["api_version"]):
            reason = (f"api_version {mf['api_version']} incompatible with host {PLUGIN_API_VERSION} "
                      "(major must match)")
            _STATE["refused"].append({"name": mf["name"], "reason": reason})
            log.warning("plugin %s refused: %s", mf["name"], reason)
            continue
        entry = d / (mf.get("entry") or "plugin.py")
        registered: list[str] = []
        try:
            spec = importlib.util.spec_from_file_location(f"aec_plugin_{mf['name']}", entry)
            if spec is None or spec.loader is None:
                raise ValueError(f"cannot load entry {entry.name}")
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            if not hasattr(mod, "register"):
                raise ValueError("entry module has no register(api) function")
            mod.register(PluginApi(mf["name"], registered))
        except Exception as e:  # noqa: BLE001 — a broken plugin is refused with its error, never fatal
            for key in registered:                       # roll back anything it managed to register
                from aec_data import edit  # type: ignore
                edit.RECIPES.pop(key, None)
            _STATE["refused"].append({"name": mf["name"], "reason": f"load failed: {e}"})
            log.warning("plugin %s refused: load failed: %s", mf["name"], e)
            continue
        _STATE["registered_keys"].extend(registered)
        _STATE["loaded"].append({"name": mf["name"], "version": mf["version"],
                                 "api_version": mf["api_version"],
                                 "description": mf.get("description"), "author": mf.get("author"),
                                 "recipes": registered})
        log.info("plugin %s v%s loaded: %d recipe(s)", mf["name"], mf["version"], len(registered))
    return out


def status() -> dict[str, Any]:
    """The current plugin state for GET /plugins (no re-load)."""
    return {"enabled": enabled(), "api_version": PLUGIN_API_VERSION, "dir": str(_plugins_dir()),
            "loaded": _STATE["loaded"], "refused": _STATE["refused"]}
