"""R23-REVIT-EXPORT-CFG — the bridge exported IFC with a bare `IFCExportOptions()`.

One consequence outranks all the others. **GlobalId stability is our first non-negotiable**: pins,
RFIs, clash results, cost lines and the as-built verification stamp all key off IFC GlobalId. Revit
only guarantees stable GlobalIds across re-export when `StoreIFCGUID` is on — it writes the GUID back
onto the element as the `IfcGUID` shared parameter so the next export re-uses it. With the bare
default, a republish could silently re-key the model and detach every one of those links from the
geometry it described. Nothing errors; the data just stops meaning anything.

The Revit API surface cannot run here, so the option map and the audit are pure functions in
`massing_export.py` and the button script only applies them. That puts the part most likely to be
wrong — which options, spelled how — under test.

Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_revit_export_cfg.py
"""
import os
import sys

_LIB = os.path.join(os.path.dirname(__file__), "..", "..", "integrations", "pyrevit",
                    "Massing.extension", "lib")
sys.path.insert(0, os.path.abspath(_LIB))

import massing_export as mx  # noqa: E402

# ---- the GUID option is the point of the whole change ------------------------------------------
opts = mx.export_options()
assert opts[mx.GUID_OPTION] == "true", opts
assert mx.guid_stability_ok(opts) is True

# and the guard actually refuses the unsafe cases, rather than only passing the happy one
assert mx.guid_stability_ok({}) is False, "a missing StoreIFCGUID must NOT read as safe"
assert mx.guid_stability_ok({mx.GUID_OPTION: "false"}) is False
assert mx.guid_stability_ok(None) is False
assert mx.guid_stability_ok({mx.GUID_OPTION: "TRUE"}) is True   # case is not the caller's problem
# A Python bool reads as safe, deliberately. The check exists to stop a publish that would re-key the
# model, and `True` stringifies to "True", which the exporter accepts — so refusing it would block a
# publish that was in fact correct. The failure this guards against is a MISSING or false option, not
# an unconventionally-typed true one; the strings-only rule is asserted separately below, where it
# belongs, against the shipped map.
assert mx.guid_stability_ok({mx.GUID_OPTION: True}) is True

# ---- values are exporter-parseable strings, never Python bools ---------------------------------
for k, v in opts.items():
    assert isinstance(v, str), (k, type(v))
    assert v in ("true", "false"), (k, v)

# ---- the whole-model rule: defaulting to the active view ships a partial building ---------------
assert opts["VisibleElementsOfCurrentView"] == "false", opts
assert opts["ExportRoomsInView"] == "false", opts

# ---- data the downstream engines actually read --------------------------------------------------
assert opts["ExportBaseQuantities"] == "true"      # 5D/takeoff reads IfcElementQuantity
assert opts["ExportSchedulesAsPsets"] == "true"
assert opts["IncludeSiteElevation"] == "true"      # georeferencing is a stated non-negotiable

# every option carries a stated reason — this is a curated set, not a pile of everything available
assert set(mx.RATIONALE) == set(opts), set(mx.RATIONALE) ^ set(opts)
for k, why in mx.RATIONALE.items():
    assert len(why) > 30, (k, why)

# a returned copy must not let a caller mutate the module constant for everyone else
opts["StoreIFCGUID"] = "false"
assert mx.export_options()[mx.GUID_OPTION] == "true", "export_options() must return a fresh copy"

# ---- the pre-publish audit reports only what it found -------------------------------------------
assert mx.audit_summary({}) == []
assert mx.audit_is_clean({"unplaced_rooms": 0, "imported_cad": 0}) is True
# an audit that lists everything it checked and found nothing trains people to skip reading it
assert mx.audit_summary({"unplaced_rooms": 0, "in_place_families": 3})[0]["key"] == "in_place_families"

found = mx.audit_summary({"unplaced_rooms": 2, "imported_cad": 1, "revit_warnings": 40})
assert [f["key"] for f in found] == ["unplaced_rooms", "imported_cad", "revit_warnings"], found
assert [f["count"] for f in found] == [2, 1, 40]
assert all(f["label"] and f["why"] for f in found), found
assert mx.audit_is_clean({"unplaced_rooms": 1}) is False

# junk counts must not crash the publish button or invent findings
assert mx.audit_summary(None) == []
assert mx.audit_summary({"unplaced_rooms": None, "imported_cad": 0}) == []
assert mx.audit_summary({"not_a_check": 99}) == []

print("R23-REVIT-EXPORT-CFG OK - the Revit bridge no longer exports with a bare IFCExportOptions(). "
      "The option that matters is StoreIFCGUID: Revit only guarantees stable GlobalIds across a "
      "re-export when it writes the GUID back onto the element as the IfcGUID shared parameter, and "
      "GlobalId is what every pin, RFI, clash result, cost line and as-built verification stamp in "
      "the platform keys off - so a republish under the old default could silently re-key the model "
      "and detach all of it from the geometry it described, with nothing raising an error. The "
      "button now REFUSES to publish if the configuration it is about to apply would not preserve "
      "GlobalIds, rather than trusting the constant - while still reading a Python bool as safe, "
      "because that check exists to stop a re-keying publish and refusing a correct one would block "
      "real work. Every shipped value is the exporter's own string. Whole-model export is forced "
      "because defaulting to the active view is how a coordination model ships with most of the "
      "building missing. And a pre-publish audit names the conditions that reliably produce "
      "uncoordinatable IFC - unplaced rooms, in-place families, imported CAD, unresolved warnings - "
      "reporting only what it actually found, since an audit that lists its clean checks too is an "
      "audit people learn to skip.")
