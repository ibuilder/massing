"""MCP tool catalog + dispatcher — the project/model surface external AI agents can drive.

The Model Context Protocol lets a client (Claude Desktop, Cursor, an agent) call a server's tools by
name. This module is the *pure* half: a catalog of tools an agent can run against a project (read the
snapshot and records, run the CDE / KPI / model-quality checks, run a standards-compliance check, and
create an RFI) and a dispatcher that executes one against a DB session. `mcp_server.py` wires this to
the protocol; keeping the logic here means it's testable without the MCP SDK and reuses the same engines
the HTTP API does — nothing is duplicated or fabricated."""
from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

# Tool catalog. input_schema is JSON Schema (what the agent must pass).
TOOLS: list[dict[str, Any]] = [
    {"name": "list_projects", "description": "List projects (id + name).",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "project_snapshot",
     "description": "Cross-module status snapshot for a project: RFI/submittal/CO/punch/safety tallies, "
                    "schedule + budget KPIs and the risk headline.",
     "input_schema": {"type": "object", "properties": {"project_id": {"type": "string"}},
                      "required": ["project_id"]}},
    {"name": "list_records",
     "description": "List records of a module (e.g. rfi, submittal, information_container) for a project.",
     "input_schema": {"type": "object", "properties": {
         "project_id": {"type": "string"}, "module": {"type": "string"},
         "limit": {"type": "integer", "default": 50}}, "required": ["project_id", "module"]}},
    {"name": "cde_status", "description": "ISO 19650 CDE container discipline for a project.",
     "input_schema": {"type": "object", "properties": {"project_id": {"type": "string"}},
                      "required": ["project_id"]}},
    {"name": "bim_kpi_scorecard", "description": "The 10-category BIM KPI scorecard for a project.",
     "input_schema": {"type": "object", "properties": {"project_id": {"type": "string"}},
                      "required": ["project_id"]}},
    {"name": "openbim_quality",
     "description": "openBIM model quality (LOIN, IDS compliance, export health, bSDD) — needs a loaded model.",
     "input_schema": {"type": "object", "properties": {
         "project_id": {"type": "string"}, "use_case": {"type": "string"}}, "required": ["project_id"]}},
    {"name": "standards_check",
     "description": "Run a standards-compliance check (iso19650 | cobie | ids | uniclass) against the "
                    "project's data; returns findings with clause references and recommendations.",
     "input_schema": {"type": "object", "properties": {
         "project_id": {"type": "string"},
         "standard": {"type": "string", "enum": ["iso19650", "cobie", "ids", "uniclass"]}},
         "required": ["project_id", "standard"]}},
    {"name": "create_rfi",
     "description": "Create an RFI (Request for Information) on a project.",
     "input_schema": {"type": "object", "properties": {
         "project_id": {"type": "string"}, "subject": {"type": "string"},
         "question": {"type": "string"}, "discipline": {"type": "string"}},
         "required": ["project_id", "subject", "question"]}},
    # --- MCP-PACK: the authoring + analysis engines, so an agent is a first-class author, not just a reader.
    {"name": "list_recipes",
     "description": "The authoring-coverage matrix: every edit recipe an agent can drive with run_recipe, "
                    "grouped by category with the IFC class each emits. No project needed.",
     "input_schema": {"type": "object", "properties": {}}},
    {"name": "run_recipe",
     "description": "Drive a GUID-stable authoring recipe (e.g. add_wall, add_column, set_pset) against the "
                    "project's IFC, saving a new audited version — the same server path the UI uses. Params "
                    "are validated by the authoring guardrails; the edit is undoable. Reconvert/publish "
                    "happens via the normal publish flow, not this tool. See list_recipes for names + params.",
     "input_schema": {"type": "object", "properties": {
         "project_id": {"type": "string"}, "recipe": {"type": "string"},
         "params": {"type": "object"}}, "required": ["project_id", "recipe"]}},
    {"name": "schedule_risk",
     "description": "Monte Carlo schedule forecast over the CPM network: P10/P50/P80/P90 completion, "
                    "per-activity criticality index, and delay drivers; calibrated by the team's pull-plan PPC.",
     "input_schema": {"type": "object", "properties": {
         "project_id": {"type": "string"}, "iterations": {"type": "integer", "default": 1000}},
         "required": ["project_id"]}},
    {"name": "carbon_report",
     "description": "Embodied-carbon (A1–A3) inventory per element off the model index, plus Buy Clean limit "
                    "checks and a LEED material inventory. Needs a loaded model.",
     "input_schema": {"type": "object", "properties": {
         "project_id": {"type": "string"}, "gfa_m2": {"type": "number"}}, "required": ["project_id"]}},
    {"name": "permit_readiness",
     "description": "Submission-readiness report over the code engines + drawing register: egress, "
                    "approvability, code analysis, and sheet-series coverage. Needs a loaded model.",
     "input_schema": {"type": "object", "properties": {
         "project_id": {"type": "string"}, "occupancy_group": {"type": "string"},
         "construction_type": {"type": "string"}}, "required": ["project_id"]}},
    {"name": "drawing_qa",
     "description": "Drawing-set QA review: set integrity (duplicate/gap numbers, titleblock), issuance "
                    "hygiene, and model cross-checks — every finding cited to its sheet. Runs without a model "
                    "(register-only) and adds the cross-checks when one exists.",
     "input_schema": {"type": "object", "properties": {"project_id": {"type": "string"}},
                      "required": ["project_id"]}},
    # --- AI read tools (P2): the model's own numbers, readable by any agent ------------------------
    {"name": "model_quantities",
     "description": "Measured quantity takeoff rolled up by discipline: reinforcement tonnage, MEP "
                    "linear runs + fitting counts, structural volume, wall/slab areas. Needs a model.",
     "input_schema": {"type": "object", "properties": {"project_id": {"type": "string"}},
                      "required": ["project_id"]}},
    {"name": "computed_schedules",
     "description": "The door / window / room schedules computed straight from the model (marks, "
                    "sizes, levels) — the same data the A-601 sheet prints. Needs a model.",
     "input_schema": {"type": "object", "properties": {"project_id": {"type": "string"}},
                      "required": ["project_id"]}},
    {"name": "clash_results",
     "description": "Geometric clash detection over the source model (element-pair intersections with "
                    "volumes + GUIDs). Needs a model.",
     "input_schema": {"type": "object", "properties": {"project_id": {"type": "string"}},
                      "required": ["project_id"]}},
    {"name": "code_violations",
     "description": "Computed occupancy-load + egress-capacity findings (IBC 1004/1005) from the "
                    "model's spaces and doors, citing sections — pre-check facts, not a certified "
                    "review. Needs a model with IfcSpaces.",
     "input_schema": {"type": "object", "properties": {"project_id": {"type": "string"}},
                      "required": ["project_id"]}},
]

TOOL_NAMES = frozenset(t["name"] for t in TOOLS)
# Tools that mutate the project (write). These carry an editor-role gate in dispatch, mirroring the
# require_role("editor") their HTTP routes use — membership alone is not enough when RBAC is on.
_WRITE_TOOLS = frozenset({"create_rfi", "run_recipe"})


def dispatch(db: Session, name: str, args: dict[str, Any], actor: str = "mcp",
             user: str | None = None) -> Any:
    """Execute a tool by name against the DB session. Raises ValueError on an unknown tool.

    Defense-in-depth authorization: the MCP server is local/stdio today, but dispatch must not be the
    layer that trusts everyone if that ever changes. The effective identity is `user`, else the
    `AEC_MCP_USER` env var, else the admin api-key (the historical stdio behaviour). Under RBAC a
    non-admin identity is membership-scoped: `list_projects` returns only member projects, and any tool
    addressing a `project_id` outside the membership raises PermissionError."""
    import os as _os

    from . import bim_kpi, cde, standards_expert
    from . import modules as me
    from .models import Project
    from .rbac import member_project_ids
    a = args or {}
    pid = a.get("project_id")

    from . import rbac

    ident = user or _os.environ.get("AEC_MCP_USER") or "api-key"
    allowed = member_project_ids(db, ident)          # None = unrestricted (RBAC off / admin)
    if allowed is not None and pid is not None and pid not in allowed:
        raise PermissionError(f"identity {ident!r} is not a member of project {pid!r}")

    # Write tools carry the same editor gate as their HTTP routes — membership alone isn't enough when
    # RBAC is on (a viewer-role member must not be able to author or create records over MCP).
    if name in _WRITE_TOOLS and rbac.RBAC_ON and ident != "api-key":
        role = rbac.role_for(db, pid, ident) if pid else None
        if rbac.ROLE_ORDER.get(role or "", -1) < rbac.ROLE_ORDER["editor"]:
            raise PermissionError(
                f"tool {name!r} requires editor on project {pid!r} (identity {ident!r} has "
                f"{role or 'no'} role)")

    if name == "list_projects":
        q = db.query(Project)
        if allowed is not None:
            q = q.filter(Project.id.in_(allowed))
        return [{"id": p.id, "name": p.name} for p in q.limit(500).all()]
    if name == "project_snapshot":
        from . import assistant
        return assistant.project_snapshot(db, pid)
    if name == "list_records":
        return me.list_records(db, a["module"], pid, limit=int(a.get("limit") or 50))
    if name == "cde_status":
        return cde.status(db, pid)
    if name == "bim_kpi_scorecard":
        return bim_kpi.scorecard(db, pid)
    if name == "openbim_quality":
        from . import ids_authoring, openbim_quality
        from .model_index import _INDEX, _ensure_loaded
        _ensure_loaded(pid)
        idx = _INDEX.get(pid)
        if not idx:
            return {"error": "no model loaded for this project"}
        uc = a.get("use_case")
        return openbim_quality.summary(idx, ids_authoring.specs_for_use_case(uc) if uc else None)
    if name == "standards_check":
        return standards_expert.check(db, pid, a["standard"])
    if name == "create_rfi":
        data = {"subject": a["subject"], "question": a["question"]}
        if a.get("discipline"):
            data["discipline"] = a["discipline"]
        return me.create_record(db, "rfi", pid, {"data": data}, actor, None)
    if name == "list_recipes":
        from . import authoring_matrix
        return authoring_matrix.matrix()
    if name == "run_recipe":
        return _run_recipe(db, pid, a["recipe"], a.get("params") or {}, user=ident)
    if name == "schedule_risk":
        from . import schedule_risk
        acts = me.list_records(db, "schedule_activity", pid, limit=1_000_000)
        ppc_val = None
        try:                                             # calibrate the tail on the team's own PPC
            from . import pull_plan
            ppc_val = (pull_plan.board(db, pid).get("metrics") or {}).get("ppc_pct")
        except Exception:  # noqa: BLE001 — no pull-plan data → uncalibrated defaults
            ppc_val = None
        return schedule_risk.simulate(acts, iterations=int(a.get("iterations") or 1000), ppc_pct=ppc_val)
    if name == "carbon_report":
        from . import carbon_compliance
        idx = _model_index(pid)
        if idx is None:
            return {"error": "no model loaded for this project"}
        result = carbon_compliance.element_carbon(idx, gfa_m2=a.get("gfa_m2"))
        return {**result, "buy_clean": carbon_compliance.buy_clean_check(result),
                "leed_inventory": carbon_compliance.leed_inventory(result)}
    if name == "permit_readiness":
        from . import permit_check
        model = _open_source(db, pid)
        if model is None:
            return {"error": "no model loaded for this project"}
        return permit_check.readiness(db, pid, model,
                                      occupancy_group=a.get("occupancy_group") or "",
                                      construction_type=a.get("construction_type") or "")
    if name == "drawing_qa":
        from . import drawing_qa
        return drawing_qa.review(db, pid, _open_source(db, pid))
    if name == "model_quantities":
        from aec_data import qto  # type: ignore
        return qto.discipline_summary(_require_model(db, pid))
    if name == "computed_schedules":
        from aec_data import drawing_schedules  # type: ignore
        return drawing_schedules.schedules(_require_model(db, pid))
    if name == "clash_results":
        from aec_data import clash  # type: ignore
        return clash.detect(_require_model(db, pid))
    if name == "code_violations":
        from . import codecheck_egress
        return codecheck_egress.egress_from_model(_require_model(db, pid))
    raise ValueError(f"unknown tool {name!r}")


def _require_model(db: Session, pid: str):
    """The opened source IFC for the read tools — a clear error instead of a stack trace without one."""
    m = _open_source(db, pid)
    if m is None:
        raise ValueError("project has no source IFC — load a model first")
    return m


def _model_index(pid: str) -> dict | None:
    """The loaded property/quantity index for a project (loading it if needed), or None if no model."""
    from .model_index import _INDEX, _ensure_loaded
    _ensure_loaded(pid)
    return _INDEX.get(pid)


def _open_source(db: Session, pid: str):
    """Open the project's source IFC for the model-file engines, or None if there isn't one / it fails."""
    from .models import Project
    p = db.get(Project, pid)
    if not p or not p.source_ifc:
        return None
    try:
        from aec_data.ifc_loader import open_model  # type: ignore
        return open_model(p.source_ifc)
    except Exception:  # noqa: BLE001 — no readable model → the caller falls back to register-only / error
        return None


def _run_recipe(db: Session, pid: str, recipe: str, params: dict[str, Any], user: str | None) -> Any:
    """Apply an authoring recipe to the project's IFC, saving a new audited, undoable version — the same
    path `POST /projects/{pid}/edit` uses (guardrail validation, edit_history push, audit). Reconvert /
    publish is intentionally left to the normal publish flow; this returns the recipe result."""
    import re
    from datetime import datetime, timezone
    from pathlib import Path

    from aec_data import edit as ed  # type: ignore

    from . import audit, edit_history, pid_lock
    from .models import Project
    # Same per-project serialization as POST /edit: without it an MCP edit racing a UI edit would both
    # read the same source_ifc and the last pointer-swap commit silently orphans the other's version.
    with pid_lock.mutating(pid):
        p = db.get(Project, pid)
        if p is not None:
            db.refresh(p)                              # the pointer may have moved while we waited
        if not p or not p.source_ifc:
            raise ValueError("project has no source IFC to author against")
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
        base_stem = re.sub(r"(_\d{14,20})+$", "", Path(p.source_ifc).stem)
        out = str(Path(p.source_ifc).with_name(f"{base_stem}_{stamp}.ifc"))
        result = ed.apply_recipe(p.source_ifc, recipe, params, out)  # raises ValueError/KeyError on bad input
        edit_history.push(pid, p.source_ifc)
        p.source_ifc = out
        audit.record(db, action="ifc.edit", actor=user or "mcp", method="MCP",
                     path=f"/projects/{pid}/edit", detail=result)
        db.commit()
    return result


def catalog() -> list[dict[str, Any]]:
    """Tool catalog for discovery (name + description + input schema)."""
    return TOOLS
