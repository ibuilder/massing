"""DISC-SSOT: sheet-series is a derived view of the canonical discipline map (classification), not a
parallel table. sheetgen + the drawing-set cover both derive from classification.series_of_ifc_class /
sheet_series, so discipline ↔ sheet-series can never drift. (Takt trade stays a separate build axis.)
Run: PYTHONPATH=src;../data/src ./.venv/Scripts/python.exe test_disc_ssot.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_api import classification as C  # noqa: E402
from aec_api import drawingset, sheetgen  # noqa: E402

# --- series_of_ifc_class reproduces the former hand-kept sheetgen._CLASS_SERIES exactly ---------------
# (this is the map that used to live in two places; the values below are the ground truth it must match)
_LEGACY_CLASS_SERIES = {
    "IfcDuctSegment": "M", "IfcDuctFitting": "M", "IfcAirTerminal": "M", "IfcUnitaryEquipment": "M",
    "IfcPipeSegment": "P", "IfcPipeFitting": "P", "IfcSanitaryTerminal": "P",
    "IfcCableSegment": "E", "IfcCableCarrierSegment": "E", "IfcElectricAppliance": "E",
    "IfcOutlet": "E", "IfcLightFixture": "E", "IfcElectricDistributionBoard": "E",
    "IfcFireSuppressionTerminal": "FP", "IfcAlarm": "FA", "IfcSensor": "FA",
    "IfcCommunicationsAppliance": "T",
}
for cls, want in _LEGACY_CLASS_SERIES.items():
    got = C.series_of_ifc_class(cls)
    assert got == want, f"{cls}: derived series {got!r} != legacy {want!r}"

# the FA/FP refinement: fire-suppression (discipline F) → FP series; fire-alarm classes → FA series even
# though their *discipline* folds to Electrical
assert C.discipline_of_ifc_class("IfcSprinkler") == "F" and C.series_of_ifc_class("IfcSprinkler") == "FP"
assert C.discipline_of_ifc_class("IfcAlarm") == "E" and C.series_of_ifc_class("IfcAlarm") == "FA"
# for any non-FA/FP class the series is exactly its discipline code (the derived-view invariant)
for cls in ("IfcColumn", "IfcWall", "IfcDoor", "IfcSlab", "IfcRoof", "IfcPump", "IfcTransformer"):
    d = C.discipline_of_ifc_class(cls)
    s = C.series_of_ifc_class(cls)
    assert s == ("FP" if d == "F" else d), f"{cls}: series {s!r} must follow discipline {d!r}"
# curtain-wall host context flows through (a mullion under a curtain wall is Architectural, series A)
assert C.series_of_ifc_class("IfcMember", host_class="IfcCurtainWall") == "A"

# --- sheetgen.detect_series now derives from the SSOT, unchanged behaviour --------------------------
assert not hasattr(sheetgen, "_CLASS_SERIES"), "the duplicate class→series table must be gone"
base = sheetgen.detect_series(set())
assert base == [s for s in ("G", "C", "L", "S", "A", "FP", "FA", "P", "M", "E", "T") if s in ("G", "S", "A")]
# an MEP + fire model surfaces exactly its series (in NCS binding order), always incl. G/S/A
mep = sheetgen.detect_series({"IfcWall", "IfcDuctSegment", "IfcPipeSegment", "IfcCableSegment",
                              "IfcFireSuppressionTerminal", "IfcAlarm", "IfcCommunicationsAppliance"})
assert mep == ["G", "S", "A", "FP", "FA", "P", "M", "E", "T"], mep

# --- the drawing-set cover derives series names from the SSOT (no private table) ---------------------
assert not hasattr(drawingset, "_DISCIPLINE_SERIES"), "cover must not keep its own series→name table"
assert drawingset._series_of("A-101") == "A" and drawingset._series_of("FP-201") == "FP"
assert drawingset._series_of("AD-101") == "A", "a non-distinct 2-letter designator folds to its discipline"
assert drawingset._series_name("FA") == "Fire Alarm" and drawingset._series_name("M") == "Mechanical"

# --- trade stays a SEPARATE axis (not folded into discipline/series) --------------------------------
from aec_api import fourd  # noqa: E402

assert fourd.TRADE_FOR_CLASS["IfcWall"] == "Envelope", "a wall's trade is Envelope (not its A discipline)"
assert fourd.TRADE_FOR_CLASS["IfcColumn"] == "Structure"

print("DISC-SSOT OK - sheet-series is now a derived view of the canonical discipline map: "
      "classification.series_of_ifc_class reproduces the former sheetgen._CLASS_SERIES exactly (incl. the "
      "FP/FA refinement + curtain-wall host context), sheetgen.detect_series and the drawing-set cover both "
      "derive from it (their private tables removed), so discipline↔sheet-series can never drift; takt trade "
      "(fourd.TRADE_FOR_CLASS) stays a deliberately separate build-sequence axis.")
