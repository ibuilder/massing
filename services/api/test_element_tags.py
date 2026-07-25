"""R21-TAGS — element tags, and the placement that makes them readable.

`space_tags` already labels rooms, but rooms are large and far apart. Element tags are the hard case
because doors and windows cluster, so the real problem is not what a tag says — it is **placement**.
Two tags on one baseline are worse than one tag, because a reader cannot tell which element either
belongs to, and the drawing now asserts something false rather than merely saying less.

The rule under test: a tag prefers to sit on its element; when that spot is taken it is displaced,
and displacement is exactly what earns it a leader. A leader on an undisplaced tag is noise; a
displaced tag with no leader is a number nobody can attribute to anything.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_element_tags.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_element_tags.db"
os.environ["STORAGE_DIR"] = "./test_storage_element_tags"
if os.path.exists("./test_element_tags.db"):
    os.remove("./test_element_tags.db")

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import drawings as d  # noqa: E402


def boxes_overlap(a, b):
    return (abs(a["x"] - b["x"]) < d.TAG_W + d.TAG_GAP
            and abs(a["y"] - b["y"]) < d.TAG_H + d.TAG_GAP)


# ---- an isolated tag sits ON its element, and needs no leader -----------------------------------
solo = d.place_tags([(100.0, 100.0, "D1")])
assert len(solo) == 1
assert solo[0]["x"] == 100.0 and solo[0]["y"] == 100.0, solo
assert solo[0]["leader"] is False, "a tag on its own element must not draw a pointless leader"
assert solo[0]["text"] == "D1"

# ---- THE RULE: clustered tags never overlap, and every displaced one gets a leader ---------------
# five doors within a few millimetres of each other on the sheet — the case that breaks naive tagging
cluster = d.place_tags([(200.0, 200.0, f"D{i}") for i in range(5)])
assert len(cluster) == 5
for i, a in enumerate(cluster):
    for b in cluster[i + 1:]:
        assert not boxes_overlap(a, b), (a, b)
# the first keeps the anchor; the rest moved, and each of those carries a leader
assert cluster[0]["leader"] is False
assert all(t["leader"] for t in cluster[1:]), cluster
for t in cluster[1:]:
    assert (t["x"], t["y"]) != tuple(t["anchor"]), t
# every tag keeps its own anchor, so a leader points at the right element
assert [t["anchor"] for t in cluster] == [[200.0, 200.0]] * 5

# ---- more elements than the ring has slots: still no overlaps, still nothing dropped -------------
dense = d.place_tags([(300.0, 300.0, f"W{i}") for i in range(25)])
assert len(dense) == 25, "a silently omitted tag is an element that merely LOOKS untagged"
for i, a in enumerate(dense):
    for b in dense[i + 1:]:
        assert not boxes_overlap(a, b), (i, a, b)
assert sum(1 for t in dense if t["leader"]) == 24

# ---- determinism: a drawing that shuffles between runs cannot be diffed or checked ---------------
anchors = [(10.0 * i, 20.0, f"T{i}") for i in range(12)] + [(55.0, 20.0, "X")]
assert d.place_tags(anchors) == d.place_tags(anchors)

# ---- the cap is honoured, and taking the first N is stated rather than silent --------------------
many = d.place_tags([(5.0 * i, 5.0 * i, str(i)) for i in range(50)], max_tags=10)
assert len(many) == 10
assert [t["text"] for t in many] == [str(i) for i in range(10)]
assert d.place_tags([]) == []

# ---- SVG: a leader is drawn if and only if the tag was displaced ---------------------------------
svg_solo = d.tag_svg(solo)
assert "<rect" in svg_solo and "D1" in svg_solo
assert "<line" not in svg_solo, "no displacement → no leader line"
svg_cluster = d.tag_svg(cluster)
assert svg_cluster.count("<line") == 4, svg_cluster.count("<line")
assert svg_cluster.count("<rect") == 5
assert svg_cluster.count("<circle") == 4, "each leader terminates in a dot on its element"

# tag text comes from model data and is therefore untrusted
bad = d.tag_svg([{"x": 0, "y": 0, "anchor": [0, 0], "text": '<script>&', "leader": False}])
assert "<script>" not in bad and "&lt;script&gt;" in bad, bad

# ---- a tag carrying a dimension is the common real case -----------------------------------------
dim = d.place_tags([(50.0, 50.0, "D2  900 x 2100")])
assert "900 x 2100" in d.tag_svg(dim)

# ---- R21-BREAKLINE: a view that stops mid-element says so ----------------------------------------
# Without the mark, a partial view is indistinguishable from a complete one — the same class of error
# as a clash report that does not say which pairs it tested.
bl = d.break_line(0.0, 100.0, 220.0, 100.0)
assert bl.startswith("<polyline") and "points=" in bl
pts = [p.split(",") for p in bl.split('points="')[1].split('"')[0].split()]
xs = [float(a) for a, _ in pts]
ys = [float(b) for _, b in pts]
assert xs[0] == 0.0 and xs[-1] == 220.0, (xs[0], xs[-1])
assert ys[0] == 100.0 and ys[-1] == 100.0
# it actually zigs: some vertex leaves the run by the amplitude, on BOTH sides
assert max(ys) > 100.0 and min(ys) < 100.0, (min(ys), max(ys))
assert abs(max(ys) - 100.0 - d.BREAK_AMPLITUDE) < 0.51, max(ys)

# a vertical run zigs horizontally — the zig is normal to the run, not to the page
vert = d.break_line(50.0, 0.0, 50.0, 200.0)
vxs = [float(p.split(",")[0]) for p in vert.split('points="')[1].split('"')[0].split()]
assert max(vxs) > 50.0 and min(vxs) < 50.0, (min(vxs), max(vxs))

# a short run still produces a mark — a break line that vanished because the view was narrow would
# silently turn a partial view back into an apparently complete one
short = d.break_line(0.0, 0.0, 8.0, 0.0)
assert short.startswith("<polyline"), short
# ...but a zero-length run is not a break at all
assert d.break_line(10.0, 10.0, 10.0, 10.0) == ""

print("R21-TAGS + R21-BREAKLINE OK - element tags now place themselves without landing on top of one another, which "
      "is the whole difficulty: `space_tags` already labelled rooms, but rooms are large and far "
      "apart while doors and windows cluster, and two tags sharing a baseline are worse than one tag "
      "because the drawing then asserts something a reader cannot attribute. A tag prefers to sit ON "
      "its element and is displaced to the nearest free slot only when that spot is taken - and "
      "displacement is precisely what earns it a leader, since a leader on an undisplaced tag is "
      "noise while a displaced tag without one is an unattributable number. When every candidate "
      "slot is occupied the tag is pushed clear rather than dropped, because a silently omitted tag "
      "is an element that merely LOOKS untagged. Placement is deterministic, so the same plan tags "
      "identically on every run and a drawing can actually be diffed. BREAK LINES close the "
      "companion gap: a detail running to the sheet edge tells a reader nothing about whether the "
      "element stops there or continues for thirty metres, so a partial view was indistinguishable "
      "from a complete one - the same class of error as a clash report that never says which pairs "
      "it tested. The zig is normal to the run rather than to the page, so a vertical break reads "
      "correctly, and a short run still produces a mark instead of vanishing.")
