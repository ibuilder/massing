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
]

TOOL_NAMES = frozenset(t["name"] for t in TOOLS)


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

    ident = user or _os.environ.get("AEC_MCP_USER") or "api-key"
    allowed = member_project_ids(db, ident)          # None = unrestricted (RBAC off / admin)
    if allowed is not None and pid is not None and pid not in allowed:
        raise PermissionError(f"identity {ident!r} is not a member of project {pid!r}")

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
    raise ValueError(f"unknown tool {name!r}")


def catalog() -> list[dict[str, Any]]:
    """Tool catalog for discovery (name + description + input schema)."""
    return TOOLS
