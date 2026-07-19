"""Structural + MEP analysis endpoints (REL-3 leaf split of `authoring.py`): the analytical model,
gravity/lateral solves, and the MEP browser/sizing/connectivity/coverage checks. URLs unchanged —
`authoring.py` includes this router."""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from ..db import get_db
from ..rbac import require_role
from .authoring_shared import project_with_source as _project

router = APIRouter()


@router.get("/projects/{pid}/analytical")
def analytical_summary(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """W10-7: the structural analytical model (analysis models, curve/surface members, point connections,
    load cases) derived alongside the physical frame. Build/refresh it with the `derive_analytical`
    recipe via POST /edit."""
    from aec_data import analytical  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    return analytical.summary(open_model(p.source_ifc))


@router.get("/projects/{pid}/structure/solve")
def structure_solve(pid: str,
                    live_occupancy: str = Query("office"),
                    sdl_psf: float = Query(20.0, ge=0),
                    slab_thickness_in: float = Query(8.0, gt=0),
                    tributary_ft: float | None = Query(None, gt=0),
                    gross_area_sf: float | None = Query(None, gt=0),
                    e_ksi: float = Query(29000.0, gt=0),
                    i_in4: float = Query(800.0, gt=0),
                    db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """STRUCT-SOLVE: apply an ASCE 7 gravity load case (dead + live by occupancy) to the W10-7 analytical
    curve members and run a determinate member-by-member statics solve — per-beam reactions, max shear/
    moment, indicative deflection + shear/moment/deflection diagrams, plus per-column tributary axial.
    **Preliminary only — not a substitute for a licensed structural engineer.** Requires an analytical
    model (run the `derive_analytical` recipe first)."""
    from aec_data.ifc_loader import open_model  # type: ignore

    from .. import struct_solve

    p = _project(db, pid)
    return struct_solve.solve(open_model(p.source_ifc), live_occupancy=live_occupancy, sdl_psf=sdl_psf,
                              slab_thickness_in=slab_thickness_in, tributary_ft=tributary_ft,
                              gross_area_sf=gross_area_sf, e_ksi=e_ksi, i_in4=i_in4)


@router.get("/projects/{pid}/structure/lateral")
def structure_lateral(pid: str,
                      sds: float = Query(1.0, gt=0), sd1: float = Query(0.6, gt=0),
                      r: float = Query(8.0, gt=0), ie: float = Query(1.0, gt=0),
                      system: str = Query("other"),
                      wind_speed_mph: float = Query(115.0, gt=0), exposure: str = Query("C"),
                      dead_psf: float = Query(90.0, gt=0), area_sf: float | None = Query(None, gt=0),
                      risk_category: str = Query("II"), cd: float | None = Query(None, gt=0),
                      elastic_drift_ratio: float | None = Query(None, gt=0),
                      db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """STRUCT-LATERAL: ASCE 7 lateral analysis — seismic Equivalent Lateral Force (§12.8) + simplified
    directional MWFRS wind — base shear distributed to per-story forces / shears / overturning, with the
    governing case flagged, plus a preliminary §12.12 story-drift screen (allowable Δa always; pass/fail
    when `elastic_drift_ratio` is supplied). Story weights estimated from floor area × `dead_psf`.
    **Preliminary — not a substitute for a licensed structural engineer** (no modal or P-delta)."""
    from aec_data.ifc_loader import open_model  # type: ignore

    from .. import lateral

    p = _project(db, pid)
    drift: dict[str, float | str] = {"risk_category": risk_category}
    if cd is not None:
        drift["cd"] = cd
    if elastic_drift_ratio is not None:
        drift["target_elastic_drift_ratio"] = elastic_drift_ratio
    return lateral.lateral_from_model(
        open_model(p.source_ifc), dead_psf=dead_psf, area_sf=area_sf,
        seismic={"sds": sds, "sd1": sd1, "r": r, "ie": ie, "system": system},
        wind={"speed_mph": wind_speed_mph, "exposure": exposure}, drift=drift)


@router.get("/projects/{pid}/spec-links")
def spec_links(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """W11 SpecLink: the model's `Pset_Massing_SpecLink` breadcrumbs rolled up — each linked spec
    section (MasterFormat number + title) with its element tally, plus the unlinked count. Stamp
    links with the `set_spec_link` recipe (guids + section + optional title/url)."""
    from aec_data import edit  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    return edit.spec_link_summary(open_model(p.source_ifc))


@router.get("/projects/{pid}/mep")
def mep_summary(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """W11 B6: MEP system browser — each IfcDistributionSystem with its segment/fitting/terminal
    breakdown + a connectivity signal (elements with unconnected ports), plus segments/fittings not
    yet assigned to any system. Add fittings with the `add_mep_fitting` recipe."""
    from aec_data import mep  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    return mep.mep_summary(open_model(p.source_ifc))


@router.get("/projects/{pid}/mep/sizing")
def mep_sizing(pid: str,
               duct_max_fpm: float = Query(2500.0, gt=0),
               pipe_max_fps: float = Query(8.0, gt=0),
               db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """MEP-SIZE: engineering size checks over authored MEP — computes flow velocity in each duct/pipe from
    the design size + flow (`Pset_Massing_MEPSizing`) and checks it against accepted limits (ASHRAE
    low-velocity air, erosion-limit water, NEC 392 tray fill), pass/fail like the IBC checks. Elevates MEP
    from *modeled* to *engineered*. **Preliminary — not a substitute for a licensed MEP engineer.**"""
    from aec_data import mep_sizing as _ms  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    return _ms.sizing_check(open_model(p.source_ifc), duct_max_fpm=duct_max_fpm, pipe_max_fps=pipe_max_fps)


@router.get("/projects/{pid}/mep/pressure-loss")
def mep_pressure_loss(pid: str,
                      duct_friction_max: float = Query(0.10, gt=0),
                      pipe_friction_max: float = Query(4.0, gt=0),
                      hazen_c: float = Query(140.0, gt=0),
                      db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """MEP depth: friction (pressure) loss per authored duct/pipe run (empirical round-duct + Hazen-
    Williams rates from the sizing pset's size + flow + length) with per-system series-sum totals and
    the **index run** a balancing engineer hunts first. Rates checked against the equal-friction
    budgets. **Preliminary — no branch topology/fittings/diversity; final balancing by a PE.**"""
    from aec_data import mep_sizing as _ms  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    return _ms.pressure_loss(open_model(p.source_ifc), duct_friction_max=duct_friction_max,
                             pipe_friction_max=pipe_friction_max, hazen_c=hazen_c)


@router.get("/projects/{pid}/mep/tray-fill")
def mep_tray_fill(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """MEP depth: per-conductor NEC 392.22 cable-tray fill — computed from the actual authored
    IfcCableSegment diameters on each tray's distribution system vs the Table 392.22(A) allowable
    (7 in² per 6 in of width), instead of a supplied ratio. **Preliminary pre-check, not a PE design.**"""
    from aec_data import mep_sizing as _ms  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    return _ms.tray_fill(open_model(p.source_ifc))


@router.get("/projects/{pid}/mep/thermal-loads")
def mep_thermal_loads(pid: str,
                      envelope_btuh_sf: float = Query(12.0, gt=0),
                      block_sf_per_ton: float = Query(350.0, gt=0),
                      db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """MEP depth: space-by-space cooling-load screen (W/sf method) — people/lighting/equipment
    densities by space type + a flat envelope allowance per IfcSpace, summed to tons and compared to
    the block `GFA ÷ 350` estimate so the team sees WHERE the load lives. **A screen, not an ASHRAE
    heat-balance calc — design loads by a licensed mechanical engineer.**"""
    from aec_data import mep_sizing as _ms  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    return _ms.thermal_loads(open_model(p.source_ifc), envelope_btuh_sf=envelope_btuh_sf,
                             block_sf_per_ton=block_sf_per_ton)


@router.get("/projects/{pid}/mep/connectivity")
def mep_connectivity(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """W10-4: MEP connectivity validation — ports connected vs open, port-to-port connection count, and the
    **dangling** (floating) elements whose ports are all unconnected. Wire elements with the `connect_mep`
    recipe (`POST /edit` with `{guid_a, guid_b}`)."""
    from aec_data import mep  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    return mep.connectivity(open_model(p.source_ifc))


@router.get("/projects/{pid}/mep/sprinkler-coverage")
def sprinkler_coverage(pid: str, hazard: str = "light", db: Session = Depends(get_db),
                       _: str = Depends(require_role("viewer"))):
    """MEP-FP: a sprinkler coverage pre-check — SPRINKLER head count vs the number NFPA 13 would require for
    the model's protected floor area (IfcSpace `NetFloorArea`) at the given hazard class (`light` /
    `ordinary` / `extra`). A planning assist, not a hydraulic design."""
    from aec_data import mep  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    return mep.sprinkler_coverage(open_model(p.source_ifc), hazard)


@router.get("/projects/{pid}/element-connections")
def element_connections(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """B5: the element-to-element connection graph (`IfcRelConnectsElements`) — connected pairs + per-element
    degree. Author edges with the `connect_elements` recipe (`POST /edit` with `{guid_a, guid_b}`)."""
    from aec_data import edit as ed  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    return ed.element_connections(open_model(p.source_ifc))
