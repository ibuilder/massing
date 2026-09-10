"""Self-contained desktop runtime — the whole app in ONE process: FastAPI serving both the API
and the built web frontend, backed by SQLite + local file storage, in single-operator local mode.
No Docker / Postgres / MinIO. This is the local backend the Tauri .exe spawns, and a convenient
`python -m aec_api.desktop` for running the full free app locally.

Env defaults are applied HERE, before the app is imported, because db / rbac / main read them at
import time. Everything lives under one data directory so the install is portable and uninstall
is a folder delete.
"""
from __future__ import annotations

import os
import sys
import threading
import time
import webbrowser
from pathlib import Path


def data_dir() -> Path:
    """Per-user data directory (overridable with AEC_DATA_DIR) holding the SQLite db, storage,
    and IFC copies — so the desktop app keeps everything in one place."""
    base = os.environ.get("AEC_DATA_DIR") or (
        os.environ.get("LOCALAPPDATA") if os.name == "nt"
        else os.path.join(os.path.expanduser("~"), ".local", "share"))
    d = Path(base) / "AEC-BIM"
    d.mkdir(parents=True, exist_ok=True)
    return d


def repo_root() -> Path | None:
    """The source checkout this file lives in, or None when there is not one.

    **This exists because `parents[4]` took the shipped Linux app down.** In a PyInstaller bundle
    `__file__` is `$TMPDIR/_MEIxxxxxx/aec_api/desktop.py`, and with the default `TMPDIR=/tmp` that
    path has exactly FOUR parents -- so `parents[4]` raised `IndexError: 4` and `aec-bim-server`
    died before binding a port. The candidate list is built eagerly, so it raised before the loop
    could reach the bundled copy appended ahead of it.

    Verified against the published v0.3.1133 AppImage: crashed every time under `TMPDIR=/tmp`, and
    the same binary started and served `/health`, the frontend and `/modules` under a deeper one.
    Windows and macOS temp paths are eight parents deep, which is why it was never seen in testing.

    A frozen build has no checkout to fall back to, so it returns None rather than guessing; and the
    index is bounds-checked anyway, because a hard-coded depth is a fact about the source layout
    that a file move silently invalidates.
    """
    if getattr(sys, "frozen", False) or getattr(sys, "_MEIPASS", ""):
        return None
    parents = Path(__file__).resolve().parents          # .../services/api/src/aec_api/desktop.py
    return parents[4] if len(parents) > 4 else None     # parents[4] == the repo root


def web_dist() -> str | None:
    """Locate the built web app: bundled beside the frozen exe (PyInstaller _MEIPASS), else the
    repo's apps/web/dist, else an explicit AEC_WEB_DIST."""
    meipass = getattr(sys, "_MEIPASS", "")
    candidates = []
    if meipass:
        candidates.append(Path(meipass) / "web")
    root = repo_root()
    if root:
        candidates.append(root / "apps" / "web" / "dist")
    for c in candidates:
        if c.is_dir() and (c / "index.html").exists():
            return str(c)
    d = os.environ.get("AEC_WEB_DIST")
    return d if d and os.path.isdir(d) else None


def modules_dir() -> str | None:
    """Locate the GC-portal module.json catalog: bundled beside the frozen exe (_MEIPASS/modules),
    else the repo's services/api/modules. The frozen build needs this since modules.py's __file__
    no longer resolves to the source tree."""
    meipass = getattr(sys, "_MEIPASS", "")
    root = repo_root()
    candidates = []
    if meipass:
        candidates.append(Path(meipass) / "modules")
    # `parents[3]` was `services`, not `services/api` -- so this built `services/modules`, which
    # does not exist. `is_dir()` swallowed it, so it returned None instead of raising and nothing
    # broke: `modules_registry.MODULES_DIR` has its own correct default. A DEAD fallback masked by a
    # working one, one index away from the class that took the app down.
    if root:
        candidates.append(root / "services" / "api" / "modules")
    for c in candidates:
        if c.is_dir():
            return str(c)
    return None


def apply_local_defaults() -> dict:
    """Set the single-operator local-build env defaults (only if not already overridden)."""
    d = data_dir()
    os.environ.setdefault("DATABASE_URL", f"sqlite:///{(d / 'aec.db').as_posix()}")
    os.environ.setdefault("STORAGE_DIR", str(d / "storage"))
    os.environ.setdefault("IFC_DIR", str(d / "ifc"))
    os.environ.setdefault("AEC_LOCAL_MODE", "1")     # no login; operator owns the one site
    os.environ.setdefault("AEC_AUTOSYNC", "0")       # no scheduled cloud sync in the free local app
    wd = web_dist()
    if wd:
        os.environ.setdefault("AEC_WEB_DIST", wd)
    md = modules_dir()
    if md:
        os.environ.setdefault("AEC_MODULES_DIR", md)
    return {"data_dir": str(d), "web_dist": wd, "modules_dir": md}


def main() -> None:
    info = apply_local_defaults()
    host = os.environ.get("AEC_HOST", "127.0.0.1")
    port = int(os.environ.get("AEC_PORT", "8765"))
    url = f"http://{host}:{port}/"

    if os.environ.get("AEC_OPEN_BROWSER", "1") == "1" and info["web_dist"]:
        def _open():
            time.sleep(1.2)                          # give uvicorn a moment to bind
            try:
                webbrowser.open(url)
            except Exception:                        # noqa: BLE001 — headless is fine
                pass
        threading.Thread(target=_open, daemon=True).start()

    import uvicorn
    print(f"AEC BIM (local) -> {url}  data: {info['data_dir']}  web: {info['web_dist'] or '(API only)'}")
    uvicorn.run("aec_api.main:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
