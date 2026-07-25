"""R21-VG-OVERRIDES — object styles + rule-based view filters, with the distinction that matters.

`view_templates.py` already carried hide / isolate / colour rules on the QUERY-DSL spine, so the gap
was narrower and more specific than "graphics overrides": there was no line WEIGHT, no line pattern,
and no CUT-vs-PROJECTION distinction at all.

That last one is the whole feature. The same element draws two ways in one view — heavy where the view
plane cuts it, light where it is merely seen beyond the cut — and a reader uses that weight difference
to read depth off a flat sheet. Colour cannot express it, because it is not a colour difference.

The property that makes it composable, and the easiest thing to get wrong: an override is a PARTIAL.
A rule naming only a colour must leave the weights exactly as the object style set them. Were an
override a full replacement, every colour rule would silently erase the cut/projection weight
difference for everything it touched.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_vg_overrides.py
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_vg_overrides.db"
os.environ["STORAGE_DIR"] = "./test_storage_vg_overrides"
if os.path.exists("./test_vg_overrides.db"):
    os.remove("./test_vg_overrides.db")

from aec_api import view_templates as vt  # noqa: E402
from aec_api.query_dsl import QueryError  # noqa: E402

# ---- category defaults: cut is heavier than projection, for EVERY category ---------------------------
for cls in ("IfcWall", "IfcSlab", "IfcColumn", "IfcDuctSegment", "IfcDoor", "IfcSite", "IfcWhatever"):
    s = vt.default_style(cls)
    assert s["cut"]["weight"] > s["projection"]["weight"], (cls, s)
    assert vt.MIN_WEIGHT <= s["projection"]["weight"] <= vt.MAX_WEIGHT
# structure reads heavier than MEP — that ordering is the drafting convention, not an accident
assert vt.default_style("IfcColumn")["cut"]["weight"] > vt.default_style("IfcDuctSegment")["cut"]["weight"]
# an unfamiliar class must NOT default to the heaviest group, or it shouts on every sheet it appears on
assert vt.default_style("IfcBurjThing")["group"] == "other"
assert (vt.default_style("IfcBurjThing")["cut"]["weight"]
        < vt.default_style("IfcColumn")["cut"]["weight"])
assert vt.default_style("")["group"] == "other"

# ---- validation refuses what it cannot draw ----------------------------------------------------------
def bad(t, why):
    try:
        vt._norm(t)
    except QueryError:
        return
    raise AssertionError(f"expected refusal: {why}")


bad({"rules": [{"selector": "IfcWall", "color": "#fff"}]}, "3-digit hex")
bad({"rules": [{"selector": "IfcWall", "color": "#ff0000", "weight": 99}]}, "weight out of range")
bad({"rules": [{"selector": "IfcWall", "color": "#ff0000", "weight": 0.0}]}, "weight below min")
bad({"rules": [{"selector": "IfcWall", "color": "#ff0000", "weight": "thick"}]}, "weight not a number")
bad({"rules": [{"selector": "IfcWall", "color": "#ff0000", "pattern": "squiggly"}]}, "unknown pattern")
bad({"rules": [{"selector": "IfcWall", "color": "#ff0000", "applies": "elevation"}]}, "bad applies")
bad({"object_styles": {"ifcwall": {}}}, "style setting neither side")
bad({"object_styles": {"ifcwall": {"cut": {}}}}, "empty override stores nothing")
bad({"name": "empty"}, "a template that does nothing")

# BACKWARD COMPATIBILITY: a template written before this change must still validate, and must still
# mean exactly what it meant — the new expressiveness is additive, not a migration.
old = vt._norm({"name": "Legacy", "hide_classes": ["IfcFurniture"],
                "rules": [{"selector": "IfcWall", "color": "#FF0000"}]})
assert old["rules"][0]["color"] == "#ff0000"
assert old["rules"][0]["applies"] == "both", "an un-scoped rule keeps applying to both sides"
assert old["object_styles"] == {}
assert "weight" not in old["rules"][0], "a legacy rule must not acquire a weight it never declared"

# ---- resolution against a model ----------------------------------------------------------------------
IDX = {
    # psets are nested in the property index, which is what the DSL's Pset::Prop path resolves against
    "W1": {"ifc_class": "IfcWall", "name": "Ext",
           "psets": {"Pset_WallCommon": {"FireRating": "2HR"}}},
    "W2": {"ifc_class": "IfcWall", "name": "Int"},
    "C1": {"ifc_class": "IfcColumn", "name": "C1"},
    "D1": {"ifc_class": "IfcDuctSegment", "name": "D1"},
    "F1": {"ifc_class": "IfcFurniture", "name": "Desk"},
}
tpl = vt._norm({
    "id": "t1", "name": "Arch Plan",
    "hide_classes": ["IfcFurniture"],
    "object_styles": {"ifcwall": {"cut": {"weight": 0.9, "pattern": "solid"}}},
    "rules": [
        # a colour-only rule — the case that must NOT flatten weights
        {"selector": "Pset_WallCommon.FireRating=2HR", "color": "#cc0000"},
        # a projection-only rule: dash what is seen beyond the cut, leave the cut face alone
        {"selector": "IfcDuctSegment", "color": "#0088cc", "pattern": "dashed",
         "applies": "projection"},
    ],
})

g = vt.graphics(IDX, tpl, cut_guids={"W1", "C1"})
G = g["graphics"]
assert "F1" not in G, "a hidden class carries no graphics at all"
assert g["visible_count"] == 4 and g["cut_count"] == 2, g

# the object style raised the wall's CUT weight and left projection on the category default
assert G["W2"]["cut"]["weight"] == 0.9
assert G["W2"]["projection"]["weight"] == vt.default_style("IfcWall")["projection"]["weight"]
assert G["W2"]["cut"]["weight"] > G["W2"]["projection"]["weight"]

# THE PARTIAL-OVERRIDE RULE: the fire-rating rule set a COLOUR only, so W1 keeps the 0.9 cut weight
assert G["W1"]["cut"]["color"] == "#cc0000" and G["W1"]["projection"]["color"] == "#cc0000"
assert G["W1"]["cut"]["weight"] == 0.9, "a colour rule must not flatten the weight beneath it"
assert G["W1"]["cut"]["weight"] > G["W1"]["projection"]["weight"], \
    "and it must not collapse the cut/projection distinction either"
# W2 has no fire rating, so the rule never touched it
assert G["W2"]["cut"]["color"] == "#111111"

# a projection-scoped rule touches ONE side only
assert G["D1"]["projection"]["pattern"] == "dashed" and G["D1"]["projection"]["color"] == "#0088cc"
assert G["D1"]["cut"]["pattern"] == "solid", "applies=projection must leave the cut side untouched"
assert G["D1"]["cut"]["color"] == "#111111"

# is_cut reports what the plane cuts; it never invents a cut
assert G["W1"]["is_cut"] is True and G["W2"]["is_cut"] is False
assert vt.graphics(IDX, tpl)["cut_count"] == 0, "no cut set → nothing is claimed to be cut"
# ...but the cut side is still RESOLVED, so a caller can apply it later
assert vt.graphics(IDX, tpl)["graphics"]["W1"]["cut"]["weight"] == 0.9

# later rules win, matching resolve()'s existing documented semantics
tpl2 = vt._norm({"id": "t2", "rules": [{"selector": "IfcWall", "color": "#111111"},
                                       {"selector": "IfcWall", "color": "#00ff00"}]})
assert vt.graphics(IDX, tpl2)["graphics"]["W1"]["cut"]["color"] == "#00ff00"

# determinism: same template + same index → identical answer, every time
assert vt.graphics(IDX, tpl) == vt.graphics(IDX, tpl)
# an empty model resolves to an empty answer rather than raising
assert vt.graphics({}, tpl)["graphics"] == {}
assert vt.graphics(None, tpl)["visible_count"] == 0

# resolve() is unchanged — the older consumers still get exactly their old shape
r = vt.resolve(IDX, tpl)
assert set(r) == {"template", "name", "visible", "hidden_count", "visible_count", "colors",
                  "colored_count", "note"}, sorted(r)
assert r["colors"]["W1"] == "#cc0000"

print("R21-VG-OVERRIDES OK - view templates now carry the distinction that separates a drawing from a "
      "dump: CUT vs PROJECTION. The same element draws two ways in one view - heavy where the view "
      "plane cuts it, light where it is only seen beyond the cut - and that weight difference, not "
      "colour, is how a reader reads depth off a flat sheet, which is why colour rules alone (all "
      "this module had before) could not express it. Weights are millimetres on the SHEET, the same "
      "paper-space reasoning the hatch patterns use, so a wall reads at one weight at 1:100 and 1:10. "
      "Category defaults keep cut heavier than projection for every class, structure reads heavier "
      "than MEP, and an unfamiliar class lands in the neutral group rather than the heaviest so it "
      "never shouts. The property that makes it composable: an override is a PARTIAL - a rule naming "
      "only a colour leaves the weights exactly as the object style set them, because a full-"
      "replacement override would let any colour rule silently erase the cut/projection difference "
      "for everything it touched. Rules may scope themselves to one side, later rules win, every "
      "template saved before this change still validates and resolves identically, and resolve() "
      "keeps its exact old shape for the consumers already on it.")
