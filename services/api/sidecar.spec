# PyInstaller spec for the Tauri SIDECAR — a single-file binary Tauri can ship as externalBin.
# Same payload as desktop.spec (FastAPI + SPA + module catalog + ifcopenshell) but ONE FILE, so
# it drops into apps/web/src-tauri/binaries/ with the target-triple name Tauri expects.
#
# Build:  ./.venv/Scripts/python.exe -m PyInstaller sidecar.spec --noconfirm
import os
import sys
from PyInstaller.utils.hooks import collect_all, collect_submodules

HERE = os.path.abspath(SPECPATH)                    # services/api
REPO = os.path.abspath(os.path.join(HERE, "..", ".."))
WEB_DIST = os.path.join(REPO, "apps", "web", "dist")
DATA_SRC = os.path.join(HERE, "..", "data", "src")

for p in (os.path.join(HERE, "src"), os.path.abspath(DATA_SRC)):
    if p not in sys.path:
        sys.path.insert(0, p)

datas, binaries, hiddenimports = [], [], []
for pkg in ("ifcopenshell", "uvicorn", "aec_api"):
    d, b, h = collect_all(pkg)
    datas += d; binaries += b; hiddenimports += h
hiddenimports += collect_submodules("aec_data")
hiddenimports += [
    "multipart",
    "uvicorn.logging", "uvicorn.loops.auto", "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto", "uvicorn.lifespan.on",
]
if os.path.isdir(WEB_DIST):
    datas += [(WEB_DIST, "web")]
datas += [(os.path.join(HERE, "modules"), "modules")]

a = Analysis(
    ["desktop_entry.py"],
    pathex=["src", DATA_SRC],
    binaries=binaries, datas=datas, hiddenimports=hiddenimports,
    excludes=["tkinter", "matplotlib", "PySide6", "PyQt5", "pytest"],
)
pyz = PYZ(a.pure)

# onefile: bundle everything into a single executable named for the host (Tauri appends the triple)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="aec-bim-server",
    onefile=True,
    console=True,
    icon=os.path.join(REPO, "apps", "web", "src-tauri", "icons", "icon.ico")
        if os.path.exists(os.path.join(REPO, "apps", "web", "src-tauri", "icons", "icon.ico")) else None,
)
