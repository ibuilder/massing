# -*- coding: utf-8 -*-
__title__ = "Settings"
__doc__ = """Configure the Massing connection: API URL, web (app) URL and your API key.
Get a key + URLs from Settings -> Massing licence in the Massing web app (Commercial plan and up
includes REST API access). Stored per-user in pyRevit config."""
__author__ = "Massing (massing.build)"

from pyrevit import forms, script
import massing_config as mc

cur = mc.read()

# Simple sequential prompts (works across pyRevit versions)
api_url = forms.ask_for_string(default=cur["api_url"] or "https://massing.build/api",
                               prompt="Massing API URL (e.g. https://your-host/api)", title="Massing — API URL")
if api_url is None:
    script.exit()
app_url = forms.ask_for_string(default=cur["app_url"] or "https://massing.build",
                               prompt="Massing web app URL (for 'Open in Massing' links)", title="Massing — App URL")
if app_url is None:
    script.exit()
api_key = forms.ask_for_string(default=cur["api_key"],
                               prompt="API key (Bearer). Commercial plan and up.", title="Massing — API key")
if api_key is None:
    script.exit()
project_name = forms.ask_for_string(default=cur["project_name"] or "",
                                    prompt="Default Massing project name (blank = use the Revit file name)",
                                    title="Massing — Project")
if project_name is None:
    script.exit()

mc.write(api_url=api_url, app_url=app_url, api_key=api_key, project_name=project_name)
forms.alert("Massing connection saved.\nAPI: {0}".format(api_url.rstrip('/')), title="Massing", warn_icon=False)
