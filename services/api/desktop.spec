# PyInstaller spec for the AEC BIM free single-project desktop build.
# Bundles the FastAPI app + the desktop-mode web SPA + the GC-portal module catalog into a
# self-contained app (one process: API + SPA on 127.0.0.1:8765, SQLite, local mode).
#
# Build:  ./.venv/Scripts/python.exe -m PyInstaller desktop.spec --noconfirm
# (run from services/api, after `npm run build:desktop` has produced apps/web/dist)
import os
import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules


HERE = os.path.abspath(SPECPATH)                    # services/api (SPECPATH is the spec's dir)
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
WEB_DIST = os.path.join(REPO, "apps", "web", "dist")
DATA_SRC = os.path.join(HERE, "..", "data", "src")   # services/data/src (aec_data package)

# make aec_api + aec_data importable at spec-eval time (collect_all/collect_submodules import them)
for p in (os.path.join(HERE, "src"), os.path.abspath(DATA_SRC)):
    if p not in sys.path:
        sys.path.insert(0, p)

# Packages that must NOT be distributed, declared once in aec_api.supply_chain.SHIP_EXCLUDED and read
# here rather than repeated. A permissively-licensed dependency can require a copyleft one it only
# uses on a path we never take; it has to be installed for metadata, and left out of the artifact.
# Hard-coding a name here would fix one package and leave the next arrival to be noticed by nobody.
from aec_api.supply_chain import excluded_import_names   # noqa: E402

SHIP_EXCLUDES = excluded_import_names()

datas, binaries, hiddenimports = [], [], []

# heavy / dynamically-loaded packages PyInstaller can't fully trace on its own
for pkg in ("ifcopenshell", "uvicorn", "aec_api"):
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hiddenimports += h
hiddenimports += collect_submodules("aec_data")
hiddenimports += [
    "multipart",                       # python-multipart: UploadFile (bundle import)
    "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on",
]

# the SPA (built with `npm run build:desktop`) and the 68 module.json definitions
if os.path.isdir(WEB_DIST):
    datas += [(WEB_DIST, "web")]
datas += [(os.path.join(HERE, "modules"), "modules")]

a = Analysis(
    ["desktop_entry.py"],
    pathex=["src", DATA_SRC],          # aec_api + aec_data source roots
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    excludes=["tkinter", "matplotlib", "PySide6", "PyQt5", "pytest"] + SHIP_EXCLUDES,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz, a.scripts, [],
    exclude_binaries=True,
    name="AEC-BIM",
    console=True,                      # show the local-server log; set False for a silent window
    icon=os.path.join(REPO, "apps", "web", "src-tauri", "icons", "icon.ico")
        if os.path.exists(os.path.join(REPO, "apps", "web", "src-tauri", "icons", "icon.ico")) else None,
)
coll = COLLECT(exe, a.binaries, a.datas, name="AEC-BIM")
