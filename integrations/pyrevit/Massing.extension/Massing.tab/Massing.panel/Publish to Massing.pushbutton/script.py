# -*- coding: utf-8 -*-
__title__ = "Publish to\nMassing"
__doc__ = """Export the active Revit model to IFC and publish it to Massing in one click — no paid
Autodesk bridge. The model is converted to Fragments server-side; when it's ready you can open it in
the Massing web viewer. Re-publishing the same project updates it.

Configure the connection first via Massing > Settings."""
__author__ = "Massing (massing.build)"

import os
import tempfile
import time

from pyrevit import forms, script

import massing_config as mc
from massing_api import MassingError

from Autodesk.Revit.DB import IFCExportOptions

doc = __revit__.ActiveUIDocument.Document  # noqa: F821  (pyRevit-injected)
output = script.get_output()

client = mc.get_client()
if not client:
    script.exit()

cfg = mc.read()
project_name = cfg["project_name"] or (os.path.splitext(os.path.basename(doc.PathName))[0] if doc.PathName else "Revit model")

with forms.ProgressBar(title="Publishing to Massing…", cancellable=False) as pb:
    try:
        # 1) export the active document to IFC (built-in Revit IFC exporter — free, no APS bridge)
        pb.update_progress(1, 5)
        out_dir = tempfile.mkdtemp(prefix="massing_ifc_")
        doc.Export(out_dir, project_name, IFCExportOptions())
        ifc_path = os.path.join(out_dir, project_name + ".ifc")
        if not os.path.exists(ifc_path):
            forms.alert("Revit did not produce an IFC export.", title="Massing", warn_icon=True)
            script.exit()
        with open(ifc_path, "rb") as fh:
            ifc_bytes = fh.read()

        # 2) find or create the Massing project
        pb.update_progress(2, 5)
        pid = client.find_or_create_project(project_name)

        # 3) upload the IFC (server saves it + kicks the Fragments conversion)
        pb.update_progress(3, 5)
        client.upload_ifc(pid, ifc_bytes, filename=project_name + ".ifc", publish=True)

        # 4) wait for the server-side publish to finish
        pb.update_progress(4, 5)
        client.wait_for_publish(pid, timeout=600, interval=4, sleeper=time.sleep)

        pb.update_progress(5, 5)
    except MassingError as e:
        forms.alert("Publish failed:\n{0}".format(e), title="Massing", warn_icon=True)
        script.exit()

url = client.viewer_url(pid)
output.print_md("# ✅ Published **{0}** to Massing".format(project_name))
output.print_md("{0:,} KB IFC uploaded and converted.".format(len(ifc_bytes) // 1024))
output.print_md("[Open in Massing]({0})".format(url))
if forms.alert("Published to Massing.\nOpen it in the web viewer now?", title="Massing",
               ok=False, yes=True, no=True):
    script.open_url(url)
