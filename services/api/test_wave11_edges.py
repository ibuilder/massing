"""Wave 11 authoring modules — edge-case & error-path coverage that the happy-path suites
(test_types/groups/rebar/steel_connections/drawing/detailing/rules/representations) don't exercise:
empty/None inputs, degenerate values, idempotency, error raises, and one real crash that was found and
fixed (sheet_svg on an empty model). Standalone script, same style as the others.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_wave11_edges.py"""
import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import ifcopenshell.api  # noqa: E402
import ifcopenshell.util.element as ue  # noqa: E402

from aec_data import (  # noqa: E402
    connections,
    detailing,
    drawing,
    edit,
    families,
    groups,
    massing,
    rebar,
    rules,
)
from aec_data import representations as rep  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402


def _raises(fn, exc=ValueError):
    try:
        fn()
    except exc:
        return True
    return False


TMP = os.path.join(os.path.dirname(__file__), "_w11edges_test.ifc")
massing.generate_blank_ifc(TMP, name="W11 Edges", storeys=1, storey_height=3.5, ground_size=30.0)
m = open_model(TMP)
st = m.by_type("IfcBuildingStorey")[0].Name

# ────────────────────────────────────────────────────────────────────────────────────────────────
# families.py — validation/error paths + dims-variant dedup + single-material inspector + IFC import
# ────────────────────────────────────────────────────────────────────────────────────────────────
# ensure_type: unknown key, and degenerate dims, must raise
assert _raises(lambda: families.ensure_type(m, "no_such_family")), "unknown family key must raise"
assert _raises(lambda: families.ensure_type(m, "desk", dims=[1.0, 2.0])), "2-elem dims must raise"
assert _raises(lambda: families.ensure_type(m, "desk", dims=[1.0, 0.0, 2.0])), "zero-size dims must raise"
assert _raises(lambda: families.ensure_type(m, "desk", dims=[1.0, -1.0, 2.0])), "negative dims must raise"

# ensure_type dims-variant: two distinct sizes → two distinct types; same size re-used → one
t_a = families.ensure_type(m, "desk", dims=[1.8, 0.8, 0.75])
t_b = families.ensure_type(m, "desk", dims=[1.2, 0.6, 0.75])
t_a2 = families.ensure_type(m, "desk", dims=[1.8, 0.8, 0.75])
assert t_a.GlobalId != t_b.GlobalId, "distinct dims must be distinct type variants"
assert t_a2.GlobalId == t_a.GlobalId, "same-dims variant must dedupe"
assert "1.8" in t_a.Name and "×" in t_a.Name, t_a.Name          # Revit-style size-suffixed name

# create_type: class/name validation
assert _raises(lambda: families.create_type(m, "IfcWall", "Nope")), "non-Type class must raise"
assert _raises(lambda: families.create_type(m, "IfcFurnitureType", "   ")), "blank name must raise"
assert _raises(lambda: families.create_type(m, "IfcFurnitureType", "Bad", dims=[1, 2])), "bad dims must raise"

# edit_type_params: missing type + bad dims
assert _raises(lambda: families.edit_type_params(m, "NOTAGUID000000000000000", name="x")), \
    "editing a missing type must raise"
gtype = families.create_type(m, "IfcFurnitureType", "EdgeChair", dims=[0.5, 0.5, 0.9])
assert _raises(lambda: families.edit_type_params(m, gtype, dims=[0.5, 0.5])), "edit bad dims must raise"

# edit_type_params on a type created WITHOUT geometry → builds a box on first dims edit (else-branch)
gnogeom = families.create_type(m, "IfcFurnitureType", "NoGeomType")     # no dims → no box solid
typ_ng = next(t for t in m.by_type("IfcFurnitureType") if t.GlobalId == gnogeom)
assert families._rep_solid(typ_ng) is None, "type should start with no box solid"
res_ng = families.edit_type_params(m, gnogeom, dims=[1.0, 1.0, 1.0])
assert res_ng["dims"] == [1.0, 1.0, 1.0] and families._rep_solid(typ_ng) is not None, res_ng

# assign_material_set: empty layers must raise
assert _raises(lambda: families.assign_material_set(m, gtype, [])), "empty material layers must raise"

# type_detail: a single-material (not layer-set) association is reported with thickness None
single_typ_guid = families.create_type(m, "IfcColumnType", "SteelColOnly", dims=[0.3, 0.3, 3.0])
single_typ = next(t for t in m.by_type("IfcColumnType") if t.GlobalId == single_typ_guid)
steel_mat = next((mm for mm in m.by_type("IfcMaterial") if mm.Name == "Steel S355"), None) \
    or ifcopenshell.api.run("material.add_material", m, name="Steel S355")
ifcopenshell.api.run("material.assign_material", m, products=[single_typ], material=steel_mat)
det_single = families.type_detail(m, single_typ_guid)
assert det_single["materials"] == [{"material": "Steel S355", "thickness": None}], det_single["materials"]

# import_types_from_ifc: whole function was untested — round-trip a type through a library file
LIB = os.path.join(os.path.dirname(__file__), "_w11edges_lib.ifc")
massing.generate_blank_ifc(LIB, name="Lib", storeys=1, storey_height=3.0, ground_size=10.0)
mlib = open_model(LIB)
families.create_type(mlib, "IfcFurnitureType", "Imported Bench", dims=[1.5, 0.4, 0.45])
mlib.write(LIB)
before_types = {(t.is_a(), t.Name) for t in m.by_type("IfcTypeProduct")}
imported = families.import_types_from_ifc(m, LIB)
assert any(i["name"] == "Imported Bench" for i in imported), imported
assert ("IfcFurnitureType", "Imported Bench") not in before_types
assert any(t.Name == "Imported Bench" for t in m.by_type("IfcFurnitureType")), "type not imported"
# re-importing the same library imports nothing new (dedup by class+name)
again = families.import_types_from_ifc(m, LIB)
assert again == [], f"re-import should dedupe, got {again}"

# ────────────────────────────────────────────────────────────────────────────────────────────────
# groups.py — empty/stale inputs, degenerate arrays, missing-guid inspectors, array-detach invariant
# ────────────────────────────────────────────────────────────────────────────────────────────────
cg = families.create_type(m, "IfcColumnType", "COL Edge", dims=[0.4, 0.4, 3.5])
c0 = edit.place_type(m, cg, st, [0.0, 0.0])
c1 = edit.place_type(m, cg, st, [3.0, 0.0])

# create_assembly needs at least one real part; all-stale guids also raise
assert _raises(lambda: groups.create_assembly(m, "Empty", [])), "empty assembly must raise"
assert _raises(lambda: groups.create_assembly(m, "Stale", ["NOTAGUID000000000000000"])), \
    "all-stale assembly must raise"

# create_group tolerates a None name (→ 'Group') and all-stale guids (→ 0 members, still a group)
gnull = groups.create_group(m, None, ["NOTAGUID000000000000000"])
assert gnull["name"] == "Group" and gnull["members"] == 0, gnull

# array_element degenerate cases: 1×1 makes no copies; nx/ny clamp up from 0/negative
assert groups.array_element(m, c0, nx=1, ny=1)["count"] == 0, "1x1 array should make no copies"
assert groups.array_element(m, c0, nx=0, ny=-3, dx=1.0)["count"] == 0, "0/-neg clamps to 1x1 → 0 copies"

# array-detach invariant: arraying a GROUPED element must NOT swell the source group
grp = groups.create_group(m, "BayLine", [c1])
assert grp["members"] == 1, grp
arr = groups.array_element(m, c1, nx=3, ny=1, dx=1.5)
assert arr["count"] == 2, arr
grp_after = groups.group_detail(m, grp["guid"])
assert grp_after["member_count"] == 1, \
    f"arrayed copies must be detached from the source group, got {grp_after['member_count']}"

# inspectors on a missing guid: ungroup → {removed:0}; group_detail → raises
assert groups.ungroup(m, "NOTAGUID000000000000000") == {"removed": 0}, "ungroup missing must be no-op"
assert _raises(lambda: groups.group_detail(m, "NOTAGUID000000000000000")), \
    "group_detail on a missing guid must raise"

# ────────────────────────────────────────────────────────────────────────────────────────────────
# rebar.py — degenerate tie spacing, invalid bar size falls back (no crash), non-column raise
# ────────────────────────────────────────────────────────────────────────────────────────────────
rcol = edit.add_column(m, [10, 10], 3.5, 0.5, 0.5, st)
# tie_spacing 0 must not divide-by-zero (guarded by max(spacing, 0.05)); still ≥2 ties
r0 = rebar.add_rebar_cage(m, rcol, tie_spacing=0.0)
assert r0["bars"] == 4 and r0["ties"] >= 2, r0
# invalid bar size silently falls back to #5 (rebar_diameter default) — cage still builds
rcol2 = edit.add_column(m, [14, 10], 3.5, 0.5, 0.5, st)
r_badsize = rebar.add_rebar_cage(m, rcol2, bar_size="#999", tie_size="#zzz")
assert r_badsize["bars"] == 4, r_badsize
# huge tie spacing → exactly the 2 end ties
rcol3 = edit.add_column(m, [18, 10], 3.5, 0.5, 0.5, st)
r_huge = rebar.add_rebar_cage(m, rcol3, tie_spacing=100.0)
assert r_huge["ties"] == 2, r_huge

# ────────────────────────────────────────────────────────────────────────────────────────────────
# connections.py — bolt-count clamping (0 / >4), single-bolt shear tab, wrong-class raises
# ────────────────────────────────────────────────────────────────────────────────────────────────
sc = edit.add_steel_column(m, [22, 10], 3.5, "W12x26", st)
sb = edit.add_steel_beam(m, [22, 10], [28, 10], "W16x40", st)
# bolts=0 → a plate with no bolts (no crash)
bp0 = connections.add_base_plate(m, sc, bolts=0)
assert bp0["bolts"] == 0, bp0
# bolts request above 4 is capped at 4 corner bolts
sc2 = edit.add_steel_column(m, [26, 14], 3.5, "W12x26", st)
bp_many = connections.add_base_plate(m, sc2, bolts=9)
assert bp_many["bolts"] == 4, f"bolt count must cap at 4, got {bp_many['bolts']}"
# shear tab with a single bolt exercises the bolts==1 dz branch (no div-by-zero)
stab1 = connections.add_shear_tab(m, sb, bolts=1)
assert stab1["bolts"] == 1, stab1
# shear tab on a COLUMN (not a beam) must raise
assert _raises(lambda: connections.add_shear_tab(m, sc)), "shear tab on a non-beam must raise"
# base plate on a beam must raise
assert _raises(lambda: connections.add_base_plate(m, sb)), "base plate on a non-column must raise"

# ────────────────────────────────────────────────────────────────────────────────────────────────
# drawing.py — the sheet_svg empty-model CRASH (found + fixed) + empty schedules + keynote priority
# ────────────────────────────────────────────────────────────────────────────────────────────────
# REGRESSION: plan_svg's empty branch must expose 'paper'/'inner' so sheet_svg doesn't KeyError.
empty_plan = drawing.plan_svg(m, storey="Nonexistent Level")
assert empty_plan["elements"] == 0 and "paper" in empty_plan and "inner" in empty_plan, \
    "empty plan_svg must still carry paper/inner (else sheet_svg crashes)"
sh_empty = drawing.sheet_svg(m, storey="Nonexistent Level")     # previously raised KeyError('paper')
assert sh_empty["svg"].startswith("<svg") and ">A-101<" in sh_empty["svg"], sh_empty
assert sh_empty["plan"]["elements"] == 0, sh_empty

# schedules on a model with no doors/windows/rooms → well-formed empty tables (no crash)
_fresh = os.path.join(os.path.dirname(__file__), "_w11edges_empty.ifc")
massing.generate_blank_ifc(_fresh, name="Empty Sched", storeys=1, storey_height=3.0, ground_size=10.0)
mempty = open_model(_fresh)
sch = drawing.schedules(mempty)
assert sch["doors"]["rows"] == [] and sch["windows"]["rows"] == [] and sch["rooms"]["rows"] == [], sch
dsvg = drawing.schedule_svg(mempty, "doors")
assert dsvg["rows"] == 0 and dsvg["svg"].startswith("<svg") and "DOOR SCHEDULE" in dsvg["svg"], dsvg

# keynote priority: an element carrying BOTH MasterFormat and UniFormat → MasterFormat wins the bubble
kw = edit.add_wall(mempty, [0, 0], [6, 0], 3.0, 0.2, mempty.by_type("IfcBuildingStorey")[0].Name)
detailing.classify(mempty, [kw], "UniFormat", "B2010", "Ext walls")
detailing.classify(mempty, [kw], "MasterFormat", "04 20 00", "Unit Masonry")
kplan = drawing.plan_svg(mempty, keynotes=True)
assert kplan["keynotes"] == 1 and "04 20 00" in kplan["svg"] and "B2010" not in kplan["svg"], \
    "MasterFormat should outrank UniFormat in the keynote legend"

# ────────────────────────────────────────────────────────────────────────────────────────────────
# detailing.py — empty guids, name-dedup (no identification), inspector on a missing guid
# ────────────────────────────────────────────────────────────────────────────────────────────────
assert detailing.classify(m, [], "MasterFormat", "01 00 00") == 0, "empty classify must return 0"
assert detailing.classify(m, None, "MasterFormat", "01 00 00") == 0, "None classify must return 0"
# attach with no guids still returns 0 (and does not raise even though it builds the info/ref)
assert detailing.attach_document(m, [], "Orphan Detail") == 0, "empty attach must return 0"
# dedup by NAME when no identification is supplied
wdoc = edit.add_wall(m, [0, 20], [6, 20], 3.0, 0.2, st)
detailing.attach_document(m, [wdoc], "Shared By Name", location="a.svg")
n_info = len(m.by_type("IfcDocumentInformation"))
detailing.attach_document(m, [wdoc], "Shared By Name", location="a.svg")
assert len(m.by_type("IfcDocumentInformation")) == n_info, "same-name doc (no id) must dedupe the info"
# element_detailing on a missing guid raises (by_guid)
assert _raises(lambda: detailing.element_detailing(m, "NOTAGUID000000000000000"), Exception), \
    "element_detailing on a missing guid must raise"

# ────────────────────────────────────────────────────────────────────────────────────────────────
# rules.py — empty ruleset, idempotent re-apply (no duplicate codes), property-value & fire-host facets
# ────────────────────────────────────────────────────────────────────────────────────────────────
assert rules.apply_rules(m, rules=[])["matches"] == 0, "empty ruleset matches nothing"
assert rules.validate_rules(m, rules=[])["gaps"] == 0, "empty ruleset has no gaps"

# a fresh external wall + window; apply the seed rules TWICE and confirm codes don't pile up
rwall = edit.add_wall(m, [0, 24], [8, 24], 3.0, 0.2, st)
edit.set_element_pset(m, rwall, "Pset_WallCommon", "IsExternal", True, "bool")
rwin = edit.add_opening(m, rwall, width=1.5, height=1.2, sill=0.9, kind="window")
rules.apply_rules(m)
codes1 = detailing.element_detailing(m, rwin)["classifications"]
rules.apply_rules(m)                                             # idempotent-ish
codes2 = detailing.element_detailing(m, rwin)["classifications"]
mf1 = [c for c in codes1 if c["code"] == "08 51 00"]
mf2 = [c for c in codes2 if c["code"] == "08 51 00"]
assert len(mf1) == 1 and len(mf2) == 1, f"re-apply duplicated a keynote: {len(mf1)}→{len(mf2)}"

# a custom rule using the property-VALUE facet + the host_fire_rated facet (both untested branches)
edit.set_element_pset(m, rwall, "Pset_WallCommon", "FireRating", "2HR", "str")
custom = [{
    "name": "rated-host-window",
    "applies": {"entity": "IfcWindow", "host_fire_rated": True},
    "attach": {"classify": [{"system": "MasterFormat", "code": "08 88 00", "title": "Fire glazing"}]},
}, {
    "name": "value-facet-window",
    "applies": {"entity": "IfcWindow",
                "property": {"pset": "Pset_WindowCommon", "prop": "IsExternal", "value": "TRUE"}},
    "attach": {"classify": [{"system": "UniFormat", "code": "B2099", "title": "Special"}]},
}]
edit.set_element_pset(m, rwin, "Pset_WindowCommon", "IsExternal", True, "bool")
rc_custom = rules.apply_rules(m, rules=custom)
fired = {a["rule"] for a in rc_custom["applied"] if a["guid"] == rwin}
assert "rated-host-window" in fired, f"host_fire_rated facet did not fire: {fired}"
assert "value-facet-window" in fired, f"property-value facet did not fire: {fired}"
# a value facet that does NOT match must not fire
custom_nomatch = [{"name": "nomatch",
                   "applies": {"entity": "IfcWindow",
                               "property": {"pset": "Pset_WindowCommon", "prop": "IsExternal",
                                            "value": "FALSE"}},
                   "attach": {"classify": [{"system": "UniFormat", "code": "ZZZ"}]}}]
assert rules.apply_rules(m, rules=custom_nomatch)["matches"] == 0, "wrong-value facet must not match"

# ────────────────────────────────────────────────────────────────────────────────────────────────
# representations.py — empty/None set_lod, int stage coercion, lod_summary on a fresh model
# ────────────────────────────────────────────────────────────────────────────────────────────────
assert rep.set_lod(m, [], "300") == 0 and rep.set_lod(m, None, "300") == 0, "empty set_lod must be 0"
# an integer stage is coerced to its string form and accepted
assert rep.set_lod(m, [rwall], 300) == 1, "int stage 300 should coerce to '300'"
assert ue.get_pset(m.by_guid(rwall), "Pset_MassingLOD")["Stage"] == "300"
# ensure_contexts is safe to run on a populated model, and the SECOND pass creates nothing new
rep.ensure_contexts(m)                                          # first pass builds the Plan tree
r_ctx2 = rep.ensure_contexts(m)                                 # second pass must be a no-op
assert r_ctx2["created"] == 0, f"ensure_contexts not idempotent, got {r_ctx2['created']} new"

for f in (TMP, LIB, _fresh):
    if os.path.exists(f):
        os.remove(f)

print("W11 EDGES OK - families (unknown key / bad dims / non-Type class / blank name / missing-type edit "
      "raise; dims-variant dedupe; no-geom→box on first dims edit; single-material inspector; "
      "import_types_from_ifc round-trip + re-import dedupe) - groups (empty/stale assembly raise; None name; "
      "1x1 & clamped arrays make 0 copies; arrayed copies detached from source group; missing-guid "
      "ungroup no-op / group_detail raise) - rebar (tie_spacing 0 guarded, invalid bar size falls back, "
      "huge spacing → 2 ties) - connections (bolts 0 / capped at 4 / single-bolt tab; wrong-class raises) - "
      "drawing (FIXED sheet_svg KeyError on empty model; empty schedules; MasterFormat outranks UniFormat "
      "keynote) - detailing (empty/None guids → 0; name-dedup; missing-guid inspector raises) - rules "
      "(empty ruleset; idempotent re-apply no dup codes; host_fire_rated + property-value facets; "
      "wrong-value no match) - representations (empty/None set_lod; int-stage coercion; ensure_contexts "
      "idempotent).")
