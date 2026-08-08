"""Scan-to-BIM deviation analysis — compare an as-built point cloud against the as-designed model and
report where reality departs from the model beyond tolerance (the QA/QC step after a pour or an
erection). For each scan point we take the nearest distance to the model surface (KD-tree over the
model's triangulated vertices), classify it against a tolerance band, and summarize: % within
tolerance, mean/max/p95 deviation, a deviation histogram, and the out-of-tolerance count — the data
behind a red/green heatmap.

Pure over numpy arrays; scipy cKDTree for the nearest-neighbour query. `model_surface_points` pulls the
reference vertices from an opened IFC via ifcopenshell.geom (guarded)."""
from __future__ import annotations

import contextlib
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


def per_element_deviation(model, points: Any, tolerance: float = 0.05,
                          min_points: int = 8, max_points_per_element: int = 400) -> dict[str, Any]:
    """Deviation attributed **per element**, which is what LOD 500 verification needs.

    `analyze` compares a cloud against the whole model and returns one aggregate. That answers "how
    close is this building to its model" and cannot answer "is *this wall* where we drew it" — so it
    can never verify an element.

    The query runs the other way round here: for each element's own surface vertices, find the
    nearest **scan** point. That direction is what makes attribution possible, and it also exposes the
    thing that matters most: an element the scanner never saw returns large distances rather than
    small ones, so it is reported as **uncovered** instead of quietly passing.

    Coverage is not correctness. An element with fewer than `min_points` samples inside the coverage
    band is returned with ``covered=False`` and no verdict — the same rule the carbon takeoff uses for
    elements it has no factor for. Silence is not a pass.
    """
    import ifcopenshell.geom as geom
    import numpy as np
    from scipy.spatial import cKDTree

    pts = np.asarray(points, dtype=float).reshape(-1, 3)
    if len(pts) == 0:
        return {"elements": [], "tolerance": tolerance, "scan_points": 0,
                "error": "empty point cloud", "covered": 0, "uncovered": 0,
                "within_tolerance": 0, "out_of_tolerance": 0}
    tree = cKDTree(pts)
    # a vertex further than this from any scan point was simply not scanned; beyond ~5x tolerance the
    # distance stops being a measurement of error and becomes a measurement of absence
    coverage_band = max(tolerance * 5.0, 0.25)

    settings = geom.settings()
    with contextlib.suppress(Exception):
        settings.set(settings.USE_WORLD_COORDS, True)
    out: list[dict[str, Any]] = []
    # num_threads=1 deliberately. This scan SAMPLES (`max_points_per_element`) and BREAKS early, so
    # what it returns depends on the order elements arrive in. ifcopenshell's default is single-
    # threaded file order; letting the shared worker count apply here would make identical requests
    # return different subsets run to run — a nondeterministic answer that still looks like an answer.
    from aec_data.geomconf import bounded_iterator  # type: ignore
    it = bounded_iterator(geom, settings, model, num_threads=1)
    if not it.initialize():
        return {"elements": [], "tolerance": tolerance, "scan_points": int(len(pts)),
                "error": "no geometry in model", "covered": 0, "uncovered": 0,
                "within_tolerance": 0, "out_of_tolerance": 0}
    while True:
        shape = it.get()
        verts = np.asarray(shape.geometry.verts, dtype=float).reshape(-1, 3)
        # Vertices alone are a poor sample of a coarse solid: a box has eight of them and they are
        # all corners, which is exactly where a scan sheet is thinnest. Adding triangle centroids
        # puts sample points in the middle of each face, where a scan actually lands.
        faces = np.asarray(getattr(shape.geometry, "faces", []), dtype=int).reshape(-1, 3)
        if len(faces) and len(verts):
            valid = faces[(faces < len(verts)).all(axis=1)]
            if len(valid):
                verts = np.vstack([verts, verts[valid].mean(axis=1)])
        if len(verts) > max_points_per_element:      # even sampling keeps a big element affordable
            verts = verts[:: max(1, len(verts) // max_points_per_element)]
        row: dict[str, Any] = {"guid": shape.guid, "ifc_class": shape.type,
                               "name": getattr(shape, "name", "") or None}
        if len(verts):
            dist, _ = tree.query(verts, k=1)
            seen = dist[dist <= coverage_band]
            row["sampled"] = int(len(verts))
            row["scanned_points"] = int(len(seen))
            if len(seen) >= min_points:
                row.update(covered=True,
                           mean_deviation=round(float(seen.mean()), 4),
                           max_deviation=round(float(seen.max()), 4),
                           p95_deviation=round(float(np.percentile(seen, 95)), 4),
                           within_tolerance=bool(np.percentile(seen, 95) <= tolerance))
            else:
                row.update(covered=False, within_tolerance=None,
                           note="not enough scan coverage to judge — absence of points is not a pass")
        else:
            row.update(covered=False, within_tolerance=None, sampled=0, scanned_points=0,
                       note="element has no geometry to compare")
        out.append(row)
        if not it.next():
            break

    covered = [r for r in out if r.get("covered")]
    return {
        "elements": out, "tolerance": tolerance, "coverage_band": round(coverage_band, 4),
        "scan_points": int(len(pts)),
        "covered": len(covered), "uncovered": len(out) - len(covered),
        "within_tolerance": sum(1 for r in covered if r["within_tolerance"]),
        "out_of_tolerance": sum(1 for r in covered if not r["within_tolerance"]),
        "note": "Per-element deviation: nearest SCAN point to each element's own surface vertices, so "
                "the result is attributable. An element the scan never covered is reported uncovered "
                "with no verdict — it is not evidence of correctness. The verdict uses p95 rather than "
                "max so one stray return cannot fail an otherwise good element.",
    }


def verify_from_scan(model, deviation: dict[str, Any], verified_by: str = "",
                     date: str | None = None, apply: bool = True) -> dict[str, Any]:
    """Turn a per-element deviation into **LOD 500 verification stamps** — the last link in the chain.

    Until now getting a model to LOD 500 meant asserting verification element by element, by hand, on
    a model with thousands of elements. A scan already contains that evidence; this reads it.

    Three outcomes, and the distinction between them is the whole value:
      * **verified** — covered by the scan and inside tolerance. Gets `Massing_AsBuilt` *and* the
        measured deviation, so the assertion carries a stated accuracy (BIMForum requires accuracy to
        be expressed by means other than the LOD number).
      * **finding** — covered and OUTSIDE tolerance. Deliberately not stamped: the element has been
        verified as wrong, which is a punch item, not a handover.
      * **uncovered** — the scan never saw it. Not stamped and not counted against the model; it needs
        another scan position, and no amount of processing turns absence into evidence.

    `apply=False` returns exactly the same plan without writing, so a team can see what a scan would
    assert before it touches the model.
    """
    from aec_data import edit_asbuilt  # type: ignore

    rows = deviation.get("elements") or []
    verified, findings, uncovered = [], [], []
    for r in rows:
        if not r.get("covered"):
            uncovered.append(r.get("guid"))
        elif r.get("within_tolerance"):
            verified.append(r)
        else:
            findings.append({"guid": r.get("guid"), "ifc_class": r.get("ifc_class"),
                             "p95_deviation": r.get("p95_deviation"),
                             "max_deviation": r.get("max_deviation")})

    stamped = dims = 0
    if apply and verified:
        guids = [r["guid"] for r in verified]
        # LOD-500-LOA: this pipeline HAS the accuracy in hand and used to spend it on a free-text
        # note. The scan's tolerance is the accuracy the survey was performed to, so it is declared
        # as one — label plus a number, which is what makes the claim resolvable by a receiving
        # party. It is deliberately NOT mapped onto a USIBD level: that table is not ours to embed,
        # and a self-describing "p95 <= 15 mm" needs no lookup to be useful.
        _tol_m = float(deviation.get("tolerance") or 0.05)
        stamped = edit_asbuilt.verify_asbuilt(
            model, guids, verified_by=verified_by or "scan", method="laser-scan",
            note=f"p95 deviation within {deviation.get('tolerance')} m", date=date,
            loa_level="measured (scan p95)", tolerance_mm=_tol_m * 1000.0)
        # the measured deviation IS the stated accuracy — without it the stamp claims verification
        # while saying nothing about how closely the model matches what was built
        for r in verified:
            dims += int(edit_asbuilt.record_asbuilt_dimension(
                model, [r["guid"]], "ScanDeviation", float(r["p95_deviation"]),
                design=0.0, tolerance=float(deviation.get("tolerance") or 0.05),
            ).get("stamped") or 0)

    return {
        "applied": bool(apply), "verified": len(verified), "stamped": stamped,
        "accuracy_recorded": dims, "findings": findings, "findings_count": len(findings),
        "uncovered": len(uncovered), "uncovered_guids": uncovered[:200],
        "tolerance": deviation.get("tolerance"),
        "note": "Verified elements are stamped WITH their measured deviation, so the LOD 500 "
                "assertion states its accuracy. Out-of-tolerance elements are returned as findings "
                "and deliberately NOT stamped — verified-as-wrong is a punch item. Uncovered "
                "elements need another scan position; absence of points never becomes evidence.",
    }


def model_surface_points(model, max_points: int = 200000):
    """Triangulated-surface vertices of the IFC model (reference for the deviation query). Iterates
    ifcopenshell.geom; capped at `max_points` so a huge model can't blow memory. Returns an Nx3 list."""
    import ifcopenshell.geom as geom
    import numpy as np

    settings = geom.settings()
    verts: list = []
    from aec_data.geomconf import bounded_iterator  # type: ignore
    it = bounded_iterator(geom, settings, model, num_threads=1)
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
