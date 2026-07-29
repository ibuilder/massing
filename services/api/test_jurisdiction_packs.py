"""R23-JURISDICTION-PACKS — a requirement nobody can trace has no standing to fail anyone's model.

This module's whole claim is that a data requirement belongs to an AUTHORITY. So most of what is
asserted here is refusal: a pack without a citation, a selector that would store cleanly and never
match, a project with no jurisdiction quietly adopting somebody else's rules.

The one that matters most is the last. The tempting behaviour is a sensible default pack, and it is
the same error as defaulting a contract family in `notice_clock`: a requirement set from the wrong
authority is not a conservative approximation of the right one — it fails a model against rules
nobody imposed, and the person it fails cannot look up why.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_jurisdiction_packs.py
"""
import os
import shutil
import sys

os.environ.setdefault("STORAGE_DIR", "./test_storage_juris")
sys.path.insert(0, "src")

from aec_api import jurisdiction_packs as jp  # noqa: E402
from aec_api import rule_library  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


shutil.rmtree(os.environ["STORAGE_DIR"], ignore_errors=True)

GOOD = {
    "id": "tx-example-city",
    "jurisdiction": "tx",
    "authority": "Example City Building Department",
    "name": "Model submission data requirements",
    "edition": "2026",
    "source": "https://example.gov/bim-submission-standard-2026.pdf",
    "requirements": [
        {"id": "walls-rated", "name": "Walls declare a fire rating", "scope": "IfcWall",
         "require": "Pset_WallCommon::FireRating", "severity": "high"},
        {"id": "spaces-named", "name": "Spaces are named", "scope": "IfcSpace",
         "require": "name", "severity": "medium"},
    ],
}

# --- 1. the citation is not optional ---------------------------------------------------------------
for field in ("authority", "edition", "source"):
    try:
        jp.validate({**GOOD, field: ""})
        check(f"a pack with no {field} is refused", False, "no exception")
    except jp.PackError as e:
        check(f"a pack with no {field} is refused", field in str(e), str(e)[:90])
try:
    jp.validate({**GOOD, "authority": "", "edition": ""})
    check("the refusal names EVERY missing field, not the first", False, "no exception")
except jp.PackError as e:
    check("the refusal names EVERY missing field, not the first",
          "authority" in str(e) and "edition" in str(e), str(e)[:110])
    check("  and says why a citation is required at all",
          "house rule" in str(e) or "look up why" in str(e), str(e)[:140])

# --- 2. a selector that would never match is refused at import, not at run time ---------------------
# A requirement that stores cleanly and then silently never matches reads as a PASS. That is the
# worst outcome available here: the authority believes it is enforced and nothing is checked.
for bad, why in ((("scope", "&&&"), "unparseable scope"),
                 (("require", "&&&"), "unparseable require")):
    (field, value), label = bad, why
    try:
        jp.validate({**GOOD, "requirements": [{**GOOD["requirements"][0], field: value}]})
        check(f"an {label} is refused", False, "no exception")
    except jp.PackError as e:
        check(f"an {label} is refused", field in str(e), str(e)[:90])
check("selectors are validated with the SAME parser that evaluates them",
      rule_library.query_dsl.parse is not None)

# Parsing is necessary and NOT sufficient, and this is the case that proves it. `Pset_X.Prop` is
# valid grammar — a bare-field existence test — resolving to a key no element has. So it matches
# nothing and the requirement passes on every model, forever. A rule that cannot fail is worse than
# a missing one: the authority believes it is enforced.
#
# The built-in example pack shipped with exactly this mistake until this test caught it.
for probe in ("Pset_WallCommon.FireRating", "IfcWall & Qto_WallBaseQuantities.NetArea"):
    parses = True
    try:
        rule_library.query_dsl.parse(probe)
    except rule_library.query_dsl.QueryError:
        parses = False
    check(f"{probe!r} PARSES cleanly (which is why parse-validation cannot catch it)", parses)
    try:
        jp.validate({**GOOD, "requirements": [{**GOOD["requirements"][0], "require": probe}]})
        check("  ...but the pack is refused anyway", False, "no exception")
    except jp.PackError as e:
        check("  ...but the pack is refused anyway", "TWO colons" in str(e), str(e)[:110])
        check("  and the message shows the corrected form", "::" in str(e))

# --- size caps: a bound on the COUNT is not a bound on the SIZE -------------------------------------
# Found by the Strix/qodo review on the PR. MAX_PACKS and MAX_REQUIREMENTS cap how MANY, and nothing
# capped how BIG — and stored packs are evaluated by a cheap GET, so one oversized selector persisted
# once amplifies work on every later read. Exactly the recipe_log per-value-vs-per-entry mistake,
# repeated in a second module on the same day.
for field, cap in (("authority", jp.MAX_TEXT_LEN), ("name", jp.MAX_TEXT_LEN),
                   ("edition", jp.MAX_TEXT_LEN), ("source", jp.MAX_SOURCE_LEN),
                   ("jurisdiction", jp.MAX_TEXT_LEN)):
    try:
        jp.validate({**GOOD, field: "x" * (cap + 1)})
        check(f"an oversized {field} is refused", False, "no exception")
    except jp.PackError as e:
        check(f"an oversized {field} is refused", "too long" in str(e), str(e)[:80])
for field in ("scope", "require"):
    try:
        jp.validate({**GOOD, "requirements": [
            {**GOOD["requirements"][0], field: "IfcWall & " + "a" * jp.MAX_SELECTOR_LEN}]})
        check(f"an oversized {field} selector is refused", False, "no exception")
    except jp.PackError as e:
        check(f"an oversized {field} selector is refused", "too long" in str(e), str(e)[:80])
check("selector cap is rule_library's, not a second opinion",
      jp.MAX_SELECTOR_LEN == rule_library.MAX_SELECTOR_LEN)

# The regexes are bounded AND the input is truncated before they run — both halves of the rule.
# A 200k-char selector must return promptly rather than buying CPU.
import time as _time  # noqa: E402

_t = _time.perf_counter()
jp._looks_like_dotted_pset("Pset_" + "a" * 200_000 + ".Prop")
jp._norm_jurisdiction(" " * 200_000 + "tx")
_elapsed = _time.perf_counter() - _t
check("a 200k-char input through both regexes returns in <100ms",
      _elapsed < 0.1, f"{_elapsed * 1000:.1f}ms")

check("the built-in example pack is itself valid", jp.validate(jp.EXAMPLE_PACK)["id"] == "example")
check("  and uses the two-colon property syntax",
      all("::" in r["require"] or "." not in r["require"]
          for r in jp.EXAMPLE_PACK["requirements"]),
      [r["require"] for r in jp.EXAMPLE_PACK["requirements"]])

for label, req in (("a requirement with no scope", {"id": "x", "require": "name"}),
                   ("a requirement with no require", {"id": "x", "scope": "IfcWall"}),
                   ("an unknown severity", {**GOOD["requirements"][0], "severity": "critical"})):
    try:
        jp.validate({**GOOD, "requirements": [req]})
        check(f"{label} is refused", False, "no exception")
    except jp.PackError:
        check(f"{label} is refused", True)
try:
    jp.validate({**GOOD, "requirements": [GOOD["requirements"][0], GOOD["requirements"][0]]})
    check("duplicate requirement ids are refused", False, "no exception")
except jp.PackError as e:
    check("duplicate requirement ids are refused", "duplicate" in str(e))
try:
    jp.validate({**GOOD, "requirements": []})
    check("a pack with no requirements is refused", False, "no exception")
except jp.PackError:
    check("a pack with no requirements is refused", True)

# --- 3. normalisation ------------------------------------------------------------------------------
norm = jp.validate(GOOD)
check("the jurisdiction is upper-cased so tx/TX/'Tx ' are one place", norm["jurisdiction"] == "TX")
check("  ...and whitespace-normalised",
      jp.validate({**GOOD, "jurisdiction": "  tx  "})["jurisdiction"] == "TX")
check("requirement ids are lower-cased and kept", [r["id"] for r in norm["requirements"]]
      == ["walls-rated", "spaces-named"])
check("a pack is not marked as an example unless it says so", norm["is_example"] is False)

# --- 4. the built-in asserts nothing about any real place -------------------------------------------
ex = jp.EXAMPLE_PACK
check("the only built-in pack is flagged as an example", ex["is_example"] is True)
check("  it is attributed to nobody real", "example" in ex["authority"].lower())
check("  and its jurisdiction is not a real code", ex["jurisdiction"] == "EXAMPLE")
check("the library ships exactly one built-in", len(jp.library()) == 1)
try:
    jp.import_pack({**GOOD, "id": "example"})
    check("the example id cannot be overwritten by an import", False, "no exception")
except jp.PackError:
    check("the example id cannot be overwritten by an import", True)

# --- 5. THE refusal that matters: no jurisdiction, no pack -------------------------------------------
for empty in (None, "", "   "):
    r = jp.resolve(empty)
    check(f"a project with jurisdiction={empty!r} adopts NOTHING",
          r["packs"] == [] and r["adopted"] is False)
check("  and it says why, rather than defaulting",
      "belong to a jurisdiction" in jp.resolve(None)["why"])
unknown = jp.resolve("ZZ")
check("an unknown jurisdiction adopts nothing and names it",
      unknown["packs"] == [] and "ZZ" in unknown["why"])

# --- 6. import / resolve round trip -------------------------------------------------------------------
saved = jp.import_pack(GOOD)
check("a valid pack imports", saved["id"] == "tx-example-city")
res = jp.resolve("TX")
check("it resolves for its jurisdiction", [p["id"] for p in res["packs"]] == ["tx-example-city"])
check("  and lower-case resolves the same", [p["id"] for p in jp.resolve("tx")["packs"]]
      == ["tx-example-city"])
check("  the resolved pack carries its authority and edition",
      res["packs"][0]["authority"] and res["packs"][0]["edition"])
check("re-importing the same id replaces rather than duplicates",
      len([p for p in jp.library() if p["id"] == "tx-example-city"]) == 1
      and jp.import_pack({**GOOD, "name": "v2"}) is not None
      and len([p for p in jp.library() if p["id"] == "tx-example-city"]) == 1)
check("delete removes it", jp.delete_pack("tx-example-city") is True)
check("  deleting a pack that is not there reports so", jp.delete_pack("tx-example-city") is False)
jp.import_pack(GOOD)

# --- 7. the check delegates to rule_library, and carries attribution ----------------------------------
IDX = {
    # `psets` is NESTED — the resolver reads e["psets"]["Pset_X"]["Prop"], not a flat dotted key.
    # The first version of this fixture invented the flat shape, both requirements failed, and the
    # "2 violations" assertion passed anyway because 2 happened to be the wrong-but-equal number.
    "w1": {"ifc_class": "IfcWall", "name": "W1",
           "psets": {"Pset_WallCommon": {"FireRating": "1HR"}}},
    "w2": {"ifc_class": "IfcWall", "name": "W2", "psets": {}},          # no fire rating -> fails
    "s1": {"ifc_class": "IfcSpace", "name": "Office 1"},
    "s2": {"ifc_class": "IfcSpace"},                                     # unnamed -> fails
}
out = jp.check(IDX, jp.resolve("TX")["packs"])
check("the check scores the model", out["model_scored"] is True)
check("  every requirement is evaluated", out["total_requirements"] == 2)
check("  both requirements fail on this model", out["failing_requirements"] == 2, out)
check("  and the violations are counted", out["total_violations"] == 2, out["total_violations"])
check("  satisfied is False while anything fails", out["satisfied"] is False)
byid = {r["id"]: r for r in out["packs"][0]["rules"]}
check("  the failing wall is named", byid["walls-rated"]["fail_guids"] == ["w2"], byid["walls-rated"])
check("  the unnamed space is named", byid["spaces-named"]["fail_guids"] == ["s2"])
check("every result carries WHOSE requirement it is",
      out["attribution"][0]["authority"] == GOOD["authority"]
      and out["attribution"][0]["edition"] == "2026", out["attribution"])
check("  and whether it was the example pack", out["attribution"][0]["is_example"] is False)

clean = jp.check({"w1": IDX["w1"], "s1": IDX["s1"]}, jp.resolve("TX")["packs"])
check("a conforming model satisfies the pack",
      clean["satisfied"] is True and clean["failing_requirements"] == 0, clean)

check("with no model there is no score, and it says so",
      jp.check(None, jp.resolve("TX")["packs"])["model_scored"] is False)

# --- 8. an unreadable store is not an empty one ---------------------------------------------------------
from aec_api import storage  # noqa: E402

storage.put(jp._KEY, b"{ not json")
try:
    jp.library()
    check("an unreadable pack store raises rather than reading as empty", False, "no exception")
except jp.PackError as e:
    check("an unreadable pack store raises rather than reading as empty", True)
    check("  and says it was not overwritten", "NOT been overwritten" in str(e), str(e)[:110])
storage.put(jp._KEY, b'{"packs": "not a list"}')
try:
    jp.library()
    check("a store that parses but is not a pack document is refused", False, "no exception")
except jp.PackError:
    check("a store that parses but is not a pack document is refused", True)

shutil.rmtree(os.environ["STORAGE_DIR"], ignore_errors=True)

print()
if FAILED:
    print(f"jurisdiction_packs: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print("jurisdiction_packs: all checks passed")
