"""LOD-ASPECTS — a band is the MINIMUM across the ISO 7817-1 aspects, not a count of LOIN facets.

THE DEFECT THIS EXISTS FOR, measured before the fix and reproduced below as a regression:

    a generic IfcWall box + classification + Pset_WallCommon + Qto_WallBaseQuantities  ->  LOD 350
    the same box with psets and qtos removed, NOT ONE VERTEX CHANGED                   ->  LOD 200

`achieved_lod` mapped a count of LOIN facets straight onto a band (`_FACETS_TO_LOD[5] = "LOD 400"`)
and nothing on that path looked at a shape. LOD is a claim about how far an element's GEOMETRY has
been thought through; LOIN facets measure how completely it is DESCRIBED. A well-tagged placeholder
is exactly where the two come apart, and it is the most common thing in a design-stage model — so
the number was wrong in the reassuring direction, on a figure that goes into contracts and BIM
execution plans.

WHAT MADE IT FIXABLE. The properties index carried no geometry at all — `{guid, ifc_class, name,
type_name, storey, host, psets, qtos}` — so the four geometric aspects were not merely unused, they
were *undecidable*. v0.3.901 adds shape FACTS to the index (`rep_types`, `rep_ids`, `has_openings`,
`has_material`, `placed`), which is what lets the aspects be scored at all.

THE TWO-SIDED CLAIM. Every case here asserts both that the band moved for the right reason AND that
something which should NOT move did not. A scorer that simply returned "LOD 200" for everything
would satisfy half of this file; the paired assertions are what make that visible.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_lod_aspects.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_lod_aspects.db"
os.environ["STORAGE_DIR"] = "./test_storage_lodaspects"
for _f in ("./test_lod_aspects.db",):
    if os.path.exists(_f):
        os.remove(_f)

from aec_api import lod  # noqa: E402

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail and not ok else ''}")
    if not ok:
        failures.append(name)


def el(**kw):
    """An element as the served index carries it. Defaults are a placed, materialless shape with no
    representation — i.e. the least the index can say — so each case varies exactly one thing."""
    base = {"ifc_class": "IfcWall", "type_name": None, "psets": {}, "qtos": {},
            "rep_types": [], "rep_ids": [], "has_openings": False,
            "has_material": False, "placed": True}
    base.update(kw)
    return base


FULL_INFO = {"type_name": "Basic Wall", "classification": "B2010",
             "psets": {"Pset_WallCommon": {"IsExternal": "true", "FireRating": "2HR"}},
             "qtos": {"Qto_WallBaseQuantities": {"NetSideArea": 12.0}}}

# ---- THE REGRESSION. The exact pair that produced 350 vs 200 on tagging alone. ----------------
box_tagged = el(rep_types=["BoundingBox"], **FULL_INFO)
box_bare = el(rep_types=["BoundingBox"])

check("a fully tagged BOUNDING BOX does not claim a coordination band",
      lod.achieved_lod(box_tagged) == "LOD 200", lod.achieved_lod(box_tagged))
check("...and stripping its information does not move the band, because the GEOMETRY did not change",
      lod.achieved_lod(box_bare) == lod.achieved_lod(box_tagged),
      f"tagged={lod.achieved_lod(box_tagged)} bare={lod.achieved_lod(box_bare)}")
# The information reading still exists and still differs — it was never the wrong measurement, only
# the wrong label. Asserting it moved is what proves the two readings were genuinely separated
# rather than one of them deleted.
check("...while the INFORMATION score still separates them",
      lod.information_score(box_tagged) > lod.information_score(box_bare),
      f"{lod.information_score(box_tagged)} vs {lod.information_score(box_bare)}")

# ---- DETAIL is the axis IFC answers directly ---------------------------------------------------
swept = el(rep_types=["SweptSolid"], **FULL_INFO)
brep = el(rep_types=["Brep"], **FULL_INFO)
check("a swept solid conveys design intent — LOD 300", lod.achieved_lod(swept) == "LOD 300",
      lod.achieved_lod(swept))
check("a resolved solid (Brep) reaches the coordination band — LOD 350",
      lod.achieved_lod(brep) == "LOD 350", lod.achieved_lod(brep))
check("...and the ordering is strict: box < swept < brep",
      lod._LOD_RANK[lod.achieved_lod(box_tagged)] < lod._LOD_RANK[lod.achieved_lod(swept)]
      < lod._LOD_RANK[lod.achieved_lod(brep)],
      f"{lod.achieved_lod(box_tagged)} / {lod.achieved_lod(swept)} / {lod.achieved_lod(brep)}")

# ---- THE MINIMUM RULE. One weak aspect holds the whole element down. ---------------------------
# The spec is explicit that requirements are minimums and cumulative — an accurately detailed
# element located approximately "can be no higher than LOD 200". This is that rule, executable.
unplaced_brep = el(rep_types=["Brep"], placed=False, **FULL_INFO)
check("a Brep with NO PLACEMENT is held down by location, not lifted by detail",
      lod.achieved_lod(unplaced_brep) == "LOD 100", lod.achieved_lod(unplaced_brep))
check("...and the report names location as the limiting aspect",
      lod.aspects(unplaced_brep)["location"]["supported"] == "LOD 100",
      str(lod.aspects(unplaced_brep)["location"]))
# The twin: same element, placement restored, band recovers. Without this the assertion above
# passes against a scorer that returns LOD 100 whenever `placed` is read at all.
check("...and restoring the placement restores the band",
      lod.achieved_lod(el(rep_types=["Brep"], placed=True, **FULL_INFO)) == "LOD 350")

# ---- UNDECIDABLE IS REPORTED, NOT ROUNDED ------------------------------------------------------
a = lod.aspects(brep)
check("location is honest that accuracy is unreadable from the index",
      a["location"]["decidable"] is False and a["location"]["cap"] is None,
      str(a["location"]))
check("...but a placeholder's detail IS decidable — a box cannot be anything else",
      lod.aspects(box_tagged)["detail"]["decidable"] is True,
      str(lod.aspects(box_tagged)["detail"]))
check("the ceiling is at least the achieved band, never below it",
      lod._LOD_RANK[lod.lod_ceiling(brep)] >= lod._LOD_RANK[lod.achieved_lod(brep)],
      f"ceiling={lod.lod_ceiling(brep)} achieved={lod.achieved_lod(brep)}")
check("...and for a box the two AGREE, because nothing about it is unread",
      lod.lod_ceiling(box_tagged) == lod.achieved_lod(box_tagged) == "LOD 200",
      f"ceiling={lod.lod_ceiling(box_tagged)} achieved={lod.achieved_lod(box_tagged)}")

# An element with no readable shape must not score as a simple one. Failing toward "cannot tell"
# is the only safe direction: the indexer swallows a malformed representation and returns [].
noshape = el(rep_types=[], **FULL_INFO)
check("no readable shape scores the FLOOR, not a middle band",
      lod.achieved_lod(noshape) == "LOD 100", lod.achieved_lod(noshape))
check("...with a high ceiling, because the shape is unread rather than absent",
      lod.lod_ceiling(noshape) == "LOD 400", lod.lod_ceiling(noshape))

# ---- LOD 500 IS UNCHANGED, and that is deliberate ----------------------------------------------
# This logic was already right: LOD 500 is earned by someone going and looking, and an element
# measured OUTSIDE tolerance is a finding rather than a handover. Re-asserted here so the aspect
# rework cannot quietly regress it.
verified = el(rep_types=["BoundingBox"],
              psets={"Massing_AsBuilt": {"Status": "VERIFIED"},
                     "Massing_AsBuiltDim": {"Length_Measured": 3.0, "WithinTolerance": "true"}})
out_of_tol = el(rep_types=["Brep"],
                psets={"Massing_AsBuilt": {"Status": "VERIFIED"},
                       "Massing_AsBuiltDim": {"Length_Measured": 3.0, "WithinTolerance": "false"}})
check("a field-verified element reaches LOD 500 even from a BOX — observation, not modelling",
      lod.achieved_lod(verified) == "LOD 500", lod.achieved_lod(verified))
check("...and one measured OUTSIDE tolerance is not promoted",
      lod.achieved_lod(out_of_tol) != "LOD 500", lod.achieved_lod(out_of_tol))

# ---- the aspect set is complete and stable -----------------------------------------------------
check("all five ISO 7817-1 aspects are reported for every element",
      set(lod.aspects(swept)) == set(lod.ASPECTS) and len(lod.ASPECTS) == 5,
      str(sorted(lod.aspects(swept))))

print(f"\ntest_lod_aspects {'OK' if not failures else 'FAILED: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
