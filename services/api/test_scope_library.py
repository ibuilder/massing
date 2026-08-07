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
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_scope_library.db"
os.environ["STORAGE_DIR"] = "./test_storage_scope_library"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_scope_library.db",):
    if os.path.exists(_f):
        os.remove(_f)

from aec_api import scope_library as sl  # noqa: E402
from aec_data.disciplines import MF_DIVISIONS  # noqa: E402

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

# --- the SAME invariant from the other side, which is how the defect got through ------------------
#
# The assertion above guards one direction: nothing from Exhibit A reaches the agreement body. Nothing
# guarded the exhibit itself, and `_exhibit_flowables` rendered every id it was given. For a plumbing
# subcontract that meant 31 clauses in the signed PDF against 11 in the preview, and the 20 conditions
# clauses printed TWICE in one document — Article 3 and Exhibit A both.
#
# A one-directional check on a two-directional invariant is exactly as convincing as a correct one and
# covers half the ground. So: assert the partition, both ways, against the renderer's own selection.
from aec_api import contracts as _contracts  # noqa: E402

_ids = sl.default_ids("plumbing")
_exhibit = [c for c in sl.clauses_by_ids(_ids) if c["category"] in sl.EXHIBIT_CATEGORIES]
_body = [c for c in sl.clauses_by_ids(_ids) if c["category"] not in sl.EXHIBIT_CATEGORIES]

check("the exhibit and the agreement body are disjoint",
      not ({c["id"] for c in _exhibit} & {c["id"] for c in _body}),
      "a clause printed in both is printed twice in one signed subcontract")
check("...and together they account for every selected clause",
      len(_exhibit) + len(_body) == len(sl.clauses_by_ids(_ids)),
      "a partition that loses clauses silently drops them from the document")

# The renderer, not a re-implementation of it: count the Paragraph flowables it actually emits. Two
# are the title and subtitle, then two per clause (heading + body).
try:
    _flow = _contracts._exhibit_flowables(_contracts._styles(), {
        "project": "P", "vendor": "V", "trade": "plumbing"}, None)
    _rendered = (len([f for f in _flow if type(f).__name__ == "Paragraph"]) - 2) // 2
    check("the PDF exhibit renders exactly what the preview returns",
          _rendered == len(_exhibit),
          f"PDF renders {_rendered}, preview returns {len(_exhibit)} — what is signed is not what "
          f"was shown")
except AttributeError as e:  # pragma: no cover — the helper was renamed
    check("the PDF exhibit renders exactly what the preview returns", False,
          f"could not reach the renderer: {e}. This check must be repaired, not deleted — it is the "
          f"only thing tying the signed document to the preview.")

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

# --- the routes, over HTTP -----------------------------------------------------------------------
# Asserted through TestClient and `/openapi.json` rather than by walking `app.routes`: this app builds
# its routers lazily, so `app.routes` reports wrapper objects with no real paths and a live route
# reads as missing. The generated schema is what a client actually sees.
from fastapi.testclient import TestClient  # noqa: E402

from aec_api.main import app  # noqa: E402

with TestClient(app) as client:
    paths = client.get("/openapi.json").json()["paths"]
    check("both scope routes are published in the schema",
          {"/scope-library", "/scope-library/exhibit"} <= set(paths),
          f"missing {sorted({'/scope-library', '/scope-library/exhibit'} - set(paths))}")

    full = client.get("/scope-library")
    check("GET /scope-library answers", full.status_code == 200, f"{full.status_code} {full.text[:120]}")
    all_clauses = full.json()["clauses"]
    check("...with the whole catalog when unfiltered", len(all_clauses) > 200, f"{len(all_clauses)}")
    check("...and reports the divisions available to filter by",
          len(full.json()["divisions"]) >= 15, str(full.json()["divisions"])[:80])

    narrowed = client.get("/scope-library", params={"trade": "Plumbing"}).json()
    # The property is "no OTHER trade's clauses", not a ratio. An earlier version of this asserted
    # `< 1/3 of the catalog` and failed at 85/249 — the code was right and the bar was invented. The
    # universal clauses (62) and the curated conditions (13) are deliberately offered alongside every
    # division, so a correct narrowing is still most of what a composer shows.
    other_div = sorted({c["division"] for c in narrowed["clauses"]
                        if c.get("division") and c["division"] != "22"})
    check("?trade= excludes every other division's clauses", not other_div,
          f"pulled divisions {other_div} into a plumbing composer")
    check("...and is meaningfully smaller than the whole catalog",
          len(narrowed["clauses"]) < len(all_clauses),
          f"{len(narrowed['clauses'])} of {len(all_clauses)} — the filter did nothing")
    check("...while still offering the universal clauses that apply to every trade",
          sum(1 for c in narrowed["clauses"] if not c.get("division")) > 30,
          "narrowing dropped the general requirements a subcontract still needs")
    check("...and resolves the trade to its division for the caller",
          narrowed["division"] == "22" and narrowed["division_name"] == MF_DIVISIONS["22"],
          f"{narrowed['division']!r}/{narrowed['division_name']!r}")
    check("an UNKNOWN trade returns the full catalog rather than an empty one",
          len(client.get("/scope-library", params={"trade": "Basketweaving"}).json()["clauses"])
          == len(all_clauses),
          "an empty composer reads as 'no clauses exist' rather than 'we could not map that trade'")

    ex = client.get("/scope-library/exhibit", params={"trade": "Plumbing"})
    check("GET /scope-library/exhibit answers", ex.status_code == 200,
          f"{ex.status_code} {ex.text[:120]}")
    body = ex.json()
    check("the exhibit is assembled and numbered",
          body["clauses"] and all(c.get("number") for c in body["clauses"]),
          f"{len(body.get('clauses', []))} clauses")
    check("...carries bodies, so the composer can preview what will be signed",
          all(c.get("body", "").strip() for c in body["clauses"]))
    check("...contains ONLY exhibit categories — conditions belong to the agreement body",
          {c["category"] for c in body["clauses"]} <= sl.EXHIBIT_CATEGORIES,
          f"{sorted({c['category'] for c in body['clauses']})} — a caller would render these twice "
          f"in one contract package")
    check("...and says what is NOT included, not just what is",
          body["counts"].get("Exclusions", 0) > 0, str(body["counts"]))
    # Derived from the library rather than hand-picked: a literal id here would silently stop
    # exercising the override the day that clause is renamed, and the check would still pass.
    _two = [c["id"] for c in sl.CLAUSES if c["category"] in sl.EXHIBIT_CATEGORIES][:2]
    picked = client.get("/scope-library/exhibit", params={"clauses": ",".join(_two)}).json()
    check("an explicit clause list overrides the trade default",
          [c["id"] for c in picked["clauses"]] == _two,
          f"asked for {_two}, got {[c['id'] for c in picked['clauses']]}")
    check("...and the preview path is the same one the signed PDF renders from",
          set(sl.default_ids("Plumbing")) >= {c["id"] for c in body["clauses"]},
          "the preview showed clauses document.pdf would not — two code paths that can drift")

print(f"\ntest_scope_library {'OK' if not failures else 'FAILED: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
