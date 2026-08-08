"""LOD-ELEMENT-TABLE — a target you can address to an element, and an assessment that compares them.

THE DEFECT THIS EXISTS FOR. `lod_target` records carried `{element_category, discipline, phase,
target_lod}` and `element_category` is **free text**, so no target could be joined to an element.
`assess()` returned the authored targets and the achieved distribution side by side and never put
them together. A team could author "curtain wall reaches LOD 350 at CD", press assess, and be handed
a distribution that cannot answer the question they asked. The matrix was authorable and
uncomparable.

WHY MOST-SPECIFIC-WINS IS THE WHOLE POINT. One target per stage cannot say that at Construction Docs
a curtain wall is expected at 350 while an interior partition is expected at 300 — it makes one of
them wrong whichever number is chosen. Targets are therefore addressable by IFC class, by Uniformat
code, or by discipline, and the narrowest matching rule decides.

NOTHING FROM THE BIMForum TABLE IS SHIPPED. Part II is CC BY-NC and states its own rows are
"examples ... intended to be customized by the user". The platform provides the structure; every
row below is a fixture, not content.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_lod_element_table.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_lod_element_table.db"
os.environ["STORAGE_DIR"] = "./test_storage_lodelemtable"
for _f in ("./test_lod_element_table.db",):
    if os.path.exists(_f):
        os.remove(_f)

from aec_api import lod  # noqa: E402

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail and not ok else ''}")
    if not ok:
        failures.append(name)


CD = "Construction Docs"


def t(**kw):
    base = {"element_category": "", "discipline": "", "ifc_class": "", "uniformat": "",
            "phase": CD, "target_lod": "LOD 300"}
    base.update(kw)
    return base


def el(ifc_class, classification=None, reps=("Brep",)):
    return {"ifc_class": ifc_class, "classification": classification,
            "rep_types": list(reps), "placed": True, "has_material": True,
            "psets": {}, "qtos": {}}


# ---- resolution order: the narrowest matching rule decides -------------------------------------
TARGETS = [
    t(discipline="Architectural", target_lod="LOD 200", element_category="Arch default"),
    t(uniformat="B2010", target_lod="LOD 300", element_category="Exterior walls"),
    t(ifc_class="IfcCurtainWall", target_lod="LOD 350", element_category="Curtain wall"),
]
cw = el("IfcCurtainWall", "B2010.10")
check("an IFC-class rule beats a Uniformat rule and a discipline rule",
      (lod.target_for(cw, TARGETS, CD) or {}).get("target_lod") == "LOD 350",
      str(lod.target_for(cw, TARGETS, CD)))
wall = el("IfcWall", "B2010.20")
check("...and a Uniformat rule beats a discipline rule",
      (lod.target_for(wall, TARGETS, CD) or {}).get("target_lod") == "LOD 300",
      str(lod.target_for(wall, TARGETS, CD)))
# A Uniformat target is matched by PREFIX — B2010 covers B2010.10, which is how the classification
# tree is meant to read. Exact-only matching would silently skip every element carrying a more
# precise code than the rule was written at, and report them as untargeted.
check("...and the Uniformat match is a PREFIX, not an equality",
      (lod.target_for(el("IfcSlab", "B2010.99.7"), TARGETS, CD) or {}).get("target_lod") == "LOD 300",
      str(lod.target_for(el("IfcSlab", "B2010.99.7"), TARGETS, CD)))

# The twin for every "wins" claim: with the narrow rules removed, the broad one applies. Without
# this the assertions above pass against a resolver that only ever returns the last rule it saw.
only_disc = [TARGETS[0]]
check("removing the narrow rules falls back to the discipline rule",
      (lod.target_for(cw, only_disc, CD) or {}).get("target_lod") == "LOD 200",
      str(lod.target_for(cw, only_disc, CD)))

# ---- a rule belongs to ITS stage ---------------------------------------------------------------
check("a target authored for another stage does not apply",
      lod.target_for(cw, TARGETS, "Concept / SD") is None,
      str(lod.target_for(cw, TARGETS, "Concept / SD")))
check("...and an element no rule addresses has no target",
      lod.target_for(el("IfcPipeSegment", "D2020"), [TARGETS[1], TARGETS[2]], CD) is None)

# ---- compliance: achieved vs target, per stage --------------------------------------------------
# `assess` needs a DB session for the register, so the comparison is exercised through the same
# helper it uses. A Brep reaches LOD 350; a BoundingBox reaches LOD 200.
idx = {
    "a": el("IfcCurtainWall", "B2010.10"),                       # 350 achieved, 350 target -> met
    "b": el("IfcCurtainWall", "B2010.10", reps=("BoundingBox",)),  # 200 achieved, 350 target -> short
    "c": el("IfcWall", "B2010.20"),                              # 350 achieved, 300 target -> met
    "d": el("IfcPipeSegment", "D2020"),                          # no rule addresses it
}
met = short = untargeted = 0
worst: dict[str, int] = {}
for e in idx.values():
    tgt = lod.target_for(e, TARGETS, CD)
    if not tgt:
        untargeted += 1
        continue
    if lod._LOD_RANK[lod.achieved_lod(e)] >= lod._LOD_RANK[tgt["target_lod"]]:
        met += 1
    else:
        short += 1
        worst[tgt["element_category"]] = worst.get(tgt["element_category"], 0) + 1

check("two elements meet their target and one is short", (met, short) == (2, 1), f"{met}/{short}")
check("...and the short one is attributed to the RULE that decided, not to 'target'",
      worst == {"Curtain wall": 1}, str(worst))
# An element no rule addresses must NOT be counted as compliant. A model element table covering a
# third of the model and reporting 100% is the failure this item exists to remove.
check("an unaddressed element is reported as untargeted, never as passing",
      untargeted == 1, str(untargeted))

# The pipe segment IS addressable once a rule is written for it — proving the previous assertion is
# about the absence of a rule and not about that element being unmatchable.
with_pipe = [*TARGETS, t(discipline="Plumbing", target_lod="LOD 300", element_category="Plumbing")]
pipe_t = lod.target_for(el("IfcPipeSegment", "D2020"), with_pipe, CD)
check("...and writing a rule for it makes it targeted",
      pipe_t is not None and pipe_t["target_lod"] == "LOD 300", str(pipe_t))

# ---- the register must actually CARRY the addressing fields ------------------------------------
# `matrix()` projects the register into the list `target_for` reads. A field the register accepts
# and the projection drops is a field a user can fill in that nothing uses — which is precisely the
# state this item found the whole matrix in.
import json  # noqa: E402

mod = json.load(open("modules/lod_target/module.json", encoding="utf-8"))
names = [f["name"] for f in mod["fields"]]
check("the lod_target register offers ifc_class and uniformat",
      "ifc_class" in names and "uniformat" in names, str(names))
src = open("src/aec_api/lod.py", encoding="utf-8").read()
proj = src.split("def matrix(", 1)[1].split("return {", 1)[0]
check("...and matrix() projects BOTH of them through to the resolver",
      '"ifc_class"' in proj and '"uniformat"' in proj,
      "matrix() drops a field the register accepts")

print(f"\ntest_lod_element_table {'OK' if not failures else 'FAILED: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
