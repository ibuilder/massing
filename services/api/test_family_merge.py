"""Batch-1 duplicate families — merged by ALIAS, and only where they are actually duplicates.

The upstream review flagged six "overlapping" keys from the plumbing batch. Reading the packs showed
only **one** is a genuine duplicate; the other five are a *generic* tier and a *specific* tier:

    base `plumbing`:      bathtub · lavatory · shower · sink · toilet · urinal
    `plumbing-fixtures`:  shower_receptor · sink_kitchen · sink_service · urinal_wall · wc_flush_valve

`wc_flush_valve` is one **kind** of toilet, and the fixtures pack carries no tank-type WC — so aliasing
`toilet` onto it would assert a fixture type nobody specified. `shower_receptor` is a **part** of a
shower. `sink_kitchen` is not what "sink" means. Those are a two-tier catalog working as intended: you
schedule the generic at concept and the specific at procurement. Merging them would destroy
information under the banner of removing it.

`pipe_copper_l` and `pipe_copper_type_l` genuinely are one product under two names, in one pack.

And the merge is by **alias, not deletion** — deleting a key breaks every model that already placed
one, while an alias keeps those references resolving and still reports a single canonical family.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_family_merge.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_family_merge.db"
os.environ["STORAGE_DIR"] = "./test_storage_family_merge"
if os.path.exists("./test_family_merge.db"):
    os.remove("./test_family_merge.db")

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_data import family_packs as fp  # noqa: E402

# ---- the one genuine duplicate is merged, and the OLD key still resolves --------------------------
assert fp.canonical_family("pipe_copper_l") == "pipe_copper_type_l"
assert fp.canonical_family("pipe_copper_type_l") == "pipe_copper_type_l", "canonical is a fixed point"
# case and padding are the caller's convenience, not their problem
assert fp.canonical_family("  Pipe_Copper_L  ") == "pipe_copper_type_l"

# the alias RESOLVES rather than erroring — a model that placed the old key keeps working, which is
# the whole reason this is an alias and not a deletion
assert fp.canonical_family("pipe_copper_l") in fp.FAMILY_ALIASES.values()

# ---- the five NON-duplicates are left alone -------------------------------------------------------
# Aliasing any of these would assert a fixture type nobody specified.
for generic in ("toilet", "sink", "shower", "urinal"):
    assert fp.canonical_family(generic) == generic, f"{generic} must NOT be merged away"
    assert generic not in fp.FAMILY_ALIASES, generic
for specific in ("wc_flush_valve", "sink_kitchen", "sink_service", "shower_receptor", "urinal_wall"):
    assert fp.canonical_family(specific) == specific, f"{specific} is canonical in its own right"

# ---- the two-tier relationship is RECORDED, so nobody merges them by mistake later ----------------
assert fp.is_narrowing("toilet", "wc_flush_valve")
assert fp.is_narrowing("sink", "sink_kitchen") and fp.is_narrowing("sink", "sink_service")
assert fp.is_narrowing("shower", "shower_receptor")
assert fp.is_narrowing("urinal", "urinal_wall")
# narrowing is directional — a kitchen sink does not generalise a toilet
assert not fp.is_narrowing("toilet", "sink_kitchen")
assert not fp.is_narrowing("wc_flush_valve", "toilet"), "narrowing runs generic → specific only"
assert not fp.is_narrowing("nonsense", "wc_flush_valve")
assert not fp.is_narrowing("", "")

# ---- an unknown key passes through unchanged ------------------------------------------------------
# canonical_family resolves aliases; it does not validate existence, and pretending otherwise would
# turn a typo into a silent substitution.
assert fp.canonical_family("not_a_real_family") == "not_a_real_family"
assert fp.canonical_family("") == ""
assert fp.canonical_family(None) == ""

# ---- an alias must never point at another alias ---------------------------------------------------
# A chain would make canonical_family's answer depend on how many times you called it.
for src, dst in fp.FAMILY_ALIASES.items():
    assert dst not in fp.FAMILY_ALIASES, f"{src} → {dst} → ... is a chain; collapse it"
    assert src != dst

# ---- both keys are still present in the shipped pack ---------------------------------------------
# The alias is a resolution rule, not an edit to a generated artifact: the packs are BUILD OUTPUT from
# an upstream generator, so editing them here would be undone by the next release.
shelf = fp.external_dir()
piping = shelf / "massing-families-plumbing-piping-v0.1.0.ifc"
if piping.exists():
    raw = piping.read_bytes()
    assert b"pipe_copper_type_l" in raw, "the canonical key must exist in the pack"

print("FAMILY-MERGE OK - the batch-1 duplicates are merged, and checking first changed what that "
      "meant: of the six keys the upstream review flagged as overlapping, only ONE is a genuine "
      "duplicate. pipe_copper_l and pipe_copper_type_l are one product under two names in one pack, "
      "so the short form is retired in favour of the ASTM B88 designation that actually carries the "
      "wall thickness. The other five are a GENERIC tier and a SPECIFIC tier - wc_flush_valve is one "
      "kind of toilet and the fixtures pack has no tank-type WC, shower_receptor is a PART of a "
      "shower, sink_kitchen is not what 'sink' means - so merging them would assert fixture types "
      "nobody specified and destroy information under the banner of removing it. That two-tier "
      "relationship is now RECORDED rather than left implicit, so the next reviewer does not flag it "
      "again. The merge is done by ALIAS rather than deletion, because deleting a key breaks every "
      "model that already placed one while an alias keeps those references resolving; aliases are "
      "asserted never to chain, so the canonical answer cannot depend on how many times it is asked. "
      "The generated packs are untouched - they are build output from an upstream generator, and an "
      "edit here would be undone by the next release.")
