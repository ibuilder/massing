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
from ..models import Project, ProjectModel, Topic, Viewpoint


def _clash_viewpoint(point: dict | None, guids: list[str]) -> Viewpoint | None:
    """CLASH-WALKTHROUGH: a deterministic framed viewpoint for a clash — camera at a fixed diagonal
    standoff from the clash point, target = the point, components = the offending pair. Reopening the
    topic (or stepping the clash list in walk mode) lands the reviewer right at the clash."""
    if not point or not all(k in point for k in ("x", "y", "z")):
        return None
    d = 4.0 / (3 ** 0.5)                     # 4 m diagonal standoff, slightly elevated
    return Viewpoint(
        camera={"type": "perspective",
                "position": {"x": point["x"] + d, "y": point["y"] + d, "z": point["z"] + d},
                "target": {"x": point["x"], "y": point["y"], "z": point["z"]}, "fov": 60},
        components=[g for g in guids if g],
    )


def clash_topic_identity(_title: str, guids: list | None) -> tuple[str, ...]:
    """Same two GlobalIds = the same clash, even if the title's volume string drifts."""
    return tuple(sorted(str(g) for g in (guids or []) if g))


def load_clash_identities(db: Session, pid: str) -> set[tuple[str, ...]]:
    """Open clash topics already filed for this project, keyed by the GUID pair.

    Creating the same clash twice (a retry after topics committed, or a second Run) must not mint
    a second Topic — the Issues panel would double and BCF export would carry duplicates.
    """
    found: set[tuple[str, ...]] = set()
    for t in db.query(Topic).filter(Topic.project_id == pid, Topic.type == "clash"):
        found.add(clash_topic_identity(t.title, t.element_guids))
    return found
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
    a_q: str | None = None,
    b_q: str | None = None,
    min_volume: float = 1e-3,
    tolerance: float = 0.0,
    narrow: bool = True,
    max_narrow: int = 1500,
    create_topics: bool = False,
    limit: int = 200,
    db: Session = Depends(get_db),
    actor: str = Depends(require_role("editor")),
):
    """Detect clashes between two element groups: IFC-class lists (comma-separated `a`/`b`) and/or
    QUERY-DSL selectors (`a_q`/`b_q`, e.g. `IfcDuctSegment & storey=L3`) — selectors scope a side to
    the matching GUID set, composing with the class filter. narrow=true runs the mesh
    boolean-intersection narrow phase. With create_topics=true, top clashes become BCF topics."""
    from aec_data import clash  # type: ignore

    def _sel(q: str | None) -> set[str] | None:
        if not q:
            return None
        from .. import query_dsl
        from .properties import _INDEX, _ensure_loaded
        _ensure_loaded(pid)
        try:
            return set(query_dsl.select(_INDEX.get(pid), q, limit=20000)["guids"])
        except query_dsl.QueryError as e:
            raise HTTPException(422, f"bad selector: {e}")

    ifc = _source_ifc(db, pid)
    results = clash.detect_file(ifc, _classes(a), _classes(b), min_volume, tolerance,
                               narrow=narrow, max_narrow=max_narrow,
                               guids_a=_sel(a_q), guids_b=_sel(b_q))

    created = 0
    if create_topics:
        seen = load_clash_identities(db, pid)
        for c in results[:limit]:
            title = f"Clash: {c['a_class']} × {c['b_class']} ({c['method']} vol {c['volume']})"
            ident = clash_topic_identity(title, [c["a_guid"], c["b_guid"]])
            if ident in seen:
                continue
            seen.add(ident)
            t = Topic(
                project_id=pid, type="clash", status="open",
                title=title,
                anchor=c["point"], element_guids=[c["a_guid"], c["b_guid"]],
            )
            db.add(t)
            vp = _clash_viewpoint(c.get("point"), [c["a_guid"], c["b_guid"]])   # CLASH-WALKTHROUGH
            if vp is not None:
                t.viewpoints.append(vp)
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

    # the ONLY IFC paths this project may federate — its own source + registered discipline models.
    # A client-supplied `disciplines` map may *select* from these, but never inject an arbitrary path
    # (that would be authenticated arbitrary-file read). Build the allow-list first, then intersect.
    p = db.get(Project, pid)
    allowed: set[str] = set()
    if p and p.source_ifc:
        allowed.add(p.source_ifc)
    registry = list(db.query(ProjectModel).filter_by(project_id=pid))
    allowed.update(m.ifc_path for m in registry)

    valid = {k: v for k, v in (disciplines or {}).items()
             if v in allowed and Path(v).exists()}
    if not valid:                                   # auto-build from the project's model registry
        if p and p.source_ifc and Path(p.source_ifc).exists():
            valid["Source"] = p.source_ifc
        for m in registry:
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
        seen = load_clash_identities(db, pid)
        for c in results[:limit]:
            title = (f"Clash: {c['a_model']}:{c['a_class']} × {c['b_model']}:{c['b_class']} "
                     f"({c['method']} vol {c['volume']})")
            ident = clash_topic_identity(title, [c["a_guid"], c["b_guid"]])
            if ident in seen:
                continue
            seen.add(ident)
            t = Topic(
                project_id=pid, type="clash", status="open",
                title=title,
                anchor=c["point"], element_guids=[c["a_guid"], c["b_guid"]])
            db.add(t)
            vp = _clash_viewpoint(c.get("point"), [c["a_guid"], c["b_guid"]])   # CLASH-WALKTHROUGH
            if vp is not None:
                t.viewpoints.append(vp)
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


@router.post("/projects/{pid}/clash/matrix")
def clash_matrix(pid: str, body: dict = Body(default={}), _: str = Depends(require_role("viewer"))):
    """R21-SOFT-CLASH — the discipline-pair coordination matrix.

    Every pair is `clashes`, `clean` or **`untested`**, and the third is the point: a pair nobody ran
    is reported as untested and never folded into the clean count, so "clash-free" cannot be claimed
    over a partial matrix. `coordinated` is true only at full coverage with zero findings.
    """
    from .. import soft_clash
    pairs = [(p[0], p[1]) for p in (body.get("tested_pairs") or [])
             if isinstance(p, (list, tuple)) and len(p) >= 2]
    return soft_clash.matrix(body.get("disciplines") or [], pairs, body.get("findings") or [])


@router.get("/projects/{pid}/clash/sequence")
def clash_sequence(pid: str, min_overlap_days: int = 1, crew_threshold: int = 0,
                   db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """R21-4D-CLASH — space contention plus install-before-support.

    Space contention: two trades scheduled into one location in one window. Nothing in the model is
    wrong when this happens — every element clears every other — which is why a geometric clash run
    cannot find it. Same-trade overlap is not a finding (one trade sequencing its own crews is
    planning). Activities without a location or dates are skipped and counted, so a clean result is
    never claimed over a schedule that was half unreadable.

    Install-before-support reads directed pairs from the source IFC (`support_graph`) and the
    activities' `element_guids`. A project with a schedule but no IFC still returns space contention;
    the support half reports as checked-with-zero-pairs rather than inventing geometry.
    """
    from aec_data.support_graph import connection_graph, directed_install_pairs

    from .. import modules as me
    from .. import sequence_clash
    acts = me.list_records(db, "schedule_activity", pid, limit=sequence_clash.MAX_ACTIVITIES) \
        if "schedule_activity" in me.TABLES else []
    # Empty list, not None: the engine must record that the support half RAN. None would leave
    # not_covered claiming the binding exists but nobody asked, which is a lie on this route.
    support_pairs: list = []
    try:
        model = open_source_ifc(db, pid)
        support_pairs = directed_install_pairs(connection_graph(model), model)
    except HTTPException as e:
        if e.status_code != 409:
            raise
    return sequence_clash.analyze(acts, min_overlap_days=min_overlap_days,
                                  crew_threshold=crew_threshold, support_pairs=support_pairs)


@router.get("/projects/{pid}/clash/clearance-rules")
def clash_clearance_rules(pid: str, _: str = Depends(require_role("viewer"))):
    """The soft-clash clearance rules — each with the code or manufacturer basis it came from, so a
    finding can be argued with rather than merely asserted."""
    from .. import soft_clash
    return {"rules": soft_clash.CLEARANCE_RULES, "classes": soft_clash.scoped_classes(),
            "note": "A class with no stated rule gets NO clearance rather than a default distance."}


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


def _run_estimate(pid: str, body: dict) -> dict:
    """Price the model. Shared by `/cost/estimate` and `/cost/sov` so the schedule of values can never
    be built from a *different* estimate than the one the estimate endpoint returns — two code paths
    computing "the estimate" is exactly how a billed number stops matching the priced one."""
    from .. import fived
    from .standards import _idx_for
    # R25-QTO-WIRE: measure the MODEL. A rate is only as good as what it multiplies, and an
    # estimate whose quantities arrive in the request body can be internally consistent while
    # describing a different building. A caller-supplied `quantities` is still honoured — an
    # estimator legitimately overrides a measured quantity — but it now *overrides* the model's
    # own number rather than being the only source of one, and each line reports which it used.
    measured, sources = {}, {}
    try:
        from aec_data import qto

        from ..db import SessionLocal
        from ..deps import open_source_ifc
        with SessionLocal() as db:
            m = qto.measure(open_source_ifc(db, pid))
        measured, sources = m["quantities"], m["sources"]
    except Exception:                    # noqa: BLE001 — no model yet: fall back to what was sent
        measured, sources = {}, {}
    override = body.get("quantities") or {}
    for guid, qs in override.items():
        measured.setdefault(guid, {}).update(qs)
        # an overridden quantity is neither declared by the model nor measured from it
        sources.setdefault(guid, {}).update(dict.fromkeys(qs, "override"))
    # R25-COST-VINTAGE: resolve the project's pinned cost database, localized and escalated, so a
    # `rate_from: "vintage"` rule prices off a dated source rather than a bare number. Absent a
    # pinned vintage the map is empty — and a rule that asked for one then lands in `no_rate`
    # rather than being quietly priced from somewhere else.
    vintage_rates, vintage_meta = {}, None
    try:
        from .. import cost_db
        from ..db import SessionLocal
        from ..models import Project
        with SessionLocal() as db2:
            proj = db2.get(Project, pid)
            if proj is not None:
                rates, meta = cost_db.rates_for_project(db2, proj)
                vintage_rates, vintage_meta = rates or {}, meta
    except Exception:                    # noqa: BLE001 — no cost database installed is a valid state
        vintage_rates, vintage_meta = {}, None
    return fived.estimate(_idx_for(pid), body.get("rules") or [], measured, sources=sources,
                          vintage_rates=vintage_rates, vintage=vintage_meta)


@router.post("/projects/{pid}/cost/sov")
def cost_sov(pid: str, body: dict = Body(default={}), db: Session = Depends(get_db),
             _: str = Depends(require_role("viewer"))):
    """R27-SOV-LOOP — build a schedule of values **from** the estimate rather than re-keying it.

    Body: the same `{rules, quantities?}` as `/cost/estimate`, plus `markup_pct` (default 0) and
    `grouping` (`code` | `division` | `line`).

    Every other link in this chain already existed — the estimate measures and prices the model,
    `cost.g703` reads SOV records into a continuation sheet, and the pay-app PDF renders them — but
    nothing joined the first to the second, so the numbers were typed in again and the trace from a
    billed line back to a model element was lost at the one seam where somebody is asking to be paid.

    Read three fields before using the result. `covers_whole_model` is false whenever any scope could
    not be priced, and those elements are listed in `excluded` rather than dropped. `at_cost` is true
    when no markup was supplied — correct for cost-plus, an under-bill on lump sum. And `reconciles`
    proves the regrouping lost no money, **not** that the estimate was right.

    This does not write records: it returns the items for review. Committing them is a separate,
    deliberate act — an SOV that appeared in the register as a side effect of pricing is one nobody
    decided to sign.
    """
    from .. import sov_build
    from ..query_dsl import QueryError
    try:
        est = _run_estimate(pid, body)
        return {"estimate_lines": est["line_count"],
                **sov_build.from_estimate(est,
                                          markup_pct=body.get("markup_pct", 0.0),
                                          grouping=str(body.get("grouping") or "code"))}
    except QueryError as e:
        raise HTTPException(422, str(e)) from None
    except ValueError as e:
        raise HTTPException(422, str(e)) from None


@router.post("/projects/{pid}/cost/estimate")
def cost_estimate(pid: str, body: dict = Body(default={}), db: Session = Depends(get_db),
                  _: str = Depends(require_role("viewer"))):
    """5D — price the model through the QUERY-DSL selector spine.

    Body: `{rules: [{selector, code, description?, basis, unit_cost}], quantities?: {guid: {basis: n}}}`.
    Rules layer: **later rules win**, and every element records which rule priced it, so a line traces
    back to the selector that produced it.

    Two numbers matter as much as the total: `unpriced` (elements no rule matched — never silently
    zeroed, because the total would still look like a total) and `missing_quantity` (a rate with
    nothing to multiply is an unknown cost, not a cost of nothing). `complete` is false whenever
    either is non-empty, which makes the total a floor rather than an estimate.
    """
    from ..query_dsl import QueryError
    try:
        return _run_estimate(pid, body)
    except QueryError as e:
        raise HTTPException(422, str(e)) from None


@router.post("/projects/{pid}/estimate/diff")
def estimate_diff_route(pid: str, body: dict = Body(default={}),
                        _: str = Depends(require_role("viewer"))):
    """R25-ESTIMATE-DIFF — diff two `/estimate` payloads by GlobalId.

    Body: `{before: <estimate>, after: <estimate>}`. Every dollar of the change is attributed to one
    of four causes — `added` / `removed` (scope), `requantified` (the design changed) and `repriced`
    (the estimate changed, not the building) — plus `both` when quantity and rate moved together,
    which is reported as one change rather than split into two half-truths.

    `reconciles` says whether the attributed deltas add back to the difference in totals. A diff whose
    parts do not sum to the whole is worse than no diff: it looks authoritative while losing money.
    """
    from .. import estimate_diff
    before, after = body.get("before") or {}, body.get("after") or {}
    # Validate the shape here rather than letting a malformed payload raise into the global 500
    # handler and land in the error-log feed. The sibling estimate route converts bad input to 422;
    # a diff of two things that are not estimates is a caller error, not a server fault.
    for name, side in (("before", before), ("after", after)):
        if not isinstance(side, dict):
            raise HTTPException(422, f"{name} must be an estimate object")
        if side.get("lines") is not None and not isinstance(side["lines"], list):
            raise HTTPException(422, f"{name}.lines must be a list")
        if side.get("by_element") is not None and not isinstance(side["by_element"], dict):
            raise HTTPException(422, f"{name}.by_element must be an object keyed by GlobalId")
    try:
        return estimate_diff.diff(before, after)
    except (TypeError, ValueError, AttributeError) as e:
        raise HTTPException(422, f"could not diff these estimates: {e}") from None


_PRESETS = ("key", "quad", "plan-pair")     # asserted against sheet_layout.presets in test_sheet_layout
_PAGES = ("ARCH-C", "ARCH-D", "ARCH-B", "ARCH-A", "A0", "A1", "A2", "A3", "A4")
# asserted against drawings.PAGES in test_sheet_layout — two lists, one fact.

# Exported as a constant so no response text is derived from a caught exception (py/stack-trace-exposure).
_CONSTRAINT_REFUSED = ("constraint set refused: check that every entry is an object with a known "
                       "`kind` (fix/equal/distance/offset/equal_spacing/min_clearance), that its "
                       "variables exist, and that the set is within the size limits")


@router.post("/projects/{pid}/constraints/solve")
def constraints_solve(pid: str, body: dict = Body(default={}),
                      _sec: str = Depends(require_role("viewer"))):
    """W10-9 / R23-CONSTRAINTS — solve dimensional locks, or name what stopped them.

    Body: `{variables: {name: value}, constraints: [{kind, a, b?, value?, distance?, offset?, vars?,
    min?, strength?, id?}]}`. Kinds: `fix` · `equal` · `distance` · `offset` · `equal_spacing` ·
    `min_clearance`. Strengths are **tiers, not weights** — `required` · `strong` · `medium` · `weak`
    — each satisfied exactly and frozen before the next may move what is left, so a preference can
    never bend a hard lock by a millimetre.

    Three things it refuses to do quietly. An **over-constrained** system names the constraints that
    cannot hold rather than satisfying whichever was reached first. An **under-constrained** one
    reports its remaining degrees of freedom instead of silently picking one of infinitely many
    solutions. And clearances are **checked, never enforced** — sliding geometry to satisfy a code
    minimum would move something somebody placed on purpose.

    Shipped as an engine in v0.3.701 and left unreachable until v0.3.711; it solved nothing in
    between. Pure computation over caller-supplied values — it neither reads nor writes the model.
    """
    from aec_data import dim_constraints
    try:
        return dim_constraints.solve(body.get("variables") or {}, body.get("constraints") or [])
    except dim_constraints.ConstraintError:
        # A fixed message: nothing in the response derives from the caught exception. The refusal is
        # what the caller needs to act on, and `conflicts` — the interesting case — comes back as a
        # normal 200 result rather than an error.
        raise HTTPException(422, _CONSTRAINT_REFUSED) from None


@router.get("/projects/{pid}/georeference")
def project_georeference(pid: str, db: Session = Depends(get_db),
                         _: str = Depends(require_role("viewer"))):
    """Where this model sits on the earth, in the kernel's `GeoReference` shape.

    `method` matters as much as the coordinates: `map-conversion` is a survey transform out of IFC4's
    `IfcMapConversion`, `site-coordinates` is only `IfcSite` lat/long (all IFC2X3 can carry), and
    `null` means the model is not georeferenced at all. Those differ by orders of magnitude in what
    they can be used for — a site coordinate will put a pin on a map and must not be used to set out.

    A model with no georeferencing reports `georeferenced: false` rather than defaulting to (0, 0):
    null island is a real place, and a wrong answer shaped like a right one is the failure this
    codebase keeps finding.
    """
    from aec_data import geo  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore
    return geo.read(open_model(_source_ifc(db, pid)))


@router.get("/projects/{pid}/drawings/sheet-regions")
def sheet_regions_endpoint(pid: str, preset: str = "key", page: str = "A1",
                           db: Session = Depends(get_db),
                           _sec: str = Depends(require_role("viewer"))):
    """R27-LAYOUT ①(a) — the sheet's **layout layer**: what occupies which rectangle, in page points.

    This is the producer for the `layout` that `POST /takeoff/2d` accepts. Wiring the consumer without
    it (v0.3.706) left that route asking for something no caller could obtain — the same one-way
    asymmetry `R25-TASK-BIND` existed to close, reintroduced while closing a different instance of it.

    Each region carries `basis: "authored"` — these **are** the numbers the sheet was drawn with, not a
    recovery from rendered output — plus the exact page↔world affine, so a takeoff scoped to a viewport
    needs no calibration step at all. A viewport with no geometry reports `to_page: null`: the mapping
    is **unknown**, never an identity, since an identity would silently report page points as metres.
    """
    from aec_data import sheet_layout
    from aec_data.drawings import bake, storey_elevations

    # Validate the request BEFORE opening the model. `presets()` falls back to "key" for any
    # unrecognised name — right for a library, wrong for a route, where a typo would return a
    # DIFFERENT layout labelled as the one asked for and every page coordinate below it would be
    # honest about the wrong sheet. Checking it first also means a bad preset reports ITSELF rather
    # than whatever the model open happened to complain about.
    if preset not in _PRESETS:
        raise HTTPException(422, f"unknown viewport preset; known: {', '.join(_PRESETS)}")
    # `compose_viewports` used to silently substitute A1; it now refuses. This route still checks
    # first because it ECHOES the requested page back — a 422 here names the typo, not a model error.
    if page not in _PAGES:
        raise HTTPException(422, f"unknown page size; known: {', '.join(_PAGES)}")
    model = open_source_ifc(db, pid)        # raises the project's own 404/409 when there is no model
    vps = sheet_layout.presets(preset)
    layout = sheet_layout.compose_viewports(bake(model), vps, page=page,
                                            levels=storey_elevations(model))
    out = sheet_layout.sheet_regions(layout)
    out["preset"], out["page"] = preset, page
    return out


@router.post("/projects/{pid}/drawings/received-regions")
async def received_sheet_regions(pid: str, file: UploadFile = File(...), page_index: int = Query(0, ge=0),
                                 _db: Session = Depends(get_db),
                                 _sec: str = Depends(require_role("viewer"))):
    """R27-LAYOUT ①(b) — the layout layer of a sheet we did **not** draw.

    `sheet-regions` above answers "what occupies which rectangle" for our own sheets, by keeping the
    numbers `compose_viewports` computed. Every consultant sheet had no such answer: `sheet_extract`
    regexes the text layer with no notion of *where on the page* anything sits, so a note, a takeoff
    or a revision could only attach to a page number. This reads the rectangles out of the page's own
    content stream and classifies them.

    Each region reports `basis: "vector"`. `to_page` is **null for every region** — the page↔world
    mapping cannot be recovered from a received sheet, and an identity would silently report page
    points as metres. Any scale printed on the sheet comes back as `scale_denom_proposed`, for a
    calibration step to accept: a takeoff auto-calibrated wrong looks finished, which is worse than
    one nobody calibrated. A page whose vectors are gone (a scan) returns a stated **unknown** region
    rather than an empty list — an empty list is a claim about the drawing, unknown is a claim about us.
    """
    from .. import sheet_recover
    data = await file.read()
    if not data:
        raise HTTPException(422, "empty upload")
    return sheet_recover.recover_regions(data, page_index)


@router.post("/projects/{pid}/takeoff/2d")
def takeoff_2d(pid: str, body: dict = Body(default={}), db: Session = Depends(get_db),
               _sec: str = Depends(require_role("viewer"))):
    """TAKEOFF-2D: quantify + price regions traced on a 2D drawing (PDF page / scan) — the drawings-only
    case the model takeoff misses. Body: `{scale_units_per_px, unit?, regions:[{category, points, label?}],
    overrides?}` (or supply `calibration:{p1,p2,real_distance}` to derive the scale). Returns per-region +
    per-assembly quantities and cost, feeding the same 5D estimate. **Preliminary — trace/scale dependent.**

    With `layout` (a `sheet_regions` result) and `px_per_point`, two more answers ride along, both
    about *which drawing on the sheet* something sits on: `scope` for the traced regions, and
    `annotation_scope` for an optional `annotations:[{id?, kind?, x, y}]` or `{points:[[x,y],…]}`
    (a revision cloud). Both are omitted entirely when their input is absent."""
    from .. import takeoff2d
    scale = body.get("scale_units_per_px")
    cal = body.get("calibration") or {}
    if scale is None and cal:
        scale = takeoff2d.calibration_scale(cal.get("p1", [0, 0]), cal.get("p2", [1, 0]),
                                            float(cal.get("real_distance", 1.0)))
    # `takeoff2d.valid_scale` rather than `float(scale) <= 0`: the old guard let `inf` through (inf > 0
    # is true), and an infinite scale nulls every quantity AND the grand total while still returning
    # 200 — FastAPI encodes inf as null. It also raised ValueError -> 500 on a non-numeric string.
    # Refusing here is the honest outcome; a takeoff whose scale cannot be measured with has no answer.
    s = takeoff2d.valid_scale(scale)
    if s is None:
        raise HTTPException(422, "a positive, finite scale_units_per_px (or a valid calibration) is "
                                 "required")
    regions = body.get("regions") or []
    out = takeoff2d.quantify(regions, s,
                             unit=str(body.get("unit") or "m"),
                             overrides=body.get("overrides") or {})
    # R27-LAYOUT ②: when the caller supplies the sheet's layout, say which drawing each trace is on.
    # One scale over a whole sheet is right for a sheet holding ONE drawing and quietly wrong for
    # every other — a plan at 1:100 beside a detail at 1:20 prices the detail fivefold. Optional, so
    # the single-drawing case is untouched; supplied, it reports which traces are unscoped (off any
    # drawing — a quantity measured over a legend is not a quantity) or ambiguous (crossing two
    # scales, where no single number is correct).
    layout = body.get("layout")
    # **Both type guards run BEFORE the layout gate, and that placement is the fix for a real bug.**
    # `annotations`' guard originally sat inside `if layout:`, so a request with `annotations: {}` and
    # no layout returned a normal takeoff and dropped the field on the floor — the silent no-op the
    # guard exists to prevent, reintroduced by where it was put. A malformed field is malformed
    # whether or not a different field is present.
    #
    # A wrong TYPE for a whole field is a caller who cannot be answered; one unreadable viewport or
    # one bad annotation row inside a well-formed field is reported instead (`unreadable_viewports`,
    # or `scope: "unknown"`) rather than failing the request.
    if layout is not None and not isinstance(layout, dict):
        raise HTTPException(422, "layout must be a sheet_regions object with a `regions` list")
    if (ann_field := body.get("annotations")) is not None and not isinstance(ann_field, list):
        raise HTTPException(422, "annotations must be a list of {id?, kind?, x, y} or "
                                 "{id?, kind?, points:[[x,y],…]} objects")
    if layout:
        from .. import takeoff_scope
        out["scope"] = takeoff_scope.scope(regions, layout,
                                           px_per_point=body.get("px_per_point"))
        # R27-LAYOUT ③ / R37-TESTED-UNWIRED: the same question for NOTES, keynotes and revision
        # clouds. `scope_annotations` was the item's own named deliverable and this router called
        # `scope` and `check_calibration` and not it — the only one of the three the module exports
        # that nothing could reach.
        #
        # It rides on `layout` and `px_per_point` here rather than on a route of its own because it
        # is not a second engine: its docstring is explicit that an annotation and a traced polygon
        # pose the identical question — which drawing is this on — so it maps annotations onto the
        # same region shape and calls `scope`. A separate route would have duplicated the coordinate
        # contract, and two places to get `px_per_point` wrong is how the two answers drift apart.
        #
        # Optional and absent when not asked for: a caller tracing quantities with no notes gets the
        # response it always got, and `annotation_scope: null` is never emitted as an empty finding.
        annotations = body.get("annotations")
        if annotations:
            out["annotation_scope"] = takeoff_scope.scope_annotations(
                annotations, layout, px_per_point=body.get("px_per_point"))
        # The calibration is checkable against a sheet WE drew: the scale is not something to
        # measure but something already known. Disagreement is REPORTED, never substituted.
        #
        # `takeoff_scope.viewports`, not a second copy of its filter. This line WAS that copy —
        # `[r for r in (layout.get("regions") or []) if r.get("kind") == "viewport"]`, the helper's
        # own body inlined — and it is how the last malformed-layout crash survived hardening the
        # engine: a `layout["regions"]` that is a string iterated its characters here and raised out
        # of `.get`. Two derivations of "which regions are viewports" meant one of them stayed
        # unhardened, which is the failure this session keeps meeting in different clothes.
        vps, _unreadable = takeoff_scope.viewports(layout)
        out["calibration_check"] = [
            {"viewport": v.get("index"), "label": v.get("label"),
             **takeoff_scope.check_calibration(float(scale), v.get("scale_denom"),
                                               px_per_point=body.get("px_per_point"))}
            for v in vps]
    return out


@router.get("/projects/{pid}/models/georeferencing")
def model_georeferencing(pid: str, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """Shared-coordinates / setout basis for the project's source model — full IfcMapConversion
    (eastings/northings/height, true-north bearing, scale) + IfcProjectedCRS (EPSG, datums) + LoGeoRef
    level. The survey basis a coordinator needs for federation and BIM-to-field layout. 409 if no IFC."""
    from .. import georef
    return georef.georeferencing(open_source_ifc(db, pid))


@router.get("/projects/{pid}/models/footprint.geojson")
def model_footprint_geojson(pid: str, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """GIS-OUT — the building footprint + site point as a **WGS84 GeoJSON FeatureCollection**, anchored
    on the model's IfcSite reference lat/long (equirectangular local-tangent transform; building-scale,
    not survey-grade). Drops the model onto a web map / GIS. `available` is false when the model carries
    no site lat/long. 409 if there's no source IFC."""
    from .. import gis_out
    return gis_out.to_geojson(open_source_ifc(db, pid))


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


@router.post("/projects/{pid}/scan/verify-lod500")
async def scan_verify_lod500(pid: str, file: UploadFile = File(...),
                             tolerance: float = Query(0.05, gt=0),
                             apply: bool = Query(True),
                             verified_by: str = Query(""),
                             db: Session = Depends(get_db),
                             _sec: str = Depends(require_role("editor"))):
    """Scan → **LOD 500**: attribute an uploaded point cloud to individual elements and stamp the ones
    that verify.

    `/scan/deviation` compares the cloud to the whole model and returns one aggregate — useful for QA,
    useless for verification, because it cannot say *which* element is right. This runs the query per
    element and turns the result into three outcomes: within tolerance → stamped as field-verified with
    its measured deviation (so the assertion states an accuracy); outside tolerance → returned as a
    finding and deliberately not stamped; never scanned → reported uncovered, because absence of
    points is not evidence.

    `apply=false` returns the same plan without writing, so a team can see what a scan would assert.
    """
    import ifcopenshell  # type: ignore
    from starlette.concurrency import run_in_threadpool

    from .. import scan_deviation as sd
    ifc_path = _source_ifc(db, pid)
    raw = await file.read()
    pts = await run_in_threadpool(lambda: sd.parse_point_cloud(raw.decode("utf-8", "ignore")))
    if len(pts) == 0:
        raise HTTPException(400, "no readable XYZ points in the upload")
    try:
        model = await run_in_threadpool(lambda: ifcopenshell.open(ifc_path))
        dev = await run_in_threadpool(lambda: sd.per_element_deviation(model, pts, tolerance))
    except Exception as e:  # noqa: BLE001 — geometry failure is a 4xx, not a 500
        raise HTTPException(400, f"could not build model geometry: {e}") from e
    if dev.get("error"):
        raise HTTPException(409, str(dev["error"]))
    result = await run_in_threadpool(
        lambda: sd.verify_from_scan(model, dev, verified_by=verified_by, apply=apply))
    if apply and result["stamped"]:
        await run_in_threadpool(lambda: model.write(ifc_path))
    return {**result, "deviation": {k: v for k, v in dev.items() if k != "elements"},
            "elements": dev["elements"][:500]}


@router.get("/projects/{pid}/egress/routes")
def egress_routes(pid: str, elevation: float = 0.0, max_travel_m: float = Query(61.0, gt=0),
                  cell: float = Query(0.3, gt=0.05, le=2.0),
                  db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """D2 — **routed** travel distance to the nearest exit, per space.

    IBC 1017 limits travel distance measured *along the path of egress travel*. The existing
    straight-line check ignores every wall between a space and its exit, so it reports a shorter
    distance than anyone can walk and passes plans that do not comply. This routes over the actual
    floor plate and reports both numbers plus their ratio, so the understatement is visible.

    `max_travel_m` defaults to 61 m (200 ft, IBC 1017.2 sprinklered Business) — occupancy- and
    sprinkler-dependent, so it is a parameter rather than a constant.
    """
    import ifcopenshell  # type: ignore

    from .. import egress_route
    ifc_path = _source_ifc(db, pid)
    try:
        return egress_route.analyze(ifcopenshell.open(ifc_path), elevation, max_travel_m, cell=cell)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/projects/{pid}/egress/plan.svg")
def egress_plan_svg(pid: str, elevation: float = 0.0, max_travel_m: float = Query(61.0, gt=0),
                    cell: float = Query(0.3, gt=0.05, le=2.0),
                    db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """The routed egress / life-safety plan as SVG — walls, exits, and each space's actual path to its
    nearest exit, coloured by outcome so a failing space is findable at a glance."""
    import ifcopenshell  # type: ignore
    from fastapi import Response

    from .. import egress_route
    ifc_path = _source_ifc(db, pid)
    try:
        svg = egress_route.plan_svg(ifcopenshell.open(ifc_path), elevation, max_travel_m, cell=cell)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e
    return Response(svg, media_type="image/svg+xml")


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


@router.get("/projects/{pid}/models/norm-valid")
def model_norm_valid(pid: str, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """NORM-VALID · **normative openBIM conformance** — a validation gauntlet in the spirit of the
    buildingSMART validation service: a recognised FILE_SCHEMA + populated header, a single IfcProject
    with units + a geometric context, valid & unique 22-char GlobalIds, OwnerHistory presence (required
    in IFC2X3), and no physical element outside the spatial structure. Each check reports pass/warn/fail;
    `passed` is true when nothing fails. Complements model_qa (authoring quality) and IDS (data). 409 if
    the project has no source IFC."""
    from aec_data import norm_valid  # type: ignore
    return norm_valid.validate(open_source_ifc(db, pid))


@router.get("/projects/{pid}/models/schema-diag")
def model_schema_diag(pid: str, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """R31-SCHEMA-DIAG · **structural validity against the IFC SCHEMA**, not against a spec.

    The neighbouring endpoints all score the model against *rules*: `/models/qa` is hygiene (duplicate
    GlobalIds, orphans, unenclosed spaces), `/models/norm-valid` is the normative gauntlet, IDS is data
    quality. None of them answers *is this file structurally a valid IFC* — an entity type not declared
    in the schema, a `#12345` that resolves to nothing, an ABSTRACT type instantiated directly, a `$`
    in a slot the schema declares mandatory, an attribute list of the wrong length.

    That is a different failure class, and it matters because we **write** IFC: a model can be 100%
    IDS-compliant and still be rejected on import by another tool. It is also the class a viewer hides
    — the geometry renders, so the file looks fine until somebody else opens it.

    Unlike every sibling here this reads the file as **text and never loads a model**, so it still
    reports on a file `ifcopenshell` cannot open — which is precisely the case a load-based diagnostic
    cannot speak about. Findings carry the instance id, so a fault is locatable in a million-line file.

    409 if the project has no source IFC.
    """
    from aec_data import schema_diag  # type: ignore  # deferred — pulls the ifcopenshell schema wrapper
    return schema_diag.diagnose_file(_source_ifc(db, pid))


@router.get("/projects/{pid}/models/warnings")
def model_warnings_feed(pid: str, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """WARN-1 · **unified model-warnings feed** — every individual defect the hygiene (model_qa) and
    normative-conformance (norm_valid) lenses surface, flattened into one worst-first punch list (fails
    before warns, each with its offender sample for zoom-to-GUID). Where the model-CI badge says pass/warn/
    fail, this is the actionable list behind it. 409 if the project has no source IFC."""
    from .. import model_warnings
    return model_warnings.feed(open_source_ifc(db, pid))


@router.get("/projects/{pid}/models/export-qa")
def model_export_qa(pid: str, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """IFC-QA · **export round-trip fidelity** — writes the source IFC out and reopens it, then compares
    schema / units / entity counts / GlobalId set / storeys / property payload. Proves the re-export is
    lossless (the #1 openBIM complaint is silent loss on export). 409 if the project has no source IFC."""
    from aec_data import roundtrip_qa  # type: ignore
    return roundtrip_qa.roundtrip(open_source_ifc(db, pid))


@router.get("/projects/{pid}/models/health")
def model_health_scorecard(pid: str, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """Composite **Model Health** scorecard — one 0–100 score over the model-quality checks (integrity/
    hygiene, ISO 19650 KPIs, clash coordination, verified-as-built), each lens linking to its tool. Opens
    the source IFC for the hygiene lens when present; the data/coordination/verified lenses work from the
    records + published index, so it still scores without a parsed model."""
    from .. import model_health
    model = None
    try:
        model = open_source_ifc(db, pid)             # enables the hygiene lens; other lenses don't need it
    except Exception:                                # noqa: BLE001 — no source IFC: score the DB-based lenses
        pass
    return model_health.scorecard(db, pid, model=model, elements=_index_elements(pid))


@router.get("/projects/{pid}/model/assets")
def model_assets(pid: str, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """ASSET-REG — the maintainable-asset register derived straight from the IFC: serviceable equipment /
    terminals / controls / transport (subtype-resolved; ducts/pipes/fittings excluded), GUID-keyed, tagged
    with discipline + storey + type, with per-discipline / per-category / per-class tallies. 409 if the
    project has no source IFC."""
    from .. import model_assets as ma
    return ma.assets(open_source_ifc(db, pid))


@router.post("/projects/{pid}/model/assets/seed")
def model_assets_seed(pid: str, db: Session = Depends(get_db), actor: str = Depends(require_role("editor"))):
    """Seed the `asset_register` module from the model-derived assets (idempotent by tag) — turns the IFC
    into a populated FM register in one call, ready for pm_schedule + warranty/serial per asset."""
    from .. import model_assets as ma
    return ma.seed(db, pid, ma.assets(open_source_ifc(db, pid)).get("assets", []), actor)


@router.get("/projects/{pid}/model/equipment")
def model_equipment(pid: str, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """MEP-EQUIP — the procurement equipment schedule derived from the IFC: procurable MEP units grouped by
    class + type into RFQ line-items with a quantity + representative spec (from the model's Psets);
    ducts/pipes/fittings + controls excluded. 409 if the project has no source IFC."""
    from .. import equipment as eq
    return eq.schedule(open_source_ifc(db, pid))


@router.post("/projects/{pid}/model/equipment/spec-check")
def model_equipment_spec_check(pid: str, requirements: dict = Body(default={}, embed=True),
                               db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """MEP-EQUIP SPEC-CONFLICT — cross-check the scheduled equipment against a specified-requirement set
    (`{ifc_class: {spec_key: expected}}`) → the mismatches (a modelled Pset value disagreeing with the
    spec) + missing specified properties. Deterministic; no spec-document scanning. 409 if no source IFC."""
    from .. import equipment as eq
    sched = eq.schedule(open_source_ifc(db, pid))
    return {**eq.spec_conflicts(sched.get("lines", []), requirements or {}),
            "line_count": sched.get("line_count", 0), "unit_count": sched.get("unit_count", 0)}


@router.get("/projects/{pid}/model/equipment/starter-requirements")
def model_equipment_starter(pid: str, db: Session = Depends(get_db),
                            _sec: str = Depends(require_role("viewer"))):
    """MEP-EQUIP — the curated starter requirement set for the spec-check: the properties an engineer
    expects every unit of the common equipment classes to carry before buyout (`"*"` = presence-required).
    Feed it to `/model/equipment/spec-check` as-is or edited."""
    from .. import equipment as eq
    from ..models import Project
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    return {"requirements": eq.STARTER_REQUIREMENTS,
            "note": "\"*\" means the property must be present (any non-empty value passes); replace "
                    "with a concrete value to require it."}


@router.post("/projects/{pid}/model/equipment/to-submittals")
def model_equipment_to_submittals(pid: str, db: Session = Depends(get_db),
                                  actor: str = Depends(require_role("editor"))):
    """MEP-EQUIP tie — mint one **product-data submittal** per scheduled equipment type (idempotent by
    title: re-running after a model change only adds the NEW types). The procurement schedule and the
    submittal log stay one thread. 409 if no source IFC."""
    from .. import equipment as eq
    from .. import rbac
    sched = eq.schedule(open_source_ifc(db, pid))
    return eq.to_submittals(db, pid, sched.get("lines", []), actor, rbac.party_role_for(db, pid, actor))


@router.get("/projects/{pid}/model/equipment/budget-lines")
def model_equipment_budget_lines(pid: str, db: Session = Depends(get_db),
                                 _sec: str = Depends(require_role("viewer"))):
    """MEP-EQUIP tie — the equipment schedule as **budget-suggestion rows** (qty EA per type), priced
    from the project's own price-observation ledger where it has seen the type (median), else unpriced
    for a manual allowance. Read-only. 409 if no source IFC."""
    from .. import equipment as eq
    sched = eq.schedule(open_source_ifc(db, pid))
    return eq.budget_lines(db, pid, sched.get("lines", []))


@router.get("/projects/{pid}/model/space-utilization")
def model_space_utilization(pid: str, area_per_person: float = Query(default=10.0, gt=0, le=1000),
                            db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """SPACE-UTIL — occupancy capacity per `IfcSpace` at the given area-per-person standard, rolled up by
    space type + totals. Pure arithmetic over the modelled net floor areas. 409 if no source IFC."""
    from .. import space_util as su
    return su.from_model(open_source_ifc(db, pid), area_per_person)


@router.post("/projects/{pid}/model/space-demand")
def model_space_demand(pid: str, program: dict = Body(default={}, embed=True),
                       area_per_person: float = Body(default=10.0, embed=True),
                       db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """SPACE-UTIL — a headcount `program` (`{space_type: headcount}`) vs. the modelled inventory → required
    vs. supplied area + the gap (deficit/surplus) per type. Deterministic supply/demand planner."""
    from .. import space_util as su
    return su.demand(su._spaces_from_model(open_source_ifc(db, pid)), program or {}, area_per_person)


@router.get("/projects/{pid}/model/design-metrics")
def model_design_metrics(pid: str, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """DESIGN-METRICS — program-efficiency numbers over the model (floors · GFA · net floor area ·
    net-to-gross · unit count · area by space type) + a deterministic **average-daylight-factor estimate**
    from the model's actual windows (glazed area vs net floor area, CIBSE formula — not ray-traced).
    409 if the project has no source IFC."""
    from .. import design_metrics as dm
    return dm.metrics(open_source_ifc(db, pid))


@router.post("/projects/{pid}/model/adjacency")
def model_adjacency(pid: str, program: dict = Body(default={}), db: Session = Depends(get_db),
                    _sec: str = Depends(require_role("viewer"))):
    """TESTFIT-ADJ — adjacency + dimensional-compliance over the model's IfcSpaces: which spaces physically
    touch (bboxes within a wall gap on the same storey), scored against a program's `required_adjacent` /
    `forbidden` type-pairs, plus a dimensional rule pack (`min_room_dim` · `min_area` · `min_ceiling_height`,
    global or `by_type`). Deterministic, no OCC (footprints from the extruded profiles). 409 without a
    source IFC. Body: {required_adjacent, forbidden, dimensional}."""
    from aec_data import adjacency as adj  # type: ignore
    return adj.evaluate(open_source_ifc(db, pid), program)


@router.get("/projects/{pid}/model/constraints")
def model_constraints(pid: str, db: Session = Depends(get_db),
                      _sec: str = Depends(require_role("viewer"))):
    """AUTH-CONSTRAINTS ① (R18) — validate the model's OWN constraint graph (RelVoids/RelFills hosts,
    storey containment): broken hosts and dangling fills are **errors**, missing containment and
    level/elevation disagreements are **warnings**, bare openings and unhosted inserts informational.
    Placement checks (an insert outside its host wall's extent) are attribute-based, no OCC; anything
    unmeasurable is skipped and counted, never guessed. 409 without a source IFC."""
    from aec_data import constraints  # type: ignore
    return constraints.check(open_source_ifc(db, pid))


@router.get("/projects/{pid}/model/element/{guid}/effective-props")
def element_effective_props(pid: str, guid: str, db: Session = Depends(get_db),
                            _sec: str = Depends(require_role("viewer"))):
    """FAMILY-DEPTH ② (R18) — the effective property view for one element: every pset/property
    with its effective value, its source (`instance` | `type`), the shadowed type value where an
    occurrence override is in play, and the override count. The properties panel's type-vs-instance
    answer, straight from the model."""
    from aec_data import instance_props  # type: ignore
    try:
        return instance_props.effective_properties(open_source_ifc(db, pid), guid)
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get("/projects/{pid}/model/wall-joins")
def model_wall_joins(pid: str, tol: float = 0.05, db: Session = Depends(get_db),
                     _sec: str = Depends(require_role("viewer"))):
    """AUTH-CONSTRAINTS ③ (R18) — detect L/T wall joins (endpoint coincidence / endpoint-on-axis,
    same storey, non-parallel): the corner point, the through/stub classification, and counts.
    Resolution is the `resolve_wall_joins` edit recipe (GUID-stable butt joins, idempotent)."""
    from aec_data import wall_joins  # type: ignore
    return wall_joins.find(open_source_ifc(db, pid), tol=max(0.005, min(float(tol), 0.5)))


@router.get("/projects/{pid}/model/roundtrip")
def model_roundtrip(pid: str, db: Session = Depends(get_db),
                    _sec: str = Depends(require_role("viewer"))):
    """INTEROP-RT (R19) — the round-trip fidelity gauntlet on the project model: serialize →
    fresh parse → compare (GUID stability · class · name · containment · type · psets). Unmatched
    reported both ways; `fidelity_ok` is the verdict."""
    from aec_data import roundtrip  # type: ignore
    return roundtrip.roundtrip(open_source_ifc(db, pid))


@router.get("/projects/{pid}/master-builder/brief")
def master_builder_brief(pid: str, workspace: str | None = None, persona: str | None = None,
                         db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """MASTER-BUILDER — the whole project in one view: runs the 8-step Master Builder Protocol (place →
    program/HBU → feasibility → regulatory → design-integration → delivery → risk → handover) over the
    project's own data, grounds it in the project's jurisdiction, and reports a readiness status + the
    concrete gap per step (each linking to the tool that closes it). A readiness synthesis over the data
    on hand — not a substitute for licensed judgment, a plan check, or committed underwriting."""
    from .. import master_builder
    from ..master_builder_scope import apply_scope
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    place_context = None
    try:                                             # best-effort georeferencing → real place grounding
        from .. import georef
        site = (georef.georeferencing(open_source_ifc(db, pid)) or {}).get("site")
        if site:
            place_context = {"ref_latitude": site.get("ref_latitude"),
                             "ref_longitude": site.get("ref_longitude")}
    except Exception:                                # noqa: BLE001 — no/opaque model: brief still runs
        pass
    payload = master_builder.brief(db, pid, place_context=place_context)
    return apply_scope(payload, workspace, persona)


@router.get("/projects/{pid}/pulse")
def project_pulse(pid: str, db: Session = Depends(get_db),
                  user: str = Depends(require_role("viewer"))):
    """PROJECT PULSE — five optional cards as `PulseInput`. Mapping lives here so the
    home shell does not re-derive `score` / `variancePct` / `floatDays` from engine
    shapes that do not use those names. Fail-open per card; 404 only if the project
    itself is missing."""
    from .. import project_pulse as pulse
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    return pulse.compose(db, pid, user)


@router.get("/projects/{pid}/master-builder/brief.md")
def master_builder_brief_md(pid: str, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """MASTER-BUILDER brief as a shareable Markdown document — the printable one-page project-readiness
    brief (place grounding, per-step readiness + gaps, hazards to verify, the honest-status boundary)."""
    from .. import master_builder
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    place_context = None
    try:
        from .. import georef
        site = (georef.georeferencing(open_source_ifc(db, pid)) or {}).get("site")
        if site:
            place_context = {"ref_latitude": site.get("ref_latitude"),
                             "ref_longitude": site.get("ref_longitude")}
    except Exception:                                # noqa: BLE001
        pass
    md = master_builder.to_markdown(master_builder.brief(db, pid, place_context=place_context))
    return Response(md, media_type="text/markdown")


@router.get("/projects/{pid}/preflight")
def preflight_gate(pid: str, db: Session = Depends(get_db), _sec: str = Depends(require_role("viewer"))):
    """Pre-flight **issuance gate** — one PASS/HOLD verdict + a pre-issue checklist composing model health
    (hygiene · clash · code-readiness · verified-as-built), **discipline-classification completeness**,
    **keynote/spec completeness**, **drawing-set QA**, the **pinned-IDS validation**, and **open
    high-priority issues** (a hard blocker). Each check deep-links to its tool. Run it before issuing —
    `POST /drawing-set/issue` runs it automatically and stamps the verdict on the issuance."""
    from .. import preflight
    return preflight.run(db, pid)


@router.get("/projects/{pid}/models/{mid}/alignment-fit")
def model_alignment_fit(pid: str, mid: str, db: Session = Depends(get_db),
                        _sec: str = Depends(require_role("viewer"))):
    """R41-MODEL-ALIGN — propose a yaw correction for a discipline model that arrived rotated.

    The report above says the project's models DISAGREE; this says what to do about one of them. It
    fits a yaw-only oriented box to the model's footprint and proposes the rotation that puts the
    building back on its own axes — accepted only when the oriented box saves at least 20% of the
    axis-aligned area.

    **That threshold is the feature, not a tuning constant.** A true minimum-area rectangle sat 37°
    off a real building's own walls to buy 14% — arithmetically optimal and visibly wrong, because
    the walls are what a person sees. Refusing the margin is what buys a wall-parallel answer rather
    than merely the smallest one.

    **A PROPOSAL, never an edit.** The source IFC is opened read-only and nothing is written. Applying
    an alignment means storing a transform against the model, which is a separate change — so
    `applied` is always false here, and says so rather than leaving a caller to assume.
    """
    import ifcopenshell  # type: ignore

    from aec_data import align, drawings  # type: ignore

    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    m = db.query(ProjectModel).filter_by(project_id=pid, id=mid).first()
    if not m or not Path(m.ifc_path).exists():
        raise HTTPException(404, "model not found")

    pts = drawings.plan_points(ifcopenshell.open(m.ifc_path))
    fit = align.fit_yaw(pts) if pts is not None else None
    return {
        "model": mid,
        "discipline": m.discipline,
        "fit": None if fit is None else {
            "yaw_deg": round(fit.yaw_deg, 3),
            "currently_at_deg": round(fit.fitted_deg, 3),
            "extent_m": [round(fit.extent[0], 3), round(fit.extent[1], 3)],
            "obb_area_m2": round(fit.obb_area, 2),
            "aabb_area_m2": round(fit.aabb_area, 2),
            "area_saving": round(fit.saving, 4),
            "accepted": fit.accepted,
            "reason": fit.reason,
        },
        "applied": False,
        "note": ("a proposal only — the source file is never modified; applying an alignment stores a "
                 "transform against the model"),
    }


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


@router.get("/projects/{pid}/energy/model")
def energy_model(pid: str, db: Session = Depends(get_db),
                 _sec: str = Depends(require_role("viewer"))):
    """ENERGY phase 1 — the thermal model extracted from the IFC: zones, zero-thickness surfaces
    (each tagged `exact` or `bbox` so a consumer knows how far to trust its polygon), and
    constructions computed from the model's own layered assemblies. The intermediate both the
    gbXML and IDF writers serialize, so the two exports can never disagree."""
    from aec_data import energy_export  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    return energy_export.build(open_model(_source_ifc(db, pid)))


@router.get("/projects/{pid}/energy/export.gbxml")
def energy_gbxml(pid: str, db: Session = Depends(get_db),
                 _sec: str = Depends(require_role("viewer"))):
    """ENERGY phase 1 — gbXML envelope export (Campus / Building / Space / Surface + Construction /
    Layer / Material). Geometry and constructions only: no HVAC, schedules or loads."""
    from aec_data import energy_export  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    xml = energy_export.to_gbxml(open_model(_source_ifc(db, pid)))
    return Response(xml, media_type="application/xml",
                    headers={"Content-Disposition": 'attachment; filename="envelope.gbxml"'})


@router.get("/projects/{pid}/energy/export.idf")
def energy_idf(pid: str, db: Session = Depends(get_db),
               _sec: str = Depends(require_role("viewer"))):
    """ENERGY phase 1 — EnergyPlus IDF envelope export (Building / Zone / Material / Construction /
    BuildingSurface:Detailed). Add HVAC, schedules and loads in the simulation setup."""
    from aec_data import energy_export  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    idf = energy_export.to_idf(open_model(_source_ifc(db, pid)))
    return Response(idf, media_type="text/plain",
                    headers={"Content-Disposition": 'attachment; filename="envelope.idf"'})


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
