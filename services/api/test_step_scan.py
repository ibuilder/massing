"""Fast STEP metadata scanner (G3): header + entity-type histogram without ifcopenshell.
Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_step_scan.py"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "data", "src"))

from aec_data import step_scan  # noqa: E402

SPF = """ISO-10303-21;
HEADER;
FILE_DESCRIPTION(('ViewDefinition [CoordinationView]'),'2;1');
FILE_NAME('sample.ifc','2026-07-08T00:00:00',(''),(''),'','','');
FILE_SCHEMA(('IFC4'));
ENDSEC;
DATA;
#1=IFCPROJECT('guid',$,$);
#2=IFCWALL('w1',$,$);
#3=IFCWALL('w2',$,$);
#4=IFCWALLSTANDARDCASE('w3',$,$);
#5=IFCDOOR('d1',$,$);
#6=IFCDOOR('d2',$,$);
#7=IFCDOOR('d3',$,$);
ENDSEC;
END-ISO-10303-21;
"""

with tempfile.TemporaryDirectory() as d:
    p = os.path.join(d, "sample.ifc")
    with open(p, "w", encoding="utf-8") as f:
        f.write(SPF)
    r = step_scan.scan_file(p)
    assert r["ok"] and r["schema"] == "IFC4", r
    assert r["total_entities"] == 7 and r["distinct_types"] == 4, r
    hist = {h["ifc_class"]: h["count"] for h in r["histogram"]}
    assert hist["IFCDOOR"] == 3 and hist["IFCWALL"] == 2, hist
    assert r["histogram"][0]["ifc_class"] == "IFCDOOR", "sorted by count desc"
    assert r["file_size_bytes"] > 0, r

# missing file guards cleanly
assert step_scan.scan_file(None)["ok"] is False
assert step_scan.scan_file("/nope/x.ifc")["ok"] is False

print("STEP SCAN OK - streaming scan reads FILE_SCHEMA (IFC4) + entity histogram without a full parse "
      "(7 entities, 4 types, IFCDOOR=3 top, IFCWALL=2); missing-file guarded")
