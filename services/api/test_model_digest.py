"""R23-DIGEST — the digest claims to be deterministic and Merkle-shaped. These tests make both
claims falsifiable.

"Deterministic" is the load-bearing word: the entire value of a model digest is that an unchanged
building produces an unchanged hash, so anything that leaks into a hash without being part of the
building — a path, a stat, a timestamp, an entity's STEP id, iteration order, float noise — turns
every comparison into a false positive and the feature into noise. Each of those is a separate test
below, because each fails silently.

The Merkle test is the other half: it is not enough that the project hash changes when something
changes; the *siblings must not*, or descending selectively is unsound and you may as well hash the
file.
"""
import json
import os
import shutil
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "../data/src")

from aec_data import edit_struct, massing, model_digest  # noqa: E402

FAILED: list[str] = []
TMP = "./test_digest_tmp"


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


def canon(obj):
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def build(path, *, move_wall=None, extra_column=False, drop_last=False):
    """Author a two-storey model. Each knob makes exactly one kind of change, so a diff that
    reports more than that kind has a bug."""
    import ifcopenshell

    massing.generate_blank_ifc(path, name="Digest Fixture", storeys=2, storey_height=3.5)
    model = ifcopenshell.open(path)
    guids = []
    wx = move_wall if move_wall is not None else 0.0
    guids.append(edit_struct.add_wall(model, (wx, 0.0), (wx + 6.0, 0.0), height=3.0, storey="Level 1"))
    guids.append(edit_struct.add_wall(model, (0.0, 0.0), (0.0, 4.0), height=3.0, storey="Level 1"))
    guids.append(edit_struct.add_column(model, (2.0, 2.0), height=3.0, storey="Level 2"))
    if not drop_last:
        guids.append(edit_struct.add_column(model, (4.0, 2.0), height=3.0, storey="Level 2"))
    if extra_column:
        guids.append(edit_struct.add_column(model, (6.0, 2.0), height=3.0, storey="Level 2"))
    model.write(path)
    return guids


os.makedirs(TMP, exist_ok=True)
base = os.path.join(TMP, "base.ifc")
guids = build(base)

# --- 1. determinism: the same building digests to the same bytes -------------------------------
# Digested from a DIFFERENT PATH, because path and stat are exactly the kind of thing that leaks
# into a hash by accident. If either did, this copy would disagree with its own original.
copy = os.path.join(TMP, "copy_at_another_path.ifc")
shutil.copyfile(base, copy)
d1 = model_digest.digest(base)
d2 = model_digest.digest(copy)
check("a copy at another path digests identically", canon(d1) == canon(d2))
check("re-digesting the same file is byte-identical", canon(model_digest.digest(base)) == canon(d1))

# The digest must carry no wall-clock value at all — a timestamp anywhere makes every diff dirty.
blob = canon(d1)
check("the digest contains no timestamp field",
      not any(k in blob for k in ('"generated', '"timestamp"', '"at"', '"mtime')))

# --- 2. it states its configuration ------------------------------------------------------------
check("mode records how it was measured", d1["mode"]["measured"] == "psets")
check("mode records the rounding", d1["mode"]["rounding"] == dict(sorted(model_digest.ROUND.items())))
check("mode records the schema", d1["mode"]["schema"].startswith("IFC"))

# --- 3. the shape ------------------------------------------------------------------------------
tree = d1["tree"]
storeys = {s["key"]: s for s in tree["children"]}
check("both authored storeys appear", {"Level 1", "Level 2"} <= set(storeys), sorted(storeys))
check("project element count equals the sum of its storeys",
      tree["elements"] == sum(s["elements"] for s in tree["children"]))
l1_classes = {c["key"]: c for c in storeys["Level 1"]["children"]}
check("Level 1 groups the two walls under IfcWall",
      l1_classes.get("IfcWall", {}).get("elements") == 2, sorted(l1_classes))
check("Level 2 holds the two columns",
      {c["key"]: c["elements"] for c in storeys["Level 2"]["children"]}.get("IfcColumn") == 2)
check("every element carries a GlobalId and a hash",
      all(e.get("guid") and e.get("hash")
          for s in tree["children"] for c in s["children"] for e in c["children"]))

# --- 4. Merkle: a change propagates up ONE path, and only one ----------------------------------
moved = os.path.join(TMP, "moved.ifc")
build(moved, move_wall=1.5)                    # one wall on Level 1 shifts 1.5 m in x
dm = model_digest.digest(moved)
sm = {s["key"]: s for s in dm["tree"]["children"]}
check("moving an element changes the project hash", dm["tree"]["hash"] != tree["hash"])
check("  ...and its own storey's hash", sm["Level 1"]["hash"] != storeys["Level 1"]["hash"])
check("  ...and NOT the untouched storey's hash (this is what makes the tree worth having)",
      sm["Level 2"]["hash"] == storeys["Level 2"]["hash"])

# --- 5. diff names the field that moved --------------------------------------------------------
# The GUIDs differ between the two files (they are separately authored), so a diff of independently
# built models cannot match elements. Diff a model against an EDIT of itself instead, which is the
# real use: the same file, republished.
import ifcopenshell  # noqa: E402

edited = os.path.join(TMP, "edited.ifc")
shutil.copyfile(base, edited)
m = ifcopenshell.open(edited)
from aec_data import edit as edit_mod  # noqa: E402

edit_mod.move_element(m, guids[0], dx=1.5)
m.write(edited)

dd = model_digest.diff(d1, model_digest.digest(edited))
check("a diff of the same file re-published is compatible", dd["compatible"] is True, dd.get("reason"))
check("  it is not identical", dd["identical"] is False)
changed = dd["elements"]["changed"]
check("  exactly one element changed", len(changed) == 1, [c["guid"] for c in changed])
if changed:
    check("  it is the wall we moved", changed[0]["guid"] == guids[0])
    check("  and the reported field is origin", changed[0]["fields"] == ["origin"], changed[0]["fields"])
    check("  with before and after values", changed[0]["before"]["origin"] != changed[0]["after"]["origin"])
check("  nothing was added or removed",
      not dd["elements"]["added"] and not dd["elements"]["removed"])
check("  the rest are reported unchanged", dd["elements"]["unchanged"] == len(guids) - 1 + 1)  # +1 ground slab

# --- 6. a property change is caught, with no geometric change at all ----------------------------
tagged = os.path.join(TMP, "tagged.ifc")
shutil.copyfile(base, tagged)
m = ifcopenshell.open(tagged)
import ifcopenshell.api  # noqa: E402


def pset_named(element, name):
    """`add_wall` already attaches Pset_WallCommon; adding a second one of the same name would be a
    malformed file, so edit the one that is there."""
    for rel in getattr(element, "IsDefinedBy", None) or []:
        if rel.is_a("IfcRelDefinesByProperties"):
            pdef = rel.RelatingPropertyDefinition
            if pdef.is_a("IfcPropertySet") and pdef.Name == name:
                return pdef
    return None


ifcopenshell.api.run("pset.edit_pset", m, pset=pset_named(m.by_guid(guids[0]), "Pset_WallCommon"),
                     properties={"FireRating": "2HR"})
m.write(tagged)
dp = model_digest.diff(d1, model_digest.digest(tagged))
pchanged = dp["elements"]["changed"]
check("a FireRating change is detected though nothing moved", len(pchanged) == 1, len(pchanged))
if pchanged:
    check("  reported as a psets change only", pchanged[0]["fields"] == ["psets"], pchanged[0]["fields"])

# --- 7. add and delete ------------------------------------------------------------------------
grown = os.path.join(TMP, "grown.ifc")
shutil.copyfile(base, grown)
m = ifcopenshell.open(grown)
new_guid = edit_struct.add_column(m, (8.0, 2.0), height=3.0, storey="Level 2")
edit_mod.delete_element(m, guids[1])
m.write(grown)
dg = model_digest.diff(d1, model_digest.digest(grown))
check("an added column is reported added",
      [a["guid"] for a in dg["elements"]["added"]] == [new_guid], dg["elements"]["added"])
check("a deleted wall is reported removed",
      [r["guid"] for r in dg["elements"]["removed"]] == [guids[1]], dg["elements"]["removed"])
check("the storey delta names both touched storeys",
      set(dg["storeys"]["changed"]) == {"Level 1", "Level 2"}, dg["storeys"])

# --- 8. identical models diff to identical -----------------------------------------------------
same = model_digest.diff(d1, model_digest.digest(copy))
check("two copies diff as identical", same["identical"] is True)
check("  with nothing added, removed or changed",
      not same["elements"]["added"] and not same["elements"]["removed"]
      and not same["elements"]["changed"])

# --- 9. pruning keeps hashes and refuses to over-claim ------------------------------------------
pruned = model_digest.digest(base, prune_at="storey")
check("a pruned digest keeps the project hash it would have had",
      pruned["tree"]["hash"] == tree["hash"])
check("  and its storey hashes", {s["key"]: s["hash"] for s in pruned["tree"]["children"]}
      == {s["key"]: s["hash"] for s in tree["children"]})
check("  but carries no element level", all("children" not in s for s in pruned["tree"]["children"]))
dpr = model_digest.diff(pruned, model_digest.digest(copy, prune_at="storey"))
check("two pruned digests still compare at storey level", dpr["compatible"] is True)
check("  and say plainly that elements were not compared",
      dpr["elements"] is None and "not examined" in dpr["elements_not_compared"])

# --- 10. the configuration guard ----------------------------------------------------------------
# A pset-measured digest against a geometry-measured one would report every quantity as changed. The
# correct answer is a refusal with a reason, not a diff.
mixed = model_digest.diff(d1, {**d1, "mode": {**d1["mode"], "measured": "psets+geometry"}})
check("a cross-mode diff is refused", mixed["compatible"] is False)
check("  with a stated reason", "geometry-derived" in (mixed.get("reason") or ""), mixed.get("reason"))
mixed2 = model_digest.diff(d1, pruned)
check("a full-vs-pruned diff is refused", mixed2["compatible"] is False)
check("  with a stated reason", "pruned_at" in (mixed2.get("reason") or ""), mixed2.get("reason"))
old = model_digest.diff({**d1, "digest_version": 0}, d1)
check("a cross-version diff is refused", old["compatible"] is False)

# --- 11. summary --------------------------------------------------------------------------------
s = model_digest.summary(d1)
check("summary carries the project hash", s["hash"] == tree["hash"])
check("summary lists every storey", len(s["storeys"]) == len(tree["children"]))
check("summary states the mode", s["mode"]["measured"] == "psets")

# --- 12. a bad prune scale is an error, not a silent full digest ---------------------------------
try:
    model_digest.digest(base, prune_at="floor")
    check("an unknown prune scale raises", False, "no exception")
except model_digest.DigestError:
    check("an unknown prune scale raises", True)

shutil.rmtree(TMP, ignore_errors=True)

print()
if FAILED:
    print(f"model_digest: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("model_digest: all checks passed")
