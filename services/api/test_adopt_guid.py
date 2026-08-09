"""The preview and the commit must produce the SAME element, not two elements that look alike.

THE DEFECT, MEASURED. `edit_preview` authors the requested element a second time into a throwaway
one-storey model, purely to get fast geometry back. Both runs mint their own GlobalId, so the shape
the viewer displayed and the element that landed in the real IFC were different elements. Verified
against a live project on 2026-08-09 — same recipe, same params, run back to back::

    preview   header X-Element-Guid : 33a6Uiew11Mv_Pc4qvizwA
    committed /edit  "changed"      : 0POIcNSNv2lh4Acrld7xm4
    the preview GUID in /elements   : False

That was survivable while the preview fragment was thrown away on commit — the wrong GUID lived for
about a second. **R42-COMMIT-DELTA keeps the fragment**, so the mismatch stopped being a window and
became a standing condition: the user's newly drawn wall was on screen carrying a GlobalId that
exists in no index, so selection, the properties panel, LOD, QTO and pins would all miss the one
element they had just created — until they pressed Rebuild.

The roadmap anticipated an index-timing hazard here and it was right that there was one. It did not
anticipate this, because this is not about timing at all: reindexing forever would never have fixed
an identity that was wrong from the start.

WHY THE REFUSALS GET MORE TESTS THAN THE HAPPY PATH. A GlobalId is the join key for the entire
platform — pins, RFIs, clashes, cost, the 4D binding. A function that rewrites one has to be far more
willing to refuse than to guess: adopting an id that is already in the model would silently fuse two
elements into one for every downstream reader, which is worse than the bug being fixed.
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "data", "src"))

import ifcopenshell
import ifcopenshell.api

from aec_data import edit  # noqa: E402

_A = "1P2m3n4o5p6q7r8s9t0uvw"          # well-formed IFC GlobalIds (22 chars of the base64 alphabet)
_B = "0A1b2C3d4E5f6G7h8I9j0K"


def _model():
    m = ifcopenshell.api.run("project.create_file")
    ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcProject", name="P")
    return m


def _wall(m, name="W"):
    return ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcWall", name=name)


def test_adopts_the_requested_guid() -> None:
    m = _model()
    w = _wall(m)
    got = edit.adopt_guid(m, w.GlobalId, _A)
    assert got == _A, "adopt_guid must report the id actually in force, not the one requested"
    assert w.GlobalId == _A
    print("PASS  the created element takes the preview's GlobalId   the two are now one element")


def test_no_want_guid_is_a_no_op() -> None:
    # Every existing caller passes nothing. The old behaviour has to be exactly preserved, or this
    # fix becomes a change to all 96 recipes rather than to one path.
    m = _model()
    w = _wall(m)
    before = w.GlobalId
    assert edit.adopt_guid(m, before, "") == before
    assert edit.adopt_guid(m, before, None) == before   # type: ignore[arg-type]
    assert w.GlobalId == before
    print("PASS  absent want_guid changes nothing   the pre-existing path is untouched")


def test_refuses_a_guid_already_in_the_model() -> None:
    # THE DANGEROUS ONE. Two elements sharing a GlobalId is not a cosmetic problem: every join in the
    # platform is keyed on it, so the pins, cost lines and clashes of one element would silently
    # attach to the other. Refusing loudly is the only safe answer.
    m = _model()
    taken = _wall(m, "existing")
    taken.GlobalId = _A
    w = _wall(m, "new")
    try:
        edit.adopt_guid(m, w.GlobalId, _A)
        raise AssertionError("adopting an id already in the model must raise, not create a duplicate")
    except ValueError as e:
        assert "already used" in str(e)
    assert w.GlobalId != _A, "and the model must be left untouched by the refusal"
    assert taken.GlobalId == _A
    print("PASS  refuses a GlobalId already in the model   duplicates would fuse two elements")


def test_refuses_a_malformed_guid() -> None:
    # An IFC GlobalId is exactly 22 chars of a specific alphabet. Writing junk here produces a file
    # that other tools reject on read — a corruption that surfaces far from its cause.
    m = _model()
    w = _wall(m)
    for bad in ("", "short", "x" * 23, "has spaces in it 12345", "bad/chars+here========"):
        if bad == "":
            continue                                  # the empty string is the documented no-op
        try:
            edit.adopt_guid(m, w.GlobalId, bad)
            raise AssertionError(f"malformed id accepted: {bad!r}")
        except ValueError:
            pass
    print("PASS  refuses a malformed GlobalId   22 chars of the IFC alphabet, or nothing")


def test_refuses_when_the_recipe_did_not_create_exactly_one_element() -> None:
    # Recipes that report a COUNT (batch_tag, set_pset over a selection) have no single element to
    # re-key. Picking one arbitrarily would re-key the wrong element and look like it worked.
    m = _model()
    _wall(m)
    for changed in (7, None, ["a", "b"], "not-a-guid"):
        try:
            edit.adopt_guid(m, changed, _A)           # type: ignore[arg-type]
            raise AssertionError(f"accepted a non-single-element result: {changed!r}")
        except ValueError as e:
            assert "exactly one element" in str(e) or "well-formed" in str(e)
    print("PASS  refuses when the recipe made a count, not an element   no arbitrary re-keying")


def test_refuses_when_the_reported_element_is_not_in_the_model() -> None:
    """The twin of the happy path: a `changed` GUID nothing in the model carries.

    Without this, a recipe whose reported id drifted from what it actually created would fall through
    silently — adopt_guid would find nothing, change nothing, and return as if it had worked.
    """
    m = _model()
    _wall(m)
    try:
        edit.adopt_guid(m, _B, _A)                    # _B is well-formed but belongs to nothing
        raise AssertionError("must raise when the reported element cannot be found")
    except ValueError as e:
        assert "no element" in str(e)
    print("PASS  refuses when the reported element is not in the model   a silent no-op would lie")


def test_end_to_end_through_apply_recipe() -> None:
    """The whole point, through the real entry point: author twice, get ONE identity.

    This is the assertion that would have caught the live defect. It exercises `apply_recipe` — the
    function the route calls — rather than the helper alone, because the defect was never in the
    helper: it was that nothing connected the two runs at all.
    """
    with tempfile.TemporaryDirectory() as td:
        base = os.path.join(td, "base.ifc")
        m = _model()
        ifcopenshell.api.run("unit.assign_unit", m,
                             units=[m.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE")])
        ifcopenshell.api.run("context.add_context", m, context_type="Model")
        site = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcSite", name="S")
        bldg = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcBuilding", name="B")
        st = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcBuildingStorey", name="L1")
        st.Elevation = 0.0
        proj = m.by_type("IfcProject")[0]
        ifcopenshell.api.run("aggregate.assign_object", m, products=[site], relating_object=proj)
        ifcopenshell.api.run("aggregate.assign_object", m, products=[bldg], relating_object=site)
        ifcopenshell.api.run("aggregate.assign_object", m, products=[st], relating_object=bldg)
        m.write(base)

        out1 = os.path.join(td, "free.ifc")
        r1 = edit.apply_recipe(base, "add_wall", {"start": [0, 0], "end": [4, 0], "height": 3}, out1)
        minted = r1["changed"]

        # Now author the SAME wall again, from the same base, asking it to adopt the first id — this
        # is exactly what the preview/commit pair does.
        out2 = os.path.join(td, "adopted.ifc")
        r2 = edit.apply_recipe(base, "add_wall", {"start": [0, 0], "end": [4, 0], "height": 3}, out2,
                               want_guid=minted)
        assert r2["changed"] == minted, (
            f"the commit reported {r2['changed']!r} but was asked to adopt {minted!r} — the client "
            f"would key its kept fragment on an id the model does not have")

        # And it is really on disk, not just in the returned dict: a reader that never saw the return
        # value has to find the element by that id. Asserted against a reader we did not write.
        reread = ifcopenshell.open(out2)
        assert any(w.GlobalId == minted for w in reread.by_type("IfcWall")), \
            "the adopted GlobalId did not survive the write"
        print(f"PASS  two independent authoring runs produce ONE identity   {minted}")


if __name__ == "__main__":
    test_adopts_the_requested_guid()
    test_no_want_guid_is_a_no_op()
    test_refuses_a_guid_already_in_the_model()
    test_refuses_a_malformed_guid()
    test_refuses_when_the_recipe_did_not_create_exactly_one_element()
    test_refuses_when_the_reported_element_is_not_in_the_model()
    test_end_to_end_through_apply_recipe()
    print("test_adopt_guid OK")
