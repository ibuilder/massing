"""PIPELINE-SCALES — the drawing pipeline survives an EMPTY model and keeps identity at size.

Most drawing tests here build one small fixture and assert one engine against it. Two failure
classes slip through that shape, and this repo has been bitten by both:

1. **The zero case.** An empty or near-empty model reaches every engine eventually — a fresh
   project, a failed import, a storey nobody has drawn on yet. `bake` returning nothing, or a
   `np.vstack` over an empty list, raises where a user expects an empty drawing. A blank model is
   not an error state; it is the state every project starts in.

2. **A fixture too small to be wrong.** `fixture-too-small-manufactures-numbers` records a check
   that produced a confident 6.44% which became 0.92% at real scale. A pipeline verified only on
   two walls can hide anything that degrades with element count — and identity is exactly such a
   property, because a mis-indexed field only collides once there are enough elements to collide.

So this walks ONE model per scale through the whole chain — bake → cut → guided cut → plan/section/
elevation SVG — and asserts at each size that every polyline's GlobalId **resolves in the model**.
That last assertion is the one worth the runtime: `cut_baked_guided` returning the right SHAPE with
a shifted field would pass a length check and fail this.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_pipeline_scales.py
"""
from __future__ import annotations

import os
import sys

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import drawings, edit, massing  # noqa: E402
from aec_data.ifc_loader import open_model  # noqa: E402

FAILED: list[str] = []


def check(label: str, ok: bool, detail: object = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail != "" else ""))
    if not ok:
        FAILED.append(label)


def build(tag: str, storeys: int, partitions: int, ground: float) -> str:
    """A closed wall rectangle plus `partitions` interior walls, so plans have real linework."""
    path = os.path.join(os.path.dirname(__file__), f"_pipescale_{tag}.ifc")
    massing.generate_blank_ifc(path, name=f"Scale {tag}", storeys=storeys,
                               storey_height=3.5, ground_size=ground)
    m = open_model(path)
    st = m.by_type("IfcBuildingStorey")[0].Name
    span = ground * 0.6
    ring = [(2, 2), (2 + span, 2), (2 + span, 2 + span), (2, 2 + span), (2, 2)]
    for i in range(len(ring) - 1):
        edit.add_wall(m, list(ring[i]), list(ring[i + 1]), 3.0, 0.2, st)
    for k in range(partitions):
        y = 2 + span * (k + 1) / (partitions + 1)
        edit.add_wall(m, [2, y], [2 + span, y], 3.0, 0.15, st)
    m.write(path)
    return path


def walk(tag: str, storeys: int, partitions: int, ground: float, *, empty: bool = False) -> None:
    print(f"\n--- {tag} ---")
    if empty:
        path = os.path.join(os.path.dirname(__file__), f"_pipescale_{tag}.ifc")
        massing.generate_blank_ifc(path, name="Empty", storeys=1, storey_height=3.5, ground_size=20.0)
    else:
        path = build(tag, storeys, partitions, ground)
    model = open_model(path)

    meshes = drawings.bake(model)
    check(f"{tag}: bake returns a list", isinstance(meshes, list), f"n={len(meshes)}")
    check(f"{tag}: world_bounds does not raise on this model",
          drawings.world_bounds(model) is not None or len(meshes) == 0)
    levels = drawings.storey_elevations(model)
    check(f"{tag}: storey_elevations found the levels", len(levels) == storeys, len(levels))

    guided = drawings.cut_baked_guided(meshes, "plan", 1.5)
    plain = drawings.cut_baked(meshes, "plan", 1.5)
    check(f"{tag}: guided and plain cuts agree on polyline count",
          len(guided) == len(plain), (len(guided), len(plain)))

    # THE assertion this file exists for: identity survives at every size.
    def _resolves(g: str) -> bool:
        try:
            return model.by_guid(g) is not None       # by_guid RAISES on an unknown id
        except Exception:                              # noqa: BLE001 — unresolvable IS the finding
            return False

    bad = [g for g, _c, _p in guided if not _resolves(g)]
    check(f"{tag}: EVERY polyline guid resolves in the model", not bad, bad[:4])

    svg = drawings.plan_svg(model, 0.0, cut_height=1.5)
    # Valid SVG, not a specific prolog. **The empty model renders through a DIFFERENT path** —
    # `plan_drawing_svg` short-circuits to `to_svg([], subtitle="no geometry")` when there is no
    # linework, no below-cut depth and no grid — and that helper emits a bare `<svg xmlns=…>` while
    # the populated path emits `<?xml …?><svg …>`. Both are valid and both render; asserting the
    # prolog here failed the empty case on a difference that is not the contract. Recorded rather
    # than silenced: the two documents are built by two independent writers, which is the shape that
    # lets them drift apart on something that DOES matter.
    check(f"{tag}: plan_svg renders valid SVG", isinstance(svg, str) and "<svg" in svg, len(svg))
    # An empty model draws an empty plan; a populated one must tag its linework.
    check(f"{tag}: plan_svg tags linework when there IS linework",
          (svg.count('data-guid=') > 0) == (len(guided) > 0),
          (svg.count('data-guid='), len(guided)))
    check(f"{tag}: by_discipline renders too — identity is not mode-dependent",
          isinstance(drawings.plan_svg(model, 0.0, cut_height=1.5, by_discipline=True), str))
    check(f"{tag}: section_svg renders",
          isinstance(drawings.section_svg(model, "ns", None, "SECTION"), str))
    # NOTE the sibling asymmetry — plan/section take a MODEL, elevation takes baked MESHES plus a
    # required levels + title. A sweep script calling it like its siblings reported a false break.
    check(f"{tag}: elevation_svg renders",
          isinstance(drawings.elevation_svg(meshes, "north", levels, "NORTH"), str))

    os.remove(path)


walk("empty", storeys=1, partitions=0, ground=20.0, empty=True)
walk("small", storeys=1, partitions=2, ground=20.0)
walk("medium", storeys=3, partitions=10, ground=40.0)
walk("large", storeys=8, partitions=26, ground=60.0)

print()
if FAILED:
    print(f"pipeline_scales: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("pipeline_scales: the drawing pipeline survives an empty model and keeps GlobalId identity "
      "at 1, 3 and 8 storeys — every emitted polyline resolves to a real element at every size.")
