# -*- coding: utf-8 -*-
"""Shared config + client factory for the Massing pyRevit buttons. Stores the API URL, web (app)
URL and API key in pyRevit's per-user config (Massing > Settings writes it). Revit-side only."""
from pyrevit import script, forms

from massing_api import MassingClient, MassingError  # noqa: F401 (re-exported)

_SECTION = "massing"


def _cfg():
    return script.get_config(_SECTION)


def read():
    c = _cfg()
    return {
        "api_url": getattr(c, "api_url", "") or "",
        "app_url": getattr(c, "app_url", "") or "",
        "api_key": getattr(c, "api_key", "") or "",
        "project_name": getattr(c, "project_name", "") or "",
    }


def write(api_url=None, app_url=None, api_key=None, project_name=None):
    c = _cfg()
    if api_url is not None:
        c.api_url = api_url.strip().rstrip("/")
    if app_url is not None:
        c.app_url = app_url.strip().rstrip("/")
    if api_key is not None:
        c.api_key = api_key.strip()
    if project_name is not None:
        c.project_name = project_name.strip()
    script.save_config()


def get_client(require=True):
    """Build a MassingClient from the stored config. If unconfigured and require=True, prompts the
    user to open Settings and returns None."""
    cfg = read()
    if require and not cfg["api_url"]:
        forms.alert("Massing isn't configured yet.\nClick Massing > Settings to set your API URL + key.",
                    title="Massing", warn_icon=True)
        return None
    return MassingClient(cfg["api_url"], cfg["api_key"], app_url=cfg["app_url"] or None)
