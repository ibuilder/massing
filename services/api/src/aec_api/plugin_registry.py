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

import json
import logging
import os
import subprocess
import sys
import tempfile
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


#: How long a plugin gets, in seconds, for one discovery or one recipe run.
#:
#: Wall-clock only. `setrlimit` would cap memory too and is POSIX-only; this repo has already refused
#: a Windows-unavailable memory cap rather than ship a guard that silently does nothing on the
#: platform it is developed on. Stated here rather than left as an unnoticed gap.
PLUGIN_TIMEOUT_S = int(os.environ.get("AEC_PLUGIN_TIMEOUT_S", "30") or 30)

#: Environment the child must NOT inherit. It has no DB session and no storage handle because there is
#: nothing here to build one from — not because it declines to build one.
_STRIPPED = ("DATABASE_URL", "STORAGE_DIR", "IFC_DIR", "AEC_API_KEY", "AEC_JWT_SECRET",
             "AWS_ACCESS_KEY_ID", "AWS_SECRET_ACCESS_KEY", "S3_ENDPOINT", "AEC_METRICS_TOKEN")


def _child_env() -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in _STRIPPED}
    env["AEC_PLUGIN_CHILD"] = "1"          # so anything imported down there can tell where it is
    # UTF-8 on the pipe, in both directions, because on Windows it otherwise defaults to the ANSI
    # codepage — cp1252 on this machine, checked rather than assumed.
    #
    # **Narrower than it first looks, and the first version of this comment was wrong about it.**
    # `json.dumps` escapes non-ASCII by default, so the PROTOCOL is pure ASCII whatever the codepage
    # is; a recipe named in Chinese round-trips fine without any of this. What the pipe carries raw is
    # the DIAGNOSTIC path — the stderr tail `_host` reports when the child produced no JSON at all —
    # and that is exactly the path you are on when something has already gone wrong. Decoded as
    # cp1252, a UTF-8 traceback comes back as mojibake, and the refusal that was meant to explain the
    # failure misdescribes it instead. `test_plugin_isolation.py` asserts on that path specifically,
    # because an assertion on the protocol passes with or without these two lines.
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUTF8"] = "1"
    return env


def _host(args: list[str], stdin: str = "") -> dict[str, Any]:
    """Run `plugin_host` in a child process and read its one JSON line.

    A non-zero exit with parseable JSON is a REFUSAL and carries its reason; anything else — a crash,
    a timeout, output that is not JSON — is reported as a failure with what was actually seen. The two
    are different and the caller has to be able to tell them apart, which is why the child prints a
    protocol rather than letting a traceback stand in for one.
    """
    cmd = [sys.executable, "-m", "aec_api.plugin_host", *args]
    try:
        proc = subprocess.run(cmd, input=stdin, capture_output=True, text=True, shell=False,
                              encoding="utf-8", errors="replace",   # never the ANSI codepage
                              timeout=PLUGIN_TIMEOUT_S, env=_child_env(),
                              cwd=str(Path(__file__).resolve().parents[1]))
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"timed out after {PLUGIN_TIMEOUT_S}s"}
    try:
        return json.loads((proc.stdout or "").strip().splitlines()[-1])
    except (ValueError, IndexError):
        tail = (proc.stderr or proc.stdout or "")[-400:]
        return {"ok": False, "error": f"no JSON from plugin host (exit {proc.returncode}): {tail}"}


def _proxy_recipe(plugin_dir: Path, entry: str, key: str) -> Callable[[Any, dict], Any]:
    """A recipe that runs the plugin's code in a CHILD process, not this one.

    The signature the host registry expects is `fn(model, params)` over an in-memory model, so this
    writes the model out, runs the child against the file, and reopens the result. `edit` accepts a
    `(model, changed)` return, which is how the reopened model gets back to the caller.

    **This costs a model round-trip per call**, and `edit.apply_recipes` otherwise keeps a whole batch
    in memory. That is the price of the code not being in this process; it is only paid when plugins
    are enabled, which is off by default.
    """
    def call(model: Any, params: dict) -> Any:
        import ifcopenshell  # type: ignore

        with tempfile.TemporaryDirectory(prefix="aec-plugin-") as td:
            src, dst = str(Path(td) / "in.ifc"), str(Path(td) / "out.ifc")
            model.write(src)
            res = _host(["run", str(plugin_dir), entry, PLUGIN_API_VERSION, key, src, dst],
                        stdin=json.dumps(params or {}))
            if not res.get("ok"):
                raise ValueError(f"plugin recipe {key} failed: {res.get('error')}")
            if not Path(dst).exists():
                raise ValueError(f"plugin recipe {key} wrote no model")
            return ifcopenshell.open(dst), res.get("changed")
    return call


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
        # A plugin recipe ALWAYS hands back `(model, changed)`, because `_proxy_recipe` reopens what
        # the child wrote. Without this line the drivers use that tuple as the change summary and save
        # the pre-edit model: a green run, a plausible report, and the edit written nowhere.
        edit.REPLACING_RECIPES.add(key)
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
        edit.REPLACING_RECIPES.discard(key)
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
        entry_name = mf.get("entry") or "plugin.py"
        registered: list[str] = []
        # SEC-PLUGIN-LOADER — the plugin's code is imported in a CHILD PROCESS, never here. What comes
        # back is a list of declarations; the callables stay on the other side of the boundary and are
        # reached through `_proxy_recipe`. Everything this function checked before still runs, and now
        # it runs on data rather than in the same interpreter as the code it is checking.
        found = _host(["discover", str(d), entry_name, PLUGIN_API_VERSION])
        if not found.get("ok"):
            _STATE["refused"].append({"name": mf["name"], "reason": f"load failed: {found.get('error')}"})
            log.warning("plugin %s refused: load failed: %s", mf["name"], found.get("error"))
            continue
        try:
            api = PluginApi(mf["name"], registered)
            for r in found.get("recipes") or []:
                api.register_recipe(r["name"], _proxy_recipe(d, entry_name, r["key"]),
                                    category=r.get("category") or "plugin",
                                    produces=r.get("produces") or "")
        except Exception as e:  # noqa: BLE001 — a colliding key is refused with its error, never fatal
            for key in registered:                       # roll back anything it managed to register
                from aec_data import edit  # type: ignore
                edit.RECIPES.pop(key, None)
                edit.REPLACING_RECIPES.discard(key)
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
