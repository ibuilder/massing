"""R26-INSPECTOR — the six lifecycle facts, gathered from where they already live.

`lifecycle_strip` decides how the six states read; `element_facts` answers what they *are*. Its whole
job is keeping three answers apart — the platform looked and it is yes, it looked and it is no, and
it could not look — and each of the three lookups has a specific way of getting that wrong:

* the integrity lenses cap their offender lists at 20, so a sampled answer reports "clean" for the
  21st duplicate — a check that examined a *different* element, answering about this one;
* an element no activity claims looks unscheduled, but if nothing in the project binds tasks to
  elements at all, that is a missing capability dressed up as a finding about the building;
* the IFC stamp and a field record can both assert verification, and they are not the same evidence.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_element_facts.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_element_facts.db"
os.environ["STORAGE_DIR"] = "./test_storage_element_facts"
for f in ("./test_element_facts.db",):
    if os.path.exists(f):
        os.remove(f)

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import ifcopenshell  # noqa: E402

from aec_api import element_facts as ef  # noqa: E402
from aec_api import lifecycle_strip, model_qa, modules, modules_registry  # noqa: E402
from aec_api.db import Base, SessionLocal, engine  # noqa: E402
from aec_api.models import Project  # noqa: E402

modules_registry.load_registry()          # module tables are created by the registry, not the models
Base.metadata.create_all(engine)
db = SessionLocal()
PID = "p-elemfacts"
db.add(Project(id=PID, name="Element facts"))
db.commit()


# ---- a small model with a deliberate defect in each lens ------------------------------------------
def _model():
    m = ifcopenshell.file(schema="IFC4")
    ctx = m.create_entity("IfcProject", GlobalId=ifcopenshell.guid.new(), Name="P")
    b = m.create_entity("IfcBuilding", GlobalId=ifcopenshell.guid.new(), Name="B")
    s1 = m.create_entity("IfcBuildingStorey", GlobalId=ifcopenshell.guid.new(), Name="L1", Elevation=0.0)
    s2 = m.create_entity("IfcBuildingStorey", GlobalId=ifcopenshell.guid.new(), Name="L2", Elevation=10.0)
    m.create_entity("IfcRelAggregates", GlobalId=ifcopenshell.guid.new(), RelatingObject=ctx,
                    RelatedObjects=[b])
    m.create_entity("IfcRelAggregates", GlobalId=ifcopenshell.guid.new(), RelatingObject=b,
                    RelatedObjects=[s1, s2])
    return m, s1, s2


def _wall(m, name, guid=None):
    return m.create_entity("IfcWall", GlobalId=guid or ifcopenshell.guid.new(), Name=name)


mdl, L1, _L2 = _model()
GOOD = _wall(mdl, "Good wall")
ORPHAN = _wall(mdl, "Orphan wall")
BLANK = _wall(mdl, None)
mdl.create_entity("IfcRelContainedInSpatialStructure", GlobalId=ifcopenshell.guid.new(),
                  RelatingStructure=L1, RelatedElements=[GOOD, BLANK])

# ---- element_findings is EXACT, where model_qa is sampled ------------------------------------------
r = model_qa.element_findings(mdl, GOOD.GlobalId)
assert r["found"] and r["checked"] and r["clean"], r
assert r["ifc_class"] == "IfcWall"

r = model_qa.element_findings(mdl, ORPHAN.GlobalId)
assert not r["clean"] and [f["check"] for f in r["findings"]] == ["orphaned_elements"], r

r = model_qa.element_findings(mdl, BLANK.GlobalId)
assert [f["check"] for f in r["findings"]] == ["blank_names"], r

# a GUID that is not in the model was not examined — that is unknown, NOT clean
missing = model_qa.element_findings(mdl, "0000000000000000000000")
assert missing["found"] is False and missing["checked"] is False, missing
assert "clean" not in missing, "an unexamined element must not carry a verdict"

# ---- and the exactness is the point: the 21st offender is still reported --------------------------
# model_qa's sample stops at 20. If `checked` were read from that sample, offender #21 would come
# back clean — a check that examined a different element answering about this one.
many, ML1, _ = _model()
crowd = [_wall(many, f"Orphan {i}") for i in range(25)]
qa = model_qa.model_qa(many)
assert qa["checks"]["orphaned_elements"]["count"] == 25
assert len(qa["checks"]["orphaned_elements"]["sample"]) == 20, "the sample IS capped — that is why"
sampled = {s["guid"] for s in qa["checks"]["orphaned_elements"]["sample"]}
beyond = [w for w in crowd if w.GlobalId not in sampled]
assert beyond, "expected offenders past the sample cap"
for w in beyond:
    assert not model_qa.element_findings(many, w.GlobalId)["clean"], w.Name
    assert ef.checked(many, w.GlobalId) is False, "an offender past the cap must not read as checked-clean"

# ---- checked: unknown when the model cannot be read -----------------------------------------------
assert ef.checked(None, GOOD.GlobalId) is None, "no model = unknown, not clean"
assert ef.checked(mdl, GOOD.GlobalId) is True
assert ef.checked(mdl, "not-in-model") is None, "not in the model = unexamined"

# ---- scheduled: no binding ANYWHERE is unknown; binding-in-use-but-not-here is none ---------------
assert ef.scheduled(db, PID, GOOD.GlobalId) is None, "no activities at all = nothing was asked"

modules.create_record(db, "schedule_activity", PID,
                      {"data": {"name": "Frame L1"}}, "tester", "GC")
assert ef.scheduled(db, PID, GOOD.GlobalId) is None, \
    "activities exist but none binds an element — still nothing was asked"

bound = modules.create_record(db, "schedule_activity", PID,
                              {"data": {"name": "Erect wall"}, "element_guids": [GOOD.GlobalId]},
                              "tester", "GC")
got = ef.scheduled(db, PID, GOOD.GlobalId)
assert got and got["record_id"] == bound["id"], got
# now that binding IS in use on this project, an unclaimed element is a real "no"
assert ef.scheduled(db, PID, ORPHAN.GlobalId) == {}, ef.scheduled(db, PID, ORPHAN.GlobalId)

# ---- installed: the register's silence is a "no"; an absent register is unknown -------------------
assert ef.installed(db, PID, GOOD.GlobalId) == {"installed": False}
fv = modules.create_record(db, "field_verification", PID,
                           {"data": {"guid": GOOD.GlobalId, "element": "Good wall",
                                     "observed_date": "2026-06-11", "deviation_mm": 8}},
                           "tester", "GC")
inst = ef.installed(db, PID, GOOD.GlobalId)
assert inst["installed"] is True and inst["date"] == "2026-06-11" and inst["source"] == "field", inst

# ---- verified: captured is NOT verified; a verified record carries its accuracy -------------------
v = ef.verified(db, PID, GOOD.GlobalId)
assert v == {"verified": False}, v          # the record exists but is still `captured`
modules.transition(db, "field_verification", PID, fv["id"], "verify", "tester", "GC")
v = ef.verified(db, PID, GOOD.GlobalId)
assert v["verified"] is True and v["source"] == "field", v
assert v["deviation_m"] == 0.008, "mm converts to m — a verification states its ACCURACY"

# an element with no field record at all, and no model element to stamp: unknown
assert ef.verified(db, PID, "nobody-touched-this") is None

# ---- gather feeds the strip directly, and the strip's rules still hold ----------------------------
facts = ef.gather(db, PID, GOOD.GlobalId, model=mdl,
                  element={"guid": GOOD.GlobalId, "ifc_class": "IfcWall", "name": "Good wall"},
                  priced={"code": "03 30 00", "amount": 1200.0})
strip = lifecycle_strip.strip({"guid": GOOD.GlobalId, "ifc_class": "IfcWall"}, **facts)
assert strip["reached"] == "verified" and strip["done_count"] == 6, strip
assert not strip["inconsistencies"], strip["inconsistencies"]

# and with the model withheld, `checked` goes UNKNOWN — which stops `reached` at designed without
# claiming the later states are false
facts2 = ef.gather(db, PID, GOOD.GlobalId, model=None,
                   element={"guid": GOOD.GlobalId, "ifc_class": "IfcWall"},
                   priced={"code": "03 30 00", "amount": 1200.0})
s2 = lifecycle_strip.strip({"guid": GOOD.GlobalId, "ifc_class": "IfcWall"}, **facts2)
assert s2["states"][1]["status"] == "unknown", s2["states"][1]
assert s2["reached"] == "designed" and s2["done_count"] == 5, s2
assert not s2["inconsistencies"], "unknown is not a contradiction"

db.close()
print("R26-INSPECTOR FACTS OK - the six lifecycle states are now gathered from where they already "
      "live, and the work was in keeping three answers apart: the platform looked and it is yes, it "
      "looked and it is no, and it COULD NOT LOOK. Each lookup had its own way of confusing them. "
      "The integrity lenses cap every offender list at 20 for payload size, so reading this element's "
      "verdict out of that sample would report CLEAN for the 21st duplicate - a check that examined a "
      "different element answering about this one - which is why the rules are re-evaluated exactly "
      "for the GUID and an element absent from the model reads unknown rather than clean. An element "
      "no activity claims looks unscheduled, but where NOTHING in the project binds tasks to elements "
      "that is a missing capability dressed up as a finding about the building, so the project-wide "
      "binding is checked first and only a project that actually uses it can return a real 'no'. And "
      "the IFC LOD-500 stamp and a field record can both assert verification: the stamp wins because "
      "IFC is the source of truth, the record is the fallback, and `source` says which - because they "
      "are not the same evidence even when they agree.")
