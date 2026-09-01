"""R21-SOFT-CLASH — clearance rules, and the matrix that constrains what a report may claim.

Hard clash asks whether two solids overlap. Soft clash asks the question that actually stops work:
can a person reach this, service it, pull it out? A pump clearing every duct by 5 mm passes hard
clash and cannot be maintained.

The half that matters most is the matrix. A coordination report saying "clash-free" without saying
which discipline pairs were tested is overstating what it knows — structural-vs-plumbing being clean
means nothing if that pair was never run. So an untested pair is reported as UNTESTED and never
folded into the clean count, the same rule the scan verification follows: absence of evidence is not
evidence of absence.

Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_soft_clash.py
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_soft_clash.db"
os.environ["STORAGE_DIR"] = "./test_storage_soft_clash"
if os.path.exists("./test_soft_clash.db"):
    os.remove("./test_soft_clash.db")

from aec_api import soft_clash as sc  # noqa: E402

# ---- rules: every number is traceable, and an unknown class gets NO rule ------------------------
panel = sc.rule_for("IfcElectricDistributionBoard")
assert panel["distance_m"] == 0.9 and "110.26" in panel["basis"], panel

# a class we have no stated rule for returns None rather than a default distance — a made-up
# clearance produces confident findings nobody can defend
assert sc.rule_for("IfcWall") is None
assert sc.rule_for("IfcSomethingNew") is None
assert sc.rule_for("") is None
assert sc.rule_for(None) is None
assert sc.rule_for("ifcvalve") is not None, "class lookup is case-insensitive"

# every rule states a distance, a source to argue with, the IFC token, and why it exists
for cls, r in sc.CLEARANCE_RULES.items():
    assert cls == cls.lower(), cls
    assert 0.1 <= r["distance_m"] <= 3.0, (cls, r["distance_m"])
    assert len(r["basis"]) > 20 and len(r["why"]) > 20, cls
    assert r["label"], cls
    assert r["ifc_class"].startswith("Ifc") and r["ifc_class"].lower() == cls, (cls, r["ifc_class"])
assert sc.scoped_classes() == sorted(sc.CLEARANCE_RULES)

# starter geometry checks: all seven classes, doors high, the other six medium
geo = sc.geometry_clearance_checks()
assert len(geo) == 7, geo
assert {c["scope"] for c in geo} == {r["ifc_class"] for r in sc.CLEARANCE_RULES.values()}
door = next(c for c in geo if c["scope"] == "IfcDoor")
assert door["severity"] == "high" and door["distance_m"] == 0.9, door
others = [c for c in geo if c["scope"] != "IfcDoor"]
assert others and all(c["severity"] == "medium" for c in others), others
assert all(c["kind"] == "clearance" and c["basis"] for c in geo)

# fill_clearance_check consults the table; an unknown class with no distance is refused
filled = sc.fill_clearance_check({"kind": "clearance", "scope": "IfcDoor"})
assert filled["distance_m"] == 0.9 and filled["name"] == door["name"] and filled["basis"] == door["basis"]
try:
    sc.fill_clearance_check({"kind": "clearance", "scope": "IfcWall"})
    raise AssertionError("IfcWall has no stated clearance and must not invent one")
except ValueError as e:
    assert "stated rule" in str(e)
# an explicit distance on an unknown class is allowed (caller owns the number)
own = sc.fill_clearance_check({"kind": "clearance", "scope": "IfcWall", "distance_m": 1.2})
assert own["distance_m"] == 1.2 and "basis" not in own

# ---- pair keys are order-independent ------------------------------------------------------------
assert sc.pair_key("MEP", "Structural") == sc.pair_key("Structural", "MEP")
assert sc.pair_key("", None) == ("?", "?")

# ---- THE MATRIX: untested is its own state, and it is not clean ---------------------------------
DISCS = ["Architectural", "Structural", "MEP"]
# 3 disciplines → 6 unordered pairs including self-pairs (A×A, A×S, A×M, S×S, S×M, M×M)
m = sc.matrix(DISCS, tested_pairs=[], findings=[])
assert m["pair_count"] == 6, m["pair_count"]
assert m["counts"]["untested"] == 6, m["counts"]
assert m["counts"]["clean"] == 0, "nothing was tested, so NOTHING may be reported clean"
assert m["coordinated"] is False, "an entirely untested matrix must never read as coordinated"
assert m["coverage_pct"] == 0.0

# test one pair, find nothing → that pair is clean; the rest stay untested
m = sc.matrix(DISCS, tested_pairs=[("Structural", "MEP")], findings=[])
cell = next(c for c in m["cells"] if {c["a"], c["b"]} == {"Structural", "MEP"})
assert cell["state"] == "clean" and cell["count"] == 0, cell
assert m["counts"]["clean"] == 1 and m["counts"]["untested"] == 5, m["counts"]
assert m["coordinated"] is False, "5 untested pairs is not coordinated, however clean the 6th is"

# a finding puts the pair in `clashes`
m = sc.matrix(DISCS, tested_pairs=[("Structural", "MEP")],
              findings=[{"discipline_a": "MEP", "discipline_b": "Structural"},
                        {"discipline_a": "Structural", "discipline_b": "MEP"}])
cell = next(c for c in m["cells"] if {c["a"], c["b"]} == {"Structural", "MEP"})
assert cell["state"] == "clashes" and cell["count"] == 2, cell
assert m["counts"]["clashes"] == 1

# evidence outranks the declaration: a finding on an UNDECLARED pair still means it was tested —
# but never the reverse, since a declaration with no findings cannot manufacture coverage
m = sc.matrix(DISCS, tested_pairs=[], findings=[{"discipline_a": "Architectural",
                                                 "discipline_b": "MEP"}])
cell = next(c for c in m["cells"] if {c["a"], c["b"]} == {"Architectural", "MEP"})
assert cell["state"] == "clashes", cell
assert m["counts"]["untested"] == 5

# fully tested and fully clean is the ONLY state that may claim coordination
all_pairs = [(a, b) for i, a in enumerate(sorted(DISCS)) for b in sorted(DISCS)[i:]]
m = sc.matrix(DISCS, tested_pairs=all_pairs, findings=[])
assert m["counts"] == {"clashes": 0, "clean": 6, "untested": 0}, m["counts"]
assert m["coverage_pct"] == 100.0
assert m["coordinated"] is True

# ...and one clash removes that claim even at full coverage
m = sc.matrix(DISCS, tested_pairs=all_pairs, findings=[{"discipline_a": "MEP",
                                                        "discipline_b": "MEP"}])
assert m["coordinated"] is False, m["counts"]

# ---- degenerate inputs must not fabricate a clean bill ------------------------------------------
empty = sc.matrix([], [], [])
assert empty["pair_count"] == 0 and empty["coordinated"] is False, \
    "an empty matrix has tested nothing and must not read as coordinated"
assert empty["coverage_pct"] == 0.0
one = sc.matrix(["MEP"], [("MEP", "MEP")], [])
assert one["pair_count"] == 1 and one["coordinated"] is True
# duplicate / unsorted / blank discipline names collapse rather than inflating the matrix
dup = sc.matrix(["MEP", "MEP", " MEP ", ""], [], [])
assert dup["disciplines"] == ["?", "MEP"], dup["disciplines"]

print("R21-SOFT-CLASH OK - hard clash asks whether two solids overlap; soft clash asks the question "
      "that actually stops work, which is whether a person can reach, service or withdraw the thing "
      "- a pump clearing every duct by 5mm passes hard clash and cannot be maintained. Clearance is "
      "a RULES problem, not a geometry one: every distance here carries the code or manufacturer "
      "basis it came from, so a finding can be argued with, and a class we have no stated rule for "
      "returns NO rule rather than a default distance, because a made-up clearance produces "
      "confident findings nobody can defend. The half that constrains what a report may claim is the "
      "discipline-pair matrix: an untested pair is reported as UNTESTED and never folded into the "
      "clean count, so 'clash-free' over a partial matrix cannot be stated - structural-vs-plumbing "
      "being clean means nothing if that pair never ran. Evidence outranks the declaration (a "
      "finding proves a pair was tested) but never the reverse (a declaration with no findings "
      "cannot manufacture coverage), and an empty matrix has tested nothing so it reads as "
      "uncoordinated rather than vacuously perfect.")
