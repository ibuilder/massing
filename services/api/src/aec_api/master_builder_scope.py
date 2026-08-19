"""Which Master Builder protocol steps a workspace/persona actually asks.

Kept free of SQLAlchemy / FastAPI so the lockstep test against the TS strip can run
without the API venv. `brief()` still lives in master_builder.py; this only scopes it.
"""
from __future__ import annotations

from typing import Any

# Same maps as apps/web/src/portal/panels/readinessStrip.ts — asserted by
# test_master_builder_scope.py so the protocol cannot fork between layers.
STEPS_BY_WORKSPACE: dict[str, tuple[str, ...]] = {
    "construction": ("delivery", "risk", "design", "handover"),
    "design": ("place", "program", "design", "regulatory"),
    "developer": ("place", "program", "feasibility", "regulatory"),
}
STEPS_BY_PERSONA: dict[str, tuple[str, ...]] = {
    "superintendent": ("delivery", "risk", "handover"),
    "project_manager": ("delivery", "risk", "feasibility", "design"),
    "gc": ("delivery", "risk", "design", "feasibility"),
    "architect": ("place", "program", "design", "regulatory"),
    "engineer": ("design", "regulatory", "place"),
    "developer": ("place", "program", "feasibility", "regulatory"),
    "subcontractor": ("delivery", "risk"),
}


def scope_step_keys(workspace: str, persona: str) -> list[str]:
    """Intersect persona with workspace; empty intersect keeps the workspace set."""
    ws = STEPS_BY_WORKSPACE.get(workspace) or STEPS_BY_WORKSPACE["construction"]
    if not persona or persona == "all":
        return list(ws)
    keep = STEPS_BY_PERSONA.get(persona)
    if not keep:
        return list(ws)
    scoped = [k for k in ws if k in keep]
    return scoped or list(ws)


def apply_scope(brief: dict[str, Any], workspace: str | None, persona: str | None) -> dict[str, Any]:
    """Filter `steps` for a home strip. Overall readiness_pct / step_count stay on the full 8."""
    if not workspace:
        return brief
    keys = scope_step_keys(workspace, persona or "all")
    want = set(keys)
    out = dict(brief)
    out["steps"] = [s for s in brief.get("steps") or [] if s.get("key") in want]
    out["scope"] = {"workspace": workspace, "persona": persona or "all", "keys": keys}
    return out
