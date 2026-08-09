"""The model cache must never hand out a model that does not match its own file.

THE DEFECT, REPRODUCED. `open_model` returns a SHARED, MUTABLE `ifcopenshell.file`. `apply_recipe`
opens its input through that cache and then mutates the returned object in place before writing the
result to a *different* path. So the instant an edit finished, the cache entry for its INPUT path
held a model containing the edit — while the file itself did not::

    walls on disk in base .............. 0
    walls via open_model(base) [cached]  1     <-- after one edit that only READ base

Measured 2026-08-09. It was found by accident: a test authored the same wall twice from one base and
the second run refused with "GlobalId already used in this model" — the second `open_model(base)` was
handed the first run's mutated object.

WHY IT MATTERS MORE THAN THE STALENESS THE CACHE WAS BUILT TO AVOID. `open_model` keys on
`(path, mtime, size)` precisely so a rewritten file is never served stale. This hole is the mirror
image and worse: the file is untouched and correct, and the cache serves a *different, newer* model
under its name. Every reader that reopens a prior version is affected — undo/redo restoring an
earlier source, a version-to-version compare, a drawing or export generated from an earlier version,
two edits branching off one base. Each gets a real, fully readable model that is simply not the one
it asked for, with nothing anywhere reporting a problem.

NOT A REGRESSION FROM THE SEEDING WORK. `lru_cache` keyed the same way and had exactly the same hole
since the cache was introduced; R42-SESSION-MODEL only made the authoring loop hit the cache often
enough for it to bite. Stated here because "the last change caused it" is the cheap assumption, and
it is wrong.
"""
from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "data", "src"))

import ifcopenshell
import ifcopenshell.api

from aec_data import edit  # noqa: E402
from aec_data.ifc_loader import evict_model_cache, open_model  # noqa: E402

_WALL = {"start": [0, 0], "end": [4, 0], "height": 3}


def _base(td: str) -> str:
    path = os.path.join(td, "base.ifc")
    m = ifcopenshell.api.run("project.create_file")
    ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcProject", name="P")
    ifcopenshell.api.run("unit.assign_unit", m,
                         units=[m.create_entity("IfcSIUnit", UnitType="LENGTHUNIT", Name="METRE")])
    ifcopenshell.api.run("context.add_context", m, context_type="Model")
    site = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcSite", name="S")
    bldg = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcBuilding", name="B")
    st = ifcopenshell.api.run("root.create_entity", m, ifc_class="IfcBuildingStorey", name="L1")
    st.Elevation = 0.0
    proj = m.by_type("IfcProject")[0]
    for child, parent in ((site, proj), (bldg, site), (st, bldg)):
        ifcopenshell.api.run("aggregate.assign_object", m, products=[child], relating_object=parent)
    m.write(path)
    return path


def test_reading_a_version_after_editing_from_it_gives_the_file_not_the_edit() -> None:
    """The regression, stated as the property rather than as the symptom that exposed it.

    Asserted against a reader we did not write — `ifcopenshell.open` straight off disk — because the
    whole failure is the cache disagreeing with the file. Comparing the cache against itself would
    pass in exactly the broken state.
    """
    with tempfile.TemporaryDirectory() as td:
        base = _base(td)
        on_disk_before = len(ifcopenshell.open(base).by_type("IfcWall"))
        assert on_disk_before == 0

        edit.apply_recipe(base, "add_wall", _WALL, os.path.join(td, "v1.ifc"))

        on_disk = len(ifcopenshell.open(base).by_type("IfcWall"))
        cached = len(open_model(base).by_type("IfcWall"))
        assert on_disk == 0, "the edit must not have touched its input file"
        assert cached == on_disk, (
            f"open_model({base!r}) returned {cached} wall(s) but the file has {on_disk}. The cache is "
            f"serving the NEXT version's content under this version's name — undo, version compare "
            f"and any drawing off an earlier source would all read the wrong model.")
        print("PASS  a version reopened after an edit reads the FILE, not the edit   cache == disk")


def test_two_edits_from_one_base_do_not_see_each_other() -> None:
    """Branching, which is how the defect was actually found.

    Two edits from the same base must produce two independent single-wall models. Under the bug the
    second one inherited the first's wall — and because both runs mint from the same counter it
    surfaced as a GlobalId collision, an error that pointed nowhere near the cache.
    """
    with tempfile.TemporaryDirectory() as td:
        base = _base(td)
        a = os.path.join(td, "a.ifc")
        b = os.path.join(td, "b.ifc")
        edit.apply_recipe(base, "add_wall", _WALL, a)
        edit.apply_recipe(base, "add_wall", {"start": [0, 5], "end": [4, 5], "height": 3}, b)

        na = len(ifcopenshell.open(a).by_type("IfcWall"))
        nb = len(ifcopenshell.open(b).by_type("IfcWall"))
        assert (na, nb) == (1, 1), (
            f"each branch should hold exactly its own wall; got a={na} b={nb}. b={2} means the "
            f"second edit was handed the first edit's mutated model as its input.")
        print("PASS  two edits branching from one base stay independent   1 wall each, not 1 and 2")


def test_the_seeded_output_is_still_a_cache_HIT() -> None:
    """The twin. Eviction must not have undone R42-SESSION-MODEL's whole reason for existing.

    A fix that made every open a miss would 'pass' the two tests above while quietly costing a full
    re-parse per edit — the exact work the seeding was added to remove. So assert the win directly:
    the file an edit just wrote opens without re-reading it.
    """
    with tempfile.TemporaryDirectory() as td:
        base = _base(td)
        out = os.path.join(td, "v1.ifc")
        edit.apply_recipe(base, "add_wall", _WALL, out)

        import aec_data.ifc_loader as loader
        calls = {"n": 0}
        real = loader._open_uncached

        def counting(path):
            calls["n"] += 1
            return real(path)

        loader._open_uncached = counting                    # type: ignore[assignment]
        try:
            got = open_model(out)
            assert len(got.by_type("IfcWall")) == 1
            assert calls["n"] == 0, (
                "the edit's own output had to be re-parsed — the seed is not reaching the cache, "
                "which is the entire point of R42-SESSION-MODEL")
        finally:
            loader._open_uncached = real                    # type: ignore[assignment]
        print("PASS  the edit's OUTPUT is still served from the seed   0 re-parses")


def test_evict_reports_what_it_removed() -> None:
    """A refusal-shaped helper needs its count, or 'it evicted nothing' and 'there was nothing to
    evict' are the same observation — and a no-op eviction is precisely this bug."""
    with tempfile.TemporaryDirectory() as td:
        base = _base(td)
        open_model(base)
        assert evict_model_cache(base) == 1, "the entry that was just created must be found and removed"
        assert evict_model_cache(base) == 0, "and a second eviction must report that nothing was there"
        print("PASS  evict reports how many entries it dropped   1 then 0")


if __name__ == "__main__":
    test_reading_a_version_after_editing_from_it_gives_the_file_not_the_edit()
    test_two_edits_from_one_base_do_not_see_each_other()
    test_the_seeded_output_is_still_a_cache_HIT()
    test_evict_reports_what_it_removed()
    print("test_model_cache_mutation OK")
