"""MOD-BACKFILL — filling the sweep's reference fields, and the matches it REFUSES to make.

The field sweep added 54 reference fields beside their text twins rather than converting in place.
This fills them from the text already stored. Almost every assertion below is about a link the
matcher declines to make, because that is where the value is:

**A wrong auto-link is worse than an empty one.** An empty reference is visibly empty — somebody sees
a blank and fills it. A wrong one resolves, opens a real record and shows a plausible name, so it is
never questioned, and it silently attributes an RFI to the wrong subcontractor or a defect to the
wrong room. Nothing downstream can tell, because the value is structurally perfect. Timidity is the
feature; the tests that matter are the ones proving it stays timid.

Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_ref_backfill.py
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_ref_backfill.db"
os.environ["STORAGE_DIR"] = "./test_storage_ref_backfill"
os.environ["AEC_TRUST_XUSER"] = "1"
# WITHOUT THIS, ROLE ENFORCEMENT IS OFF AND THE ADMIN-GATE ASSERTION TESTS NOTHING. The first version
# of this file omitted it, and the non-admin call returned 200 — which failed the assertion loudly,
# but would have passed silently had the assertion been written the other way round ("an admin can
# call it"). A security check run with the security disabled is the emptiest kind of green.
os.environ["AEC_RBAC"] = "1"

for _f in ("./test_ref_backfill.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402
from aec_api.ref_backfill import normalize, pairs_for  # noqa: E402

H = {"X-User": "gc"}

# ---- 1. normalisation folds only what carries no identity --------------------------------------
assert normalize("Acme Electrical Inc.") == normalize("acme  electrical")
assert normalize("Acme Co., Inc.") == normalize("ACME")            # repeated legal suffixes
assert normalize("  Level 2 ") == "level 2"
assert normalize(None) == "" and normalize("") == "" and normalize("   ") == ""
# ...and NOT things that are real differences. Each of these would be a guess, and a guess here
# produces a link that looks right.
assert normalize("Acme Electrical") != normalize("Acme Electric")   # no edit distance
assert normalize("J&J Mechanical") != normalize("J and J Mechanical")
assert normalize("Bldg A") != normalize("Building A")               # no abbreviation expansion
assert normalize("Level 2") != normalize("Level 20")                # no prefix matching

with TestClient(app) as c:
    # ---- 2. the pair list comes from the declared config, not a hand-kept list ------------------
    # INSIDE the client block on purpose: `REGISTRY` is populated when the app starts, so calling
    # `pairs_for` at import time returns [] and every assertion below it passes vacuously. That is the
    # same shape as `all()` over an empty list — a check that cannot fail because it has no input.
    coi_pairs = pairs_for("coi")
    assert ("vendor", "vendor_company", "company") in coi_pairs, coi_pairs
    assert ("carrier", "carrier_company", "company") in coi_pairs, coi_pairs
    assert all(t == "company" for _s, _r, t in coi_pairs), coi_pairs
    assert pairs_for("rfi"), "rfi should have at least the spec_section pair"

    pid = c.post("/projects", headers=H, json={"name": "Backfill"}).json()["id"]

    def mk(mod, data):
        r = c.post(f"/projects/{pid}/modules/{mod}", headers=H, json={"data": data})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    # target register: three companies, two of which share a name after normalisation
    acme = mk("company", {"name": "Acme Electrical Inc."})
    _bolt = mk("company", {"name": "Bolt Mechanical"})
    dup_a = mk("company", {"name": "Summit Interiors"})
    dup_b = mk("company", {"name": "Summit Interiors LLC"})     # normalises to the same string

    # source records, each exercising one branch
    exact = mk("coi", {"vendor": "acme electrical", "expires": "2027-01-01"})     # -> links
    ambig = mk("coi", {"vendor": "Summit Interiors", "expires": "2027-01-01"})    # -> ambiguous
    nomatch = mk("coi", {"vendor": "Nobody Ltd", "expires": "2027-01-01"})        # -> no match
    preset = mk("coi", {"vendor": "acme electrical", "vendor_company": dup_a,
                        "expires": "2027-01-01"})                                # -> never overwritten
    # The blank case needs a module whose text twin is OPTIONAL — `coi.vendor` is required, so an
    # empty one cannot be created at all. `punchlist.responsible` is free.
    blank = mk("punchlist", {"description": "Touch up paint"})                    # -> not reported

    def run(apply=False, module="coi"):
        r = c.post(f"/projects/{pid}/modules/backfill-references",
                   headers=H, params={"module": module, "apply": str(apply).lower()})
        assert r.status_code == 200, r.text
        return r.json()

    # ---- 3. DRY RUN IS THE DEFAULT and changes nothing -----------------------------------------
    rep = run(apply=False)
    assert rep["applied"] is False
    ids = {x["record"] for x in rep["linked"]}
    assert ids == {exact}, f"expected only the exact match to link, got {ids}"
    got = c.get(f"/projects/{pid}/modules/coi/{exact}", headers=H).json()
    assert not got["data"].get("vendor_company"), "a dry run wrote to the record"

    # ---- 4. every refusal is REPORTED with a reason ---------------------------------------------
    by_record = {x["record"]: x for x in rep["skipped"]}
    assert by_record[ambig]["reason"] == "ambiguous", by_record.get(ambig)
    assert "2 records" in by_record[ambig]["detail"], by_record[ambig]["detail"]
    assert by_record[nomatch]["reason"] == "no match", by_record.get(nomatch)
    # a blank source is not a shortfall — there was nothing to match on, so it is not noise in the
    # report. Checked against a project-wide run, since `blank` is a punchlist record.
    wide = c.post(f"/projects/{pid}/modules/backfill-references",
                  headers=H, params={"apply": "false"}).json()
    assert blank not in {x["record"] for x in wide["skipped"]}, \
        "an empty text field was reported as a skip"
    # an already-set reference is neither linked nor reported: it is simply not this tool's business
    assert preset not in by_record and preset not in ids

    # ---- 5. APPLY writes exactly what the dry run promised --------------------------------------
    rep2 = run(apply=True)
    assert rep2["applied"] is True
    assert {x["record"] for x in rep2["linked"]} == ids, "apply diverged from the dry run"
    got = c.get(f"/projects/{pid}/modules/coi/{exact}", headers=H).json()
    assert got["data"]["vendor_company"] == acme, got["data"]
    # the hand-set one is untouched even though its text says "acme electrical" and would have matched
    kept = c.get(f"/projects/{pid}/modules/coi/{preset}", headers=H).json()
    assert kept["data"]["vendor_company"] == dup_a, "a hand-set reference was overwritten"

    # ---- 6. it is IDEMPOTENT — a second apply links nothing new ---------------------------------
    rep3 = run(apply=True)
    assert rep3["summary"]["linked"] == 0, rep3["summary"]
    assert rep3["summary"]["ambiguous"] == 1 and rep3["summary"]["no_match"] == 1, rep3["summary"]

    # ---- 7. ambiguity stays refused even after one candidate is renamed apart -------------------
    # (the tie is broken by the DATA changing, never by the matcher picking)
    c.patch(f"/projects/{pid}/modules/company/{dup_b}", headers=H,
            json={"name": "Summit Interiors West"})
    rep4 = run(apply=True)
    assert {x["record"] for x in rep4["linked"]} == {ambig}, rep4["linked"]
    got = c.get(f"/projects/{pid}/modules/coi/{ambig}", headers=H).json()
    assert got["data"]["vendor_company"] == dup_a

    # ---- 8. scoping to one module does not touch others -----------------------------------------
    all_rep = c.post(f"/projects/{pid}/modules/backfill-references",
                     headers=H, params={"apply": "false"}).json()
    assert all_rep["records_scanned"] >= rep["records_scanned"]

    # ---- 9. it is admin-gated: it writes across every register in one call ----------------------
    r = c.post(f"/projects/{pid}/modules/backfill-references", headers={"X-User": "sub"},
               params={"apply": "true"})
    assert r.status_code in (401, 403), f"a non-admin ran a project-wide write ({r.status_code})"

print("MOD-BACKFILL OK - reference fields fill from their text twins by EXACT match after "
      "normalisation, unique matches only, existing values never overwritten, dry-run by default, "
      "idempotent, and admin-gated. Normalisation folds case, whitespace and trailing legal suffixes "
      "(Acme Co., Inc. == ACME) and deliberately NOTHING else: no edit distance, no abbreviation "
      "expansion, no prefix matching, so 'Acme Electrical' and 'Acme Electric' stay different "
      "companies. Two records answering to one name is reported as ambiguous rather than resolved — "
      "breaking that tie by id or date would be a coin flip wearing a suit. Every refusal is returned "
      "with its reason, because a backfill that silently does 60% of the work and reports success "
      "leaves the other 40% invisible. The asymmetry driving all of it: an empty reference is visibly "
      "empty and gets filled, while a wrong one resolves, opens a real record, shows a plausible name "
      "and is never questioned.")
