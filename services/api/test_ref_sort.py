"""REF-SORT — ordering a register by a party column, and the outer join that was quietly an inner one.

PARTY-REFS made "which deliveries are Acme's" *representable*, COL-PAIR made it *visible* and
PAIR-FILTER made it *askable*. Ordering was the half still answering in UUIDs.

**Measured before the fix, on a live client**: sorting `delivery` by `supplier_company` ascending
returned `Delta, Mid Atlantic, Acme, Zeta` — the stored uuid4s in lexical order, under an ascending
arrow. Sorting the register by its *text* half was worse, because COL-PAIR renders that column as the
pair: the four linked rows sorted first as NULLs while DISPLAYING company names, so the column read as
visibly unsorted text under a sort indicator.

The sort key is therefore **what the column renders**, expressed in SQL — the same three-way rule
`refCell` draws and `pairedValue` chooses between: the referenced record's title when the link
resolves, the raw value when it does not (a legacy free-text value is text, not a blank), and the pair
twin when the column's own half is empty. Anything else re-introduces the disagreement between what is
on screen and what the order claims about it.

**The load-bearing assertion in this file is not any particular order — it is that sorting never
changes WHICH rows come back.** Resolving a title needs a join, and a join is one WHERE clause away
from deleting rows; a short list is indistinguishable from "there are none", which is the failure
PAIR-FILTER exists for. Every ordering case below is checked against the unsorted set.

That is not hypothetical here. `aggregate()` already had it: it LEFT-joins the reference target and
then filters `where(or_(join_t.project_id == pid, join_t.id.is_(None)))`. A base row joined to a
record in ANOTHER project satisfies neither arm and is dropped — **a predicate on the nullable side of
an outer join turns it back into an inner one**, defeating the intent its own comment states ("a base
record with no related record still counts"). Measured: three deliveries in the register, the joined
report counted two, with no error and no truncation flag. Nothing validates a reference value on
write, so a cross-project id is reachable, not theoretical. The scope belongs in the ON clause.

Run: PYTHONPATH=src ./.venv/bin/python test_ref_sort.py
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_refsort.db"
os.environ["STORAGE_DIR"] = "./test_refsort_storage"

for f in ("./test_refsort.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402
from aec_api.modules_registry import reference_half, text_half  # noqa: E402

FAILED: list[str] = []


def check(label, cond, detail=""):
    (print(f"PASS  {label}   {detail}") if cond
     else (FAILED.append(label), print(f"FAIL  {label}   {detail}")))


# ---- the inverse rule, before any HTTP ------------------------------------------------------------
#
# `reference_half` asks the REFERENCES which text field they claim, rather than string-building
# `name + "_company"`. The case that would break a string-builder is `assignee_name`, whose reference
# is `assignee_contact`: the stems differ, so the built name would be `assignee_name_contact`, which no
# module declares. The TypeScript copy in `apps/web/src/portal/register/fieldPairs.ts` makes the same
# choice for the same reason.
_FIELDS = {
    "supplier": {"name": "supplier", "type": "text"},
    "supplier_company": {"name": "supplier_company", "type": "reference", "module": "company"},
    "assignee_name": {"name": "assignee_name", "type": "text"},
    "assignee_contact": {"name": "assignee_contact", "type": "reference", "module": "contact"},
    "notes": {"name": "notes", "type": "textarea"},
    "lonely_company": {"name": "lonely_company", "type": "reference", "module": "company"},
}
check("reference_half inverts text_half", reference_half("supplier", _FIELDS) == "supplier_company")
check("reference_half handles the _name spelling",
      reference_half("assignee_name", _FIELDS) == "assignee_contact",
      "a string-builder would look for 'assignee_name_contact', which no module declares")
check("reference_half invents nothing for unclaimed text", reference_half("notes", _FIELDS) is None)
check("reference_half refuses a reference field", reference_half("lonely_company", _FIELDS) is None)
check("the two halves agree", text_half(reference_half("supplier", _FIELDS), _FIELDS) == "supplier")

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Ref Sort"}).json()["id"]
    pid2 = c.post("/projects", json={"name": "Other"}).json()["id"]

    def mk(key, data, project=None):
        r = c.post(f"/projects/{project or pid}/modules/{key}", json={"data": data})
        assert r.status_code in (200, 201), (key, r.status_code, r.text[:300])
        return r.json()

    firms = {n: mk("company", {"name": n, "type": "Subcontractor"})["id"]
             for n in ("Zeta Works", "Acme Electrical", "Mid Atlantic", "delta mechanical")}
    # Named to start with 'z' ON PURPOSE — see the cross-project assertion far below. A uuid4 is
    # [0-9a-f-], so a title sorting after every hex digit makes "resolved" and "not resolved"
    # distinguishable by POSITION, deterministically.
    foreign = mk("company", {"name": "Zzz Foreign Partners", "type": "Subcontractor"},
                 project=pid2)["id"]

    # One register holding every era at once, which is the whole point of the additive pattern:
    # linked rows, typed rows, a row with neither, a legacy free-text value sitting IN the reference
    # field, and a reference to a record in another project.
    rows_made = {
        "linked-zeta": mk("delivery", {"description": "linked-zeta", "supplier_company": firms["Zeta Works"], "date": "2026-01-01"}),
        "linked-acme": mk("delivery", {"description": "linked-acme", "supplier_company": firms["Acme Electrical"], "date": "2026-01-02"}),
        "linked-delta": mk("delivery", {"description": "linked-delta", "supplier_company": firms["delta mechanical"], "date": "2026-01-03"}),
        "typed-mid": mk("delivery", {"description": "typed-mid", "supplier": "Mid Atlantic", "date": "2026-01-04"}),
        "typed-beta": mk("delivery", {"description": "typed-beta", "supplier": "Beta Supply", "date": "2026-01-05"}),
        "legacy-text": mk("delivery", {"description": "legacy-text", "supplier_company": "Nu Systems Inc", "date": "2026-01-06"}),
        "blank": mk("delivery", {"description": "blank", "date": "2026-01-07"}),
        "cross-project": mk("delivery", {"description": "cross-project", "supplier_company": foreign, "date": "2026-01-08"}),
    }
    by_id = {v["id"]: k for k, v in rows_made.items()}

    def listing(**params):
        r = c.get(f"/projects/{pid}/modules/delivery", params=params)
        assert r.status_code == 200, (r.status_code, r.text[:300])
        j = r.json()
        return j.get("items", j) if isinstance(j, dict) else j

    UNSORTED = {x["id"] for x in listing()}
    check("the fixture holds every era", len(UNSORTED) == len(rows_made),
          f"{len(UNSORTED)} rows of {len(rows_made)}")

    def order(**params):
        got = listing(**params)
        # THE load-bearing check, run on every ordering below: a sort orders rows, it does not choose
        # them. A join added to resolve a title is one WHERE clause away from deleting rows, and the
        # result looks like a correct short answer.
        check(f"sorting by {params.get('sort')} {params.get('sort_dir', 'asc')} returns every row",
              {x["id"] for x in got} == UNSORTED,
              f"{len(got)} of {len(UNSORTED)}")
        return [by_id[x["id"]] for x in got]

    # ---- ordering a REFERENCE column by the record it points at ------------------------------------
    asc = order(sort="supplier_company", sort_dir="asc")
    named = [n for n in asc if n in ("linked-acme", "linked-delta", "linked-zeta")]
    check("a reference column orders by the referenced TITLE, not the stored uuid",
          named == ["linked-acme", "linked-delta", "linked-zeta"], f"{named}")
    # `delta mechanical` is stored lower-case on purpose: ordering must fold case the way `_fold`
    # does, or it sorts after `Zeta Works` on a byte comparison.
    check("ordering folds case", asc.index("linked-delta") < asc.index("linked-zeta"),
          "'delta mechanical' before 'Zeta Works' — a byte compare puts lower-case last")

    desc = order(sort="supplier_company", sort_dir="desc")
    named_d = [n for n in desc if n in ("linked-acme", "linked-delta", "linked-zeta")]
    check("descending actually reverses", named_d == ["linked-zeta", "linked-delta", "linked-acme"],
          f"{named_d}")

    # A legacy free-text value inside the reference field is what `refCell` renders verbatim as
    # unlinked text. It must order as that text, not as a blank — it is the only handle anyone has for
    # re-linking the record, and burying it under the empty rows is how it stops being noticed.
    check("a legacy free-text value in a reference field orders as its text",
          asc.index("linked-acme") < asc.index("legacy-text") < asc.index("linked-zeta"),
          "'Nu Systems Inc' sits between Acme and Zeta")

    # ---- ordering the TEXT half, which is the column 19 registers actually list ---------------------
    #
    # This is the direction COL-PAIR made visible and left unordered: the column DISPLAYS the linked
    # record for a linked row, so ordering it by the stored text alone sorts a column of company names
    # by a field that is empty for most of them.
    asc_t = order(sort="supplier", sort_dir="asc")
    interleaved = [n for n in asc_t if n in ("linked-acme", "typed-beta", "linked-delta",
                                             "typed-mid", "linked-zeta")]
    check("the text half orders by what the column SHOWS, interleaving both eras",
          interleaved == ["linked-acme", "typed-beta", "linked-delta", "typed-mid", "linked-zeta"],
          f"{interleaved}")

    # ---- blanks ------------------------------------------------------------------------------------
    #
    # `register.ts` puts blanks last "direction-independent", and said so in a comment, while the
    # server put NULLs first on SQLite ascending. The same register therefore ordered differently
    # depending on which column you clicked, since a column the server cannot sort falls back to the
    # browser comparator. The server now matches the documented rule.
    check("a row with NEITHER half filled sorts last, ascending", asc_t[-1] == "blank", f"{asc_t}")
    check("...and last descending too, which is the half that was inconsistent",
          order(sort="supplier", sort_dir="desc")[-1] == "blank")

    # ---- the project boundary ----------------------------------------------------------------------
    #
    # Same finding PAIR-FILTER hit from the filter side: a record id is caller-supplied and nothing
    # validates it on write, so a row can hold another project's id. Resolving it would leak that
    # record's title into this project's ordering — and dropping the row would be the aggregate bug
    # below. It must resolve to nothing and stay.
    # The FIRST version of this assertion was flaky and passed for the wrong reason. It asserted the
    # row sorted OUTSIDE the range of the linked names — but an unresolved reference sorts by its raw
    # uuid, and a uuid4 lands wherever its first hex digit falls, so the check was a coin toss that
    # happened to come up tails. **"Did not resolve" cannot be phrased as a position among values
    # whose order depends on an id nobody chose.** Naming the foreign company `Zzz…` fixes that: a
    # uuid begins with [0-9a-f], every one of which sorts before `zeta works`, while the resolved
    # title would sort after it. The two hypotheses now differ by position, always.
    check("a cross-project reference does not resolve to the foreign title",
          asc.index("cross-project") < asc.index("linked-zeta"),
          "a resolved 'Zzz Foreign Partners' would sort AFTER 'Zeta Works'; an unresolved uuid "
          "sorts before it, because every hex digit does")
    check("...and the row is still returned", "cross-project" in asc)

    # ---- regressions: the paths this must not have touched ------------------------------------------
    plain = order(sort="date", sort_dir="asc")
    check("an unpaired, non-reference field still sorts", len(plain) == len(UNSORTED))
    lone = order(sort="commitment", sort_dir="asc")
    check("a reference with NO text half still sorts and keeps every row", len(lone) == len(UNSORTED))

    # ---- AGG-OUTER: the join that was an inner join ------------------------------------------------
    r = c.get(f"/projects/{pid}/modules/delivery/aggregate",
              params={"group_by": "description", "agg": "count", "join": "supplier_company"})
    check("a joined aggregate answers at all", r.status_code == 200, r.text[:200])
    if r.status_code == 200:
        groups = r.json()["groups"]
        total = sum(g["count"] for g in groups)
        check("a joined report counts EVERY base row, including a cross-project reference",
              total == len(UNSORTED),
              f"counted {total} of {len(UNSORTED)} — the dropped row is the one whose reference "
              f"crosses a project")
        keys = {g["key"] for g in groups}
        check("the cross-project row is present under its own group", "cross-project" in keys,
              f"groups: {sorted(k for k in keys if k)}")

print(("FAILED: " + "; ".join(FAILED)) if FAILED else "test_ref_sort OK")
raise SystemExit(1 if FAILED else 0)
