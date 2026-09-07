"""REF-LABEL — a report and a spreadsheet stop naming a firm by its uuid.

REF-SORT made a register ORDER by what it renders. Two consumers still rendered the stored value,
both of them outside the web register where `refCell` does the resolving:

* **A grouped report.** `group_by=supplier_company` returned `key='730b6f2e-38ec-…'` — a chart whose
  categories are opaque ids — and split ONE firm in two: rows that linked the company record grouped
  under its id, rows that typed the name grouped under NULL. Measured on a live client.
* **The CSV export.** The uuid went into the reference column, so the sheet forwarded to accounting
  reads an id where a firm name belongs.

**The two fixes are deliberately different shapes, and the difference is the point.**

A group key is display-only, so it is *replaced*: grouping is on the folded display expression, and
the label is `min()` of the unfolded one so the group reads `Acme Electrical`, not `acme electrical`.
Merging uses PAIR-FILTER's rule — a typed name EXACTLY equal to the record's title, never a
substring — so the report and the filter agree on what "this firm" means.

A CSV column is NOT display-only: `imports.py` maps headers back onto fields, so export -> edit ->
re-import is a supported round-trip. Writing the title into the reference column would read better
and silently convert a linked record into loose text on the way back. So the export *adds* a
`__label` column and leaves the id alone. **That claim is asserted through the real importer below,
not argued from the suffix** — a header that did collide would be silently mis-mapped, not refused.

Run: PYTHONPATH=src ./.venv/bin/python test_ref_label.py
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_reflabel.db"
os.environ["STORAGE_DIR"] = "./test_reflabel_storage"

for f in ("./test_reflabel.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import imports  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.modules_query import is_pair_display  # noqa: E402
from aec_api.modules_registry import REGISTRY  # noqa: E402

FAILED: list[str] = []


def check(label, cond, detail=""):
    (print(f"PASS  {label}   {detail}") if cond
     else (FAILED.append(label), print(f"FAIL  {label}   {detail}")))


with TestClient(app) as c:
    # REGISTRY loads on app STARTUP, not on import. The first draft of this file read it at module
    # scope and died with KeyError('delivery') — which is the lucky failure, because the SAME mistake
    # in `test_pair_filter.py` (shipped in #469) swept an empty dict and reported the tree clean.
    # A KeyError is loud; a sweep over nothing is silent and looks exactly like a pass.
    check("the module registry is loaded before anything is read from it", len(REGISTRY) > 130,
          f"{len(REGISTRY)} modules — 0 at import time, which is how a sweep passes vacuously")

    # ---- which fields get the treatment ----------------------------------------------------------
    _DEL = REGISTRY["delivery"]
    check("a reference field renders something other than it stores",
          is_pair_display(_DEL, "supplier_company"))
    check("the TEXT half of a pair does too", is_pair_display(_DEL, "supplier"),
          "COL-PAIR renders the linked record into this column when the text is empty")
    check("an ordinary select field does NOT", not is_pair_display(_DEL, "status"),
          "this is what keeps grouping a select field byte-for-byte as it was")
    check("an unpaired text field does NOT", not is_pair_display(_DEL, "po_number"))
    check("an unknown name does NOT", not is_pair_display(_DEL, "no_such_field"))

    pid = c.post("/projects", json={"name": "Ref Label"}).json()["id"]
    pid2 = c.post("/projects", json={"name": "Other"}).json()["id"]

    def mk(key, data, project=None):
        r = c.post(f"/projects/{project or pid}/modules/{key}", json={"data": data})
        assert r.status_code in (200, 201), (key, r.status_code, r.text[:300])
        return r.json()

    acme = mk("company", {"name": "Acme Electrical", "type": "Subcontractor"})["id"]
    foreign = mk("company", {"name": "Zzz Foreign", "type": "Subcontractor"}, project=pid2)["id"]

    made = [
        mk("delivery", {"description": "linked", "supplier_company": acme, "date": "2026-01-01"}),
        mk("delivery", {"description": "typed", "supplier": "Acme Electrical", "date": "2026-01-02"}),
        mk("delivery", {"description": "typed-lower", "supplier": "acme electrical", "date": "2026-01-03"}),
        mk("delivery", {"description": "other-firm", "supplier": "Beta Supply", "date": "2026-01-04"}),
        mk("delivery", {"description": "cross", "supplier_company": foreign, "date": "2026-01-05"}),
    ]

    def groups(field):
        r = c.get(f"/projects/{pid}/modules/delivery/aggregate",
                  params={"group_by": field, "agg": "count"})
        assert r.status_code == 200, (r.status_code, r.text[:300])
        return {g["key"]: g["count"] for g in r.json()["groups"]}

    g = groups("supplier_company")
    check("a group key is the record's TITLE, not its uuid", "Acme Electrical" in g,
          f"keys: {sorted(k for k in g if k)}")
    # The contract is narrower than "no key is ever a uuid", and the first draft of this file asserted
    # the wider thing and failed — correctly. A reference this project CANNOT resolve (here, one
    # pointing into another project) still groups under its stored id, and that is deliberate:
    # folding it into the blank group would make an unresolvable link indistinguishable from "no
    # supplier at all", hiding a real data problem behind a tidier chart. `refCell` makes the same
    # call in the register — it shows the id and marks it unresolved rather than inventing a label.
    # So: a RESOLVABLE reference never groups under a uuid, and an unresolvable one deliberately does.
    def uuidish(k):
        return bool(k) and len(str(k)) == 36 and str(k).count("-") == 4

    check("no RESOLVABLE reference groups under a uuid",
          not [k for k in g if uuidish(k) and k != foreign],
          f"{[k for k in g if uuidish(k) and k != foreign]}")
    check("an UNRESOLVABLE reference keeps its id rather than merging into the blank group",
          g.get(foreign) == 1,
          "a cross-project link is a data problem; a report that hides it is worse than an ugly key")
    check("the linked row and the typed rows are ONE firm", g.get("Acme Electrical") == 3,
          f"got {g.get('Acme Electrical')} — 1 linked + 2 typed, one of them lower-case")
    check("the label keeps the record's own casing", "acme electrical" not in g,
          "grouping folds so variants merge; min() of the UNFOLDED value is what is shown")
    # The load-bearing negative. Without exact-title matching, a merge rule loose enough to be useful
    # would also swallow this row, and the report would overstate one firm's volume.
    check("a different firm stays its own group", g.get("Beta Supply") == 1)
    check("a cross-project reference does not borrow the foreign title", "Zzz Foreign" not in g,
          "resolving by id alone would pull another project's record name into this report")
    check("every record is still counted", sum(g.values()) == len(made),
          f"{sum(g.values())} of {len(made)} — a group_by that drops rows is AGG-OUTER again")

    check("grouping by the TEXT half gives the same answer", groups("supplier") == g,
          "both halves of a pair name the same thing, so they must report the same thing")

    # ---- the regression that matters most: ordinary fields are untouched ---------------------------
    #
    # Folding is applied ONLY where a column renders something other than it stores. If it leaked to
    # every group_by, a status of "Open" and one of "open" would silently merge — a different report,
    # produced by a change nobody asked for.
    mk("delivery", {"description": "s1", "status": "Open", "date": "2026-02-01"})
    mk("delivery", {"description": "s2", "status": "open", "date": "2026-02-02"})
    st = groups("status")
    check("an ordinary select field does not start folding case",
          st.get("Open") == 1 and st.get("open") == 1, f"{ {k: v for k, v in st.items() if k} }")

    # ---- the CSV export ---------------------------------------------------------------------------
    r = c.get(f"/projects/{pid}/modules/delivery/export.csv")
    assert r.status_code == 200, r.status_code
    csv_text = r.text
    header = csv_text.split("\n")[0].split(",")
    check("the reference column still carries the id", "supplier_company" in header)
    check("a label column is added beside it", "supplier_company__label" in header)
    check("the label sits immediately after its own column",
          header.index("supplier_company__label") == header.index("supplier_company") + 1,
          "adjacent, so a reader sees the name next to the id rather than hunting for it")
    check("the linked record's title reaches the sheet", "Acme Electrical" in csv_text)
    check("the id is NOT replaced", acme in csv_text,
          "replacing it would read better and break re-import; see the round-trip check below")
    linked_row = next(ln for ln in csv_text.split("\n") if ln.startswith("DEL-001"))
    cells = linked_row.split(",")
    check("the label cell holds the title",
          cells[header.index("supplier_company__label")] == "Acme Electrical", linked_row[:120])
    typed_row = next(ln for ln in csv_text.split("\n") if ln.startswith("DEL-002"))
    tcells = typed_row.split(",")
    check("a row with no link gets an EMPTY label, not an invented one",
          tcells[header.index("supplier_company__label")] == "",
          "the typed name is already in its own column; inventing a label here would duplicate it")

    # The label resolution is a lookup by caller-stored id, so it is the same IDOR shape PAIR-FILTER
    # was pulled up on: without `project_id` in the WHERE clause, a row holding another project's
    # record id would print THAT project's company name into this project's spreadsheet. A mutation
    # removing the scope survived every other assertion in this file, which is what this case is for.
    cross_row = next(ln for ln in csv_text.split("\n") if ln.startswith("DEL-005"))
    xcells = cross_row.split(",")
    check("a cross-project reference resolves to NOTHING in the sheet",
          xcells[header.index("supplier_company__label")] == "",
          f"leaked {xcells[header.index('supplier_company__label')]!r} — the foreign record's title")
    check("...and the row still carries its id, so the broken link stays visible",
          xcells[header.index("supplier_company")] == foreign)

    # ---- THE round-trip claim, asserted through the real importer ---------------------------------
    #
    # "Additive" is only true if the importer ignores the new column. `imports._norm` strips
    # non-alphanumerics, so `supplier_company__label` -> `suppliercompanylabel`, which matches no
    # field — but that is a fact to CHECK, not to reason about: a colliding header would be silently
    # mapped onto a real field and would overwrite it on the next import.
    headers_parsed, _body = imports.parse_table(csv_text.encode(), "delivery.csv")
    mapping = imports.suggest_mapping(headers_parsed, imports.importable_fields("delivery"))
    check("the importer still maps the reference column to its field",
          mapping.get("supplier_company") == "supplier_company", f"{mapping.get('supplier_company')!r}")
    check("the importer maps the LABEL column to nothing at all",
          "supplier_company__label" not in mapping,
          "if this ever fails, the export is no longer additive and a re-import would corrupt a field")
    check("no label column is mapped anywhere in the sheet",
          not [h for h in mapping if h.endswith("__label")], f"{sorted(mapping)}")

    # And the same, derived across every shipped module rather than for `delivery` alone: no module
    # declares a field whose name would normalise onto some other field's `__label` header.
    collisions = []
    for mkey, m in REGISTRY.items():
        norms = {imports._norm(f["name"]) for f in m.get("fields", [])}
        norms |= {imports._norm(f.get("label") or "") for f in m.get("fields", [])}
        for f in m.get("fields", []):
            if f.get("type") == "reference" and imports._norm(f["name"] + "__label") in norms:
                collisions.append(f"{mkey}.{f['name']}")
    check("no module has a field that would collide with a __label header", not collisions,
          f"{collisions}" if collisions else f"checked all {len(REGISTRY)} modules, not just delivery")

print(("FAILED: " + "; ".join(FAILED)) if FAILED else "test_ref_label OK")
raise SystemExit(1 if FAILED else 0)
