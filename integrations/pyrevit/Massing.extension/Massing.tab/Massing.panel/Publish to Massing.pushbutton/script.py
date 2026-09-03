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

import massing_config as mc
import massing_export as mx
from Autodesk.Revit.DB import (
    FamilyInstance,
    FilteredElementCollector,
    IFCExportOptions,
    IFCVersion,
    ImportInstance,
    SpatialElement,
)
from massing_api import MassingError
from pyrevit import forms, script

doc = __revit__.ActiveUIDocument.Document  # noqa: F821  (pyRevit-injected)
output = script.get_output()


def _count(fn):
    """Run one audit probe; a probe that fails must never block a publish."""
    try:
        return int(fn())
    except Exception:                       # noqa: BLE001 — Revit API surface varies by version
        return 0


def _audit_counts():
    """Count the conditions that reliably produce IFC nobody can coordinate against."""
    def unplaced_rooms():
        n = 0
        for r in FilteredElementCollector(doc).OfClass(SpatialElement):
            # a room with no area is unplaced or unbounded; it exports as a zero-area space
            if getattr(r, "Area", 0) == 0:
                n += 1
        return n

    def in_place():
        n = 0
        for f in FilteredElementCollector(doc).OfClass(FamilyInstance):
            sym = getattr(f, "Symbol", None)
            fam = getattr(sym, "Family", None) if sym else None
            if fam is not None and getattr(fam, "IsInPlace", False):
                n += 1
        return n

    return {
        "unplaced_rooms": _count(unplaced_rooms),
        "in_place_families": _count(in_place),
        "imported_cad": _count(lambda: len(list(
            FilteredElementCollector(doc).OfClass(ImportInstance)))),
        "revit_warnings": _count(lambda: len(list(doc.GetWarnings()))),
    }


def _export_options():
    """A CONFIGURED IFCExportOptions — never the bare default.

    The bare default was the previous behaviour and it left GlobalId stability to whatever the
    exporter happened to do, which breaks our first non-negotiable. See massing_export for why each
    option is set.
    """
    opts = IFCExportOptions()
    try:
        opts.FileVersion = IFCVersion.IFC4
    except Exception:                       # noqa: BLE001 — older Revit without IFC4 keeps its default
        pass
    named = mx.export_options()
    if not mx.guid_stability_ok(named):
        # refuse rather than publish a model that will silently re-key on the next export
        forms.alert("Export configuration would not preserve IFC GlobalIds. Publish cancelled.",
                    title="Massing", warn_icon=True)
        script.exit()
    for key, value in sorted(named.items()):
        try:
            opts.AddOption(key, value)
        except Exception:                   # noqa: BLE001 — unknown option on an older exporter
            pass
    return opts

client = mc.get_client()
if not client:
    script.exit()

cfg = mc.read()
project_name = cfg["project_name"] or (os.path.splitext(os.path.basename(doc.PathName))[0] if doc.PathName else "Revit model")

# Pre-publish audit. These conditions produce IFC nobody can coordinate against, and they are far
# cheaper to fix here than to discover in a clash meeting three weeks later. Reported, never enforced:
# a partial model is often exactly what someone means to publish.
findings = mx.audit_summary(_audit_counts())
if findings:
    lines = "\n".join("  - {0}: {1}\n      {2}".format(f["label"], f["count"], f["why"])
                      for f in findings)
    if not forms.alert("Model audit found conditions that degrade the exported IFC:\n\n{0}\n\n"
                       "Publish anyway?".format(lines),
                       title="Massing — pre-publish audit", ok=False, yes=True, no=True):
        script.exit()

with forms.ProgressBar(title="Publishing to Massing…", cancellable=False) as pb:
    try:
        # 1) export the active document to IFC (built-in Revit IFC exporter — free, no APS bridge)
        pb.update_progress(1, 5)
        out_dir = tempfile.mkdtemp(prefix="massing_ifc_")
        doc.Export(out_dir, project_name, _export_options())
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
