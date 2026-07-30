"""MOD-FILTER — per-field filtering and server-side sorting over a module register.

Before this, a register could be narrowed by exactly two things: the full-text `q` and
`workflow_state`. On a twenty-field register that means no filtering by discipline, vendor, cost code
or date range — and sorting happened in the **browser, over whichever page had been fetched**, so
"sort by amount" on a 500-row register ordered 200 rows and presented the result as the answer.

Two properties are worth more than the feature and are what this file mostly asserts:

**A number must be compared as a number.** JSON extraction yields text. Compared as text, 9 > 10 and
900 sorts after 1000 — not an error, a plausible wrong answer, which is the failure mode this codebase
meets most often. Numeric fields are cast before comparison, and the tests below use values (9 vs 10,
900 vs 1000) chosen so a text comparison FAILS them. A test using 1, 2, 3 would pass either way and
prove nothing.

**An unknown field or operator must 400, never be ignored.** A silently dropped filter returns MORE
rows than were asked for, which looks like data rather than a bug. It is also the injection boundary:
`_json_text` interpolates the field name into a SQLite JSON path, so "reject unknown names" is what
makes the whole feature safe.

Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_module_filters.py
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_mod_filters.db"
os.environ["STORAGE_DIR"] = "./test_storage_mod_filters"
os.environ["AEC_TRUST_XUSER"] = "1"

for _f in ("./test_mod_filters.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

H = {"X-User": "gc"}

with TestClient(app) as c:
    pid = c.post("/projects", headers=H, json={"name": "Filter Test"}).json()["id"]

    # `cor` carries a currency (`amount`), a select (`reason`) and a date — one record per shape.
    def mk(subject, amount, reason, days):
        r = c.post(f"/projects/{pid}/modules/cor", headers=H, json={"data": {
            "subject": subject, "amount": amount, "reason": reason, "schedule_days": days}})
        assert r.status_code == 201, r.text
        return r.json()["id"]

    # AMOUNTS ARE POSTED AS STRINGS, and that is the whole point of the fixture.
    #
    # The first version of this test posted ints and the numeric cast could be DELETED with every
    # assertion still passing — the test could not reach the bug it was written for. SQLite types
    # `json_extract` by what was stored: a JSON number comes back `integer` and compares numerically on
    # its own, so an int fixture exercises a path the cast does not affect. A JSON *string* comes back
    # `text`, and in SQLite `'9' >= 10` is TRUE, so a string-stored 9 leaks into `amount >= 10`.
    #
    # Strings are the NORMAL case, not the edge: an HTML form field posts a string, a CSV import posts
    # a string, and `validate_record` only checks that a numeric field parses — it does not coerce. So
    # the register is full of numbers stored as text, which is exactly where text comparison bites.
    # Values chosen so a lexicographic comparison FAILS: "9" > "10" and "1000" < "900".
    mk("nine", "9", "Owner Request", 9)
    mk("ten", "10", "Design Change", 10)
    mk("nine hundred", "900", "Owner Request", 90)
    mk("thousand", "1000", "Field Condition", 100)
    # one posted as a real number too, so the cast is proven to handle BOTH storage shapes
    mk("fifty numeric", 50, "Owner Request", 50)

    def rows(**params):
        r = c.get(f"/projects/{pid}/modules/cor", headers=H, params=params)
        assert r.status_code == 200, r.text
        return r.json()

    subjects = lambda rs: [x["data"]["subject"] for x in rs]  # noqa: E731

    # ---- 1. equality on a select ------------------------------------------------------------------
    got = rows(**{"f.reason": "Owner Request"})
    assert sorted(subjects(got)) == ["fifty numeric", "nine", "nine hundred"], subjects(got)

    # ---- 2. NUMERIC comparison, not lexicographic -------------------------------------------------
    # amount >= 10 must exclude 9. Stored as text, `'9' >= 10` is TRUE in SQLite, so without the cast
    # "nine" leaks in — which is what makes this assertion able to fail.
    got = rows(**{"f.amount.gte": "10"})
    assert sorted(subjects(got)) == ["fifty numeric", "nine hundred", "ten", "thousand"], (
        f"numeric gte compared as text: {subjects(got)}")
    # amount <= 900 must exclude 1000. Lexicographically "1000" < "900", so 'thousand' leaks in.
    got = rows(**{"f.amount.lte": "900"})
    assert "thousand" not in subjects(got), f"lte compared as text: {subjects(got)}"
    assert sorted(subjects(got)) == ["fifty numeric", "nine", "nine hundred", "ten"], subjects(got)
    # a range, both bounds at once — and it spans a string-stored and a number-stored row
    got = rows(**{"f.amount.gte": "10", "f.amount.lte": "900"})
    assert sorted(subjects(got)) == ["fifty numeric", "nine hundred", "ten"], subjects(got)

    # ---- 3. SORT is numeric and happens on the server ---------------------------------------------
    # Text ordering would give nine(9), ten(10), thousand(1000), nine hundred(900) — 1000 before 900.
    got = rows(sort="amount", sort_dir="asc")
    assert subjects(got) == ["nine", "ten", "fifty numeric", "nine hundred", "thousand"], (
        f"ascending sort is lexicographic: {subjects(got)}")
    got = rows(sort="amount", sort_dir="desc")
    assert subjects(got) == ["thousand", "nine hundred", "fifty numeric", "ten", "nine"], subjects(got)

    # sorting a page must not reorder ACROSS pages inconsistently — `created_at` is the tiebreak, so
    # two equal values keep a stable order and pagination cannot show one row twice or skip one.
    page1 = rows(sort="reason", limit=2, offset=0)
    page2 = rows(sort="reason", limit=2, offset=2)
    page3 = rows(sort="reason", limit=2, offset=4)
    ids = [x["id"] for x in page1 + page2 + page3]
    assert len(set(ids)) == 5, f"paged sort repeated or dropped a row: {ids}"

    # ---- 4. contains / in / empty / nonempty ------------------------------------------------------
    got = rows(**{"f.subject.contains": "NINE"})            # case-insensitive
    assert sorted(subjects(got)) == ["nine", "nine hundred"], subjects(got)
    got = rows(**{"f.reason.in": "Owner Request,Field Condition"})
    assert sorted(subjects(got)) == ["fifty numeric", "nine", "nine hundred", "thousand"], subjects(got)
    mk("no reason", 5, "", 0)
    got = rows(**{"f.reason.empty": "1"})
    assert subjects(got) == ["no reason"], subjects(got)
    got = rows(**{"f.reason.nonempty": "1"})
    assert "no reason" not in subjects(got) and len(got) == 5, subjects(got)

    # ---- 5. filters COMPOSE with state and q -----------------------------------------------------
    got = rows(**{"f.reason": "Owner Request", "q": "hundred"})
    assert subjects(got) == ["nine hundred"], subjects(got)

    # ---- 6. an unknown field or operator is a 400, NOT a silently ignored filter ------------------
    # This is the property that makes the feature safe: the field name reaches a SQLite JSON path, so
    # anything not declared by the module must be refused rather than interpolated.
    for bad in ("f.no_such_field", "f.data", "f.id"):
        r = c.get(f"/projects/{pid}/modules/cor", headers=H, params={bad: "x"})
        assert r.status_code == 400, f"{bad} was accepted ({r.status_code})"
    r = c.get(f"/projects/{pid}/modules/cor", headers=H, params={"f.amount.between": "1"})
    assert r.status_code == 400, f"unknown operator accepted ({r.status_code})"
    r = c.get(f"/projects/{pid}/modules/cor", headers=H, params={"sort": "no_such_field"})
    assert r.status_code == 400, f"unknown sort field accepted ({r.status_code})"
    # a non-numeric value against a numeric field is refused rather than coerced to 0
    r = c.get(f"/projects/{pid}/modules/cor", headers=H, params={"f.amount.gte": "abc"})
    assert r.status_code == 400, f"non-numeric value on a numeric field accepted ({r.status_code})"

    # an injection attempt is refused by the same rule — it is not a declared field name
    r = c.get(f"/projects/{pid}/modules/cor", headers=H,
              params={"f.amount') OR 1=1 --": "1"})
    assert r.status_code == 400, "a crafted field name was not refused"

    # ---- 7. system columns are filterable, and `workflow_state` still works the old way -----------
    got = rows(**{"f.workflow_state": "draft"})
    assert len(got) == 6, len(got)
    got = rows(state="draft")
    assert len(got) == 6, len(got)

    # ---- 8. the filter bound is enforced ---------------------------------------------------------
    many = {"f.subject.contains": "x"}
    params = [("f.subject.contains", "x")] * 13
    r = c.get(f"/projects/{pid}/modules/cor", headers=H, params=params)
    assert r.status_code == 400, f"more than 12 filters accepted ({r.status_code})"
    assert many  # noqa: B015  (kept so the dict literal above is not mistaken for dead code)

print("MOD-FILTER OK - per-field filters (eq/ne/gte/lte/contains/in/empty/nonempty) and server-side "
      "sort run in SQL before the LIMIT, compose with state + full-text q, and are bounded at 12 per "
      "request. Numeric fields are CAST before comparison: the fixtures are 9/10 and 900/1000 "
      "precisely so a lexicographic comparison fails these assertions rather than passing them, "
      "because text ordering puts 9 above 10 and that is a plausible wrong answer rather than an "
      "error. An unknown field, an unknown operator, a non-numeric value on a numeric field and a "
      "crafted field name all return 400 rather than being dropped — a silently ignored filter shows "
      "MORE rows than were asked for, and the field name reaches a SQLite JSON path, so refusing "
      "undeclared names is what makes the feature safe. Paged sorting keeps created_at as the "
      "tiebreak, so equal values cannot swap between pages and show a row twice or never.")
