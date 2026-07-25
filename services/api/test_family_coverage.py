"""FAMILY-COMPLETE — can the installed shelf actually build a building?

The catalog grew to 400+ families across 57 packs and nobody could answer that question, because
"how many families do we have" is not the same question. This test is the one that matters: for each
of the six target typologies, does the shelf carry every system class needed to model one.

It caught a real hole the moment it was written. 413 families of superstructure, MEP, finishes and
site — and zero `IfcFootingType`. Every typology was unbuildable for the same reason, and breadth
everywhere else did not substitute for a building having no foundations.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_family_coverage.py
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_family_coverage.db"
os.environ["STORAGE_DIR"] = "./test_storage_family_coverage"
if os.path.exists("./test_family_coverage.db"):
    os.remove("./test_family_coverage.db")

from aec_data import family_packs as fp  # noqa: E402

TYPOLOGIES = {"residential", "commercial", "hotel", "hospital", "industrial", "airport"}

# ---- the requirement tables are coherent -----------------------------------------------------------
assert set(fp.TYPOLOGY_SYSTEMS) == TYPOLOGIES, sorted(fp.TYPOLOGY_SYSTEMS)
for group in (fp.BASE_SYSTEMS, *fp.TYPOLOGY_SYSTEMS.values()):
    for system, classes in group.items():
        assert classes and all(c.startswith("Ifc") and c.endswith("Type") for c in classes), (system, classes)
# every requirement is an IFC *type* class — an occurrence class here would never match a family pack
assert "IfcFooting" not in {c for g in (fp.BASE_SYSTEMS,) for cs in g.values() for c in cs}
# foundations are a BASE requirement, not a per-typology one: no building stands without them
assert "IfcFootingType" in fp.BASE_SYSTEMS["structure"], fp.BASE_SYSTEMS["structure"]

# ---- the shelf reads ------------------------------------------------------------------------------
have = fp.shelf_classes()
assert len(have) > 50, f"only {len(have)} type classes on the shelf — is it installed?"
assert "IfcWallType" in have and "IfcDoorType" in have and "IfcFootingType" in have, sorted(have)[:20]
# the scan is a text read of STEP, so it must not invent classes that aren't entity names
assert all(c.startswith("Ifc") or c.startswith("IFC") for c in have), sorted(have)[:10]

# cached: a second call over an unchanged shelf must return the identical set
assert fp.shelf_classes() == have

# ---- THE GATE: all six typologies are buildable from the installed shelf ---------------------------
cov = fp.coverage()
assert set(cov["buildable"]) == TYPOLOGIES, (
    f"not buildable: {cov['not_buildable']} — "
    + "; ".join(f"{r['typology']}: {r['missing_systems']}"
                for r in cov["typologies"] if not r["buildable"]))
assert cov["not_buildable"] == []
assert cov["shelf_classes"] == len(have)

for row in cov["typologies"]:
    assert row["buildable"] and row["satisfied_pct"] == 100.0, row
    assert row["satisfied_systems"] == row["total_systems"] == len(row["systems"])
    names = [s["system"] for s in row["systems"]]
    assert len(names) == len(set(names)), names          # base + typology systems must not collide
    assert set(fp.BASE_SYSTEMS) <= set(names), names     # every building carries the base systems
    for s in row["systems"]:
        assert s["missing"] == [] and set(s["present"]) == set(s["required"]), s

# a single typology narrows the report rather than changing the verdict
one = fp.coverage("hospital")
assert len(one["typologies"]) == 1 and one["typologies"][0]["typology"] == "hospital"
assert one["typologies"][0]["buildable"] is True
assert [r for r in cov["typologies"] if r["typology"] == "hospital"] == one["typologies"]

# ---- partial coverage is reported as partial, never rounded up to "fine" ---------------------------
# Satisfaction is all-or-nothing per system on purpose: an HVAC package with terminals and no duct is
# not half an HVAC package, it is a package that cannot be issued. Prove the engine treats it that way
# by asking for a system the shelf provably cannot serve.
saved = fp.BASE_SYSTEMS["structure"]
try:
    fp.BASE_SYSTEMS["structure"] = (*saved, "IfcVibrationIsolatorType", "IfcNoSuchThingType")
    broken = fp.coverage("hospital")["typologies"][0]
    assert broken["buildable"] is False, broken
    assert "structure" in broken["missing_systems"], broken["missing_systems"]
    bad = next(s for s in broken["systems"] if s["system"] == "structure")
    assert "IfcNoSuchThingType" in bad["missing"] and bad["satisfied"] is False, bad
    # the classes it DOES have are still reported — a gap names what's missing, not what's present
    assert "IfcFootingType" in bad["present"], bad["present"]
    assert 0 < broken["satisfied_pct"] < 100.0, broken["satisfied_pct"]
finally:
    fp.BASE_SYSTEMS["structure"] = saved
assert fp.coverage("hospital")["typologies"][0]["buildable"] is True   # restored

# an unknown typology is refused rather than answered with an empty, passing report
for bad_key in ("stadium", "", "RESIDENTIAL"):
    try:
        fp.coverage(bad_key)
        raise AssertionError(f"expected refusal for {bad_key!r}")
    except ValueError as e:
        assert "unknown typology" in str(e), str(e)

# ---- the shelf still lists and resolves alongside the new reader -----------------------------------
listed = fp.list_packs()
assert listed["count"] >= 50 and listed["manifest"] is True, listed["count"]
assert listed["totals"]["families"] > 400 and listed["totals"]["types"] > 2500, listed["totals"]
assert listed["totals"]["undescribed"] == 0, "every installed pack should have a manifest row"
found = next(p for p in listed["packs"] if "foundations" in p["name"])
assert found["discipline"] == "structural-foundations" and found["families"] >= 10, found

print("FAMILY-COMPLETE OK - the shelf is now checked against what it takes to BUILD, not against how "
      "many families it holds. Coverage asserts on IFC type classes per system, so it proves the "
      "shelf can place a pump rather than that some catalog named something 'fire_pump'. Writing it "
      "immediately found the hole that 413 families had hidden: not one IfcFootingType anywhere, so "
      "all six typologies were unbuildable for want of foundations while the catalog looked "
      "enormous. With structural-foundations installed, residential, commercial, hotel, hospital, "
      "industrial and airport all clear every base system (structure, envelope, openings, "
      "circulation, HVAC, plumbing, electrical, fire, site) plus their own. A system is satisfied "
      "only when EVERY required class is present — terminals with no duct is not half an HVAC "
      "package — a partial shelf names the missing classes instead of rounding up, and an unknown "
      "typology is refused rather than answered with an empty report that would read as a pass.")
