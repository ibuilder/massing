# -*- coding: utf-8 -*-
__title__ = "Sync\nIssues (BCF)"
__doc__ = """Round-trip issues with Massing over the open BCF standard:
- Download: pull the project's RFIs / clashes / punch pins from Massing as a .bcfzip (open it in
  your BCF viewer of choice — BCFier, Revizto, etc.).
- Upload: push a local .bcfzip of Revit-side review comments back into Massing.

Issues are keyed by IFC GlobalId so pins land on the right elements both ways."""
__author__ = "Massing (massing.build)"

import os

from pyrevit import forms, script

import massing_config as mc
from massing_api import MassingError

doc = __revit__.ActiveUIDocument.Document  # noqa: F821

client = mc.get_client()
if not client:
    script.exit()

cfg = mc.read()
project_name = cfg["project_name"] or (os.path.splitext(os.path.basename(doc.PathName))[0] if doc.PathName else "")
if not project_name:
    forms.alert("Save the Revit model first (or set a default project name in Settings).",
                title="Massing", warn_icon=True)
    script.exit()

direction = forms.CommandSwitchWindow.show(
    ["Download issues from Massing (.bcfzip)", "Upload a .bcfzip to Massing"],
    message="Massing — sync issues (BCF):")
if not direction:
    script.exit()

try:
    pid = client.find_or_create_project(project_name)
    if direction.startswith("Download"):
        data = client.bcf_export(pid)
        dest = forms.save_file(file_ext="bcfzip", default_name=project_name + "_issues")
        if not dest:
            script.exit()
        with open(dest, "wb") as fh:
            fh.write(data)
        forms.alert("Saved {0:,} bytes.\n{1}".format(len(data), dest), title="Massing", warn_icon=False)
    else:
        src = forms.pick_file(file_ext="bcfzip")
        if not src:
            script.exit()
        with open(src, "rb") as fh:
            res = client.bcf_import(pid, fh.read(), filename=os.path.basename(src))
        forms.alert("Imported into Massing: {0}".format(res or "ok"), title="Massing", warn_icon=False)
except MassingError as e:
    forms.alert("BCF sync failed:\n{0}".format(e), title="Massing", warn_icon=True)
    script.exit()
