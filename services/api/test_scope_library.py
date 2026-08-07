"""SCOPE-LIBRARY — the clause library grew 13 -> 249, and the contract documents still work.

WHAT CHANGED. `scope_library` held 13 hand-written clauses: general conditions, supplementary
conditions, and six trade "Scope" paragraphs. It now also carries 236 clauses imported from the
ScopeMaker seed library (the user's own `ibuilder/procore-exhibit-generator`), division-scoped and
split into inclusions, exclusions and clarifications.

WHY THAT MATTERS MORE THAN THE COUNT. A subcontract is not argued over its general conditions. It is
argued over what is and is not in the subcontractor's number, and the curated 13 contained **no
exclusions at all** — every scope it produced was silent on the boundary. 69 of the imported clauses
are exclusions. That is the actual capability being added; 249 is just the size of it.

THE THREE WAYS THIS COULD BREAK QUIETLY, each asserted below:

  1. `contracts.py` composes the agreement body from every clause whose category is not an exhibit
     category. It used to test `!= "Scope"`, which was complete when "Scope" was the only exhibit
     category. With exclusions in the library that test silently prints the SUBCONTRACTOR's
     exclusions into the AGREEMENT body, where they read as the Contractor's own carve-outs. Hence
     `EXHIBIT_CATEGORIES`, and hence the assertion that an exclusion never reaches the agreement.
  2. `_BY_ID` is a dict. A clause id colliding between the curated and imported halves would shadow
     one of them with no error at all — the exhibit would simply be missing a paragraph.
  3. `division` is a CSI MasterFormat key, and `aec_data.disciplines.MF_DIVISIONS` is the only
     authority for those (DISC-SSOT). A clause naming a division the spine does not have would render
     under a blank heading rather than fail.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_scope_library.py
"""
import sys

from aec_api import scope_library as sl
from aec_data.disciplines import MF_DIVISIONS

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail and not ok else ''}")
    if not ok:
        failures.append(name)


# --- the library is actually bigger, and not vacuously ------------------------------------------
check("the library carries both halves", len(sl.CLAUSES) > 200, f"{len(sl.CLAUSES)} clauses")
check("the curated half survived the merge",
      all(any(c["id"] == cur["id"] for c in sl.CLAUSES) for cur in sl._CURATED),
      "a hand-written clause was lost when the imported half was added")

ids = [c["id"] for c in sl.CLAUSES]
check("no clause id is claimed twice — a collision SHADOWS one silently",
      len(ids) == len(set(ids)),
      f"{len(ids) - len(set(ids))} duplicate(s): "
      f"{[i for i in set(ids) if ids.count(i) > 1][:4]}")

# --- DISC-SSOT: divisions come from the spine, not from a second copy ----------------------------
bad_div = sorted({c["division"] for c in sl.CLAUSES
                  if c.get("division") and c["division"] not in MF_DIVISIONS})
check("every clause division exists in the MasterFormat spine", not bad_div,
      f"{bad_div} not in MF_DIVISIONS — the clause would render under a blank heading")
check("division_name reads the spine", sl.division_name("22") == MF_DIVISIONS["22"],
      f"got {sl.division_name('22')!r}, spine says {MF_DIVISIONS['22']!r}")
check("...and a universal clause has no division name", sl.division_name(None) is None)

# --- the capability that was actually missing ----------------------------------------------------
exclusions = [c for c in sl.CLAUSES if c["category"] == "Exclusions"]
check("the library can now say what is NOT in scope", len(exclusions) > 20,
      f"only {len(exclusions)} exclusions — the boundary is what a subcontract argument is about")
divs_with_both = {d for d in MF_DIVISIONS
                  if any(c.get("division") == d and c["category"] == "Scope" for c in sl.CLAUSES)
                  and any(c.get("division") == d and c["category"] == "Exclusions" for c in sl.CLAUSES)}
check("multiple divisions carry inclusions AND exclusions", len(divs_with_both) >= 10,
      f"only {len(divs_with_both)} divisions have both")

# --- trade scoping actually narrows ---------------------------------------------------------------
everything = sl.default_ids(None)
plumbing = sl.default_ids("Plumbing")
check("a recognised trade narrows the exhibit", len(plumbing) < len(everything) / 3,
      f"plumbing={len(plumbing)} vs all={len(everything)} — an exhibit nobody reads hides scope gaps")
p_divs = {sl._BY_ID[i].get("division") for i in plumbing
          if sl._BY_ID[i]["category"] in sl.EXHIBIT_CATEGORIES}
check("...to its own division (plus universal/curated)", p_divs <= {"22", None},
      f"plumbing exhibit pulled divisions {sorted(d for d in p_divs if d)}")
check("an UNRECOGNISED trade falls back rather than returning an empty exhibit",
      len(sl.default_ids("Landscaping")) == len(everything),
      "an unknown trade produced a narrowed — and therefore wrong — exhibit")
check("division_for_trade refuses to guess", sl.division_for_trade("Landscaping") is None
      and sl.division_for_trade("plumbing") == "22",
      "guessing a division silently fills an exhibit with the wrong trade's inclusions")

# --- defect (1): the agreement body must not print the subcontractor's exclusions -----------------
agreement = [x for x in sl.default_ids("Plumbing")
             if x not in {s["id"] for s in sl.CLAUSES if s["category"] in sl.EXHIBIT_CATEGORIES}]
leaked = [x for x in agreement if sl._BY_ID[x]["category"] == "Exclusions"]
check("no exclusion reaches the agreement body", not leaked,
      f"{leaked[:3]} printed into the agreement, where they read as the Contractor's carve-outs")
check("...and the agreement body is not empty either", len(agreement) > 3,
      f"{len(agreement)} clauses — a refusal-only assertion passes on an empty list")
check("Scope and Exclusions are both exhibit categories",
      {"Scope", "Exclusions"} <= sl.EXHIBIT_CATEGORIES, str(sorted(sl.EXHIBIT_CATEGORIES)))

# --- the API contracts.py depends on is unchanged in shape ---------------------------------------
sample = sl.clauses_by_ids(sl.default_ids("Concrete"))
check("clauses_by_ids returns renderable clauses", sample
      and all(isinstance(c.get("title"), str) and isinstance(c.get("body"), str) for c in sample),
      "contracts.py renders c['title'] and c['body'] — a missing key is an AttributeError mid-PDF")
check("every clause has a non-empty body", all(c["body"].strip() for c in sl.CLAUSES),
      "an empty clause renders as a numbered blank line in a signed document")
check("merge still substitutes tokens",
      sl.merge("for {{project}}", {"project": "Tower"}) == "for Tower")
check("...and leaves unknown tokens alone rather than emptying them",
      sl.merge("for {{nope}}", {}) == "for {{nope}}",
      "an unresolved token must stay visible — a silently blanked merge field ships a broken contract")
check("library() still exposes the composer catalog",
      {"id", "category", "title"} <= set(sl.library()[0]),
      str(sorted(sl.library()[0])))
check("library(division) narrows the catalog",
      {c.get("division") for c in sl.library("22")} <= {"22", None},
      "the composer would offer another trade's clauses")

# --- numbering: the label has to point at exactly one clause --------------------------------------
numbered = sl.numbered(sl.clauses_by_ids(sl.default_ids("Plumbing")))
nums = [c["number"] for c in numbered]
check("every clause gets a number", len(nums) == len(numbered) and all(nums))
check("no two clauses share a number — 'we agreed to 3.2' must be unambiguous",
      len(nums) == len(set(nums)), f"{len(nums) - len(set(nums))} collision(s)")
check("numbering restarts per section", nums[0] == "1.1",
      f"first clause numbered {nums[0]!r}")
_given = sl.clauses_by_ids(sl.default_ids("Plumbing"))
check("numbering preserves the order it was given",
      [c["id"] for c in numbered] == [c["id"] for c in _given],
      "numbered() must not sort — the caller chose the order, and a resorted exhibit renumbers "
      "clauses that were already cited in negotiation")
check("...and numbered() does not mutate the clauses it was handed",
      all("number" not in c for c in _given),
      "the shared library dicts were written through — every later caller inherits stale numbers")

print(f"\ntest_scope_library {'OK' if not failures else 'FAILED: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
