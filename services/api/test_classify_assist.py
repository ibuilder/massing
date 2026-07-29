"""R22-CLASSIFY-AI — the coverage number has to be believable before the proposals matter.

The defect this module was built around is in `classification.classify()`: it returns a
`(code, title)` tuple for ANY ifc_class, falling back to the system's default bucket when the class
is not in the map. The return type cannot express "I did not know". A model we authored is full of
mapped classes so it never shows; an imported model is full of `IfcBuildingElementProxy`, and every
one prices as `01 00 00 General Requirements` while the estimate reports a complete takeoff.

That is the `get_area` shape again — a fault that only fires on a particular provenance of model, so
the everyday path never catches it. The first test below pins the underlying behaviour so nobody
"fixes" this module by going back through the silent path.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_classify_assist.py
"""
import sys

sys.path.insert(0, "src")

from aec_api import classification as cls  # noqa: E402
from aec_api import classify_assist as ca  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


def el(guid, ifc_class, name=None, type_name=None):
    return {"guid": guid, "ifc_class": ifc_class, "name": name, "type_name": type_name}


# --- 0. the behaviour this module exists to make visible -------------------------------------------
code, title = cls.classify("IfcBuildingElementProxy", "masterformat")
check("an unmapped class still returns a (code, title) from the class map",
      (code, title) == cls.CLASSIFICATIONS["masterformat"]["default"], (code, title))
check("  which is the default bucket, indistinguishable from a real answer",
      code == "01 00 00")

# --- 1. the systems it will and will not propose for ------------------------------------------------
check("it proposes for the systems with a published class map",
      set(ca.systems()) == set(cls.CLASSIFICATIONS), ca.systems())
for refused in ("uniclass", "Uniclass", "omniclass"):
    try:
        ca.propose([], refused)
        check(f"{refused!r} is refused", False, "no exception")
    except ca.ClassifyError as e:
        check(f"{refused!r} is refused", True)
        if refused == "uniclass":
            check("  with the standing reason, not a bare 'unknown system'",
                  "never guessed" in str(e), str(e)[:80])
try:
    ca.propose([], "nonsense")
    check("an unknown system is an error, not an empty result", False, "no exception")
except ca.ClassifyError:
    check("an unknown system is an error, not an empty result", True)

# --- 2. the four bases ------------------------------------------------------------------------------
elements = [
    el("g1", "IfcWall", "CMU Partition Type A"),           # keyword: masonry
    el("g2", "IfcWall", "Gyp Bd Partition 3-5/8"),         # keyword: gypsum
    el("g3", "IfcWall", "Wall-01"),                        # class_map only
    el("g4", "IfcBuildingElementProxy", "Widget 12"),      # unmapped
    el("g5", "IfcSlab", "Level 2 Slab"),                   # class_map
    el("g6", "IfcDoor", "D-101"),                          # class_map, and declared below
]
declared = {"g6": [{"system": "CSI MasterFormat", "code": "08 11 13", "title": "Hollow Metal Doors"}]}

p = ca.propose(elements, "masterformat", declared)
by_guid = {r["guid"]: r for r in p["rows"]}
check("a declared code wins over everything derivable", by_guid["g6"]["basis"] == "declared")
check("  and the model's own code is reported, not ours",
      by_guid["g6"]["code"] == "08 11 13", by_guid["g6"]["code"])
check("a name keyword beats the class map", by_guid["g1"]["basis"] == "keyword"
      and by_guid["g1"]["code"] == "04 20 00", by_guid["g1"])
check("  and a different keyword gives a different code on the SAME class",
      by_guid["g2"]["code"] == "09 20 00", by_guid["g2"]["code"])
check("  each keyword row carries the pattern that fired",
      "matches /" in by_guid["g1"]["evidence"])
check("a plain wall falls to the class map", by_guid["g3"]["basis"] == "class_map")
check("  at LOW confidence, because it is a fact about the class",
      by_guid["g3"]["confidence"] == "low")
check("  and the evidence says so in words",
      "true of the CLASS" in by_guid["g3"]["evidence"])
check("an unmapped class gets NO code", by_guid["g4"]["basis"] == "unmapped"
      and by_guid["g4"]["code"] is None, by_guid["g4"])
check("  and its evidence names the bucket it would otherwise have been given",
      "01 00 00" in by_guid["g4"]["evidence"] and "not a classification" in by_guid["g4"]["evidence"])

# --- 3. coverage counts DECLARED only ----------------------------------------------------------------
check("coverage counts only what the model declares", p["declared"] == 1 and p["total"] == 6)
check("  so the percentage is 16.7, not 83.3", p["classified_pct"] == 16.7, p["classified_pct"])
check("  proposals are counted separately", p["proposable"] == 4, p["proposable"])
check("  as are the elements nothing can classify", p["unmapped"] == 1)
check("  and the result says the figure excludes our guesses",
      "not the model" in p["counts_only_declared"])
check("  with a warning naming the estimate consequence",
      "default bucket" in (p["unmapped_warning"] or ""), p["unmapped_warning"])
check("the basis counts add up to the total", sum(p["by_basis"].values()) == p["total"])

nothing = ca.propose(elements, "masterformat")          # no `declared` supplied at all
check("with no declared map supplied, coverage is 0% and says the map was absent",
      nothing["classified_pct"] == 0.0 and nothing["declared_supplied"] is False)

# --- 4. system-name matching is exact, not fuzzy ------------------------------------------------------
# The first version matched substrings both ways, so the display name "CSI MasterFormat (US/CA)"
# contributed the fragment "us" and a model declaring "AusSpec" matched MasterFormat. A wrong system
# match is worse than none: it reports an element as classified under a standard it never was.
for name, expect in (("MasterFormat", True), ("masterformat", True), ("CSI MasterFormat", True),
                     ("CSI  MasterFormat ", True), ("AusSpec", False), ("us", False),
                     ("Uniclass 2015", False), ("NRM 1", False)):
    got = ca.propose([el("x", "IfcDoor", "D")], "masterformat",
                     {"x": [{"system": name, "code": "08 11 13", "title": "t"}]})
    is_declared = got["rows"][0]["basis"] == "declared"
    check(f"a source named {name!r} {'matches' if expect else 'does NOT match'} masterformat",
          is_declared is expect, got["rows"][0]["basis"])

noid = ca.propose([el("x", "IfcDoor", "D")], "masterformat",
                  {"x": [{"system": "MasterFormat", "code": None, "title": "t"}]})
check("a classification reference with no Identification classifies nothing",
      noid["rows"][0]["basis"] != "declared")

# --- 5. NRM1 external/internal — where the class map is confidently wrong ------------------------------
nrm = ca.propose([el("w1", "IfcWall", "External Cavity Wall"),
                  el("w2", "IfcWall", "Internal Partition"),
                  el("w3", "IfcWall", "Wall")], "nrm1")
n = {r["guid"]: r for r in nrm["rows"]}
check("NRM1: an externally-named wall proposes external walls",
      n["w1"]["code"] == "2.6" and n["w1"]["basis"] == "keyword")
check("NRM1: an internally-named wall proposes internal walls",
      n["w2"]["code"] == "2.7" and n["w2"]["basis"] == "keyword")
check("NRM1: an unnamed wall takes the class map's guess — which is 'external' for every IfcWall",
      n["w3"]["code"] == "2.6" and n["w3"]["basis"] == "class_map", n["w3"])

# --- 6. the plan is explicit, and refuses loudly --------------------------------------------------------
plan = ca.apply_plan(p["rows"], ["g1", "g3"], "masterformat")
check("a plan is built for the accepted GUIDs only", plan["count"] == 2, plan["count"])
check("  as ordinary set_classification recipe steps",
      all(s["recipe"] == "set_classification" for s in plan["steps"]))
check("  carrying the system's real name, not our key",
      plan["steps"][0]["params"]["system"] == cls.CLASSIFICATIONS["masterformat"]["name"])
check("  and the code from the row", plan["steps"][0]["params"]["code"] == "04 20 00")

mixed = ca.apply_plan(p["rows"], ["g1", "g4", "g6", "ghost", "g1"], "masterformat")
check("only the applicable one becomes a step", mixed["count"] == 1, mixed["count"])
reasons = {s["guid"]: s["reason"] for s in mixed["skipped"]}
check("  an unmapped element is skipped WITH a reason", "g4" in reasons)
check("  an already-declared element is skipped, not double-tagged",
      "already declared" in reasons.get("g6", ""), reasons.get("g6"))
check("  a GUID not in the proposal set is skipped by name",
      "not in the proposal set" in reasons.get("ghost", ""))
check("  nothing is silently dropped: every rejected GUID is accounted for",
      set(reasons) == {"g4", "g6", "ghost"}, sorted(reasons))
check("  a duplicate accept does not produce two steps", mixed["count"] == 1)

ed = ca.apply_plan(p["rows"], ["g1"], "masterformat", edition="2020")
check("an edition rides through to the recipe", ed["steps"][0]["params"]["edition"] == "2020")

# --- 7. read_declared walks the reference chain ----------------------------------------------------------
class FakeEnt:
    def __init__(self, kind, **kw):
        self._kind = kind
        self.__dict__.update(kw)

    def is_a(self, other=None):
        return self._kind if other is None else other == self._kind


class FakeModel:
    def __init__(self, rels):
        self._rels = rels

    def by_type(self, kind):
        return self._rels if kind == "IfcRelAssociatesClassification" else []


source = FakeEnt("IfcClassification", Name="MasterFormat")
# A reference pointing at ANOTHER reference (a facet of a code) rather than straight at the source —
# reading only one level reports system=None for every correctly-authored hierarchical code.
parent_ref = FakeEnt("IfcClassificationReference", Identification="08", Name="Openings",
                     ReferencedSource=source)
leaf = FakeEnt("IfcClassificationReference", Identification="08 11 13", Name="Hollow Metal Doors",
               ReferencedSource=parent_ref)
obj = FakeEnt("IfcDoor", GlobalId="d1")
got = ca.read_declared(FakeModel([FakeEnt("IfcRelAssociatesClassification",
                                          RelatingClassification=leaf, RelatedObjects=[obj])]))
check("read_declared walks up a reference chain to the owning IfcClassification",
      got["d1"][0]["system"] == "MasterFormat", got)
check("  and keeps the leaf's code", got["d1"][0]["code"] == "08 11 13")

# A self-referencing chain is malformed input, not a reason to hang a whole-model scan.
loop = FakeEnt("IfcClassificationReference", Identification="X", Name="loop")
loop.ReferencedSource = loop
looped = ca.read_declared(FakeModel([FakeEnt("IfcRelAssociatesClassification",
                                             RelatingClassification=loop,
                                             RelatedObjects=[FakeEnt("IfcWall", GlobalId="w9")])]))
check("a self-referencing chain terminates instead of hanging the scan",
      looped["w9"][0]["code"] == "X")

# --- 8. an empty model ------------------------------------------------------------------------------------
empty = ca.propose([], "masterformat", {})
check("no elements is not a crash", empty["total"] == 0 and empty["classified_pct"] is None)
check("  and the headline says so", "no elements" in empty["headline"])

print()
if FAILED:
    print(f"classify_assist: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("classify_assist: all checks passed")
