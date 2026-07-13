"""Design-lifecycle endpoints — the RIBA/AIA phase spine + itemized soft costs for a project."""
from __future__ import annotations

from fastapi import APIRouter, Body, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from .. import adjacency, design_phase, resilience, soft_costs, spine
from .. import modules as me
from ..db import get_db
from ..models import Project
from ..rbac import current_user, require_role

router = APIRouter()


# --- Track V: AI concept-render bridge (feature-flagged; AIRI-style generative concept visuals) -----
@router.get("/projects/{pid}/concept-render/status")
def concept_render_status(pid: str, _: str = Depends(require_role("viewer"))):
    """Status of the (external, feature-flagged) AI concept-render bridge."""
    from .. import render_bridge
    return render_bridge.status()


@router.post("/projects/{pid}/concept-render/request")
def concept_render_request(pid: str, payload: dict = Body(default={}),
                           db: Session = Depends(get_db), _: str = Depends(require_role("editor"))):
    """Build a grounded concept-render prompt from the project's program + massing (passed in `payload`
    as `program` / `massing`, or the concept program is fetched). No-op unless AEC_RENDER_BRIDGE is set."""
    from .. import render_bridge
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    program = payload.get("program")
    if program is None:
        try:
            program = adjacency.summary(db, pid)
        except Exception:                         # noqa: BLE001 — no concept program is fine
            program = None
    return render_bridge.request(payload, program=program, massing=payload.get("massing"))


@router.post("/projects/{pid}/concept-render/ingest", status_code=201)
def concept_render_ingest(pid: str, payload: dict = Body(default={}),
                          db: Session = Depends(get_db), actor: str = Depends(require_role("editor"))):
    """Ingest a generated image reference from the external service → stored as a `concept_render` record.
    No-op unless AEC_RENDER_BRIDGE is enabled."""
    from .. import render_bridge
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    res = render_bridge.validate_ingest(payload)
    if not res.get("accepted"):
        return res
    data = {"title": (payload.get("title") or "Concept render")[:120], "prompt": res["prompt"],
            "style": res.get("style") or "photoreal", "image_url": res["image_url"], "source": res["source"]}
    try:
        rec = me.create_record(db, "concept_render", pid, {"data": data}, actor, None)
        res["record_id"] = rec["id"]
        res["stored"] = True
    except Exception as e:                         # noqa: BLE001 — storage failure shouldn't 500 the bridge
        res["stored"] = False
        res["store_error"] = str(e)[:120]
    return res


# --- M1: per-project material palette (the material editor) --------------------------------------
_PALETTE_KEY = "{pid}/palette.json"


@router.get("/projects/{pid}/materials/palette")
def get_material_palette(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """The material palette for the project (M1): the default class→material/colour table, the saved
    per-project overrides, and the **effective** palette (default with overrides applied) — what the
    model actually renders. Drives the material-editor UI."""
    import json

    from aec_data import materials as mats  # type: ignore

    from .. import storage
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    try:
        overrides = json.loads(storage.get(_PALETTE_KEY.format(pid=pid)))
    except Exception:                             # noqa: BLE001 — no saved overrides yet
        overrides = {}
    return {"default": mats.palette_to_json(mats.PALETTE),
            "overrides": overrides,
            "effective": mats.palette_to_json(mats.merge_palette(overrides))}


@router.put("/projects/{pid}/materials/palette")
def put_material_palette(pid: str, body: dict = Body(...), db: Session = Depends(get_db),
                         _: str = Depends(require_role("editor"))):
    """Save per-project material overrides (class → {name, category, color:[r,g,b], transparency}).
    Only the classes you change need be present; the rest fall back to the default palette. Persisted
    to project storage; call `…/materials/apply` to re-colour + republish the model."""
    import json

    from aec_data import materials as mats  # type: ignore

    from .. import storage
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    overrides = body.get("overrides", body) if isinstance(body, dict) else {}
    storage.put(_PALETTE_KEY.format(pid=pid), json.dumps(overrides).encode())
    return {"overrides": overrides, "effective": mats.palette_to_json(mats.merge_palette(overrides))}


@router.post("/projects/{pid}/materials/apply")
def apply_material_palette(pid: str, db: Session = Depends(get_db),
                           actor: str = Depends(require_role("editor"))):
    """Re-colour the model with the saved palette overrides and republish it: load the source IFC,
    re-run the M1 material/surface-style assignment with the merged palette, write it back, and kick
    the convert→fragments + reindex so the viewer shows the new colours. No-op message if no model."""
    import json
    import tempfile

    import ifcopenshell

    from aec_data import materials as mats  # type: ignore

    from .. import storage
    from .authoring import _publish_bg
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    try:
        raw = storage.get(f"{pid}/source.ifc")
    except Exception:                             # noqa: BLE001 — nothing published yet
        raise HTTPException(400, "no source model to re-colour — generate or upload one first")
    try:
        overrides = json.loads(storage.get(_PALETTE_KEY.format(pid=pid)))
    except Exception:                             # noqa: BLE001
        overrides = {}
    # /app is read-only in prod → work entirely in a tempfile, then push back to storage
    with tempfile.NamedTemporaryFile(suffix=".ifc", delete=False) as tf:
        tf.write(raw)
        tmp = tf.name
    try:
        model = ifcopenshell.open(tmp)
        counts = mats.apply_palette(model, mats.merge_palette(overrides))
        model.write(tmp)
        with open(tmp, "rb") as fh:
            storage.put(f"{pid}/source.ifc", fh.read())
    finally:
        import os
        os.unlink(tmp)
    _publish_bg(pid)
    return {"applied": counts, "publish": "running"}


@router.get("/projects/{pid}/program/summary")
def program_summary(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Concept space-program rollup + adjacency graph: total/net/gross area, mix by use, the node/edge
    graph, unmet adjacency preferences, and the massing hints (gross area + use mix) it feeds."""
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    return adjacency.summary(db, pid)


def _hard_cost(p: Project) -> float:
    """Project hard cost from the seeded dev budget (category='hard'); 0 if not seeded yet."""
    budget = getattr(p, "dev_budget", None) or {}
    total = 0.0
    for ln in budget.get("lines", []):
        if (ln.get("category") or "").lower() == "hard":
            total += float(ln.get("unit_cost") or 0) * float(ln.get("quantity") or 1)
    return total


@router.get("/projects/{pid}/lifecycle")
def lifecycle(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """The project's design phases (RIBA 0–7 ↔ AIA) with gate state, deliverables, ISO-19650 status,
    and the phase-allocated A/E design fee from the itemized soft costs."""
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    hard = _hard_cost(p)
    lc = design_phase.lifecycle(db, pid, hard_cost=hard, soft_cost_pct=25.0)
    lc["soft_costs"] = soft_costs.itemize(hard, 25.0) if hard else None
    lc["hard_cost"] = hard
    return lc


@router.post("/projects/{pid}/lifecycle/seed")
def seed(pid: str, db: Session = Depends(get_db), actor: str = Depends(require_role("editor"))):
    """Seed the eight design-phase records on a project (idempotent)."""
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    return design_phase.seed_phases(db, pid, actor)


@router.get("/lifecycle/reference")
def reference(_: str = Depends(current_user)):
    """The canonical RIBA↔AIA phase definitions + soft-cost taxonomy (for the UI, no project needed)."""
    return {"phases": design_phase.PHASES,
            "soft_cost_components": soft_costs.COMPONENTS,
            "ae_phase_split": soft_costs.AE_PHASE_SPLIT}


@router.get("/projects/{pid}/resilience/flood")
def resilience_flood(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Flood risk (ASCE 24 / FEMA): the Design Flood Elevation (BFE + freeboard) and the flood-proof-MEP
    check — asset-register items installed below the DFE, flagged to be elevated or flood-proofed."""
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    return resilience.flood_assessment(db, pid)


@router.get("/projects/{pid}/resilience/stormwater")
def resilience_stormwater(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Stormwater (Rational Method): peak runoff Q = C·i·A per catchment plus a first-order detention
    volume, so drainage is sized against a real design storm."""
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    return resilience.stormwater(db, pid)


@router.get("/projects/{pid}/resilience/weather")
def resilience_weather(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Weather-sequenced construction: weather-sensitive schedule activities, the site-weather-risk
    register, and weather-delay days rolled up from the daily reports."""
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    return resilience.weather(db, pid)


@router.get("/projects/{pid}/resilience/climate-risk")
def resilience_climate_risk(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Physical climate-risk rollup for ESG — flood exposure + stormwater load + site-weather hazards +
    logged weather delays folded into a single scored rating with the driving factors."""
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    return resilience.climate_risk(db, pid)


@router.get("/projects/{pid}/spine/traceability")
def spine_traceability(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Discipline Spine traceability — trace discipline → sheets → specs → bid packages → cost codes →
    budget, with per-discipline rollups and the coverage gaps (unpackaged specs, unbudgeted packages,
    un-specced sheets) so scope can't fall between the model, the documents and the money."""
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    return spine.traceability(db, pid)


@router.get("/projects/{pid}/design/options/compare")
def design_options_compare(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Compare the project's design options / variants apples-to-apples — program + economics per
    option, best-in-class per metric, deltas vs the selected option. The selected option's drawing set
    is the project's current documentation (2D regenerates live from the model)."""
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    from .. import design_options
    return design_options.compare(db, pid)


@router.get("/projects/{pid}/design/standards")
def design_standards_ruleset(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """The design-standards ruleset — approved / preferred / prohibited assemblies, materials, products."""
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    from .. import design_standards
    return design_standards.ruleset(db, pid)


@router.get("/projects/{pid}/design/standards/check")
def design_standards_check(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Audit the loaded model against the design-standards ruleset (prohibited / non-approved
    type + material use). Returns the ruleset only when no model is loaded."""
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    from .. import design_standards
    from .properties import _INDEX, _ensure_loaded
    try:
        _ensure_loaded(pid)
    except Exception:                     # noqa: BLE001 — ruleset-only when no model is loaded
        pass
    return design_standards.check(db, pid, _INDEX.get(pid))


@router.get("/projects/{pid}/mep/schedule")
def mep_schedule(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """The MEP equipment schedule from the register + a per-system capacity rollup."""
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    from .. import mep
    return mep.schedule(db, pid)


@router.get("/projects/{pid}/mep/model-extract")
def mep_model_extract(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """MEP elements read off the loaded model (by IFC class) — complements the register schedule."""
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    from .. import mep
    from .properties import _INDEX, _ensure_loaded
    try:
        _ensure_loaded(pid)
    except Exception:                     # noqa: BLE001 — no model is a valid (empty) state
        pass
    return mep.extract_from_model(_INDEX.get(pid))


@router.get("/projects/{pid}/model/capabilities")
def model_capabilities(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """IFC read-schema capabilities + the detected schema of this project's loaded model (IFC5/IFCX
    is detected and reported, not yet parsed)."""
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    from .. import model_capabilities as mc
    return mc.capabilities(p.source_ifc)


@router.get("/projects/{pid}/drawings/sync-status")
def drawings_sync_status(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Model fingerprint + version for 2D staleness detection — the client compares `version` /
    `signature` across renders to know when the on-demand drawings need regenerating. `version` bumps
    every time a new model is published (see /drawings/stream for the push equivalent)."""
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    from .. import model_capabilities as mc
    from .. import model_events
    from .properties import _INDEX, _ensure_loaded
    try:
        _ensure_loaded(pid)
    except Exception:                     # noqa: BLE001 — no model is a valid state
        pass
    sig = mc.model_signature(_INDEX.get(pid))
    # reconcile the version with the current signature (covers a fresh reload on another worker)
    ev = model_events.observe(pid, sig.get("signature"))
    return {**sig, "version": ev["version"], "changed_at": ev.get("at")}


@router.get("/projects/{pid}/drawings/stream")
async def drawings_stream(pid: str, request: Request, _: str = Depends(require_role("viewer"))):
    """Server-sent events: pushes the model `version` and re-pushes the instant it changes (a new model
    is published), so open 2D drawing views regenerate themselves — live propagation from the model
    without polling or an external event bus."""
    import asyncio
    import json as _json

    from fastapi.responses import StreamingResponse

    from .. import model_events

    async def gen():
        last = None
        while not await request.is_disconnected():
            ev = model_events.current(pid)
            if ev["version"] != last:
                last = ev["version"]
                yield f"data: {_json.dumps({'version': ev['version'], 'signature': ev.get('signature')})}\n\n"
            await asyncio.sleep(4)

    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/projects/{pid}/mep/size")
def mep_size(pid: str, kind: str = "duct", flow: float = 0.0, velocity: float = 0.0,
             load: float = 0.0, size: float = 0.0, hanger_kind: str = "pipe_steel",
             db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """First-pass MEP sizing. kind = duct (flow=CFM, velocity=fpm) | pipe (flow=GPM, velocity=fps) |
    cooling (load=BTU/h) | hanger (hanger_kind=duct|pipe_steel|pipe_copper, size=in)."""
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    from .. import mep
    if kind == "pipe":
        return mep.size_pipe(flow, velocity or 6.0)
    if kind == "cooling":
        return mep.size_cooling(load)
    if kind == "hanger":
        return mep.hanger_spacing(hanger_kind, size)
    return mep.size_duct(flow, velocity or 1000.0)


@router.get("/projects/{pid}/envelope/audit")
def envelope_audit(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Envelope code-compliance — every envelope assembly checked against IECC 2021 climate-zone
    minimums (opaque R-value / fenestration U-factor), with a compliance rollup."""
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    from .. import envelope
    return envelope.audit(db, pid)


@router.get("/projects/{pid}/envelope/check")
def envelope_check(pid: str, element_type: str = "Wall", climate_zone: str = "4",
                   r_value: float | None = None, u_factor: float | None = None,
                   db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Check a single assembly against IECC 2021 (element_type + climate_zone + r_value or u_factor)."""
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    from .. import envelope
    return envelope.check_assembly(element_type, climate_zone, r_value, u_factor)


@router.get("/projects/{pid}/diligence/readiness")
def diligence_readiness(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Pre-acquisition go/no-go rollup: due-diligence items by category/state (cleared vs flagged vs
    open, high-risk flags) + entitlement applications by status (approved vs pending vs denied,
    approvals nearing expiration). The screen a developer reads before releasing contingencies."""
    from datetime import date, timedelta

    from .. import modules as me
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")

    dd = me.list_records(db, "due_diligence", pid, limit=1000) if "due_diligence" in me.TABLES else []
    by_cat: dict[str, dict] = {}
    high_risk = []
    for r in dd:
        d = r.get("data") or {}
        cat = d.get("category") or "Other"
        c = by_cat.setdefault(cat, {"total": 0, "cleared": 0, "flagged": 0, "open": 0})
        c["total"] += 1
        st = r.get("workflow_state")
        c["cleared" if st == "cleared" else "flagged" if st == "flagged" else "open"] += 1
        if (d.get("risk") or "") in ("High", "Deal-breaker"):
            high_risk.append({"ref": r.get("ref"), "item": r.get("title"), "risk": d["risk"],
                              "category": cat, "state": st})

    ents = me.list_records(db, "entitlement", pid, limit=1000) if "entitlement" in me.TABLES else []
    ent_counts: dict[str, int] = {}
    expiring = []
    horizon = date.today() + timedelta(days=180)
    for r in ents:
        st = r.get("workflow_state") or "draft"
        ent_counts[st] = ent_counts.get(st, 0) + 1
        exp = (r.get("data") or {}).get("approval_expires")
        if st == "approved" and exp:
            try:
                if date.fromisoformat(str(exp)[:10]) <= horizon:
                    expiring.append({"ref": r.get("ref"), "application": r.get("title"), "expires": exp})
            except ValueError:
                pass

    dd_total = len(dd)
    dd_cleared = sum(c["cleared"] for c in by_cat.values())
    ents_pending = sum(v for k, v in ent_counts.items() if k in ("draft", "submitted", "hearing", "appealed"))
    return {
        "due_diligence": {"total": dd_total, "cleared": dd_cleared,
                          "flagged": sum(c["flagged"] for c in by_cat.values()),
                          "by_category": by_cat, "high_risk": high_risk},
        "entitlements": {"total": len(ents), "by_state": ent_counts,
                         "approved": ent_counts.get("approved", 0), "pending": ents_pending,
                         "denied": ent_counts.get("denied", 0), "expiring_within_180d": expiring},
        "go": bool(dd_total and dd_cleared == dd_total and not high_risk
                   and not ents_pending and not ent_counts.get("denied")),
    }
