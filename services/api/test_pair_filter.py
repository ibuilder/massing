"""PAIR-FILTER — filtering a register by a linked party must not drop the rows that typed its name.

MOD-SWEEP's additive pattern never converts a text field, so a register in use across the change
holds both eras at once: some rows point at the `company` record, some still carry the name somebody
typed. "Everything open with this subcontractor" is the question the reference fields were added to
make askable, and a filter that matches only the linked rows answers it with a SHORT list.

**A short filtered list is the dangerous shape.** It is indistinguishable from "there are none" —
nothing on screen is wrong, the count is simply lower than the truth. `modules_query` already
describes this failure for sorting ("Nothing was wrong on screen; it was the wrong 200 rows"); the
filter had it too.

The widened clause matches a text twin EQUAL to the linked record's title, case-insensitively, never
a substring. That is the whole of the judgement, and it is asserted in both directions here: the
variant row is found (exact), and the different-firm row is NOT (no `contains`). A `contains` match
would pull "Acme Electrical Supply" into a filter for "Acme Electrical" on a register people ask
money questions against.

Run: PYTHONPATH=src ./.venv/bin/python test_pair_filter.py
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_pairfilter.db"
os.environ["STORAGE_DIR"] = "./test_pairfilter_storage"

for f in ("./test_pairfilter.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402
from aec_api.modules_registry import REF_SUFFIXES, text_half  # noqa: E402

FAILED: list[str] = []


def check(label, cond, detail=""):
    (print(f"PASS  {label}   {detail}") if cond
     else (FAILED.append(label), print(f"FAIL  {label}   {detail}")))


# ---- the rule itself, before any HTTP -------------------------------------------------------------
_FIELDS = {
    "supplier": {"name": "supplier", "type": "text"},
    "supplier_company": {"name": "supplier_company", "type": "reference", "module": "company"},
    "assignee_name": {"name": "assignee_name", "type": "text"},
    "assignee_contact": {"name": "assignee_contact", "type": "reference", "module": "contact"},
    "lonely_company": {"name": "lonely_company", "type": "reference", "module": "company"},
    "notes": {"name": "notes", "type": "textarea"},
}
check("text_half finds the plain stem", text_half("supplier_company", _FIELDS) == "supplier")
check("text_half finds the _name stem", text_half("assignee_contact", _FIELDS) == "assignee_name")
check("text_half returns None for a lone reference", text_half("lonely_company", _FIELDS) is None)
check("text_half refuses a text field", text_half("supplier", _FIELDS) is None)
check("REF_SUFFIXES is non-trivial", len(REF_SUFFIXES) > 4, f"{len(REF_SUFFIXES)} suffixes")

# ---- the guard that a mutation SURVIVED, turned into a checked precondition -----------------------
#
# `_eq_or_pair` refuses to widen when the resolved field is a SYSTEM column or not a reference. That
# branch is redundant today — `text_half` independently returns None for anything that is not a
# reference — and a mutation removing it changed no result, which is worth recording rather than
# hiding behind a nicer-looking score.
#
# It stops being redundant the moment a module declares a REFERENCE field whose name is also a system
# column: `_resolve_field` would hand back the system stub (so `expr` is the row column) while
# `text_half`, reading the module's own fields, would find a pair and widen with a JSON path — two
# different columns in one clause. No module does that today (`action_item.assignee` collides by name
# but is text), so instead of leaving a dead branch nothing exercises, the PRECONDITION is asserted.
# The day it fails, the guard becomes load-bearing and someone is looking at it.
from aec_api.modules_query import SYSTEM_COLUMNS  # noqa: E402
from aec_api.modules_registry import REGISTRY  # noqa: E402

_collisions = [f"{k}.{f['name']}" for k, m in REGISTRY.items() for f in m.get("fields", [])
               if f.get("name") in SYSTEM_COLUMNS and f.get("type") == "reference"]
check("no module declares a REFERENCE named like a system column", not _collisions,
      "the _eq_or_pair system guard is redundant only while this holds; "
      f"found {_collisions}" if _collisions else "none, so the guard stays as belt-and-braces")

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Pair Filter"}).json()["id"]

    def mk(key, data):
        r = c.post(f"/projects/{pid}/modules/{key}", json={"data": data})
        assert r.status_code in (200, 201), (key, r.status_code, r.text[:300])
        return r.json()

    acme = mk("company", {"name": "Acme Electrical", "type": "Subcontractor"})
    other = mk("company", {"name": "Delta Mechanical", "type": "Subcontractor"})

    # Three deliveries, one per era plus a decoy whose typed name only SHARES A PREFIX with Acme.
    linked = mk("delivery", {"description": "Switchgear", "supplier_company": acme["id"], "date": "2026-09-01"})
    typed = mk("delivery", {"description": "Panelboards", "supplier": "Acme Electrical", "date": "2026-09-02"})
    variant = mk("delivery", {"description": "Conduit", "supplier": "Acme Electrical Supply", "date": "2026-09-03"})
    unrelated = mk("delivery", {"description": "Air handler", "supplier_company": other["id"], "date": "2026-09-04"})

    def filtered():
        r = c.get(f"/projects/{pid}/modules/delivery",
                  params={"f.supplier_company": acme["id"]})
        assert r.status_code == 200, (r.status_code, r.text[:300])
        rows = r.json()
        rows = rows.get("items", rows) if isinstance(rows, dict) else rows
        return {x["id"] for x in rows}

    got = filtered()
    # The first draft of this file used `f_supplier_company`, not `f.<field>`. No filter was applied,
    # every row came back, and the headline assertion below PASSED on a list that proved nothing —
    # the negatives are what exposed it. A positive-only filter test cannot tell "the filter widened
    # correctly" from "the filter never ran", so the negatives are not decoration here.
    check("the filter actually narrows at all", len(got) < 4, f"{len(got)} of 4 rows")
    check("the LINKED row is returned", linked["id"] in got)
    check("the TYPED row is returned too — this is the defect PAIR-FILTER fixes",
          typed["id"] in got,
          "without the widened clause this row is missing and the list looks complete")
    check("a DIFFERENT firm is not returned", unrelated["id"] not in got)
    # The load-bearing negative. `contains` would pass every other assertion in this file and pull
    # this row in, so without it the exact-vs-substring judgement is untested.
    check("a name that merely STARTS WITH the title is not returned",
          variant["id"] not in got,
          "'Acme Electrical Supply' is a different firm; matching it would over-report")
    check("exactly the two Acme rows come back", got == {linked["id"], typed["id"]}, f"{len(got)} rows")

    # ---- review finding 1: Unicode case folding ---------------------------------------------------
    #
    # SQLite `lower()` folds ASCII only — measured: lower('Ångström') = lower('ångström') is 0 —
    # while Postgres folds the full range. The same filter therefore returned DIFFERENT rows on the
    # two backends, and since this gate runs SQLite while production runs Postgres, the tested
    # behaviour was not the shipped behaviour. `db.py` now registers `aec_lower` on SQLite so both
    # agree. This case FAILS without that registration.
    nordic = mk("company", {"name": "Ångström Kraft", "type": "Subcontractor"})
    nordic_typed = mk("delivery", {"description": "Transformer", "supplier": "ångström kraft",
                                   "date": "2026-09-05"})
    r = c.get(f"/projects/{pid}/modules/delivery", params={"f.supplier_company": nordic["id"]})
    nrows = r.json()
    nrows = nrows.get("items", nrows) if isinstance(nrows, dict) else nrows
    check("a non-ASCII name differing only in CASE still matches",
          nordic_typed["id"] in {x["id"] for x in nrows},
          "SQLite lower() folds ASCII only; aec_lower is what makes this pass")

    # The ß case, which is what the FIRST attempt at this got wrong. `str.casefold` folds ß to ss and
    # Postgres `lower()` does not, so registering casefold on SQLite fixed the Å divergence and
    # created a ß one — the same defect, in the same function, in the commit claiming to remove it.
    # The contract is PARITY WITH POSTGRES, so `Straße` must NOT match `STRASSE` on either backend;
    # asserting the non-match is what pins the contract, because casefold would make it match.
    strasse = mk("company", {"name": "Straße Bau", "type": "Subcontractor"})
    shouty = mk("delivery", {"description": "Rebar", "supplier": "STRASSE BAU", "date": "2026-09-07"})
    exact = mk("delivery", {"description": "Mesh", "supplier": "straße bau", "date": "2026-09-08"})
    r = c.get(f"/projects/{pid}/modules/delivery", params={"f.supplier_company": strasse["id"]})
    srows = {x["id"] for x in (r.json().get("items", r.json()) if isinstance(r.json(), dict) else r.json())}
    check("ss is NOT folded to ß — parity with Postgres lower(), not casefold",
          shouty["id"] not in srows,
          "casefold would match this and Postgres would not, which is the divergence being avoided")
    check("a simple-lowercase difference still matches", exact["id"] in srows,
          "'straße bau' vs 'Straße Bau' differ only by simple lowercasing")

    # ---- review finding 2: the title must be resolved INSIDE the requested project -----------------
    #
    # Every module table carries project_id, and the filter value is caller-supplied. Resolving a
    # title by id alone let a record id from ANOTHER project decide what a text twin in this one
    # matched against. Two projects, a company in each, and a delivery here that typed the OTHER
    # project's company name: it must not match.
    pid2 = c.post("/projects", json={"name": "Other Project"}).json()["id"]
    r2 = c.post(f"/projects/{pid2}/modules/company",
                json={"data": {"name": "Foreign Partners", "type": "Subcontractor"}})
    foreign = r2.json()
    leaky = mk("delivery", {"description": "Ductwork", "supplier": "Foreign Partners",
                            "date": "2026-09-06"})
    r3 = c.get(f"/projects/{pid}/modules/delivery",
               params={"f.supplier_company": foreign["id"]})
    frows = r3.json()
    frows = frows.get("items", frows) if isinstance(frows, dict) else frows
    check("a title from ANOTHER project cannot decide what this project matches",
          leaky["id"] not in {x["id"] for x in frows},
          "IDOR: resolving the title by id alone crossed the project boundary")

    # A register with no pair on the filtered field must behave exactly as before.
    plain = c.get(f"/projects/{pid}/modules/delivery", params={"f.date": "2026-09-04"})
    prows = plain.json()
    prows = prows.get("items", prows) if isinstance(prows, dict) else prows
    check("an unpaired field filters unchanged", {x["id"] for x in prows} == {unrelated["id"]})

print(("FAILED: " + "; ".join(FAILED)) if FAILED else "test_pair_filter OK")
raise SystemExit(1 if FAILED else 0)
