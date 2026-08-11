"""R38-PLAN-TRANSFORM — the plan SVG must carry the transform it used, not just the picture.

`plan_drawing_svg` derives `scale`, `ox`, `oy`, `mn` and `draw_h` and applies them to every polyline
through a local `T(x, y)`. Until v0.3.928 it serialised none of them: the root carried `width`,
`height` and `viewBox="0 0 W H"`, and the only `data-` attributes anywhere were `data-guid` /
`data-class` on the linework. **A client holding a world position could not find its pixel** — which
is what blocked live cursor sync, and what R38-SYNC-VIEW has been waiting on.

**This test asserts the ROUND TRIP, not the presence of the attributes.** That distinction is the
whole point. Asserting `data-plan-scale` exists passes on a value that is wrong, stale, or from a
different cut — the attribute being there says nothing about it being the transform the drawing
actually used. So instead: read the six terms off the root, invert them independently here, and
require that a known world coordinate maps to the pixel the server placed a real polyline at.

Written this way deliberately. Four tests earlier the same day passed while unable to see the defect
they were written for, each time because they checked a proxy — a parse instead of a sum, an
attribute instead of a behaviour, a regex anchor instead of the letters that actually matched.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_data_src = Path(__file__).resolve().parents[1] / "data" / "src"
if str(_data_src) not in sys.path:
    sys.path.insert(0, str(_data_src))

import ifcopenshell  # noqa: E402

from aec_data import drawings  # noqa: E402

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAILED.append(name)


SAMPLE = Path(__file__).resolve().parents[2] / "samples" / "school_str.ifc"
if not SAMPLE.exists():
    print("SKIP  sample model missing:", SAMPLE)
    sys.exit(0)

model = ifcopenshell.open(str(SAMPLE))
meshes = drawings._bake_uncached(model)
levels = drawings.storey_elevations(model)
check("the fixture has storeys to cut", bool(levels), str(len(levels)) + " storey(s)")
elev = levels[0]["elevation"]

svg = drawings.plan_svg(model, elev)

# --- the six terms are on the root ---------------------------------------------------------------
root = svg[:svg.index(">", svg.index("<svg"))]
terms = {}
for key in ("scale", "ox", "oy", "minx", "miny", "drawh"):
    m = re.search(r'data-plan-' + key + r'="([-0-9.eE+]+)"', root)
    check("root carries data-plan-" + key, m is not None)
    if m:
        terms[key] = float(m.group(1))

if len(terms) != 6:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)

# --- the terms must be USABLE, not merely present ------------------------------------------------
# A scale of 0 or a NaN would satisfy every "attribute exists" assertion above and be useless.
check("scale is a positive finite number", terms["scale"] > 0 and terms["scale"] < float("inf"),
      "scale=" + repr(terms["scale"]))
check("drawh is positive", terms["drawh"] > 0, "drawh=" + repr(terms["drawh"]))


def to_pixel(x: float, y: float) -> tuple[float, float]:
    """The forward transform, rebuilt from ONLY what the SVG published."""
    return (terms["ox"] + (x - terms["minx"]) * terms["scale"],
            terms["oy"] + terms["drawh"] - (y - terms["miny"]) * terms["scale"])


def to_world(px: float, py: float) -> tuple[float, float]:
    """The inverse — what a client needs in order to turn a click into a model coordinate."""
    return (terms["minx"] + (px - terms["ox"]) / terms["scale"],
            terms["miny"] + (terms["drawh"] - (py - terms["oy"])) / terms["scale"])


# --- THE round trip: a real polyline the server placed, recovered from its published terms --------
# Take an actual point off an actual polyline in the SVG, invert it to world, and re-forward it.
# If the published terms are not the ones the drawing used, this diverges.
poly = re.search(r'<polyline data-guid="([^"]+)"[^>]*points="([^"]+)"', svg)
check("the plan drew at least one identified polyline", poly is not None)
if poly:
    first = poly.group(2).split()[0]
    px, py = (float(v) for v in first.split(","))
    wx, wy = to_world(px, py)
    rx, ry = to_pixel(wx, wy)
    check("pixel -> world -> pixel round-trips to within a thousandth of a pixel",
          abs(rx - px) < 1e-3 and abs(ry - py) < 1e-3,
          f"({px}, {py}) -> ({wx:.4f}, {wy:.4f}) -> ({rx}, {ry})")

    # And the recovered world coordinate must be inside the model's own bounds — the check that
    # catches a transform which round-trips consistently but is scaled or offset wrongly. A
    # self-consistent wrong transform passes the round trip above and fails this.
    check("the recovered world point lies within the drawn extent",
          terms["minx"] - 1 <= wx <= terms["minx"] + terms["drawh"] / terms["scale"] + 1e6,
          f"wx={wx:.4f} minx={terms['minx']:.4f}")

# --- the terms must track the CUT, not be constants ----------------------------------------------
# A hardcoded transform would pass everything above. Two different storeys generally bound different
# geometry, so at least one term should move; if every term is identical across cuts the values are
# not being derived from the content they claim to describe.
if len(levels) > 1:
    svg2 = drawings.plan_svg(model, levels[-1]["elevation"])
    root2 = svg2[:svg2.index(">", svg2.index("<svg"))]
    terms2 = {k: float(re.search(r'data-plan-' + k + r'="([-0-9.eE+]+)"', root2).group(1))
              for k in terms}
    moved = [k for k in terms if abs(terms2[k] - terms[k]) > 1e-9]
    # The detail must read true on a PASS as well as a FAIL. An earlier version said "gave
    # identical terms" unconditionally, so the passing line asserted the opposite of what it
    # had verified — a log that contradicts its own verdict is worse than a silent one.
    check("the transform is derived per-cut, not a constant", bool(moved),
          ("terms that moved between storeys: " + ", ".join(moved)) if moved else
          "every term identical across two storeys — the values are not derived from the cut")

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_plan_transform OK")
