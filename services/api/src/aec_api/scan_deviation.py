"""Scan-to-BIM deviation analysis — compare an as-built point cloud against the as-designed model and
report where reality departs from the model beyond tolerance (the QA/QC step after a pour or an
erection). For each scan point we take the nearest distance to the model surface (KD-tree over the
model's triangulated vertices), classify it against a tolerance band, and summarize: % within
tolerance, mean/max/p95 deviation, a deviation histogram, and the out-of-tolerance count — the data
behind a red/green heatmap.

Pure over numpy arrays; scipy cKDTree for the nearest-neighbour query. `model_surface_points` pulls the
reference vertices from an opened IFC via ifcopenshell.geom (guarded)."""
from __future__ import annotations

from typing import Any


def analyze(points: Any, reference: Any, tolerance: float = 0.05) -> dict[str, Any]:
    """points / reference: Nx3 arrays (scan points, model surface vertices). Returns the deviation
    summary + histogram. `tolerance` is the in/out threshold in model units (metres)."""
    import numpy as np
    from scipy.spatial import cKDTree

    pts = np.asarray(points, dtype=float).reshape(-1, 3)
    ref = np.asarray(reference, dtype=float).reshape(-1, 3)
    if len(pts) == 0 or len(ref) == 0:
        return {"point_count": int(len(pts)), "reference_count": int(len(ref)),
                "error": "empty point cloud or reference", "within_pct": None}
    dist, _ = cKDTree(ref).query(pts, k=1)
    within = int((dist <= tolerance).sum())
    n = int(len(pts))
    # deviation histogram in multiples of the tolerance (0-1x, 1-2x, 2-3x, 3x+)
    edges = [0, tolerance, 2 * tolerance, 3 * tolerance, float("inf")]
    labels = ["≤1×tol", "1–2×tol", "2–3×tol", ">3×tol"]
    hist = [int(((dist >= edges[i]) & (dist < edges[i + 1])).sum()) for i in range(4)]
    return {
        "point_count": n, "reference_count": int(len(ref)),
        "tolerance": tolerance,
        "within_tolerance": within, "within_pct": round(100 * within / n, 1),
        "out_of_tolerance": n - within,
        "mean_deviation": round(float(dist.mean()), 4),
        "max_deviation": round(float(dist.max()), 4),
        "p95_deviation": round(float(np.percentile(dist, 95)), 4),
        "histogram": [{"band": lbl, "count": c} for lbl, c in zip(labels, hist)],
        "note": "Nearest-surface deviation of each scan point vs the model's triangulated vertices; "
                "within-tolerance is the share ≤ the tolerance. Feeds a red/green deviation heatmap.",
    }


def model_surface_points(model, max_points: int = 200000):
    """Triangulated-surface vertices of the IFC model (reference for the deviation query). Iterates
    ifcopenshell.geom; capped at `max_points` so a huge model can't blow memory. Returns an Nx3 list."""
    import ifcopenshell.geom as geom
    import numpy as np

    settings = geom.settings()
    verts: list = []
    it = geom.iterator(settings, model)
    if it.initialize():
        while True:
            shape = it.get()
            v = shape.geometry.verts       # flat [x0,y0,z0, x1,y1,z1, ...]
            if v:
                verts.append(np.asarray(v, dtype=float).reshape(-1, 3))
                if sum(len(a) for a in verts) >= max_points:
                    break
            if not it.next():
                break
    if not verts:
        return np.zeros((0, 3))
    return np.vstack(verts)[:max_points]


def parse_point_cloud(text: str, max_points: int = 500000):
    """Parse an ASCII point cloud (XYZ / CSV — one point per line, first three numbers are x y z)."""
    import numpy as np
    pts = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line[0] in "#/":
            continue
        parts = line.replace(",", " ").split()
        if len(parts) >= 3:
            try:
                pts.append((float(parts[0]), float(parts[1]), float(parts[2])))
            except ValueError:
                continue
        if len(pts) >= max_points:
            break
    return np.asarray(pts, dtype=float) if pts else np.zeros((0, 3))
