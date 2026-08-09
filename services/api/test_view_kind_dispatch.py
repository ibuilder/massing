"""A sheet asked for an axonometric must draw one — and an unknown kind must refuse, not substitute.

THE DEFECT, MEASURED 2026-08-09 (ADR-001)
-----------------------------------------
Two composers exist. `sheet_layout.compose_viewports()` handled `kind: "axon"`; the shipping path —
`sheet()` -> `compose()` -> `_view_for_spec()`, which every sheet route uses — did not. The axon
branch sat in the WRAPPER, one level above the shared helper, and `_view_for_spec` ended in an
unconditional fall-through to plan::

    spec kind='plan'   ->  label='PLAN'      sub='cut @ 1.20 m'
    spec kind='axon'   ->  label='ISO VIEW'  sub='cut @ 1.20 m'     <- a PLAN, titled ISO VIEW

The title comes from the caller, so the sheet said one thing and drew another — on a document an
engineer may seal. Not a missing feature: a wrong drawing that looks entirely deliberate.

WHAT THESE TESTS PIN
--------------------
1. `axon` resolves through the SHIPPING path, not just through `compose_viewports`. Asserting it via
   `compose_viewports` would have passed throughout the defect, because that path always worked.
2. An unknown kind RAISES. The fall-through is how a typo became a plan; a refusal makes a caller
   bug visible at the caller.
3. The twin: `plan` still works. A refusal test with no twin passes on a function that refuses
   everything.
4. Both dispatchers agree on the set of kinds — the divergence is the root cause, so it is asserted
   directly rather than left to be rediscovered.
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "data", "src"))

import trimesh  # noqa: E402

from aec_data import drawings, sheet_layout  # noqa: E402


def _meshes():
    m = trimesh.creation.box(extents=(4.0, 1.0, 3.0))
    m.apply_translation((0.0, 0.0, 1.5))
    return [("1P2m3n4o5p6q7r8s9t0uvw", "IfcWall", m)]


def test_axon_resolves_through_the_shipping_dispatcher() -> None:
    polys, label, sub = drawings._view_for_spec(_meshes(), {"kind": "axon", "title": "ISO VIEW"})
    assert "cut @" not in sub, (
        f"the shared dispatcher returned a PLAN for an axon spec (sub={sub!r}) — the exact defect: "
        f"a sheet that says ISO VIEW and draws a plan")
    assert "NTS" in sub, f"an axonometric has no paper scale and must say so; got sub={sub!r}"
    assert label == "ISO VIEW", "the caller's title must survive"
    assert polys, "an axonometric of a solid box must produce silhouette geometry"
    print(f"PASS  axon resolves through the shipping dispatcher   sub={sub!r}, {len(polys)} outline(s)")


def test_an_unknown_kind_raises_instead_of_drawing_a_plan() -> None:
    for bad in ("axonometric", "isometric", "3d", "AXON", "", "perspective"):
        try:
            drawings._view_for_spec(_meshes(), {"kind": bad, "title": "X"})
        except ValueError as e:
            assert "unknown view kind" in str(e)
            continue
        raise AssertionError(
            f"kind={bad!r} was accepted and silently drew something. Substituting a plan for an "
            f"unrecognised kind is what made a wrong drawing look deliberate.")
    print("PASS  an unknown kind refuses   6 near-misses rejected, including case and empty")


def test_the_known_kinds_still_work() -> None:
    """The twin. Without it, 'raise on everything' would pass the refusal test above."""
    meshes = _meshes()
    for spec, expect in (
        ({"kind": "plan"}, "cut @"),
        ({"kind": "section", "axis": "x", "offset": 0.0}, "X="),
        ({"kind": "elevation", "direction": "north"}, "elev"),
        ({"kind": "axon"}, "NTS"),
    ):
        _polys, _label, sub = drawings._view_for_spec(meshes, spec)
        assert expect in sub, f"{spec['kind']}: expected {expect!r} in sub, got {sub!r}"
    # and the default (no kind at all) is still a plan, which existing callers rely on
    _p, _l, sub = drawings._view_for_spec(meshes, {})
    assert "cut @" in sub, "a spec with no kind must still default to a plan"
    print(f"PASS  every declared kind resolves, and a bare spec is still a plan   "
          f"{len(drawings.VIEW_KINDS)} kinds")


def test_both_composers_agree_on_the_set_of_kinds() -> None:
    """The root cause, asserted directly.

    ADR-001's finding was not that axon was missing — it was that two dispatchers disagreed about
    which kinds exist, and only one of them was on the shipping path. A kind that resolves through
    `_view_polys` but not `_view_for_spec` is invisible to every sheet route, which is precisely how
    this shipped.
    """
    meshes = _meshes()
    for kind in drawings.VIEW_KINDS:
        spec = {"kind": kind}
        if kind == "section":
            spec |= {"axis": "x", "offset": 0.0}
        shared = drawings._view_for_spec(meshes, spec)[2]
        wrapper = sheet_layout._view_polys(meshes, dict(spec))[2]
        assert shared == wrapper, (
            f"kind={kind!r} resolves differently in the two dispatchers:\n"
            f"  _view_for_spec -> {shared!r}\n  _view_polys    -> {wrapper!r}\n"
            f"They must agree, or a sheet route and a viewport route draw different things for the "
            f"same spec.")
    # and the wrapper must refuse what the shared helper refuses
    try:
        sheet_layout._view_polys(meshes, {"kind": "nonsense"})
    except ValueError:
        pass
    else:
        raise AssertionError("the wrapper accepted a kind the shared dispatcher refuses")
    print(f"PASS  both dispatchers agree on all {len(drawings.VIEW_KINDS)} kinds, and both refuse "
          f"the unknown")


def test_the_class_frozen_axon_still_filters() -> None:
    """`sheet_layout` keeps ONE axon branch — the class-frozen one, which is its own feature.

    Delegating that too would have silently dropped the per-viewport class freeze for axonometrics,
    trading one wrong drawing for another.
    """
    m = trimesh.creation.box(extents=(2.0, 2.0, 2.0))
    meshes = [("1P2m3n4o5p6q7r8s9t0uvw", "IfcWall", m),
              ("0A1b2C3d4E5f6G7h8I9j0K", "IfcSlab", m.copy())]
    everything = sheet_layout._view_polys(meshes, {"kind": "axon"})[0]
    walls_only = sheet_layout._view_polys(meshes, {"kind": "axon", "classes": ["IfcWall"]})[0]
    assert len(walls_only) < len(everything), (
        f"the class freeze did not filter an axonometric: {len(walls_only)} vs {len(everything)} "
        f"outlines — a 'structure only' viewport would silently show everything")
    print(f"PASS  the class-frozen axon still filters   {len(walls_only)} of {len(everything)} outlines")

# --- the `views=` grammar (R36 print slice, ADR-001 item 2) ----------------------------------------

def test_the_views_grammar_round_trips_every_kind() -> None:
    """A sheet stays a linkable URL, so the view list is a compact string rather than a POST body."""
    got = drawings.parse_views("plan@0,plan@3.5,section:x@12.5,elevation:north,axon,axon@30x20")
    assert [s["kind"] for s in got] == ["plan", "plan", "section", "elevation", "axon", "axon"]
    assert got[1]["elevation"] == 3.5
    assert got[2] == {"kind": "section", "axis": "x", "offset": 12.5}
    assert got[3] == {"kind": "elevation", "direction": "north"}
    assert got[4] == {"kind": "axon"}, "a bare axon must carry no angles, so the isometric default wins"
    assert got[5]["azimuth"] == 30.0 and got[5]["elevation_angle"] == 20.0
    print(f"PASS  the views grammar parses every kind, in order   {len(got)} viewports")


def test_every_parsed_spec_is_one_the_dispatcher_accepts() -> None:
    """The grammar and the dispatcher must not drift.

    A parser that emits a spec `_view_for_spec` refuses would turn a caller's valid-looking URL into
    a 500 at render time — the failure moved, not removed. Asserted by actually resolving each.
    """
    meshes = _meshes()
    for spec in drawings.parse_views("plan,plan@2,section:x@0,section:y@1,elevation:south,axon,axon@45x35"):
        _polys, _label, sub = drawings._view_for_spec(meshes, spec)
        assert sub, f"the dispatcher produced no sub-label for a parsed spec: {spec}"
    print("PASS  every spec the grammar emits, the dispatcher resolves   7 checked")


def test_a_malformed_view_refuses_and_names_the_token() -> None:
    """Refuse, never drop. A sheet quietly missing a view is wrong in the one way nobody checks —
    nothing on the page says a viewport was requested and skipped."""
    for bad, expect in (
        ("perspective", "unknown view kind"),
        ("plan@abc", "plan@abc"),
        ("section:z@1", "x or y"),
        ("elevation:up", "north/south/east/west"),
        ("axon@30", "azimuth x elevation"),
        ("", "parsed to nothing"),
        ("plan,,nonsense", "unknown view kind"),
    ):
        try:
            drawings.parse_views(bad)
        except ValueError as e:
            assert expect in str(e), f"{bad!r}: message {str(e)!r} does not mention {expect!r}"
            continue
        raise AssertionError(f"{bad!r} was accepted; a bad view must refuse, not silently vanish")
    print("PASS  a malformed view refuses and names the offending token   7 rejected")


def test_a_blank_views_argument_is_not_the_same_as_omitting_it() -> None:
    """The twin, and the distinction the route depends on.

    `views=` empty means the caller asked for views and got the grammar wrong; omitting `views`
    means they want the default sheet. Collapsing the two would silently serve a default sheet to
    someone whose URL was broken.
    """
    try:
        drawings.parse_views("")
    except ValueError:
        pass
    else:
        raise AssertionError("an explicitly blank views= must refuse, not fall back to the default")
    # and the route's own guard is `if not views:` — so None takes the default path, unparsed
    assert drawings.parse_views("plan"), "a single valid view must parse"
    print("PASS  blank views= refuses; omitting it is the caller's other, valid choice")


if __name__ == "__main__":
    test_axon_resolves_through_the_shipping_dispatcher()
    test_an_unknown_kind_raises_instead_of_drawing_a_plan()
    test_the_known_kinds_still_work()
    test_both_composers_agree_on_the_set_of_kinds()
    test_the_class_frozen_axon_still_filters()
    test_the_views_grammar_round_trips_every_kind()
    test_every_parsed_spec_is_one_the_dispatcher_accepts()
    test_a_malformed_view_refuses_and_names_the_token()
    test_a_blank_views_argument_is_not_the_same_as_omitting_it()
    print("test_view_kind_dispatch OK")
