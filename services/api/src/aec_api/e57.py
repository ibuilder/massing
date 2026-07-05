"""E57 point-cloud import — OPTIONAL, dependency-flagged (needs `pye57`, which is heavy/native so it
is NOT a default dependency). E57 is the inter+vendor scan-exchange format; there is no viable
in-browser parser, so we convert server-side to a plain `.xyz` (x y z [r g b]) that the existing
reference-overlay loader opens offline. Mirrors the aps.py / esign_bridge.py optional-bridge pattern:
the gates + status are testable without the dependency, and the convert raises an actionable error
until `pip install pye57` is done in the deployment."""
from __future__ import annotations

from typing import Any

# decimate large scans to keep the .xyz (and the browser) manageable
MAX_POINTS = 2_000_000


def is_available() -> bool:
    """True when the optional `pye57` reader is importable in this deployment."""
    try:
        import pye57  # noqa: F401
        return True
    except Exception:  # noqa: BLE001 — any import/native-load failure means "not available"
        return False


def status() -> dict[str, Any]:
    avail = is_available()
    return {
        "available": avail,
        "max_points": MAX_POINTS,
        "message": ("E57 import available — uploads convert to .xyz server-side." if avail else
                    "E57 import needs the optional `pye57` reader (heavy/native). "
                    "`pip install pye57` in the API deployment to enable; meshes/PLY/LAS/LAZ already "
                    "load offline via the normal Open flow."),
    }


def convert_to_xyz(data: bytes, max_points: int = MAX_POINTS) -> bytes:
    """Convert E57 bytes to a decimated ASCII `.xyz` (`x y z` or `x y z r g b`). Raises RuntimeError
    with an actionable message when `pye57` isn't installed."""
    if not is_available():
        raise RuntimeError("E57 import needs `pye57` (pip install pye57); not installed in this deployment.")
    import os
    import tempfile

    import numpy as np
    import pye57

    with tempfile.NamedTemporaryFile(suffix=".e57", delete=False) as tf:
        tf.write(data)
        path = tf.name
    try:
        e = pye57.E57(path)
        chunks: list[str] = []
        total = 0
        n_scans = e.scan_count
        # spread the budget across scans
        per_scan = max(1, max_points // max(1, n_scans))
        for i in range(n_scans):
            d = e.read_scan(i, ignore_missing_fields=True, colors=True)
            x, y, z = d["cartesianX"], d["cartesianY"], d["cartesianZ"]
            n = len(x)
            if n == 0:
                continue
            step = max(1, n // per_scan)
            idx = np.arange(0, n, step)
            has_rgb = all(k in d for k in ("colorRed", "colorGreen", "colorBlue"))
            if has_rgb:
                r, g, b = d["colorRed"], d["colorGreen"], d["colorBlue"]
                for j in idx:
                    chunks.append(f"{x[j]:.4f} {y[j]:.4f} {z[j]:.4f} {int(r[j])} {int(g[j])} {int(b[j])}")
            else:
                for j in idx:
                    chunks.append(f"{x[j]:.4f} {y[j]:.4f} {z[j]:.4f}")
            total += len(idx)
            if total >= max_points:
                break
        return ("\n".join(chunks) + "\n").encode()
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass
