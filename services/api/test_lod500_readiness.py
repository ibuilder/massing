"""LOD 500 — the assertion existed and the reader ignored it.

`edit_asbuilt.verify_asbuilt` has stamped `Massing_AsBuilt` onto elements since the G1 work, and
`asbuilt_summary` counted them. But `lod.achieved_lod` read only LOIN facets, so a model with every
element field-verified still reported "LOD 400, capped". The evidence was in the IFC and the LOD
assessment could not see it.

Two things from the BIMForum specification are encoded here, both easy to get wrong:
  * LOD 500 is not "more detail than LOD 400" — it is a *field-verified as-built* condition. No
    amount of geometry earns it, and it does not sit above 400 on the same ladder.
  * The accuracy of an LOD 500 element must be stated by some means other than the LOD number. A
    bare VERIFIED flag asserts nothing about how closely the model matches the building.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_lod500_readiness.py
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_lod500_readiness.db"
os.environ["STORAGE_DIR"] = "./test_storage_lod500"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_lod500_readiness.db"):
    os.remove("./test_lod500_readiness.db")

from aec_api import lod  # noqa: E402

FULL = {"type_name": "T", "classification": "C", "psets": {"P": {"a": 1}}, "qtos": {"q": 1}}


def el(ifc_class="IfcWall", *, verified=False, measured=False, within=None, thin=False, **ab):
    e = {"ifc_class": ifc_class}
    e.update({} if thin else FULL)
    psets = dict(e.get("psets") or {})
    if verified:
        psets["Massing_AsBuilt"] = {"Status": "VERIFIED", "Method": ab.get("method", "laser-scan"),
                                    "VerifiedBy": ab.get("by", "Survey Co"),
                                    "VerifiedDate": "2026-07-01"}
    dims = {}
    if measured:
        dims["Length_Measured"] = 3.01
        dims["Length_Design"] = 3.0
    if within is not None:
        dims["WithinTolerance"] = "true" if within else "false"
    if dims:
        psets["Massing_AsBuiltDim"] = dims
    if psets:
        e["psets"] = psets
    return e


# ---- reading the stamp ---------------------------------------------------------------------------
v = lod.verification(el(verified=True, measured=True, within=True))
assert v["verified"] and v["method"] == "laser-scan" and v["verified_by"] == "Survey Co"
assert v["accuracy_stated"] is True and v["within_tolerance"] is True
bare = lod.verification(el(verified=True))
assert bare["verified"] is True and bare["accuracy_stated"] is False, bare
assert bare["within_tolerance"] is None, "unmeasured is unknown, never assumed in tolerance"
none = lod.verification({"ifc_class": "IfcWall"})
assert none["verified"] is False and none["method"] is None
# a malformed psets value must not raise — the index is model-derived
assert lod.verification({"psets": "not-a-dict"})["verified"] is False

# ---- THE POINT: LOD 500 comes from verification, never from modelling ----------------------------
# UPDATED in v0.3.901 (LOD-ASPECTS). These assertions used to read "LOD 400", which the old
# facet-count scorer produced for any information-complete element regardless of its shape. Bands
# now come from geometry, and the best a MODEL READ can demonstrate is LOD 350: the index records
# how a shape is built, and nothing in it distinguishes a coordination-ready solid from a
# fabrication-ready one. Reporting 350-with-an-unread-ceiling is the honest version of what the
# old 400 was asserting without evidence.
#
# The POINT of this block is untouched, and it is the reason the file exists: whatever the geometry
# says, only a field verification reaches 500.
def geo(**kw):
    """The fixture with a resolved solid and a placement — i.e. as far as modelling can carry it."""
    e = el(**kw)
    e.update({"rep_types": ["Brep"], "placed": True, "has_material": True})
    return e


assert lod.achieved_lod(geo()) == "LOD 350", lod.achieved_lod(geo())
# ...and the ceiling says the rest is UNREAD rather than absent — the distinction the single
# number could not make.
assert lod.lod_ceiling(geo()) == "LOD 400", lod.lod_ceiling(geo())
# a verified element reaches 500 — even a THIN one, and even a BOX, because that is what the
# standard measures: observation of what exists, not richness of what was drawn.
assert lod.achieved_lod(geo(verified=True, measured=True, within=True)) == "LOD 500"
assert lod.achieved_lod(el(verified=True, thin=True)) == "LOD 500"
# ...but one measured OUTSIDE tolerance is not promoted: it is verified as wrong. It falls back to
# what its geometry supports, which is the honest place for it.
assert lod.achieved_lod(geo(verified=True, measured=True, within=False)) == "LOD 350"
assert "LOD 500" in lod.LOD_BANDS and lod.LOD_BANDS[-1] == "LOD 500"

# ---- the gap list: a reason and a next action per element, not a percentage -----------------------
idx = {
    "g_ok": el(verified=True, measured=True, within=True),
    "g_ok2": el("IfcSlab", verified=True, measured=True, within=True),
    "g_unverified": el("IfcWall"),
    "g_bad_tol": el("IfcBeam", verified=True, measured=True, within=False),
    "g_no_acc": el("IfcColumn", verified=True),
    "g_thin": el("IfcDoor", verified=True, measured=True, within=True, thin=True),
}
r = lod.handover_readiness(None, "p1", idx)
assert r["model_scored"] is True and r["elements"] == 6
assert r["lod500"] == 2, r["lod500"]
assert r["readiness_pct"] == round(100 * 2 / 6, 1), r["readiness_pct"]
assert r["by_reason"] == {"not_verified": 1, "no_accuracy": 1,
                          "out_of_tolerance": 1, "thin_information": 1}, r["by_reason"]
reasons = {g["guid"]: g["reason"] for g in r["gaps"]}
assert reasons == {"g_unverified": "not_verified", "g_bad_tol": "out_of_tolerance",
                   "g_no_acc": "no_accuracy", "g_thin": "thin_information"}, reasons
# every gap names what to do next — the whole point of a work list over a percentage
assert all(g["action"] and g["action"] == r["actions"][g["reason"]] for g in r["gaps"])
assert "more modelling" in r["actions"]["not_verified"], "the standard's core point must be stated"
assert all(g["ifc_class"] and g["discipline"] for g in r["gaps"])
# the elements that PASS are absent from the gap list — a work list carries only work
assert not any(g["guid"].startswith("g_ok") for g in r["gaps"])

# per-discipline readiness, so the remaining effort can be assigned
byd = {d["discipline"]: d for d in r["by_discipline"]}
assert sum(d["elements"] for d in r["by_discipline"]) == 6
assert sum(d["lod500"] for d in r["by_discipline"]) == 2
for d in r["by_discipline"]:
    assert d["readiness_pct"] == round(100.0 * d["lod500"] / d["elements"], 1), d
assert byd, byd

# ---- a truncated list says how much it withheld --------------------------------------------------
many = {f"g{i}": el("IfcWall") for i in range(50)}
cap = lod.handover_readiness(None, "p1", many, limit=10)
assert len(cap["gaps"]) == 10 and cap["truncated"] == 40, (len(cap["gaps"]), cap["truncated"])
assert cap["by_reason"]["not_verified"] == 50, "counts cover everything, not just the shown slice"
assert cap["readiness_pct"] == 0.0

# a fully verified model reports done, with an empty work list
allgood = {f"g{i}": el(verified=True, measured=True, within=True) for i in range(8)}
done = lod.handover_readiness(None, "p1", allgood)
assert done["lod500"] == 8 and done["readiness_pct"] == 100.0
assert done["gaps"] == [] and done["by_reason"] == {} and done["truncated"] == 0

# no model loaded is an honest empty state, not a 0%-that-looks-like-failure
empty = lod.handover_readiness(None, "p1", None)
assert empty["model_scored"] is False and empty["gaps"] == [] and "load one" in empty["note"].lower()

# ---- the assessment now reports the 500 band it could never reach before -------------------------
dist_idx = {"a": geo(verified=True, measured=True, within=True), "b": geo()}
# assess() needs a DB session for the target matrix; the distribution logic is what matters here
counted = {}
for e in dist_idx.values():
    counted[lod.achieved_lod(e)] = counted.get(lod.achieved_lod(e), 0) + 1
assert counted == {"LOD 500": 1, "LOD 350": 1}, counted

print("LOD500 OK - the field-verification stamp that has been written into the IFC since G1 is now "
      "READ by the LOD assessment, which previously capped every model at LOD 400 no matter how much "
      "of it had been verified: the evidence was in the file and the reader ignored it. Two things "
      "from the BIMForum specification are encoded, both commonly got wrong. LOD 500 is not 'more "
      "detail than 400' — it is a field-verified as-built condition, so an information-complete "
      "element nobody looked at stops at what its GEOMETRY supports while a THIN verified one reaches 500, which is exactly "
      "backwards from how LOD is usually described. And an element measured outside tolerance is NOT "
      "promoted: it has been verified as wrong, which is a finding rather than a handover. The "
      "accuracy requirement is enforced too — a bare VERIFIED flag states no accuracy, and the 2024 "
      "spec requires accuracy to be expressed by means other than the LOD number, so it is reported "
      "as an incomplete assertion. Above all the output is a WORK LIST: every short element carries "
      "a reason and the next action, grouped by discipline, because '62% ready' tells a project "
      "nothing it can schedule.")
