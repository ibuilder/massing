"""Build the Tauri sidecar binary and drop it into apps/web/src-tauri/binaries/ with the
target-triple name Tauri's `externalBin` expects (`aec-bim-server-<triple>[.exe]`).

Run per-platform (PyInstaller can't cross-compile) — locally or in CI:
    ./.venv/Scripts/python.exe build_sidecar.py
Assumes `npm run build:desktop` has produced apps/web/dist and PyInstaller is installed.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent                 # services/api
REPO = HERE.parents[1]
BINARIES = REPO / "apps" / "web" / "src-tauri" / "binaries"


def host_triple() -> str:
    """The Rust host target triple (what Tauri appends). Prefer rustc; fall back to a platform map."""
    try:
        out = subprocess.check_output(["rustc", "-vV"], text=True)
        for line in out.splitlines():
            if line.startswith("host:"):
                return line.split(":", 1)[1].strip()
    except Exception:                                  # noqa: BLE001 — rustc may be absent locally
        pass
    import platform
    mach = platform.machine().lower()
    arch = "aarch64" if mach in ("arm64", "aarch64") else "x86_64"
    if sys.platform.startswith("win"):
        return f"{arch}-pc-windows-msvc"
    if sys.platform == "darwin":
        return f"{arch}-apple-darwin"
    return f"{arch}-unknown-linux-gnu"


def main() -> None:
    print("==> PyInstaller (onefile sidecar)...")
    subprocess.check_call([sys.executable, "-m", "PyInstaller", "sidecar.spec", "--noconfirm",
                           "--distpath", "dist_sidecar", "--workpath", "build_sidecar"], cwd=HERE)
    ext = ".exe" if sys.platform.startswith("win") else ""
    built = HERE / "dist_sidecar" / f"aec-bim-server{ext}"
    if not built.exists():
        sys.exit(f"sidecar binary not found at {built}")
    triple = host_triple()
    BINARIES.mkdir(parents=True, exist_ok=True)
    dest = BINARIES / f"aec-bim-server-{triple}{ext}"
    shutil.copy2(built, dest)
    if not ext:                                        # ensure it's executable on unix
        os.chmod(dest, 0o755)
    print(f"==> Placed sidecar: {dest}  ({dest.stat().st_size // (1024*1024)} MB)")


if __name__ == "__main__":
    main()
