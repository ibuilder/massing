"""MOD-GUID — the platform's first non-negotiable, as a check that can fail.

`CLAUDE.md` opens with "Reference model elements by IFC GlobalId (GUID), never by transient viewer
IDs". Three fields store a GlobalId (`field_verification.guid`, `material_request.guids`,
`prefab_kit.frozen_guids`) and all three were plain `text`. A transient viewer id is a small integer;
a GlobalId is 22 characters. The field could not tell them apart, so the rule existed only as prose
and the one thing prose cannot do is fail.

Three separate claims are asserted here, because they fail for different reasons:

  1. FORMAT — a value that is not a GlobalId is rejected on write.
  2. LEGACY — a record already holding a malformed value stays editable. This is the claim I got
     wrong: I pulled this work once believing the engine had no legacy story, when `update_record`
     already validates only the fields in the patch. The check is here because a belief about
     behaviour that nobody tested is how the mistake happened in the first place.
  3. RECONCILIATION — a GlobalId in a record's field also lands in `element_guids`, so the two stores
     that held this one fact cannot disagree.

Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_guid_integrity.py
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_guid_integrity.db"
os.environ["STORAGE_DIR"] = "./test_storage_guid"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_guid_integrity.db",):
    if os.path.exists(_f):
        os.remove(_f)

from aec_api import element_facts  # noqa: E402
from aec_api import module_schema as ms

GOOD = "1kTvXnbbzCWw8lcMd1dR4o"
GOOD2 = "0Ln$JgLR9ETfP2m3nQrStU"
GOOD3 = "2wZq7HcVnB4rT9yUiOpAsD"
assert all(ms.IFC_GUID_RE.match(g) for g in (GOOD, GOOD2, GOOD3))

# --- 1. what a GlobalId is, and the four shapes of thing that is not one -----------------------------
for bad, why in [("12345", "a transient viewer id — the exact thing the non-negotiable forbids"),
                 ("TBD", "a placeholder somebody typed"),
                 ("1kTvXnbbzCWw8lcMd1dR4", "21 chars: a truncated paste, one short"),
                 ("1kTvXnbbzCWw8lcMd1dR4oX", "23 chars: a paste that picked up a neighbour"),
                 ("1kTvXnbbzCWw-lcMd1dR4o", "right length, '-' is outside the alphabet")]:
    assert not ms.IFC_GUID_RE.match(bad), f"{bad!r} must not validate ({why})"
    assert ms.guid_errors("guid", bad), why

# a hyphenated UUID is the sharpest near-miss: it IS a globally unique id, just not IFC's compressed
# form, and it is what you get by copying an id out of this system's own API rather than the model.
assert not ms.IFC_GUID_RE.match("3f2504e0-4f89-11d3-9a0c-0305e82c3301")

# --- lists: `guids` / `frozen_guids` hold many, separated by newline, comma or semicolon -------------
assert ms.split_guids(f"{GOOD}\n{GOOD2}") == [GOOD, GOOD2]
assert ms.split_guids(f" {GOOD} , {GOOD2} ") == [GOOD, GOOD2]
assert ms.split_guids([GOOD, GOOD2]) == [GOOD, GOOD2], "already-a-list must pass through"
assert ms.split_guids("") == [] and ms.split_guids(None) == []
assert ms.guid_errors("guids", f"{GOOD}\nbad1\n{GOOD2}\nbad2"), "one bad id in a list is still bad"
# capped, so pasting a hundred wrong ids is a readable message rather than a wall
many = ms.guid_errors("guids", "\n".join(f"x{i}" for i in range(50)))
assert len(many) == 4 and "47 more" in many[-1], many          # 50 bad, 3 named, 47 counted

# --- 2. THE LEGACY STORY. A partial patch must not re-validate a field it is not touching ------------
fv = {"fields": [{"name": "guid", "type": "text"}, {"name": "element", "type": "text"}]}
assert ms.validate_record(fv, {"guid": "legacy-junk"}), "writing a bad guid is an error"
assert ms.validate_record(fv, {"element": "C-12"}) == [], (
    "a patch that does not mention `guid` must be clean even though the stored guid is malformed — "
    "this is what makes the rule shippable against live data")

# --- 3. the two stores, reconciled ------------------------------------------------------------------
assert ms.guids_from_fields({"guid": GOOD}) == [GOOD]
assert sorted(ms.guids_from_fields({"frozen_guids": f"{GOOD},{GOOD2}"})) == sorted([GOOD, GOOD2])
assert ms.guids_from_fields({"guid": "TBD"}) == [], (
    "a malformed id must NOT be mirrored: validate_record already reports it, and copying it into the "
    "column every consumer trusts would spread the bad value instead of containing it")
assert ms.guids_from_fields({"element": GOOD}) == [], "only GlobalId-named fields are GlobalIds"

# `_claims` read only the singular `guid`, so the other two fields never matched here.
for field in ("guid", "guids", "frozen_guids"):
    assert element_facts._claims({"data": {field: GOOD}}, GOOD), f"{field} must claim its element"
    assert not element_facts._claims({"data": {field: GOOD}}, GOOD2)
assert element_facts._claims({"element_guids": [GOOD], "data": {}}, GOOD), "the column still works"

# --- HTTP: the write path, end to end ---------------------------------------------------------------
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as tc:
    pid = tc.post("/projects", json={"name": "GUID Tower"}).json()["id"]

    bad = tc.post(f"/projects/{pid}/modules/field_verification",
                  json={"data": {"guid": "12345", "element": "C-1"}})
    assert bad.status_code == 422, f"a viewer id must be refused, got {bad.status_code}"
    assert "GlobalId" in bad.text, bad.text[:200]

    ok = tc.post(f"/projects/{pid}/modules/field_verification",
                 json={"data": {"guid": GOOD, "element": "C-1"}})
    assert ok.status_code in (200, 201), ok.text[:200]
    rid = ok.json()["id"]

    # the mirror: the field's GlobalId is now in the column every consumer reads
    got = tc.get(f"/projects/{pid}/modules/field_verification/{rid}").json()
    assert GOOD in (got.get("element_guids") or []), (
        f"guid field must mirror into element_guids, got {got.get('element_guids')!r}")

    # a caller-supplied anchor is not replaced by the mirror, it is joined by it
    both = tc.post(f"/projects/{pid}/modules/field_verification",
                   json={"element_guids": [GOOD2], "data": {"guid": GOOD, "element": "C-2"}})
    assert sorted(both.json()["element_guids"]) == sorted([GOOD, GOOD2]), both.json()["element_guids"]

    # a record with no GlobalId anywhere keeps a null column, not an empty list — the two mean
    # different things to `pins.py` ("never anchored" vs "anchored to nothing")
    # (material_request, not field_verification — the latter's `guid` is required, so the create would
    # 422 and `.get("element_guids")` on an ERROR body is None, which passes this assert for entirely
    # the wrong reason. Assert the status first so the shape can't stand in for the behaviour.)
    none = tc.post(f"/projects/{pid}/modules/material_request", json={"data": {"material": "Sealant"}})
    assert none.status_code in (200, 201), none.text[:200]
    assert none.json().get("element_guids") is None, none.json().get("element_guids")

    # a list field, and a patch that leaves the GlobalId alone
    mr = tc.post(f"/projects/{pid}/modules/material_request",
                 json={"data": {"material": "Rebar", "guids": f"{GOOD}\n{GOOD2}"}})
    assert mr.status_code in (200, 201), mr.text[:200]
    assert sorted(mr.json()["element_guids"]) == sorted([GOOD, GOOD2]), mr.json()["element_guids"]
    patched = tc.patch(f"/projects/{pid}/modules/material_request/{mr.json()['id']}",
                       json={"material": "Rebar #5"})
    assert patched.status_code == 200, patched.text[:200]

    # --- the mirror on UPDATE, which is where the ordinary flow lives -------------------------------
    # file the record now, add the GlobalId when you get back from the field
    # material_request, because `field_verification.guid` is `required` — the module that lets you
    # file first and anchor later is the one that exercises the update path
    later = tc.post(f"/projects/{pid}/modules/material_request", json={"data": {"material": "Anchors"}})
    lid = later.json()["id"]
    assert not later.json().get("element_guids")
    up = tc.patch(f"/projects/{pid}/modules/material_request/{lid}", json={"guids": GOOD})
    assert up.status_code == 200, up.text[:200]
    assert (tc.get(f"/projects/{pid}/modules/material_request/{lid}").json()["element_guids"]
            == [GOOD]), "a GlobalId added after creation must reach the column too"

    # CORRECTING a mistyped id must MOVE the anchor, not accumulate one. This is the case a blind
    # union gets wrong: the old element stays claimed forever and two records answer for it.
    tc.patch(f"/projects/{pid}/modules/material_request/{lid}", json={"guids": GOOD2})
    assert (tc.get(f"/projects/{pid}/modules/material_request/{lid}").json()["element_guids"]
            == [GOOD2]), "correcting a GlobalId must drop the old one"

    # but an anchor set by another route (pin, BCF import, anchor-to-selection) is not ours to remove
    tc.post(f"/projects/{pid}/modules/material_request/{lid}/elements", json={"guids": [GOOD]})
    # patch to a THIRD id, not back to the one already stored: `was == now` short-circuits the whole
    # branch, so re-patching the same value tests nothing. That is how this assertion first passed
    # against a mutant that replaced the column outright.
    tc.patch(f"/projects/{pid}/modules/material_request/{lid}", json={"guids": GOOD3})
    after = tc.get(f"/projects/{pid}/modules/material_request/{lid}").json()["element_guids"]
    assert GOOD in after, f"an independently-set anchor must survive a field edit, got {after}"
    assert GOOD3 in after, f"the new field value must be anchored, got {after}"
    assert GOOD2 not in after, f"the replaced field value must be dropped, got {after}"

# --- the DEMO must obey the rule the product enforces ------------------------------------------------
# The seeded demo filed "Level 2 slab 1" into `field_verification.guid` and a sentence about
# coordinating before the next pour into `material_request.guids`: the generator falls through to
# prose for any `text`/`textarea` it does not recognise, and nothing rejected it. So the demo every
# new user opens was showing the platform's first non-negotiable being broken. `test_demo_seed`
# validates the whole corpus and catches this now; asserted here too, because the generator is what
# has to know, and it must learn it from the same list the validator uses.
from aec_api.demo_seed import _fake_guid, _value  # noqa: E402

for i in range(200):
    g = _fake_guid("mod", "guid", i)
    assert ms.IFC_GUID_RE.match(g), g
assert _fake_guid("a", 1) == _fake_guid("a", 1), "a re-seeded demo must be byte-identical"
assert len({_fake_guid("m", i) for i in range(200)}) == 200, "distinct rows must differ"
from datetime import date  # noqa: E402

for fname, ftype, n in [("guid", "text", 1), ("guids", "textarea", 2), ("frozen_guids", "textarea", 2)]:
    v = _value({"name": fname, "type": ftype}, "m", 0, date.today())
    got = ms.split_guids(v)
    assert len(got) == n and all(ms.IFC_GUID_RE.match(g) for g in got), (fname, v)

# --- the three fields are still the three fields ----------------------------------------------------
# Not a floor and not an allowlist: if a module gains a field named `guid`, this fails and whoever
# added it decides whether it is a GlobalId. A silent fourth field is how `_claims` came to cover one.
import json  # noqa: E402
from pathlib import Path  # noqa: E402

found = set()
for mj in Path("modules").glob("*/module.json"):
    for f in json.loads(mj.read_text(encoding="utf-8")).get("fields", []):
        if f["name"] in ms._GUID_FIELDS:
            found.add(f"{mj.parent.name}.{f['name']}")
assert found == {"field_verification.guid", "material_request.guids", "prefab_kit.frozen_guids"}, found

print("GUID-INTEGRITY OK - a viewer id, a placeholder, a truncated paste and a hyphenated UUID are "
      "all refused on write; a record already holding a malformed id stays editable via a patch that "
      "does not touch it; a GlobalId in a record's field mirrors into element_guids so the two stores "
      "cannot disagree, and _claims now reads all three fields instead of one.")
