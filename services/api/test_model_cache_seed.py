"""R42-SESSION-MODEL — an edit hands its post-write model to the cache, so the next edit re-uses it.

THE GAP THIS CLOSES, and it was hiding inside a correct comment. `open_model` has been cached by
`(path, mtime, size)` since it shipped — right, because a rewritten file must never be served stale.
But **every authoring edit writes a NEW timestamped file**, so the next edit's key differs and the
cache misses BY CONSTRUCTION. `open_model`'s own docstring says *"The /edit path already writes a new
timestamped file, so it was never affected"* — written as a reassurance about staleness, and it is
simultaneously the diagnosis: the authoring loop, the one path that edits the same model over and
over, could never hit the cache.

That makes this the fourth instance in two days of one shape: a mechanism that exists, is correct,
and is bypassed on the path that needs it — after the `lod_target` fields, the `modelVersions` review
keys, and the `/publish` `reconvert` flag.

WHY SEEDING IS NOT A GUESS. The model handed to the cache is the object that was just `write()`n, so
it IS the content of that path. `lru_cache` cannot express this: it populates only by calling the
function it wraps — i.e. by re-reading a file whose answer is already in memory.

WHAT THIS TEST ASSERTS. Not "the code runs" — that a PARSE WAS AVOIDED, by counting calls to
`ifcopenshell.open`. A cache test that does not count the expensive thing is measuring nothing, and
would pass just as well against a cache that never hits.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_model_cache_seed.py
"""
import os
import sys
import tempfile

os.environ["DATABASE_URL"] = "sqlite:///./test_model_cache_seed.db"
os.environ["STORAGE_DIR"] = "./test_storage_modelcacheseed"
for _f in ("./test_model_cache_seed.db",):
    if os.path.exists(_f):
        os.remove(_f)

from pathlib import Path  # noqa: E402
from unittest import mock  # noqa: E402

import ifcopenshell  # noqa: E402

from aec_data import edit, ifc_loader  # noqa: E402

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail and not ok else ''}")
    if not ok:
        failures.append(name)


TD = tempfile.mkdtemp(prefix="seedcache_")


def new_model(path: str):
    """A minimal but REAL IFC on disk — the cache keys on stat, so it must actually exist."""
    m = ifcopenshell.file(schema="IFC4")
    m.createIfcProject(ifcopenshell.guid.new(), Name="Seed Test")
    m.write(path)
    return m


base = str(Path(TD) / "base.ifc")
new_model(base)

# Counting the real parser. `_open_uncached` is the only path to it, so wrapping the module-level
# `ifcopenshell.open` counts exactly the work the cache exists to avoid.
parses: list[str] = []
_real_open = ifcopenshell.open


def counting_open(path, *a, **k):
    parses.append(str(path))
    return _real_open(path, *a, **k)


# ---- 1. a cold open parses; a repeat of the SAME file does not --------------------------------
ifc_loader._open_cached.cache_clear()
with mock.patch.object(ifcopenshell, "open", counting_open):
    ifc_loader.open_model(base)
    n_cold = len(parses)
    ifc_loader.open_model(base)
    n_warm = len(parses)
check("a cold open parses the file", n_cold == 1, f"{n_cold} parse(s)")
check("...and re-opening the same file does not parse again", n_warm == 1, f"{n_warm} parse(s)")

# ---- 2. THE POINT: a written file is served from the seed, without parsing ---------------------
# This is the authoring loop in miniature — write a NEW path, then open it, which is exactly what
# the next edit does.
out = str(Path(TD) / "after_edit.ifc")
ifc_loader._open_cached.cache_clear()
parses.clear()
with mock.patch.object(ifcopenshell, "open", counting_open):
    m = ifc_loader.open_model(base)          # 1 parse
    m.write(out)
    seeded = ifc_loader.seed_model_cache(out, m)
    after_seed = len(parses)
    got = ifc_loader.open_model(out)         # must NOT parse
    after_open = len(parses)
check("the seed is accepted for a file that exists", seeded is True)
check("seeding does not itself parse", after_seed == 1, f"{after_seed} parse(s)")
check("opening the written file is served from the seed — NO parse",
      after_open == 1, f"{after_open} parse(s) — the seed did not take")
check("...and it returns the very object that was written",
      got is m, "a different object means the cache answered from somewhere else")
# The twin. Without it, "no parse" is equally consistent with a cache that returns a stale entry for
# every key, which would be a correctness disaster wearing a performance win's clothes.
other = str(Path(TD) / "unseeded.ifc")
new_model(other)
with mock.patch.object(ifcopenshell, "open", counting_open):
    ifc_loader.open_model(other)
check("...while an UNSEEDED file still parses normally", len(parses) == 2, f"{len(parses)} parse(s)")

# ---- 3. a seed that cannot be keyed is DROPPED, never stored under a guess ---------------------
check("seeding a non-existent path is refused",
      ifc_loader.seed_model_cache(str(Path(TD) / "nope.ifc"), m) is False)

# ---- 4. the content stamp follows the model to its new home ------------------------------------
# A reader touching the seeded object before the next `open_model` would otherwise see the PREVIOUS
# version's key on post-edit geometry — the quiet mismatch derived caches get built on.
check("the seeded model carries the NEW file's content key",
      getattr(m, "__aec_content_key__", "").startswith(os.path.abspath(out)),
      getattr(m, "__aec_content_key__", "(unset)"))

# ---- 5. the real seam: apply_recipe seeds what it wrote ----------------------------------------
ifc_loader._open_cached.cache_clear()
parses.clear()
edited = str(Path(TD) / "edited.ifc")
with mock.patch.object(ifcopenshell, "open", counting_open):
    edit.apply_recipe(base, "add_storey", {"name": "L01", "elevation": 0.0}, edited)
    n_after_edit = len(parses)
    ifc_loader.open_model(edited)
    n_after_reopen = len(parses)
check("apply_recipe parses its input once", n_after_edit == 1, f"{n_after_edit} parse(s)")
check("...and its OUTPUT opens without a parse — the authoring loop now hits the cache",
      n_after_reopen == 1, f"{n_after_reopen} parse(s) — apply_recipe did not seed")

# ---- 6. eviction still bounds the cache --------------------------------------------------------
# The seed adds an entry per edit; unbounded growth on a long authoring session would trade a parse
# for a leak, which is not a trade worth making.
ifc_loader._open_cached.cache_clear()
for i in range(12):
    p = str(Path(TD) / f"bulk{i}.ifc")
    ifc_loader.seed_model_cache(p, m) if Path(p).exists() else ifc_loader.seed_model_cache(
        (new_model(p), p)[1], m)
info = ifc_loader._open_cached.cache_info()
check("the cache stays bounded after many seeds",
      info["size"] <= info["maxsize"], str(info))

print(f"\ntest_model_cache_seed {'OK' if not failures else 'FAILED: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
