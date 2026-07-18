"""PLUGIN-REGISTRY endpoints — inspect + reload the server-side recipe plugins."""
from __future__ import annotations

from fastapi import APIRouter, Depends

from ..rbac import current_user
from .cost import _require_platform_admin

router = APIRouter()


@router.get("/plugins")
def plugins_status(_: str = Depends(current_user)):
    """The plugin registry: host API version, whether discovery is enabled (`AEC_PLUGINS_ENABLED=1`),
    every loaded plugin with its namespaced recipes, and every refusal WITH its reason — a half-loaded
    plugin set is visible, never silent."""
    from .. import plugin_registry
    return plugin_registry.status()


@router.post("/plugins/reload")
def plugins_reload(_admin=Depends(_require_platform_admin)):
    """Re-discover + reload all plugins (idempotent — previous registrations are replaced). Platform
    operation: plugins execute Python at load and their recipes become available to every project."""
    from .. import plugin_registry
    return plugin_registry.load_all()
