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

# ── VG-DARK: the per-element map is the engine's product and NOT a payload ───────────────────────
# `style_summary` collapses it into the distinct resolved states, which is what a screen asks. The
# grouping key is the WHOLE state on both sides, so two categories that resolve identically collapse
# and a rule that changed one of them splits them again.
S = vt.style_summary(G)
assert sum(b["count"] for b in S) == len(G) == 4, S
assert [b["count"] for b in S] == sorted((b["count"] for b in S), reverse=True), "worst-first by count"
# W1 (fire-rated, red) and W2 (default colour) are the same CATEGORY and must not collapse together.
walls = [b for b in S if b["group"] == "enclosure"]
assert len(walls) == 2, f"a colour rule on one wall must split the bucket: {walls}"
assert {b["cut"]["color"] for b in walls} == {"#cc0000", "#111111"}, walls
# Two elements that resolve identically DO collapse — otherwise the summary is the map again.
IDX_PAIR = {"A": {"guid": "A", "ifc_class": "IfcColumn"}, "B": {"guid": "B", "ifc_class": "IfcColumn"}}
pair = vt.style_summary(vt.graphics(IDX_PAIR, vt._norm({"id": "p", "hide_classes": ["IfcNope"]}))["graphics"])
assert len(pair) == 1 and pair[0]["count"] == 2, pair
assert pair[0]["sample"] == ["A", "B"], pair
assert len(vt.style_summary({})) == 0

# `cut_count: 0` has two causes and they are not the same answer.
assert vt.graphics(IDX, tpl, cut_guids={"W1"})["cut_supplied"] is True
assert vt.graphics(IDX, tpl)["cut_supplied"] is False, "no cut list is not the same as nothing cut"
assert vt.graphics(IDX, tpl)["cut_count"] == 0

# `sample` is bounded, so a 40,000-element bucket does not carry 40,000 GUIDs back.
many = {f"{i:022d}": {"guid": f"{i:022d}", "ifc_class": "IfcColumn"} for i in range(50)}
big = vt.style_summary(vt.graphics(many, vt._norm({"id": "m", "hide_classes": ["IfcNope"]}))["graphics"])
assert len(big) == 1 and big[0]["count"] == 50 and len(big[0]["sample"]) == 5, big

# ── the ROUTE decides what crosses the wire; the engine still returns everything ──────────────────
import json as _json  # noqa: E402
import os as _os  # noqa: E402

_os.environ["DATABASE_URL"] = "sqlite:///./test_vg_overrides.db"
from fastapi.testclient import TestClient  # noqa: E402

from aec_api import storage  # noqa: E402
from aec_api.main import app  # noqa: E402

_N = 3000
_CL = ["IfcWall", "IfcSlab", "IfcColumn", "IfcDuctSegment", "IfcDoor"]
with TestClient(app) as _c:
    _pid = _c.post("/projects", json={"name": "VG"}).json()["id"]
    storage.put(f"{_pid}/props.json", _json.dumps({"elements": [
        {"guid": f"{i:022d}", "ifc_class": _CL[i % len(_CL)]} for i in range(_N)]}).encode())
    assert _c.put(f"/projects/{_pid}/view-templates", json={"templates": [{
        "id": "t1", "name": "Sheet Lines", "hide_classes": ["IfcDuctSegment"],
        "object_styles": {"ifcwall": {"cut": {"weight": 1.4}}}}]}).status_code == 200

    _base = f"/projects/{_pid}/view-templates/t1/graphics"
    # DEFAULT: counts + styles, and NOT 2,400 per-element entries. The shipped behaviour was the
    # whole map unconditionally — measured at 8.9 MB on a 50,000-element index, in a viewer-role GET,
    # read by nothing.
    _d = _c.get(_base)
    _none = _d.json()
    assert _none["graphics"] == {} and _none["graphics_mode"] == "none", _none["graphics_mode"]
    assert _none["graphics_count"] == _none["visible_count"] == 2400, _none
    # 3 styles, not 4: `IfcSlab` and `IfcColumn` are both `structure` and resolve identically, so
    # they COLLAPSE into one row — which is the summary doing its job rather than restating the map.
    # The first draft of this line asserted 4, one per surviving IFC class.
    assert _none["hidden_count"] == 600 and _none["style_count"] == 3, _none
    assert [b["group"] for b in _none["styles"]] == ["structure", "enclosure", "opening"], _none["styles"]
    assert _none["styles"][0]["count"] == 1200, "two classes in one group, one row"
    # The enclosure row carries the object-style override and the default projection beside it.
    assert _none["styles"][1]["cut"]["weight"] == 1.4, _none["styles"][1]
    assert _none["styles"][1]["projection"]["weight"] == 0.18, _none["styles"][1]
    assert _none["graphics_truncated"] is False and _none["graphics_unknown"] == []
    assert _none["max_graphics"] == vt.MAX_DETAIL == 2000
    # The bound is the POINT, so measure it rather than asserting a flag.
    assert len(_d.content) < 4000, f"default response is {len(_d.content)} bytes"

    # ?guids= — named elements only, and anything not visible is NAMED rather than dropped.
    _g1 = _none["styles"][0]["sample"][0]
    _gq = _c.get(_base, params={"guids": f"{_g1},NOPE", "cut": _g1}).json()
    assert _gq["graphics_mode"] == "guids" and list(_gq["graphics"]) == [_g1], _gq["graphics"]
    assert _gq["graphics_unknown"] == ["NOPE"], _gq["graphics_unknown"]
    assert _gq["graphics_count"] == 2400, "the population is the population in every mode"
    assert _gq["graphics_truncated"] is False, "a filter is not a truncation"
    assert _gq["cut_supplied"] is True and _gq["cut_count"] == 1, _gq
    assert _gq["graphics"][_g1]["is_cut"] is True

    # ?detail=true — the whole map, bounded, and the shortfall DECLARED.
    _all = _c.get(_base, params={"detail": "true"}).json()
    assert _all["graphics_mode"] == "all" and len(_all["graphics"]) == 2000, len(_all["graphics"])
    assert _all["graphics_truncated"] is True and _all["graphics_count"] == 2400, _all["graphics_count"]
    assert _all["graphics_unknown"] == [], "only the guids mode can fill this"
    # Under the cap it is NOT truncated — the flag must track the population, not the mode.
    assert _c.put(f"/projects/{_pid}/view-templates", json={"templates": [
        {"id": "t1", "name": "Sheet Lines", "hide_classes": ["IfcDuctSegment"],
         "object_styles": {"ifcwall": {"cut": {"weight": 1.4}}}},
        {"id": "t2", "name": "Walls only", "isolate": "IfcWall"}]}).status_code == 200
    _small = _c.get(f"/projects/{_pid}/view-templates/t2/graphics", params={"detail": "true"}).json()
    assert _small["visible_count"] == 600 and len(_small["graphics"]) == 600, _small["visible_count"]
    assert _small["graphics_truncated"] is False, "600 < 2000 is not truncated"
    assert _c.get(f"/projects/{_pid}/view-templates/nope/graphics").status_code == 404

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
      "keeps its exact old shape for the consumers already on it. VG-DARK: the per-element map was "
      "8.9 MB in a viewer-role GET on a 50k-element model and read by NOTHING, so the route now "
      "serves the distinct resolved styles (3 rows over 2,400 elements, under 4 KB) and the map is "
      "opt-in - ?guids= names the misses, ?detail=true is capped at 2,000 with the shortfall "
      "declared, graphics_count is the population in all three - and cut_supplied separates 'nothing "
      "is cut' from 'nobody said what is cut'.")
