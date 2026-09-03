# -*- coding: utf-8 -*-
"""IFC export configuration for the Revit bridge — kept OUT of the button script so it can be tested
without Revit.

The bridge used to call ``doc.Export(dir, name, IFCExportOptions())`` — a bare default. That is a
problem for one specific reason that outranks the rest:

**GlobalId stability is our first non-negotiable.** Everything in the platform keys off IFC GlobalId —
pins, RFIs, clash results, cost lines, the as-built verification stamp. If a re-export mints new
GlobalIds, every one of those links silently detaches from the geometry it described. Nothing errors;
the data just quietly stops meaning anything.

Revit's exporter only guarantees stable GlobalIds when ``StoreIFCGUID`` is on: it writes the generated
GUID back onto the element as the ``IfcGUID`` shared parameter, so the next export re-uses it instead
of deriving a fresh one. Leaving that to a checkbox in a dialog someone else ticks is not a guarantee.
"""

# Revit's exporter takes named string options via IFCExportOptions.AddOption(name, value).
# Values are the strings the exporter parses ("true"/"false"), NOT Python bools.
#
# Every entry below is here for a stated reason; this is not a pile of everything available.
_OPTIONS = [
    # ── the one that matters ────────────────────────────────────────────────────────────────────
    ("StoreIFCGUID", "true",
     "Writes the IfcGUID back onto each Revit element, so a re-export re-uses the SAME GlobalId. "
     "Without it every republish can re-key the model and silently detach every pin, RFI, clash "
     "and cost line from its geometry."),

    # ── data we actually consume downstream ─────────────────────────────────────────────────────
    ("ExportBaseQuantities", "true",
     "Emits IfcElementQuantity — the takeoff and 5D cost path reads these rather than re-deriving "
     "areas and volumes from geometry."),
    ("ExportSchedulesAsPsets", "true",
     "Revit schedules become property sets, which is how project-specific data reaches IFC at all."),
    ("ExportUserDefinedPsets", "true",
     "Honours a user's pset mapping file when one is configured."),
    ("ExportInternalRevitPropertySets", "true",
     "Keeps the Revit-native parameters; norm-validation and property mapping both read them."),

    # ── correctness of what gets exported ───────────────────────────────────────────────────────
    ("VisibleElementsOfCurrentView", "false",
     "Export the WHOLE model. Defaulting to the active view is how a coordination model quietly "
     "ships with three-quarters of the building missing."),
    ("ExportRoomsInView", "false",
     "Same reason, for rooms specifically."),
    ("ExportPartsAsBuildingElements", "true",
     "Parts export as real elements rather than being dropped."),
    ("ExportAnnotations", "false",
     "2D annotation is sheet content; it does not belong in the coordination model."),
    ("IncludeSiteElevation", "true",
     "Preserves real-world elevation — georeferencing is a stated non-negotiable."),
]

#: Named options applied to every export, as ``{name: value}``.
OPTIONS = {name: value for name, value, _why in _OPTIONS}

#: Why each option is set, keyed the same way — surfaced in the UI so the choice is auditable.
RATIONALE = {name: why for name, _value, why in _OPTIONS}

#: The single option whose absence breaks the GUID non-negotiable.
GUID_OPTION = "StoreIFCGUID"


def export_options():
    """The named options for a Massing publish, as ``{name: "true"|"false"}``."""
    return dict(OPTIONS)


def guid_stability_ok(options):
    """True when the given option map preserves GlobalIds across re-export.

    Separated from :func:`export_options` so the button can assert it against whatever it is *about
    to* apply, rather than trusting that the constant above was not edited into something unsafe.
    """
    return str((options or {}).get(GUID_OPTION, "")).lower() == "true"


# ── pre-publish model audit ─────────────────────────────────────────────────────────────────────
# These are the conditions that reliably produce IFC nobody can coordinate against. Reporting them
# BEFORE the upload is the difference between a modeller fixing one room and a project team
# discovering the gap three weeks later in a clash meeting.
AUDIT_CHECKS = [
    ("unplaced_rooms", "Unplaced or unbounded rooms",
     "Export as zero-area spaces, so area takeoff and space-based checks silently under-count."),
    ("in_place_families", "In-place families",
     "Export as undifferentiated generic solids — no type, no schedulable identity."),
    ("imported_cad", "Imported CAD (DWG/DXF) instances",
     "Arrive as loose triangle soup with no IFC class, and inflate both file size and clash noise."),
    ("revit_warnings", "Unresolved Revit warnings",
     "Duplicate/overlapping elements are the usual cause of phantom clashes downstream."),
]


def audit_summary(counts):
    """Turn raw counts into an ordered, human-readable finding list.

    Only non-zero findings are returned — an audit that lists everything it checked and found nothing
    trains people to skip reading it.
    """
    out = []
    for key, label, why in AUDIT_CHECKS:
        n = int((counts or {}).get(key) or 0)
        if n > 0:
            out.append({"key": key, "label": label, "count": n, "why": why})
    return out


def audit_is_clean(counts):
    return not audit_summary(counts)
