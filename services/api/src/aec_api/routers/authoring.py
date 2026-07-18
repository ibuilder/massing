"""Authoring endpoints (Phase 6): apply an IFC edit recipe and publish the round-trip
(reconvert -> reindex) so the viewer refreshes. Edits keep GUIDs stable, so pins/RFIs/
clashes survive. This is the server-side / AI-driven path; the desktop path is Blender +
Bonsai driven over Bonsai-MCP (same ifcopenshell.api operations)."""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import sys
import tempfile
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import APIRouter, Body, Depends, File, Form, HTTPException, Response, UploadFile
from sqlalchemy.orm import Session

from .. import audit, storage
from ..db import get_db
from ..models import Project, ProjectModel
from ..rbac import current_user, require_role
from ..throttle import rate_limited
from . import properties as props_router

_IFC_DIR = Path(os.environ.get("IFC_DIR", "/app/ifc"))   # local IFC copies the converter can read
_REPO = Path(__file__).resolve().parents[5]
_DATA_SRC = _REPO / "services" / "data" / "src"
_CONVERTER = _REPO / "services" / "converter" / "src" / "cli.mjs"
if str(_DATA_SRC) not in sys.path:
    sys.path.insert(0, str(_DATA_SRC))

router = APIRouter()

# REL-3 leaf split: documentation/provenance + structural/MEP analysis endpoints live in their own
# modules; including them here keeps every URL and main.py unchanged.
from . import authoring_analysis, authoring_docs  # noqa: E402

router.include_router(authoring_docs.router)
router.include_router(authoring_analysis.router)


# REL-3: shared with the authoring_docs / authoring_analysis leaf routers
from .authoring_shared import project_with_source as _project  # noqa: E402


@router.get("/projects/{pid}/types")
def list_types(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Catalog of placeable types ("families") in the project's source IFC, for the place-family
    picker. Deduped by (class, name)."""
    from aec_data import edit as ed  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    return {"types": ed.list_types(open_model(p.source_ifc))}


@router.get("/projects/{pid}/types/{type_guid}")
def type_detail(pid: str, type_guid: str, db: Session = Depends(get_db),
                _: str = Depends(require_role("viewer"))):
    """W10-1 type inspector: class, PredefinedType, box dims, type Psets, material layers, and the
    placed occurrences of one family type. Create/edit/material go through POST /edit with the
    create_type | edit_type_params | assign_material_set recipes (versioned + GUID-stable)."""
    from aec_data import families  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    try:
        return families.type_detail(open_model(p.source_ifc), type_guid)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/projects/{pid}/lod")
def lod_summary(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """W11 F0: element LOD-stage distribution (100/200/300/350/400/500/unset). Advance elements with the
    `set_lod` recipe; `ensure_contexts` establishes the view-keyed representation contexts the drawing
    pipeline needs. LOD is element maturity, not a geometry mode — the same GUID carries it as it refines."""
    from aec_data import representations as rep  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    return rep.lod_summary(open_model(p.source_ifc))


@router.get("/projects/{pid}/query")
def query_elements(pid: str, q: str, limit: int = 2000, db: Session = Depends(get_db),
                   _: str = Depends(require_role("viewer"))):
    """W11: power selection via the IfcOpenShell **selector DSL** — e.g. `IfcWall`,
    `IfcWall, IfcDoor`, `IfcSpace, Pset_SpaceCommon.IsExternal=TRUE`, `IfcWall, material=concrete`.
    Returns the matched elements (guid/name/class/storey). Feeds selection sets, bulk edits, schedule
    scoping, and rule-driven detail/spec attachment. 400 on invalid query syntax."""
    from aec_data import edit as ed  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    try:
        return ed.query_elements(open_model(p.source_ifc), q, limit)
    except ValueError as e:
        raise HTTPException(400, str(e)) from e


@router.get("/projects/{pid}/phasing")
def phasing_summary(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """W10-8: element phase/status distribution (new · existing · demolish · temporary · unset) over the
    model. Tag elements with the `set_phase` recipe (POST /edit); colour the model by
    `Massing_Phasing.Status` via the existing colour-by-property view."""
    from aec_data import edit as ed  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    return ed.phase_summary(open_model(p.source_ifc))


@router.get("/projects/{pid}/lod500")
def asbuilt_summary(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """W11 G1: LOD-500 readiness — the share of the model that is **field-verified as-built** (the
    reliability attribute BIMForum actually defines as LOD 500; it has no geometric requirement). Counts
    elements with `Massing_AsBuilt.Status==VERIFIED`, by verification method. Stamp elements with the
    `verify_asbuilt` recipe (POST /edit)."""
    from aec_data import edit as ed  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    return ed.asbuilt_summary(open_model(p.source_ifc))


@router.get("/projects/{pid}/groups")
def list_groups(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """W10-3: every IfcGroup (named set / selection) and IfcElementAssembly (part-of whole) in the
    model, with member counts. Create/array/ungroup go through POST /edit with the create_group |
    create_assembly | array_element | ungroup recipes (versioned + GUID-stable)."""
    from aec_data import groups  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    return groups.list_groups(open_model(p.source_ifc))


@router.get("/projects/{pid}/groups/{guid}")
def group_detail(pid: str, guid: str, db: Session = Depends(get_db),
                 _: str = Depends(require_role("viewer"))):
    """W10-3 inspector: the members/parts of one group or assembly."""
    from aec_data import groups  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    try:
        return groups.group_detail(open_model(p.source_ifc), guid)
    except ValueError as e:
        raise HTTPException(404, str(e)) from e


@router.get("/projects/{pid}/propmap/detect")
def propmap_detect(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """W9-1: every (pset, property) actually present on the model's elements — the 'source' side a
    user normalizes FROM — with occurrence counts + a sample value. Feeds the property-mapping UI."""
    from aec_data import propmap  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    return propmap.detect(open_model(p.source_ifc))


@router.post("/projects/{pid}/propmap/plan")
def propmap_plan(pid: str, rules: list[dict] = Body(..., embed=True),
                 db: Session = Depends(get_db), _: str = Depends(require_role("editor"))):
    """W9-1 dry-run: how many elements each remap rule would touch, with before/after samples. No
    mutation — apply for real via POST /edit {recipe: "map_properties", params: {rules}}."""
    from aec_data import propmap  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    return propmap.plan(open_model(p.source_ifc), rules)


# --- W9-5: site logistics on the 4D timeline --------------------------------------------------------
@router.get("/projects/{pid}/logistics")
def get_logistics(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Site-logistics resources (cranes / laydown / gates …) with schedule windows — pure data, drawn
    as time-phased overlays on the 4D timeline."""
    from .. import logistics  # type: ignore

    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    res = (p.site_logistics or {}).get("resources", [])
    return {"resources": res, "summary": logistics.summary(res)}


@router.put("/projects/{pid}/logistics")
def put_logistics(pid: str, body: dict = Body(...), db: Session = Depends(get_db),
                  actor: str = Depends(require_role("editor"))):
    """Replace the site-logistics resource list."""
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    p.site_logistics = {"resources": body.get("resources", [])}
    audit.record(db, action="logistics.save", actor=actor, method="PUT",
                 path=f"/projects/{pid}/logistics", detail={"resources": len(p.site_logistics["resources"])})
    db.commit()
    return p.site_logistics


@router.get("/projects/{pid}/logistics/state")
def logistics_state(pid: str, date: str | None = None, db: Session = Depends(get_db),
                    _: str = Depends(require_role("viewer"))):
    """Which logistics resources are active on `date` (blank = the whole plan) — drives the time-phased
    overlay as the 4D slider moves."""
    from .. import logistics  # type: ignore

    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    return logistics.state_at((p.site_logistics or {}).get("resources", []), date)


# --- W9-4: semantic model graph (IFC relationships) -------------------------------------------------
@router.get("/projects/{pid}/graph")
def model_graph(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Graph stats — node + edge counts by relationship type (contained_in / aggregates / bounds /
    has_opening / fills / serves), built from the model's own IfcRel* relationships."""
    from aec_data import graph  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    return graph.build(open_model(p.source_ifc))


@router.get("/projects/{pid}/graph/neighbors")
def model_graph_neighbors(pid: str, guid: str, depth: int = 1,
                          db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """The connected subgraph around an element out to `depth` hops — every related node cited by GUID +
    the relationship path that reaches it. The multi-hop, relational answer the property index can't give."""
    from aec_data import graph  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    return graph.neighbors(open_model(p.source_ifc), guid, depth)


# --- W9-3: IFC5-style non-destructive property-override layers ---------------------------------------
@router.get("/projects/{pid}/layers")
def get_layers(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """The project's property-override layer stack (composes over the model without mutating the IFC)."""
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    return p.prop_layers or {"layers": []}


@router.put("/projects/{pid}/layers")
def put_layers(pid: str, stack: dict = Body(...), db: Session = Depends(get_db),
               actor: str = Depends(require_role("editor"))):
    """Replace the layer stack. Pure data — nothing is written to the IFC until baked."""
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    p.prop_layers = {"layers": stack.get("layers", [])}
    audit.record(db, action="layers.save", actor=actor, method="PUT", path=f"/projects/{pid}/layers",
                 detail={"layers": len(p.prop_layers["layers"])})
    db.commit()
    return p.prop_layers


def _base_lookup(source_ifc: str):
    """A (guid, pset, prop) -> current model value resolver over the source IFC, for annotating what
    each override overrides. Opens the model once and caches element lookups by GUID."""
    import ifcopenshell.util.element as ue  # type: ignore

    from aec_data.ifc_loader import open_model  # type: ignore

    model = open_model(source_ifc)
    cache: dict = {}

    def lookup(guid: str, pset: str, prop: str):
        el = cache.get(guid)
        if el is None:
            try:
                el = model.by_guid(guid)
            except Exception:  # noqa: BLE001
                el = False
            cache[guid] = el
        if not el:
            return None
        d = ue.get_pset(el, pset)
        return d.get(prop) if isinstance(d, dict) else None

    return lookup


@router.get("/projects/{pid}/layers/resolve")
def resolve_layers(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """Compose the enabled layers into effective values, with provenance + cross-layer conflicts —
    the data-world twin of clash detection. Non-destructive; the IFC is untouched until baked."""
    from .. import layers as _layers

    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    stack = (p.prop_layers or {}).get("layers", [])
    has_ifc = bool(p.source_ifc and Path(p.source_ifc).exists())
    lookup = _base_lookup(p.source_ifc) if (stack and has_ifc) else None
    return _layers.resolve(stack, lookup)


@router.post("/projects/{pid}/layers/bake")
def bake_layers(pid: str, publish: bool = Body(default=True, embed=True),
                db: Session = Depends(get_db), actor: str = Depends(require_role("editor"))):
    """Flatten the resolved composition into the IFC (each effective override -> a GUID-stable pset
    edit), producing a new version. Republishes so pins/RFIs/clashes survive."""
    from aec_data import edit as ed  # type: ignore

    from .. import layers as _layers

    p = _project(db, pid)
    stack = (p.prop_layers or {}).get("layers", [])
    overrides = _layers.bake_overrides(stack)
    if not overrides:
        return {"baked": 0, "message": "no enabled overrides to bake"}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    base_stem = re.sub(r"(_\d{14,20})+$", "", Path(p.source_ifc).stem)
    out = str(Path(p.source_ifc).with_name(f"{base_stem}_{stamp}.ifc"))
    result = ed.apply_recipe(p.source_ifc, "apply_layers", {"overrides": overrides}, out)
    p.source_ifc = out
    audit.record(db, action="layers.bake", actor=actor, method="POST",
                 path=f"/projects/{pid}/layers/bake", detail={"baked": result["changed"]})
    db.commit()
    out_body = {"baked": result["changed"]}
    if publish:
        _publish_bg(pid)
        out_body["publish"] = "running"
    return out_body


@router.get("/families/catalog")
def family_catalog(_: str = Depends(current_user)):
    """Starter IFC family library (furniture / sanitary / appliances / plants) you can add to any
    model — generated parametrically, so it's available even for a from-scratch massing model. Place
    one via the `add_family` edit recipe (POST /projects/{id}/edit, recipe='add_family')."""
    from aec_data import families  # type: ignore

    items = families.catalog()
    cats: dict[str, list] = {}
    for it in items:
        cats.setdefault(it["category"], []).append(it)
    return {"count": len(items), "categories": cats}


@router.post("/projects/{pid}/families/import")
async def import_families(pid: str, file: UploadFile = File(...), publish: bool = False,
                          db: Session = Depends(get_db),
                          actor: str = Depends(require_role("editor"))):
    """Import external IFC **type content** (manufacturer / 3rd-party families) from an uploaded IFC
    into the project's source IFC, saving a new version. Imported types become placeable via the
    place-family picker (GET /projects/{id}/types). GUIDs of existing elements are preserved."""
    from aec_data import families  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    data = await file.read()
    model = open_model(p.source_ifc)
    imported = families.import_types_from_ifc(model, data)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    base_stem = re.sub(r"(_\d{14,20})+$", "", Path(p.source_ifc).stem)
    out_path = str(Path(p.source_ifc).with_name(f"{base_stem}_{stamp}.ifc"))
    model.write(out_path)
    p.source_ifc = out_path
    result = {"imported": imported, "count": len(imported)}
    audit.record(db, action="ifc.import_families", actor=actor, method="POST",
                 path=f"/projects/{pid}/families/import", detail=result)
    db.commit()
    if publish and imported:           # only worth a reconvert if something actually came in
        _publish_bg(pid)
        result["publish"] = "running"
    return result


@router.get("/families/library")
def family_library(_: str = Depends(current_user)):
    """The shippable IFC family library: the generated parametric catalog (grouped by category) plus
    any curated external `.ifc` files dropped in services/data/families/external. The generated
    `library.ifc` is real openBIM content that also imports into any project via /families/import."""
    from aec_data import families  # type: ignore
    from aec_data.build_family_library import LIBRARY_DIR, LIBRARY_PATH  # type: ignore

    items = families.catalog()
    cats: dict[str, list] = {}
    for it in items:
        cats.setdefault(it["category"], []).append(it)
    ext_dir = LIBRARY_DIR / "external"
    external = [{"name": p.name, "size_bytes": p.stat().st_size}
                for p in sorted(ext_dir.glob("*.ifc"))] if ext_dir.exists() else []
    lib = {"exists": LIBRARY_PATH.exists(),
           "size_bytes": LIBRARY_PATH.stat().st_size if LIBRARY_PATH.exists() else 0}
    return {"count": len(items), "categories": cats, "generated_library": lib, "external": external}


@router.post("/projects/{pid}/families/place")
def place_family(pid: str, family: str = Body(..., embed=True),
                 position: list[float] | None = Body(default=None, embed=True),
                 storey: str | None = Body(default=None, embed=True),
                 publish: bool = Body(default=False, embed=True),
                 db: Session = Depends(get_db), actor: str = Depends(require_role("editor"))):
    """Place a library family into the project's source IFC (new GUID-stable occurrence, new version).
    Thin wrapper over the `add_family` authoring recipe."""
    from aec_data import edit as ed  # type: ignore

    p = _project(db, pid)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    base_stem = re.sub(r"(_\d{14,20})+$", "", Path(p.source_ifc).stem)
    out = str(Path(p.source_ifc).with_name(f"{base_stem}_{stamp}.ifc"))
    params: dict = {"family": family}
    if position:
        params["position"] = position
    if storey:
        params["storey"] = storey
    result = ed.apply_recipe(p.source_ifc, "add_family", params, out)
    p.source_ifc = out
    audit.record(db, action="ifc.place_family", actor=actor, method="POST",
                 path=f"/projects/{pid}/families/place", detail=result)
    db.commit()
    if publish:
        _publish_bg(pid)
        result["publish"] = "running"
    return result


_ai_author_throttle = rate_limited("draft", 30)          # the paid LLM path when a key is set


@router.post("/projects/{pid}/ai/author")
def ai_author(pid: str, text: str = Body(..., embed=True),
              context: dict = Body(default={}, embed=True),
              db: Session = Depends(get_db), _: str = Depends(require_role("editor")),
              __: None = Depends(_ai_author_throttle)):
    """Natural-language authoring — map a plain-English instruction ("add a 3 m wall from 0,0 to 5,0",
    "a 5x4 m room at 0,0", "window in the selected wall") to a validated **plan** of {recipe, params}.
    Interpretation only: nothing is written. The client shows the plan for confirmation, then applies each
    step via the normal POST /edit path (GUID-stable, audited). Claude does multi-step planning when an
    Anthropic API key is set; otherwise a deterministic keyword baseline — no key required."""
    from .. import nl_ai

    # A4: ground the planner with a compact scene digest (what's already in the model), best-effort
    p = db.get(Project, pid)
    if p and p.source_ifc and Path(p.source_ifc).exists() and not (context or {}).get("scene"):
        try:
            from aec_data.ifc_loader import open_model  # type: ignore

            from .. import scene
            context = {**(context or {}), "scene": scene.digest(open_model(p.source_ifc))["prose"]}
        except Exception:                              # noqa: BLE001 — grounding is optional, never block
            pass
    return nl_ai.plan(text, context)


@router.get("/projects/{pid}/scene-digest")
def scene_digest(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """A4: a compact, LLM-friendly digest of the model — element counts by class, storeys, spaces, MEP
    systems + disciplines, phasing, LOD, and hygiene, plus a one-paragraph `prose` overview. Grounds the
    AI command bar and gives a one-glance model summary."""
    from aec_data.ifc_loader import open_model  # type: ignore

    from .. import scene
    p = _project(db, pid)
    return scene.digest(open_model(p.source_ifc))


@router.post("/projects/{pid}/edit/precheck")
def edit_precheck(pid: str, recipe: str = Body(..., embed=True), params: dict = Body(default={}, embed=True),
                  _: str = Depends(require_role("editor"))):
    """W11 E8: validate an edit's params against the authoring **guardrails** WITHOUT applying it —
    {ok, errors, warnings}. The client calls this before committing so a novice is told about a broken
    edit (zero-length wall, non-positive size, missing host) before it ever touches the model."""
    from aec_data import guards  # type: ignore

    return guards.precheck(recipe, params)


@router.post("/projects/{pid}/edit")
def edit(pid: str, recipe: str = Body(...), params: dict = Body(default={}),
         publish: bool = Body(default=False), base_source: str | None = Body(default=None),
         db: Session = Depends(get_db), actor: str = Depends(require_role("editor"))):
    """Apply an authoring recipe (set_pset | batch_tag | place_type) to the source IFC,
    saving a new version. GUIDs of existing elements are preserved.

    COLLAB-1 optimistic lock: pass `base_source` (the model signature the client last loaded, from
    `GET .../collab`) and the edit is rejected **409** if another user has published since — so a
    concurrent edit surfaces a 'model changed — reload' instead of silently overwriting their work."""
    from aec_data import edit as ed  # type: ignore

    from .. import pid_lock

    # Serialize the whole read→apply→pointer-swap per project: two concurrent edits (or an /edit + an
    # MCP run_recipe) both reading the same source_ifc would each write their own version and the last
    # commit would silently orphan the other user's edit. The optimistic base_source check catches a
    # STALE client; only the lock closes the in-flight race between two fresh ones.
    with pid_lock.mutating(pid):
        p = _project(db, pid)
        db.refresh(p)                                  # the pointer may have moved while we waited
        if base_source is not None and p.source_ifc and Path(base_source).name != Path(p.source_ifc).name:
            raise HTTPException(409, "the model changed since you loaded it (another user published) — "
                                     "reload before editing")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        # Strip any prior version timestamp(s) so chained edits don't compound the filename into an
        # ever-growing path (which blew past Windows' 260-char limit and failed the write). Each edit
        # produces "<base>_<stamp>.ifc" off the ORIGINAL stem, not the previous versioned name.
        base_stem = re.sub(r"(_\d{14,20})+$", "", Path(p.source_ifc).stem)
        out = str(Path(p.source_ifc).with_name(f"{base_stem}_{stamp}.ifc"))
        # CODE-3: the detail-rule recipe auto-resolves the IBC edition from the project's
        # jurisdiction when the caller didn't pass one — citations name the adopted edition.
        if recipe == "apply_detailing_rules" and not params.get("ibc_edition") \
                and getattr(p, "jurisdiction", None):
            from .codecheck import _project_ibc_edition
            ed_year = _project_ibc_edition(p)
            if ed_year:
                params = {**params, "ibc_edition": str(ed_year)}
        try:
            result = ed.apply_recipe(p.source_ifc, recipe, params, out)
        except PermissionError as e:                   # A1 sandbox disabled
            raise HTTPException(403, str(e)) from e
        except (ValueError, KeyError) as e:            # E8 guard rejection / sandbox reject / missing param
            raise HTTPException(400, str(e)) from e
        from .. import edit_history  # S4 — record the pre-edit version so this edit can be undone
        edit_history.push(pid, p.source_ifc)
        p.source_ifc = out  # new version becomes the source of truth
        audit.record(db, action="ifc.edit", actor=actor, method="POST",
                     path=f"/projects/{pid}/edit", detail=result)
        db.commit()
    if publish:                       # reconvert off-thread; client polls publish/status
        _publish_bg(pid)
        result["publish"] = "running"
    return result


@router.post("/projects/{pid}/edit/graph")
def edit_graph(pid: str, graph: dict = Body(...), publish: bool = Body(default=False),
               base_source: str | None = Body(default=None), db: Session = Depends(get_db),
               actor: str = Depends(require_role("editor"))):
    """AUTH-VS: execute a **recipe graph** — a set of authoring-recipe nodes wired by data dependencies
    (one node's created GUID feeds the next) — as a single GUID-stable authoring pass, saving one new
    version. Body: {graph:{nodes,edges}, publish?, base_source?}. Honors the COLLAB-1 optimistic lock."""
    from aec_data import nodegraph  # type: ignore

    from .. import pid_lock

    with pid_lock.mutating(pid):                       # same RMW race as /edit — serialize per project
        p = _project(db, pid)
        db.refresh(p)
        if base_source is not None and p.source_ifc and Path(base_source).name != Path(p.source_ifc).name:
            raise HTTPException(409, "the model changed since you loaded it (another user published) — "
                                     "reload before editing")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        base_stem = re.sub(r"(_\d{14,20})+$", "", Path(p.source_ifc).stem)
        out = str(Path(p.source_ifc).with_name(f"{base_stem}_{stamp}.ifc"))
        try:
            result = nodegraph.execute_graph(p.source_ifc, graph, out)
        except (ValueError, KeyError) as e:           # bad graph: unknown recipe/id, cycle, dangling ref
            raise HTTPException(400, str(e)) from e
        from .. import edit_history
        edit_history.push(pid, p.source_ifc)
        p.source_ifc = out
        audit.record(db, action="ifc.edit_graph", actor=actor, method="POST",
                     path=f"/projects/{pid}/edit/graph", detail={"nodes": result["node_count"]})
        db.commit()
    if publish:
        _publish_bg(pid)
        result["publish"] = "running"
    # the raw recipe outputs can be large / non-serialisable dicts — return the run shape, not every field
    return {"node_count": result["node_count"], "order": result["order"],
            "outputs": {k: (v if isinstance(v, (str, int, float)) else
                            (v.get("guid") if isinstance(v, dict) else str(v)))
                        for k, v in result["outputs"].items()},
            **({"publish": result["publish"]} if "publish" in result else {})}


@router.post("/projects/{pid}/edit/batch")
def edit_batch(pid: str, steps: list[dict] = Body(...), publish: bool = Body(default=False),
               base_source: str | None = Body(default=None),
               db: Session = Depends(get_db), actor: str = Depends(require_role("editor"))):
    """S4 — apply a **sequence of authoring steps as ONE version** (`steps: [{recipe, params}, …]`):
    the model opens once, every step runs in memory, one file is written, one edit-history entry is
    pushed — so a multi-step NL command **undoes as a single step**. All-or-nothing: every step is
    guard-prechecked before anything runs. Honors the COLLAB-1 optimistic lock via `base_source`."""
    from aec_data import edit as ed  # type: ignore

    from .. import pid_lock

    with pid_lock.mutating(pid):
        p = _project(db, pid)
        db.refresh(p)
        if base_source is not None and p.source_ifc and Path(base_source).name != Path(p.source_ifc).name:
            raise HTTPException(409, "the model changed since you loaded it (another user published) — "
                                     "reload before editing")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        base_stem = re.sub(r"(_\d{14,20})+$", "", Path(p.source_ifc).stem)
        out = str(Path(p.source_ifc).with_name(f"{base_stem}_{stamp}.ifc"))
        try:
            result = ed.apply_recipes(p.source_ifc, steps, out)
        except PermissionError as e:
            raise HTTPException(403, str(e)) from e
        except (ValueError, KeyError) as e:
            raise HTTPException(400, str(e)) from e
        from .. import edit_history
        edit_history.push(pid, p.source_ifc)               # ONE undo entry for the whole batch
        p.source_ifc = out
        audit.record(db, action="ifc.edit_batch", actor=actor, method="POST",
                     path=f"/projects/{pid}/edit/batch",
                     detail={"steps": [s.get("recipe") for s in steps]})
        db.commit()
    if publish:
        _publish_bg(pid)
        result["publish"] = "running"
    return result


@router.get("/content/catalog")
def content_catalog(_: str = Depends(current_user)):
    """CONTENT-1: the curated content catalog — logistics / furniture / landscaping parts, each mapped to the
    right IFC class + phase + classification. Place an item via `POST /projects/{pid}/edit` with the
    `place_content` recipe ({category, point, verts?, faces?})."""
    from aec_data import content  # type: ignore

    return content.catalog()


@router.get("/projects/{pid}/ffe-bom")
def ffe_bom(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """W9-6b: the **FF&E / furnishings bill of materials** from the model's placed furniture — count each
    item (by name) with its IFC class and the levels it appears on. An owner/vendor order starting point.
    409 without a source IFC."""
    from aec_data import content  # type: ignore
    from aec_data.ifc_loader import open_model  # type: ignore

    p = _project(db, pid)
    return content.furniture_bom(open_model(p.source_ifc))


@router.post("/projects/{pid}/content/import")
async def content_import(pid: str, file: UploadFile = File(...), category: str = "", e: float = 0.0,
                         n: float = 0.0, scale: float = 1.0, name: str = "", storey: str = "",
                         publish: bool = True, db: Session = Depends(get_db),
                         actor: str = Depends(require_role("editor"))):
    """CONTENT-1 (import): import a detailed mesh (glTF / GLB / OBJ / STL / PLY) and place it as the **right
    IFC** — auto-detect the catalog category from the filename (or pass `category=`), parse the mesh
    (recentred, glTF Y-up → IFC Z-up), and author it via `place_content` (correct IFC class + phase +
    classification). License-vet the source asset before importing. Versioned + undo-able + republished."""
    from aec_data import content  # type: ignore
    from aec_data import edit as ed

    p = _project(db, pid)
    data = await file.read()
    ext = Path(file.filename or "asset.glb").suffix.lower() or ".glb"
    cat = (category or "").strip().lower() or (content.detect_category(file.filename or "") or "")
    if not cat:
        raise HTTPException(400, "could not detect a content category from the filename — pass category=")
    if content.spec(cat) is None:
        raise HTTPException(400, f"unknown content category {cat!r}; see /content/catalog")
    try:
        verts, faces = content.parse_mesh(data, ext, float(scale))
    except Exception as ex:                            # noqa: BLE001 — surface any parse failure as a 400
        raise HTTPException(400, f"could not parse mesh: {ex}") from ex

    params = {"category": cat, "point": [float(e), float(n)], "verts": verts, "faces": faces,
              "name": (name or None), "storey": (storey or None)}
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    base_stem = re.sub(r"(_\d{14,20})+$", "", Path(p.source_ifc).stem)
    out = str(Path(p.source_ifc).with_name(f"{base_stem}_{stamp}.ifc"))
    try:
        result = ed.apply_recipe(p.source_ifc, "place_content", params, out)
    except (ValueError, KeyError) as ex:
        raise HTTPException(400, str(ex)) from ex
    from .. import edit_history
    edit_history.push(pid, p.source_ifc)
    p.source_ifc = out
    audit.record(db, action="content.import", actor=actor, method="POST",
                 path=f"/projects/{pid}/content/import", detail={"category": cat, "faces": len(faces)})
    db.commit()
    result["category"] = cat
    result["faces"] = len(faces)
    if publish:
        _publish_bg(pid)
        result["publish"] = "running"
    return result


@router.get("/projects/{pid}/authoring/capabilities")
def authoring_capabilities(pid: str, _: str = Depends(require_role("viewer"))):
    """Which optional/gated authoring capabilities are enabled on this server (so the UI can hide what's
    off). `execute_ifc_code` (A1) is the sandboxed Python escape hatch — off unless `AEC_ALLOW_IFC_CODE=1`."""
    from aec_data import sandbox  # type: ignore

    return {"execute_ifc_code": sandbox.enabled()}


@router.get("/projects/{pid}/edit/history")
def edit_history_state(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("viewer"))):
    """S4: whether the project's model can be undone / redone, and the stack depths."""
    from .. import edit_history

    _project(db, pid)
    return edit_history.state(pid)


def _restore_version(pid: str, db: Session, actor: str, publish: bool, redo: bool) -> dict:
    """Shared undo/redo: swap `source_ifc` to the popped version (verified to exist + stay in the project's
    IFC directory) and republish. The stored paths were written by the server, but we re-validate."""
    from .. import edit_history

    p = _project(db, pid)
    target = edit_history.redo(pid, p.source_ifc) if redo else edit_history.undo(pid, p.source_ifc)
    if target is None:
        raise HTTPException(409, "nothing to redo" if redo else "nothing to undo")
    tp = Path(target)
    # containment: the restored version must sit beside the current source IFC (defence-in-depth)
    if not tp.exists() or tp.parent.resolve() != Path(p.source_ifc).parent.resolve():
        raise HTTPException(409, "that version is no longer available")
    p.source_ifc = str(tp)
    audit.record(db, action="ifc.redo" if redo else "ifc.undo", actor=actor, method="POST",
                 path=f"/projects/{pid}/edit/{'redo' if redo else 'undo'}", detail={"restored": p.source_ifc})
    db.commit()
    out: dict = {"restored": p.source_ifc, "state": edit_history.state(pid)}
    if publish:
        _publish_bg(pid)
        out["publish"] = "running"
    return out


@router.post("/projects/{pid}/edit/undo")
def edit_undo(pid: str, publish: bool = Body(default=True, embed=True), db: Session = Depends(get_db),
              actor: str = Depends(require_role("editor"))):
    """S4: **undo** the last authoring edit — restore the prior model version + republish. GUID-stable
    (pins/RFIs/clashes keyed by GlobalId survive)."""
    return _restore_version(pid, db, actor, publish, redo=False)


@router.post("/projects/{pid}/edit/redo")
def edit_redo(pid: str, publish: bool = Body(default=True, embed=True), db: Session = Depends(get_db),
              actor: str = Depends(require_role("editor"))):
    """S4: **redo** an undone edit — restore the next model version + republish."""
    return _restore_version(pid, db, actor, publish, redo=True)


@router.post("/projects/{pid}/edit-preview")
def edit_preview(pid: str, recipe: str = Body(..., embed=True),
                 params: dict = Body(default={}, embed=True),
                 db: Session = Depends(get_db), _: str = Depends(require_role("editor"))):
    """Author just this element into a one-element IFC + convert it to a small preview fragment (fast),
    so the viewer can show real geometry immediately while the full model republishes in the
    background. Fail-open: 503 when the source/converter is unavailable, so the client just keeps its
    optimistic proxy and waits for the normal publish."""
    from aec_data import preview as pv  # type: ignore

    p = _project(db, pid)
    if not p.source_ifc or not Path(p.source_ifc).exists() or not _CONVERTER.exists():
        raise HTTPException(503, "preview unavailable")
    try:
        with tempfile.TemporaryDirectory() as td:
            tmp = str(Path(td) / "pv.ifc")
            out = str(Path(td) / "pv_out.ifc")
            frag = Path(td) / "pv.frag"
            guid = pv.build_preview_ifc(p.source_ifc, recipe, params, out, tmp)
            subprocess.run(["node", str(_CONVERTER), out, str(frag)],
                           check=True, capture_output=True, timeout=120)
            data = frag.read_bytes()
    except HTTPException:
        raise
    except Exception as e:            # noqa: BLE001 — any preview failure → client keeps the proxy
        raise HTTPException(503, f"preview failed: {str(e)[:120]}") from e
    return Response(content=data, media_type="application/octet-stream",
                    headers={"X-Element-Guid": guid or ""})


@router.post("/projects/{pid}/publish", status_code=202)
def publish(pid: str, reconvert: bool = Body(default=True), db: Session = Depends(get_db),
            actor: str = Depends(require_role("editor"))):
    """Re-run the pipeline on the current source IFC (convert to .frag + reindex), off the
    request thread. Returns immediately; poll GET publish/status for completion."""
    _project(db, pid)  # 404 guard
    audit.record(db, action="ifc.publish", actor=actor, method="POST",
                 path=f"/projects/{pid}/publish")
    db.commit()
    _publish_bg(pid)
    return {"state": "running"}


@router.post("/projects/{pid}/source-ifc")
async def upload_source_ifc(pid: str, file: UploadFile = File(...), publish: bool = True,
                            db: Session = Depends(get_db),
                            actor: str = Depends(require_role("editor"))):
    """Upload a project's source IFC (enables authoring + republish). Saves a local copy
    the converter can read plus a durable copy in object storage, then publishes."""
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    # Programmatic publishing (REST API key, e.g. the pyRevit bridge) is a Commercial+ entitlement when
    # enforcement is on. Interactive "Open IFC…" by a signed-in user stays free on any plan. No-op in open mode.
    if actor == "api-key":
        from .. import licensing
        licensing.require("api_access", "Programmatic publish (REST API)")
    data = await file.read()
    _IFC_DIR.joinpath(storage.safe_seg(pid)).mkdir(parents=True, exist_ok=True)
    ifc_path = _IFC_DIR / storage.safe_seg(pid) / "source.ifc"
    ifc_path.write_bytes(data)
    storage.put(f"{storage.safe_seg(pid)}/source.ifc", data)          # durable copy
    p.source_ifc = str(ifc_path)
    db.commit()
    audit.record(db, action="ifc.upload", actor=actor, method="POST",
                 path=f"/projects/{pid}/source-ifc")
    db.commit()
    out: dict = {"source_ifc": str(ifc_path), "size": len(data)}
    if publish:                       # convert off-thread; client polls publish/status
        _publish_bg(pid)
        out["publish"] = "running"
    return out


@router.get("/projects/{pid}/models")
def list_project_models(pid: str, db: Session = Depends(get_db),
                        _: str = Depends(require_role("viewer"))):
    """Discipline models layered on the project beyond the primary source IFC (for federated clash)."""
    rows = db.query(ProjectModel).filter_by(project_id=pid).order_by(ProjectModel.created_at).all()
    return [{"id": m.id, "discipline": m.discipline,
             "created_at": m.created_at.isoformat() if m.created_at else None} for m in rows]


@router.post("/projects/{pid}/models", status_code=201)
async def add_project_model(pid: str, file: UploadFile = File(...), discipline: str = Form("Model"),
                            db: Session = Depends(get_db), actor: str = Depends(require_role("editor"))):
    """Append a discipline IFC (STR / MEP / ARCH …) so it can take part in federated clash."""
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    data = await file.read()
    mid = uuid.uuid4().hex
    (_IFC_DIR / storage.safe_seg(pid) / "models").mkdir(parents=True, exist_ok=True)
    ifc_path = _IFC_DIR / storage.safe_seg(pid) / "models" / f"{mid}.ifc"
    ifc_path.write_bytes(data)
    storage.put(f"{storage.safe_seg(pid)}/models/{mid}.ifc", data)          # durable copy
    m = ProjectModel(id=mid, project_id=pid, discipline=(discipline or "Model").strip() or "Model",
                     ifc_path=str(ifc_path))
    db.add(m)
    audit.record(db, action="model.append", actor=actor, method="POST",
                 path=f"/projects/{pid}/models", detail={"discipline": m.discipline})
    db.commit()
    return {"id": m.id, "discipline": m.discipline, "size": len(data)}


@router.post("/projects/{pid}/raise-plan")
async def raise_plan_to_bim(pid: str, file: UploadFile = File(...),
                            wall_height: float = Form(3.0), wall_thickness: float = Form(0.2),
                            preview: bool = Form(False),
                            db: Session = Depends(get_db), actor: str = Depends(require_role("editor"))):
    """2D -> BIM raise: turn an uploaded DXF floor plan into a real IFC4 model (walls extruded from
    the line-work, IfcSpaces from closed room polygons). `preview=true` just parses and returns the
    detected wall/room counts without writing anything. Otherwise the raised IFC is registered as a
    '2D Raise' discipline model (usable in the viewer + federated clash). 400 on an unreadable DXF."""
    from aec_data import plan_to_bim  # from services/data/src (on sys.path)
    if not db.get(Project, pid):
        raise HTTPException(404, "project not found")
    data = await file.read()
    with tempfile.TemporaryDirectory() as td:   # never scratch into the read-only /app tree
        dxf_path = Path(td) / "plan.dxf"
        dxf_path.write_bytes(data)
        if preview:
            try:
                return plan_to_bim.parse_plan(str(dxf_path))
            except RuntimeError as e:
                raise HTTPException(400, str(e)) from e
        mid = uuid.uuid4().hex
        ifc_tmp = Path(td) / f"{mid}.ifc"
        try:
            stats = plan_to_bim.raise_plan(str(dxf_path), str(ifc_tmp),
                                           wall_height=wall_height, wall_thickness=wall_thickness)
        except RuntimeError as e:
            raise HTTPException(400, str(e)) from e
        ifc_bytes = ifc_tmp.read_bytes()
        (_IFC_DIR / storage.safe_seg(pid) / "models").mkdir(parents=True, exist_ok=True)
        ifc_path = _IFC_DIR / storage.safe_seg(pid) / "models" / f"{mid}.ifc"
        ifc_path.write_bytes(ifc_bytes)
        storage.put(f"{storage.safe_seg(pid)}/models/{mid}.ifc", ifc_bytes)
        m = ProjectModel(id=mid, project_id=pid, discipline="2D Raise", ifc_path=str(ifc_path))
        db.add(m)
        audit.record(db, action="model.raise", actor=actor, method="POST",
                     path=f"/projects/{pid}/raise-plan",
                     detail={"walls": stats["wall_count"], "spaces": stats["space_count"]})
        db.commit()
    return {"id": mid, "discipline": "2D Raise",
            "wall_count": stats["wall_count"], "space_count": stats["space_count"],
            "total_wall_length_m": stats["total_wall_length_m"],
            "total_floor_area_m2": stats["total_floor_area_m2"], "units": stats["units"],
            "wall_height_m": stats["wall_height_m"], "wall_thickness_m": stats["wall_thickness_m"]}


@router.delete("/projects/{pid}/models/{mid}")
def delete_project_model(pid: str, mid: str, db: Session = Depends(get_db),
                         actor: str = Depends(require_role("editor"))):
    m = db.get(ProjectModel, mid)
    if not m or m.project_id != pid:
        raise HTTPException(404, "model not found")
    try:
        Path(m.ifc_path).unlink(missing_ok=True)
    except OSError:
        pass
    db.delete(m)
    db.commit()
    return {"deleted": True, "id": mid}


@router.get("/bridge/rvt/status")
def rvt_bridge_status(_: str = Depends(current_user)):
    """Is the optional paid Revit (.rvt) → IFC bridge available? The UI checks this before offering
    the import, and shows the cost warning + the free IFC-export alternative."""
    from .. import aps
    return aps.status()


@router.get("/interop/speckle/status")
def speckle_status(_: str = Depends(current_user)):
    """Is the optional (open-source, self-hostable) Speckle interoperability bridge configured? When
    on, this verifies live connectivity to the Speckle server. IFC/Fragments stay the source of truth."""
    from .. import speckle_bridge
    return speckle_bridge.status()


@router.post("/projects/{pid}/interop/speckle/send", status_code=202)
def speckle_send(pid: str, db: Session = Depends(get_db), _: str = Depends(require_role("reviewer"))):
    """Send the project's model/data to a Speckle stream (requires the bridge configured)."""
    from .. import speckle_bridge
    if not speckle_bridge.is_enabled():
        raise HTTPException(501, speckle_bridge.status()["message"])
    p = _project(db, pid)
    try:
        return speckle_bridge.send_model(pid, p.name, p.source_ifc)
    except NotImplementedError as e:
        raise HTTPException(501, str(e)) from e


@router.post("/projects/{pid}/import/rvt", status_code=202)
async def import_rvt(pid: str, file: UploadFile = File(...), confirm_cost: bool = False,
                     publish: bool = True, db: Session = Depends(get_db),
                     actor: str = Depends(require_role("editor"))):
    """Import a native Revit .rvt by converting it to IFC via the paid APS bridge, then treat it like
    any source IFC (authoring / drawings / analysis / proforma all flow from it). Gated twice: the
    bridge must be configured (else 501 → use free IFC export), and the caller must `confirm_cost`
    (else 402) because Autodesk bills per conversion."""
    from .. import aps
    p = db.get(Project, pid)
    if not p:
        raise HTTPException(404, "project not found")
    if not aps.is_enabled():
        raise HTTPException(501, aps.status()["message"])          # bridge off → free alternative
    if not (file.filename or "").lower().endswith(".rvt"):         # reject before charging the cost
        raise HTTPException(400, "expected a Revit .rvt file (this bridge converts native .rvt only)")
    if not confirm_cost:
        raise HTTPException(402, "RVT conversion incurs Autodesk APS cloud-credit cost. Re-send with "
                                 "confirm_cost=true to proceed.")
    data = await file.read()
    if not data:
        raise HTTPException(400, "empty .rvt file")
    try:
        ifc = aps.translate_rvt_to_ifc(data, file.filename or "model.rvt")
    except RuntimeError as e:  # NotImplementedError is a RuntimeError subclass — both mean "bridge unavailable"
        raise HTTPException(502, f"RVT→IFC bridge: {e}") from e    # clear, actionable provisioning error
    _IFC_DIR.joinpath(storage.safe_seg(pid)).mkdir(parents=True, exist_ok=True)
    ifc_path = _IFC_DIR / storage.safe_seg(pid) / "source.ifc"
    ifc_path.write_bytes(ifc)
    storage.put(f"{storage.safe_seg(pid)}/source.ifc", ifc)
    p.source_ifc = str(ifc_path)
    db.commit()
    audit.record(db, action="ifc.import_rvt", actor=actor, method="POST", path=f"/projects/{pid}/import/rvt",
                 detail={"rvt": file.filename, "ifc_bytes": len(ifc)})
    db.commit()
    out: dict = {"source_ifc": str(ifc_path), "size": len(ifc), "source": "aps_rvt_bridge"}
    if publish:
        _publish_bg(pid)
        out["publish"] = "running"
    return out


def _publish(p: Project, reconvert: bool = True) -> dict:
    from aec_data import properties_index  # type: ignore

    out = {"reconverted": False, "reindexed": 0}
    # 1. reconvert IFC -> .frag (Node converter); convert to a temp file then push through
    #    storage.put so it works with both the local and S3/MinIO backends.
    if reconvert and _CONVERTER.exists() and p.source_ifc and Path(p.source_ifc).exists():
        frag_key = f"{p.id}/model.frag"
        try:
            with tempfile.TemporaryDirectory() as td:
                frag_tmp = Path(td) / "model.frag"
                subprocess.run(["node", str(_CONVERTER), p.source_ifc, str(frag_tmp)],
                               check=True, capture_output=True, timeout=600)
                storage.put(frag_key, frag_tmp.read_bytes())
            out["reconverted"] = True
            out["frag_key"] = frag_key
        except Exception as e:  # node missing / convert failed — non-fatal for the API, but LOG it:
            # a broken converter must show up in structured logs/alerting, not only in a status JSON
            # a human may never poll (a deployment can silently drop conversions for hours otherwise).
            logging.getLogger("aec.publish").exception("fragment conversion failed for %s", p.id)
            out["reconvert_error"] = str(e)[:300]
    # 2. rebuild + hot-load the properties index
    idx = properties_index.index_file(p.source_ifc)
    props_router._load(p.id, idx)  # hot-swap the in-memory index
    storage.put(f"{p.id}/props.json", __import__("json").dumps(idx).encode("utf-8"))
    out["reindexed"] = idx["counts"]["elements"]
    try:                              # snapshot a model version (GUID set) for history/diff
        from .. import versions
        out["version"] = versions.snapshot(p.id, idx)
    except Exception as e:            # noqa: BLE001 — versioning must never break a publish
        out["version_error"] = str(e)[:160]
    # 3. warm the model-takeoff cache so the first estimate is instant — but skip very large
    #    imports (geometry meshing is minutes) to avoid wasting the publish worker on them.
    try:
        if Path(p.source_ifc).stat().st_size < 25_000_000:
            from aec_data import qto  # type: ignore
            qto.takeoff_file(p.source_ifc, force_geometry=True)
            out["takeoff_warmed"] = True
    except Exception as e:            # noqa: BLE001 — warming is best-effort
        out["takeoff_warm_error"] = str(e)[:120]
    return out


# --- background publish (convert/reindex off the request thread) -------------
def _set_pub_status(pid: str, state: str, detail: dict | None = None) -> None:
    storage.put(f"{pid}/publish_status.json", json.dumps(
        {"state": state, "detail": detail,
         "at": datetime.now(timezone.utc).isoformat()}).encode())


def run_publish(pid: str) -> None:
    """Convert + reindex a project's source IFC, recording status. Pure + synchronous + idempotent —
    callable by the daemon thread now, or directly by an external task worker (RQ / Dramatiq on the
    already-optional Redis) later, with no code change. We deliberately don't run Celery: for the
    self-hosted / desktop mission a thread + durable status poll is the right amount of machinery —
    see docs/audit-2026-06.md for when a queue becomes worthwhile."""
    from ..db import SessionLocal
    _set_pub_status(pid, "running")
    try:
        with SessionLocal() as db:
            p = db.get(Project, pid)
            if not p:
                _set_pub_status(pid, "error", {"error": "project not found"})
                return
            result = _publish(p)
        _set_pub_status(pid, "error" if result.get("reconvert_error") else "done", result)
    except Exception as e:  # noqa: BLE001 — surface the failure in the status, never crash the worker
        logging.getLogger("aec.publish").exception("publish failed for %s", pid)
        _set_pub_status(pid, "error", {"error": str(e)[:300]})


def _publish_bg(pid: str) -> None:
    """Run run_publish off the request thread. A 50MB IFC convert takes minutes — doing it in-request
    would tie up a worker; clients poll publish/status. (Swap this for `worker.enqueue(run_publish, pid)`
    to move it onto a real queue without touching run_publish.)"""
    _set_pub_status(pid, "running")
    threading.Thread(target=run_publish, args=(pid,), daemon=True).start()


@router.get("/projects/{pid}/publish/status")
def publish_status(pid: str, _: str = Depends(require_role("viewer"))):
    """Poll the async publish job: idle | running | done | error (+ detail)."""
    key = f"{pid}/publish_status.json"
    if storage.exists(key):
        s = json.loads(storage.get(key))
        # interrupted-job recovery: a "running" status older than the convert timeout means the worker
        # died (e.g. server restart) — report it as an error so the client isn't stuck polling forever.
        if s.get("state") == "running" and s.get("at"):
            try:
                age = (datetime.now(timezone.utc) - datetime.fromisoformat(s["at"])).total_seconds()
                if age > 900:
                    return {"state": "error", "detail": {"error": "publish interrupted (worker restarted)"}, "at": s["at"]}
            except (ValueError, TypeError):
                pass
        return s
    return {"state": "idle"}
