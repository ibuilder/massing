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

# --- the cap note: a sheet whose pin list was capped upstream must SAY SO -------------------------
# PINS-CAP shipped an honest API and left the paper silent: `resolve_pins` reported `truncated`,
# `_plan_pins` dropped the envelope on the floor, and the sheet printed a confident subset. A
# superintendent works off the printed sheet, so this is the half that reaches the person at risk.
#
# The blocker recorded in the roadmap for this was FALSE — "the drawing engine takes positions and
# labels, not notes" — and the engine had been printing "N pin(s) not located on this sheet" the
# whole time. A blocker nobody re-checked is how a one-line fix stays open.
CAP = {"truncated": True, "shown": 2000, "total": 2400, "approx": False}
capped = _pin_layer([{"x": 1.0, "y": 1.0, "kind": "rfi", "label": "A"}], T, MN, MX, CAP)
check("a capped sheet says the pin list was capped", "Pin list capped at 2000 of 2400" in capped)
check("  ...and warns about THIS sheet without inventing a per-sheet number",
      "may not show every issue on this level" in capped,
      "the cap is spent before the storey filter, so the per-sheet shortfall is unknowable")

# THE MUTATION: a note that prints unconditionally is worse than no note, because it teaches the
# reader to ignore it. An uncapped sheet must be silent.
whole = _pin_layer([{"x": 1.0, "y": 1.0, "kind": "rfi", "label": "A"}], T, MN, MX,
                   {"truncated": False, "shown": 3, "total": 3, "approx": False})
check("an UNCAPPED sheet says nothing about caps", "Pin list capped" not in whole,
      "the honest negative — otherwise the warning is decoration, not information")
check("no cap envelope at all is also silent",
      "Pin list capped" not in _pin_layer([{"x": 1.0, "y": 1.0, "kind": "rfi"}], T, MN, MX))

# An upper-bound total is marked as one. `total_counts_candidates` means legacy `{}`/`[]` rows the
# SQL predicate cannot exclude may be counted, so the number is a ceiling, not a count.
approx = _pin_layer([{"x": 1.0, "y": 1.0, "kind": "rfi"}], T, MN, MX,
                    {"truncated": True, "shown": 2000, "total": 2400, "approx": True})
check("an upper-bound total prints as approximate", "of ~2400 project pins" in approx)

# Both notes at once must not overlay each other — and the cap note is the one that must survive.
both = _pin_layer([{"x": None, "y": None, "kind": "rfi", "label": "Nowhere"}], T, MN, MX, CAP)
check("two notes stack rather than overprinting",
      'y="16"' in both and 'y="29"' in both,
      "one y for both is one unreadable note, and the cap warning is the one that matters")
check("  ...and both are actually present", "not located on this sheet" in both
      and "Pin list capped" in both)

# A cap that empties this storey entirely still prints the warning. This is the blank-overlay case
# from PINS-CAP reaching paper: zero pins on the sheet is exactly when the reader most needs to know
# the list was cut, and `if not pins: return ""` used to swallow it.
empty = _pin_layer([], T, MN, MX, CAP)
check("A CAPPED SHEET WITH NO PINS LEFT STILL WARNS", "Pin list capped" in empty,
      "no pins + no note reads as 'this level is clean', which is the original defect on paper")

# BOTH empty representations, because the guard above distinguishes them and the loop must not.
# Found in review: `[]` fell out of the loop and `None` raised TypeError, so the warning-only layer
# — the one case that reaches the loop with no pins at all — crashed on half its legal inputs.
# `pins` is typed `list[dict] | None`; testing one spelling of "empty" tested half the contract.
none_capped = _pin_layer(None, T, MN, MX, CAP)
check("...and does so for pins=None, not just []", "Pin list capped" in none_capped,
      "a parameter typed `list[dict] | None` has two empty forms and the loop saw only one")

print()
if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_plan_pins OK")
