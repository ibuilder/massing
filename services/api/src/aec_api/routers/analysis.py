"""Analysis & QA endpoints (guide COORDINATION + ANALYSIS): clash detection (Navisworks
parity) and IDS validation (Bonsai parity). Both read the project's source IFC."""
from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, HTTPException, Query, Response, UploadFile
from sqlalchemy.orm import Session

from .. import audit, bcf_io, storage
from ..db import get_db
from ..deps import open_source_ifc
from ..deps import source_ifc_path as _source_ifc
from ..models import Project, ProjectModel, Topic
from ..rbac import require_role

_DATA_SRC = Path(__file__).resolve().parents[4] / "data" / "src"
if str(_DATA_SRC) not in sys.path:
    sys.path.insert(0, str(_DATA_SRC))

router = APIRouter()


def _classes(csv: str | None) -> list[str] | None:
    return [c.strip() for c in csv.split(",") if c.strip()] if csv else None


@router.post("/projects/{pid}/clash")
def run_clash(
    pid: str,
    a: str | None = None,
    b: str | None = None,
    min_volume: float = 1e-3,
    tolerance: float = 0.0,
    narrow: bool = True,
    max_narrow: int = 1500,
    create_topics: bool = False,
    limit: int = 200,
    db: Session = Depends(get_db),
    actor: str = Depends(require_role("editor")),
):
    """Detect clashes between two IFC-class groups (comma-separated in `a` / `b`).
    narrow=true runs the mesh boolean-intersection narrow phase (exact penetration volume).
    With create_topics=true, the top clashes become BCF `clash` topics (pins/issues)."""
    from aec_data import clash  # type: ignore

    ifc = _source_ifc(db, pid)
    results = clash.detect_file(ifc, _classes(a), _classes(b), min_volume, tolerance,
                               narrow=narrow, max_narrow=max_narrow)

    created = 0
    if create_topics:
        for c in results[:limit]:
            t = Topic(
                project_id=pid, type="clash", status="open",
                title=f"Clash: {c['a_class']} × {c['b_class']} ({c['method']} vol {c['volume']})",
                anchor=c["point"], element_guids=[c["a_guid"], c["b_guid"]],
            )
            db.add(t)
            created += 1
        audit.record(db, action="clash.create_topics", actor=actor, method="POST",
                     path=f"/projects/{pid}/clash", detail={"created": created})
        db.commit()

    return {"count": len(results), "created_topics": created, "clashes": results[:limit],
            "truncated": len(results) > limit}


@router.post("/projects/{pid}/clash/federated")
def run_clash_federated(
    pid: str,
    disciplines: dict = Body(default={}, embed=True),  # optional {"STR": "/path/str.ifc", …}
    min_volume: float = 1e-3,
    create_topics: bool = False,
    coordinate: bool = False,
    limit: int = 200,
    db: Session = Depends(get_db),
    actor: str = Depends(require_role("editor")),
):
    """Cross-discipline (federated) clash across 2+ models. Intra-model overlaps are excluded.
    If no `disciplines` map is given, it's built from the project's own models — the primary source
    IFC + any appended discipline models (POST /projects/{pid}/models). `create_topics=true` dumps the
    top clashes as raw BCF clash topics; **`coordinate=true`** instead runs the intelligence layer —
    grouping the raw clashes into tracked `coordination_issue`s, scoring severity, and reconciling
    against the prior run (new / active / resolved / reappeared)."""
    from aec_data import clash  # type: ignore

    valid = {k: v for k, v in (disciplines or {}).items() if v and Path(v).exists()}
    if not valid:                                   # auto-build from the project's model registry
        p = db.get(Project, pid)
        if p and p.source_ifc and Path(p.source_ifc).exists():
            valid["Source"] = p.source_ifc
        for m in db.query(ProjectModel).filter_by(project_id=pid):
            if Path(m.ifc_path).exists():
                key = m.discipline if m.discipline not in valid else f"{m.discipline} ({m.id[:4]})"
                valid[key] = m.ifc_path
    if len(valid) < 2:
        raise HTTPException(409, 'need >=2 accessible discipline models — append one via "Open IFC as discipline"')
    results = clash.detect_federated_files(valid, min_volume=min_volume)

    coordination = None
    if coordinate:
        from .. import clash_intel, rbac
        coordination = clash_intel.coordinate(db, pid, results, actor,
                                              rbac.party_role_for(db, pid, actor),
                                              label=f"Federated {', '.join(sorted(valid))}")
        audit.record(db, action="clash.coordinate", actor=actor, method="POST",
                     path=f"/projects/{pid}/clash/federated", detail=coordination)

    created = 0
    if create_topics and not coordinate:
        for c in results[:limit]:
            db.add(Topic(
                project_id=pid, type="clash", status="open",
                title=f"Clash: {c['a_model']}:{c['a_class']} × {c['b_model']}:{c['b_class']} "
                      f"({c['method']} vol {c['volume']})",
                anchor=c["point"], element_guids=[c["a_guid"], c["b_guid"]]))
            created += 1
        audit.record(db, action="clash.federated", actor=actor, method="POST",
                     path=f"/projects/{pid}/clash/federated", detail={"created": created})
        db.commit()

    return {"disciplines": list(valid), "count": len(results), "created_topics": created,
            "coordination": coordination, "clashes": results[:limit], "truncated": len(results) > limit}


@router.post("/projects/{pid}/clash/coordinate")
def coordinate_clashes(
    pid: str,
    body: dict = Body(default={}),
    db: Session = Depends(get_db),
    actor: str = Depends(require_role("editor")),
):
    """Group + score + reconcile a clash result set into tracked coordination issues. Body:
    `{clashes:[{a_guid,b_guid,a_class,b_class,a_model?,b_model?,volume,point:{x,y,z}}, …], label?}`.
    Lets a client run detection (federated or single) and post the results for the intelligence pass."""
    from .. import clash_intel, rbac
    clashes = body.get("clashes") or []
    if not isinstance(clashes, list):
        raise HTTPException(422, "clashes must be a list")
    return clash_intel.coordinate(db, pid, clashes, actor,
                                  rbac.party_role_for(db, pid, actor), label=body.get("label"))


@router.post("/projects/{pid}/clash/analyze")
def analyze_clashes(pid: str, body: dict = Body(default={}), _: str = Depends(require_role("viewer"))):
    """Preview grouping + severity for a clash result set WITHOUT writing any issues (dry run)."""
    from .. import clash_intel
    return clash_intel.analyze(body.get("clashes") or [])


@router.get("/projects/{pid}/clash/metrics")
def clash_metrics(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Clash coordination KPIs — status mix, worst discipline pairs, severity, aging, run burn-down."""
    from .. import clash_intel
    return clash_intel.metrics(db, pid)


# --- Wave 8 ②: model → field layout (PENZD CSV + DXF) + as-built verification --------------------
def _layout_points(db: Session, pid: str, classes: str | None):
    from .. import layout
    model = open_source_ifc(db, pid)
    cls = [c.strip() for c in classes.split(",") if c.strip()] if classes else None
    return layout, layout.points(model, cls)


@router.get("/projects/{pid}/layout/points")
def layout_points(pid: str, classes: str | None = None, limit: int = 500,
                  db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Preview the model's field-layout setout points (georeferenced) — grids + column/footing/opening/
    wall placements, each with its IFC GlobalId. `classes` optionally narrows the IFC classes."""
    _lay, pts = _layout_points(db, pid, classes)
    by_kind: dict[str, int] = {}
    for p in pts:
        by_kind[p["ifc_class"]] = by_kind.get(p["ifc_class"], 0) + 1
    return {"count": len(pts), "by_class": by_kind, "points": pts[:limit], "truncated": len(pts) > limit,
            "note": "Real-world E/N/Z (IfcMapConversion applied when present); Description carries the "
                    "element code + IFC GlobalId for the field round-trip. Export as PENZD CSV or DXF."}


@router.get("/projects/{pid}/layout/points.csv")
def layout_csv(pid: str, classes: str | None = None, order: str = Query("PENZD"),
               delimiter: str = Query(","), db: Session = Depends(get_db),
               _: str = Depends(require_role("viewer"))):
    """PENZD / PNEZD points file for total-station / marking-robot import (configurable column order)."""
    lay, pts = _layout_points(db, pid, classes)
    body = lay.to_penzd_csv(pts, order=order, delimiter=("\t" if delimiter == "tab" else delimiter))
    return Response(body, media_type="text/csv",
                    headers={"Content-Disposition": f'attachment; filename="layout-{order.lower()}.csv"'})


@router.get("/projects/{pid}/layout.dxf")
def layout_dxf(pid: str, classes: str | None = None, db: Session = Depends(get_db),
               _: str = Depends(require_role("viewer"))):
    """Layered DXF layout drawing (points + labels) for floor printers (Dusty-style)."""
    lay, pts = _layout_points(db, pid, classes)
    return Response(lay.to_dxf(pts), media_type="application/dxf",
                    headers={"Content-Disposition": 'attachment; filename="layout.dxf"'})


@router.post("/projects/{pid}/layout/verify")
def layout_verify(pid: str, body: dict = Body(default={}), db: Session = Depends(get_db),
                  _: str = Depends(require_role("viewer"))):
    """Compare as-installed total-station shots to the design setout: `{measured:[{number,e,n,z}, …],
    tolerance_m?, classes?}` → per-point 3-D deviation, flagging points out of tolerance (each anchored
    to its element GlobalId for a field-verification issue)."""
    lay, pts = _layout_points(db, pid, body.get("classes"))
    measured = body.get("measured") or []
    if not isinstance(measured, list):
        raise HTTPException(422, "measured must be a list of {number,e,n,z}")
    return lay.verify(pts, measured, float(body.get("tolerance_m", 0.02)))


# --- Wave 8 ③b: schedule-linked verified-as-built progress ----------------------------------------
def _index_elements(pid: str) -> list[dict]:
    """The published element index (guid, ifc_class, storey) for the verified-progress rollup."""
    import json
    try:
        return json.loads(storage.get(f"{pid}/props.json")).get("elements", [])
    except Exception:                                  # noqa: BLE001 — no published index yet
        return []


@router.get("/projects/{pid}/verified-progress")
def verified_progress_index(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Roll element-level field verification up to each schedule activity: verified-in-place % vs the
    claimed % complete, with the trust gap (claimed − verified) worst-first. No model parse — reads the
    published element index + the field_verification / schedule_activity records."""
    from .. import verified_progress
    return verified_progress.index(db, pid, _index_elements(pid))


@router.post("/projects/{pid}/verified-progress/from-layout")
def verified_progress_from_layout(pid: str, body: dict = Body(default={}), db: Session = Depends(get_db),
                                  actor: str = Depends(require_role("editor"))):
    """Run the as-installed layout check (`{measured, tolerance_m?, classes?}`) and create a
    field_verification record per checked point — in-tolerance → verified, out-of-tolerance → deviated,
    each anchored to its element GlobalId. Then returns the refreshed verified-progress rollup."""
    from .. import rbac, verified_progress
    lay, pts = _layout_points(db, pid, body.get("classes"))
    measured = body.get("measured") or []
    if not isinstance(measured, list):
        raise HTTPException(422, "measured must be a list of {number,e,n,z}")
    vr = lay.verify(pts, measured, float(body.get("tolerance_m", 0.02)))
    seeded = verified_progress.seed_from_layout(db, pid, vr, actor, rbac.party_role_for(db, pid, actor))
    return {"seeded": seeded, "verify": {k: vr[k] for k in ("checked", "in_tolerance", "out_of_tolerance")},
            "progress": verified_progress.index(db, pid, _index_elements(pid))}


# --- Wave 8 ④: preliminary gravity load takedown + ASCE 7 combinations ---------------------------
@router.get("/projects/{pid}/loads/defaults")
def loads_defaults(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Pre-fill the load takedown from the model — storey names/count + interior-column count."""
    from .. import loads
    return loads.from_model(open_source_ifc(db, pid))


@router.post("/projects/{pid}/loads/takedown")
def loads_takedown(pid: str, body: dict = Body(default={}), db: Session = Depends(get_db),
                   _: str = Depends(require_role("viewer"))):
    """Preliminary gravity load takedown for a typical interior column → per-storey rows + accumulated
    service/factored (ASCE 7) axial to the footing. Body: explicit `storeys:[{name,area_sf,occupancy,
    roof?}]`, OR `{storey_count, floor_area_sf, occupancy}` to auto-build uniform storeys (top = roof);
    plus `sdl_psf?, slab_thickness_in?, column_count?, concrete_pcf?`. Missing counts fall back to the
    model. **Preliminary only — not a substitute for a licensed structural engineer.**"""
    from .. import loads
    storeys = body.get("storeys")
    col = body.get("column_count")
    if not storeys:
        area = float(body.get("floor_area_sf", 0) or 0)
        if area <= 0:
            raise HTTPException(422, "provide `storeys:[…]` or a positive `floor_area_sf` (+ optional storey_count)")
        n = int(body.get("storey_count") or 0)
        if n <= 0 or col is None:
            dm = loads.from_model(open_source_ifc(db, pid))
            n = n or dm["storey_count"] or 1
            col = col if col is not None else (dm["column_count"] or 12)
        occ = body.get("occupancy") or "office"
        storeys = [{"name": f"Level {n - i}", "area_sf": area, "occupancy": occ, "roof": i == 0}
                   for i in range(n)]
    return loads.takedown(storeys, sdl_psf=float(body.get("sdl_psf", 20.0)),
                          slab_thickness_in=float(body.get("slab_thickness_in", 8.0)),
                          concrete_pcf=float(body.get("concrete_pcf", loads.CONCRETE_PCF)),
                          column_count=int(col or 12))


@router.get("/projects/{pid}/models/georeferencing")
def model_georeferencing(pid: str, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """Shared-coordinates / setout basis for the project's source model — full IfcMapConversion
    (eastings/northings/height, true-north bearing, scale) + IfcProjectedCRS (EPSG, datums) + LoGeoRef
    level. The survey basis a coordinator needs for federation and BIM-to-field layout. 409 if no IFC."""
    from .. import georef
    return georef.georeferencing(open_source_ifc(db, pid))


@router.post("/projects/{pid}/scan/deviation")
async def scan_deviation(pid: str, file: UploadFile = File(...), tolerance: float = Query(0.05, gt=0),
                         db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """Scan-to-BIM deviation — compare an uploaded as-built point cloud (XYZ/CSV) against the source
    model's surface and report % within tolerance + a deviation histogram (the QA/QC as-built check).
    409 if no source IFC; 400 on a point cloud we can't read."""
    import ifcopenshell  # type: ignore
    from starlette.concurrency import run_in_threadpool

    from .. import scan_deviation as sd
    ifc_path = _source_ifc(db, pid)  # 409 if the project has no accessible source IFC
    raw = await file.read()
    # The point-cloud parse and — far heavier — the IFC open + full tessellation are CPU-bound and
    # would block the event loop (stalling every other request on this worker) if run inline. Offload
    # to the threadpool, mirroring run_validate below.
    pts = await run_in_threadpool(lambda: sd.parse_point_cloud(raw.decode("utf-8", "ignore")))
    if len(pts) == 0:
        raise HTTPException(400, "no readable XYZ points in the upload")
    try:
        ref = await run_in_threadpool(lambda: sd.model_surface_points(ifcopenshell.open(ifc_path)))
    except Exception as e:  # noqa: BLE001 — geometry failure is a 4xx, not a 500
        raise HTTPException(400, f"could not build model geometry: {e}") from e
    if len(ref) == 0:
        raise HTTPException(409, "the model has no triangulated geometry to compare against")
    return await run_in_threadpool(lambda: sd.analyze(pts, ref, tolerance))


@router.get("/projects/{pid}/ai-readiness")
def ai_readiness_scorecard(pid: str, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """AI / data-readiness scorecard — grades the project 0-100 on single-source-of-truth, information
    completeness, model integrity and governance ("can an agent act on this data yet?")."""
    from .. import ai_readiness
    p = db.get(Project, pid)
    ifc = p.source_ifc if (p and p.source_ifc and Path(p.source_ifc).exists()) else None
    return ai_readiness.scorecard(db, pid, ifc_path=ifc)


@router.get("/projects/{pid}/models/qa")
def model_qa_report(pid: str, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """Model integrity / hygiene scan of the source IFC — duplicate GUIDs, orphaned (no-storey)
    elements, overlapping duplicates, unenclosed spaces and blank names. Complements the LOIN/IDS
    data-quality checks. 409 if the project has no source IFC."""
    from .. import model_qa
    return model_qa.model_qa(open_source_ifc(db, pid))


@router.get("/projects/{pid}/models/alignment")
def model_alignment(pid: str, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """Federation alignment report — do the project's discipline models share the same storey scheme
    and georeferenced origin? The #1 coordination problem is models on different origins/levels; this
    reads each model's storey elevations + IfcMapConversion and flags mismatches (a lightweight
    companion to federated clash). Reads the models read-only."""
    import ifcopenshell  # type: ignore

    from aec_data import drawings  # type: ignore

    files: dict[str, str] = {}
    p = db.get(Project, pid)
    if p and p.source_ifc and Path(p.source_ifc).exists():
        files["Source"] = p.source_ifc
    for m in db.query(ProjectModel).filter_by(project_id=pid):
        if Path(m.ifc_path).exists():
            key = m.discipline if m.discipline not in files else f"{m.discipline} ({m.id[:4]})"
            files[key] = m.ifc_path
    if len(files) < 2:
        raise HTTPException(409, 'need >=2 accessible models — append one via "Open IFC as discipline"')

    def _georef(model) -> dict | None:
        for mc in model.by_type("IfcMapConversion"):
            return {"eastings": getattr(mc, "Eastings", None), "northings": getattr(mc, "Northings", None),
                    "height": getattr(mc, "OrthogonalHeight", None)}
        for site in model.by_type("IfcSite"):
            if getattr(site, "RefLatitude", None) or getattr(site, "RefLongitude", None):
                return {"ref_latitude": site.RefLatitude, "ref_longitude": site.RefLongitude,
                        "ref_elevation": getattr(site, "RefElevation", None)}
        return None

    models = []
    for name, path in files.items():
        try:
            mdl = ifcopenshell.open(path)
            storeys = drawings.storey_elevations(mdl)
            models.append({"name": name, "storey_count": len(storeys),
                           "storeys": storeys, "georef": _georef(mdl)})
        except Exception as e:                           # noqa: BLE001 — a bad file shouldn't 500 the report
            models.append({"name": name, "error": str(e), "storey_count": 0, "storeys": [], "georef": None})

    ok = [m for m in models if "error" not in m]
    issues = []
    if len(ok) >= 2:
        ref = ok[0]
        ref_elevs = sorted(round(s["elevation"], 2) for s in ref["storeys"])
        for m in ok[1:]:
            if m["storey_count"] != ref["storey_count"]:
                issues.append({"type": "storey_count", "severity": "medium", "model": m["name"],
                               "detail": f"{m['storey_count']} storeys vs {ref['storey_count']} in '{ref['name']}'."})
            elevs = sorted(round(s["elevation"], 2) for s in m["storeys"])
            if elevs and ref_elevs and any(abs(a - b) > 0.05 for a, b in zip(elevs, ref_elevs)):
                issues.append({"type": "storey_elevation", "severity": "high", "model": m["name"],
                               "detail": f"Storey elevations differ from '{ref['name']}' — models may be on different datums."})
            g0, g1 = ref.get("georef"), m.get("georef")
            if g0 and g1 and "eastings" in g0 and "eastings" in g1:
                de = abs((g0.get("eastings") or 0) - (g1.get("eastings") or 0))
                dn = abs((g0.get("northings") or 0) - (g1.get("northings") or 0))
                if de > 0.1 or dn > 0.1:
                    issues.append({"type": "georef_origin", "severity": "high", "model": m["name"],
                                   "detail": f"Survey origin differs by E {de:.2f} / N {dn:.2f} m from '{ref['name']}' — align to a shared origin."})
            elif bool(g0) != bool(g1):
                issues.append({"type": "georef_missing", "severity": "low", "model": m["name"],
                               "detail": "One model is georeferenced (IfcMapConversion) and the other is not."})
    return {"models": models, "issues": issues, "aligned": not issues,
            "message": ("Models share a consistent storey scheme and origin." if not issues
                        else f"{len(issues)} alignment issue(s) found across {len(ok)} models.")}


@router.get("/projects/{pid}/quantities/disciplines")
def discipline_quantities(pid: str, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """Discipline quantity roll-up — reinforcement tonnage, MEP linear runs (duct/pipe/cable) + fitting
    counts, and structural element volume, from the IFC (Qto psets with a geometry fallback)."""
    from aec_data import qto  # type: ignore
    return qto.discipline_summary_file(_source_ifc(db, pid))


@router.get("/projects/{pid}/energy")
def energy(pid: str, u_wall: float | None = None, u_window: float | None = None,
           ach: float | None = None, hdd: float | None = None, cdd: float | None = None,
           delta_t: float | None = None, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """Envelope energy analysis (UA + degree-day) computed from the model geometry.
    Construction U-values and climate degree-days are overridable via query params."""
    from aec_data import energy as en  # type: ignore

    overrides = {k: v for k, v in {"u_wall": u_wall, "u_window": u_window, "ach": ach,
                                   "hdd": hdd, "cdd": cdd, "delta_t": delta_t}.items() if v is not None}
    return en.analyze_file(_source_ifc(db, pid), overrides)


@router.get("/projects/{pid}/mep")
def mep(pid: str, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """MEP systems inventory from the model."""
    from aec_data import energy as en  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    return en.mep_inventory(open_model(_source_ifc(db, pid)))


def _ids_key(pid: str) -> str:
    """Object-storage key for a project's pinned IDS (the information-delivery specification the
    model must satisfy) — so an EIR/BEP-mandated IDS lives with the project and validation can run
    against it without re-uploading every time."""
    return f"{pid}/ids/project.ids"


@router.put("/projects/{pid}/ids")
async def put_project_ids(pid: str, file: UploadFile = File(...), db: Session = Depends(get_db),
                          actor: str = Depends(require_role("editor"))):
    """Pin the project's IDS. Subsequent `/validate` calls (with no uploaded file) run against it."""
    data = await file.read()
    if not data.strip():
        raise HTTPException(400, "empty IDS file")
    storage.put(_ids_key(pid), data)
    audit.record(db, action="ids.store", actor=actor, method="PUT", path=f"/projects/{pid}/ids",
                 detail={"bytes": len(data), "filename": file.filename})
    db.commit()
    return {"stored": True, "bytes": len(data)}


@router.get("/projects/{pid}/ids")
def get_project_ids(pid: str, download: bool = Query(False), _sec: str = Depends(require_role("viewer"))):
    """Whether a project IDS is pinned (+ its size); `?download=1` streams the .ids back."""
    key = _ids_key(pid)
    if not storage.exists(key):
        if download:
            raise HTTPException(404, "no IDS pinned for this project")
        return {"exists": False, "bytes": 0}
    if download:
        return Response(content=storage.get(key), media_type="application/xml", headers={
            "Content-Disposition": 'attachment; filename="project.ids"'})
    return {"exists": True, "bytes": storage.size(key)}


@router.delete("/projects/{pid}/ids")
def delete_project_ids(pid: str, db: Session = Depends(get_db),
                       actor: str = Depends(require_role("editor"))):
    key = _ids_key(pid)
    existed = storage.exists(key)
    if existed:
        storage.delete(key)
        audit.record(db, action="ids.delete", actor=actor, method="DELETE", path=f"/projects/{pid}/ids")
        db.commit()
    return {"deleted": existed}


@router.post("/projects/{pid}/validate")
async def run_validate(
    pid: str,
    file: UploadFile | None = File(default=None),
    format: str = Query("json", pattern="^(json|bcf)$"),
    ids: str = Query("auto", pattern="^(auto|stored|default)$"),
    db: Session = Depends(get_db),
    _sec: str = Depends(require_role("viewer")),
):
    """Validate the source IFC against an IDS. Precedence: an **uploaded** `.ids` wins; otherwise
    `ids=auto` (default) uses the project's **pinned** IDS when one exists, else the built-in QA
    specs. `ids=stored` forces the pinned IDS (404 if none); `ids=default` forces the built-in specs.

    `format=json` (default) returns the per-specification pass/fail summary. `format=bcf` returns a
    **.bcfzip punch list of the non-conformances** — one topic per failing specification, its failing
    elements selected as components — so an IDS audit round-trips into Solibri / ACC / BIMcollab like
    any other coordination issue."""
    from aec_data import validate  # type: ignore

    ifc = _source_ifc(db, pid)
    ids_path = None
    ids_bytes: bytes | None = None
    if file is not None:
        ids_bytes = await file.read()                       # an explicit upload always wins
    elif ids in ("auto", "stored") and storage.exists(_ids_key(pid)):
        ids_bytes = storage.get(_ids_key(pid))              # fall back to the project's pinned IDS
    elif ids == "stored":
        raise HTTPException(404, "no IDS pinned for this project (PUT /projects/{pid}/ids first)")
    if ids_bytes is not None:                               # None → engine uses the built-in defaults
        # write to the OS temp dir, not the source tree — the container's /app is read-only, and a
        # shared filename would collide across concurrent requests.
        fd, ids_path = tempfile.mkstemp(suffix=".ids")
        with os.fdopen(fd, "wb") as fh:
            fh.write(ids_bytes)
    try:
        # validate_file opens the IFC + runs IDS specs (CPU-bound, seconds+). This endpoint is
        # async, so run it off the event loop or it blocks every other request on this worker.
        from starlette.concurrency import run_in_threadpool
        result = await run_in_threadpool(validate.validate_file, ifc, ids_path)
        if format == "bcf":
            records = validate.failures_to_bcf_records(result)
            data = bcf_io.export_records_bcfzip(records, topic_type="Issue")
            return Response(content=data, media_type="application/octet-stream", headers={
                "Content-Disposition": 'attachment; filename="ids-audit.bcfzip"'})
        return result
    finally:
        if ids_path:
            Path(ids_path).unlink(missing_ok=True)
