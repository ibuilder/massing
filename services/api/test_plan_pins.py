"""
Issue pins must reach the generated sheet.

Found by the live house test: an anchored RFI showed correctly in `GET /pins` and rendered nothing on
`plan.svg`. The route had no `pins` parameter at all, so `?pins=1` was silently ignored by FastAPI —
the request looked accepted and the sheet came back complete-looking and wrong. That is the shape of
failure this codebase keeps finding: not an error, just a drawing that quietly omits the thing you
raised.
"""
import sys

sys.path.insert(0, "src")
sys.path.insert(0, "../data/src")

from aec_data.drawings import _pin_layer  # noqa: E402

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


# The plan's world→sheet transform, simplified: 10 px per metre, y flipped.
MN, MX = (0.0, 0.0), (12.0, 8.0)


def T(x, y):
    return 50 + x * 10.0, 50 + 80.0 - y * 10.0


# --- the thing that was broken -------------------------------------------------------------------
svg = _pin_layer([{"x": 4.5, "y": 0.0, "kind": "rfi", "label": "Window head height"}], T, MN, MX)
check("a pin renders at all", 'id="pins"' in svg)
check("its label reaches the sheet", "Window head height" in svg)
check("an RFI is drawn in the RFI colour", "#b45309" in svg)
check("it is numbered so the sheet reads against a list", ">1</text>" in svg)

# --- no pins is not an empty layer, it is no layer ------------------------------------------------
check("no pins draws nothing", _pin_layer([], T, MN, MX) == "")
check("None draws nothing", _pin_layer(None, T, MN, MX) == "")

# --- the two refusals that make the sheet honest ---------------------------------------------------
off = _pin_layer([{"x": 99.0, "y": 99.0, "kind": "punch", "label": "Off sheet"}], T, MN, MX)
check("an off-extent pin is still DRAWN, not dropped", 'id="pins"' in off and "Off sheet" in off,
      "silently dropping it makes a sheet that looks complete and is not")
check("  ...and is marked as off-sheet rather than mislocated", ">^</text>" in off)

un = _pin_layer([{"x": None, "y": None, "kind": "rfi", "label": "Nowhere"}], T, MN, MX)
check("a pin with no position is COUNTED, not invented", "not located on this sheet" in un,
      "the sheet says how many it could not place")

# --- ordering: numbering follows the order given, so it matches an issue list ----------------------
two = _pin_layer([{"x": 1.0, "y": 1.0, "kind": "rfi", "label": "A"},
                  {"x": 2.0, "y": 2.0, "kind": "clash", "label": "B"}], T, MN, MX)
check("multiple pins number in order", ">1</text>" in two and ">2</text>" in two)
check("each kind keeps its own colour", "#b45309" in two and "#7c3aed" in two)

# --- an unknown kind must not vanish ----------------------------------------------------------------
unk = _pin_layer([{"x": 1.0, "y": 1.0, "kind": "something-new", "label": "X"}], T, MN, MX)
check("an unknown kind draws grey rather than disappearing", "#6b7280" in unk,
      "an unrendered pin is an issue nobody closes")

# --- labels are user text going into an XML document ------------------------------------------------
xss = _pin_layer([{"x": 1.0, "y": 1.0, "kind": "rfi",
                   "label": '</text><script>alert(1)</script>'}], T, MN, MX)
check("a label cannot break out of the SVG", "<script>" not in xss and "&lt;script&gt;" in xss)
amp = _pin_layer([{"x": 1.0, "y": 1.0, "kind": "rfi", "label": "M&E coordination"}], T, MN, MX)
check("a bare & does not corrupt the document", "&amp;" in amp and "M&E" not in amp)

print()
if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_plan_pins OK")
