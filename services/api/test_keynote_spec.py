"""R36-VIEWER-SUBAPP — a section keynote names the spec section that governs it.

A keynote says what an assembly IS: `200mm MASONRY WALL`, composed from the element's class, its
material and its measured thickness. The spec section says what GOVERNS it. Nothing joined the two,
so a reader holding a section had to know the mapping by heart — which is the gap this closes:

    before:   200mm MASONRY WALL
    after:    04 22 00  200mm MASONRY WALL

## Why unanimity, and why that is the interesting half

The keynote group is formed by `(class, material, rounded thickness)` — deliberately, so a wall cut
at eight storeys is one keynote rather than eight. **That partition is not the spec partition.** Two
walls can be identical in class, material and thickness and still be specified apart: an interior
partition and a fire-rated shaft wall of the same build-up. They land in one group here.

So a group cites a section only when **every** member agrees, and an unclassified member counts as a
disagreement — "I do not know about this one" cannot license a claim about it. A keynote printing a
section that governs only some of the elements it points at is **a false statement on a construction
document**, and it is worse than no citation at all, because a drawing is read as authored.

## What made this reachable

`section_drawing_svg` cut with `cut_baked_classed`, which keeps the IFC class and throws the GlobalId
away — so the frame that builds keynotes had no identity to look anything up by. `cut_baked_guided`
already existed and carries `(guid, class, polyline)`; the section path now uses it. It also ACCOUNTS
for meshes that fail to section, where the classed variant drops them silently.

Run: cd services/api && PYTHONPATH=src:../data/src ./.venv/bin/python test_keynote_spec.py
"""
import os
import re
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import ifcopenshell  # noqa: E402

from aec_data import drawings, edit, massing, specmanual  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAILED.append(name)


def classify(model, guids: list[str], code: str, title: str) -> None:
    """Attach one MasterFormat code to the named elements."""
    cl = model.create_entity("IfcClassification", Source="CSI", Edition="2020", Name="MasterFormat")
    ref = model.create_entity("IfcClassificationReference", Identification=code, Name=title,
                              ReferencedSource=cl)
    model.create_entity("IfcRelAssociatesClassification", GlobalId=ifcopenshell.guid.new(),
                        RelatingClassification=ref, RelatedObjects=[model.by_guid(g) for g in guids])


def keynotes_in(svg: str) -> list[str]:
    """The keynote column's label texts."""
    return [t.strip() for t in re.findall(r"<text[^>]*>([^<]*)</text>", svg) if t.strip()]


#: The cut plane. `section-y` cuts on a plane of constant y, so both walls must SPAN y=3 to be
#: caught by it — see the guard below, which is there because the first draft of this file used two
#: walls meeting at a corner and no single cut crossed both.
CUT_AXIS, CUT_OFFSET = "y", 3.0


def build(tmp: str):
    """Two PARALLEL walls of identical class, material and thickness, both crossed by the cut.

    Parallel and both spanning the cut plane, which is the part that matters: identical build-ups put
    them in ONE keynote group, and being in one group is what exercises the unanimity rule. Two walls
    meeting at a corner look equivalent and are not — a plane of constant y crosses only one of them,
    so every group would have a single member and the disagreement case could never arise.
    """
    if os.path.exists(tmp):
        os.remove(tmp)
    massing.generate_blank_ifc(tmp, name="Keynote Spec", storeys=1, storey_height=3.0, ground_size=20.0)
    m = open_model(tmp)
    st = m.by_type("IfcBuildingStorey")[0].Name
    a = edit.add_wall(m, [0, 0], [0, 6], 3.0, 0.2, st)
    b = edit.add_wall(m, [4, 0], [4, 6], 3.0, 0.2, st)
    return m, a, b


def section(model) -> str:
    return drawings.section_svg(model, CUT_AXIS, CUT_OFFSET, title="S", keynotes=True)


TMP = os.path.join(os.path.dirname(__file__), "_keynote_spec_test.ifc")
try:
    # ---- the fixture really does group the two walls together ------------------------------------
    # Anti-vacuity: if they landed in two groups, the disagreement case below would pass for the
    # wrong reason — each keynote would cite its own code and never exercise the rule at all.
    m, a, b = build(TMP)
    # THE guard. "One keynote text" alone is satisfied by one wall just as well as by two grouped
    # together, and the first draft of this file passed on exactly that — a cut that crossed only one
    # of the two walls, so the disagreement case below asserted nothing and reported a pass. Count
    # the ELEMENTS the cut actually caught, not the labels it drew.
    cut = drawings.cut_baked_guided(drawings.bake(m),
                                    "section-y" if CUT_AXIS == "y" else "section-x", CUT_OFFSET)
    caught = {g for g, _cls, _p in cut}
    check("the cut really crosses BOTH walls — else every group has one member and proves nothing",
          a in caught and b in caught, f"a={a in caught} b={b in caught} of {len(caught)} elements")

    plain = keynotes_in(section(m))
    walls = [t for t in plain if "WALL" in t]
    check("...and the two walls form ONE keynote group, so the unanimity rule is exercised",
          len(walls) == 1, f"{walls}")
    check("...and that keynote carries no code before anything is classified",
          bool(walls) and not re.match(r"^\d\d ", walls[0]), f"{walls}")

    # ---- both walls in the SAME section: the keynote cites it -------------------------------------
    m, a, b = build(TMP)
    classify(m, [a, b], "04 22 00", "Concrete Unit Masonry")
    codes = specmanual.element_codes(m)
    check("element_codes maps both walls by GlobalId", codes.get(a) == codes.get(b) == "04 22 00",
          f"{codes}")

    agreed = [t for t in keynotes_in(section(m))
              if "WALL" in t]
    check("a unanimous group cites its spec section",
          bool(agreed) and agreed[0].startswith("04 22 00"), f"{agreed}")
    check("...and still says what the assembly IS, rather than replacing it with a code",
          bool(agreed) and "WALL" in agreed[0] and "200mm" in agreed[0], f"{agreed}")

    # ---- the walls specified APART: the keynote must cite NEITHER ----------------------------------
    # The whole point. These two are indistinguishable to the grouping key, so without the unanimity
    # rule the group would print whichever code happened to win — a section governing one of the two
    # elements the leader points at, asserted about both.
    m, a, b = build(TMP)
    classify(m, [a], "04 22 00", "Concrete Unit Masonry")
    classify(m, [b], "09 21 16", "Gypsum Board Assemblies")
    split = [t for t in keynotes_in(section(m))
             if "WALL" in t]
    check("a group whose members are specified APART cites neither",
          bool(split) and "04 22 00" not in split[0] and "09 21 16" not in split[0], f"{split}")
    check("...and the keynote is still drawn, just without a citation",
          bool(split) and "WALL" in split[0], f"{split}")

    # ---- one classified, one not: also a disagreement -----------------------------------------------
    m, a, b = build(TMP)
    classify(m, [a], "04 22 00", "Concrete Unit Masonry")
    partial = [t for t in keynotes_in(section(m))
               if "WALL" in t]
    check("an UNCLASSIFIED member is a disagreement too — no citation is made",
          bool(partial) and "04 22 00" not in partial[0], f"{partial}")

    # ---- a model with no classifications at all draws exactly as before -----------------------------
    m, a, b = build(TMP)
    check("an unclassified model still renders its section",
          "<svg" in section(m))
finally:
    if os.path.exists(TMP):
        os.remove(TMP)

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("KEYNOTE SPEC OK - a section keynote cites the spec section governing it, resolved by GlobalId "
      "through the guid-carrying cut. A group cites only when every member agrees: walls specified "
      "apart, or one unclassified, produce the keynote with no citation rather than a section "
      "asserted about elements it does not govern.")
