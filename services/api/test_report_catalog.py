"""One answer to "what reports do I have in this project?" — built-in and saved, in one list.

R22-REPORT-BUILDER item 5. `reports.REPORTS` (56 code-defined reports) and the saved-view layer were
two registries that knew nothing about each other, rendered in two panels. The entry asked for them
to be unified **or** for the separation to be deliberate and recorded.

**The decision: separate implementations, one surface.** They are not the same kind of thing —

* a built-in report is CODE (Earned Value, WIP schedule, tri-approach appraisal), computing things no
  query builder expresses; folding it into saved views means either a query language that can do EVM,
  or 56 rows of config that secretly dispatch to Python;
* a saved view is DATA — a user's query, authored without an engineering ticket, which is the entire
  point of the item.

What was actually wrong was the *surface*: one question, two unrelated answers. `GET
/projects/{pid}/reports/catalog` is the one answer, and `kind` is explicit because the two differ in
what a caller may do with them — a built-in renders to PDF at a fixed path, a saved view is replayed
against its module. A UI inferring that from the shape of an id will infer it wrong.

The assertions that matter are the ones that would fail if the surface silently dropped a half: both
kinds present, the saved half honouring the same scope rules as `list_views`, and the counts
self-consistent with the list they describe.

Run: cd services/api && PYTHONPATH=src:../data/src ./.venv/bin/python test_report_catalog.py
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./_report_catalog.db")
os.environ.setdefault("STORAGE_DIR", "./_storage_report_catalog")
for _f in ("./_report_catalog.db",):
    if os.path.exists(_f):
        os.remove(_f)

from aec_api import reports  # noqa: E402
from aec_api.db import SessionLocal, engine  # noqa: E402
from aec_api.models import Base, SavedView  # noqa: E402
from aec_api.modules_registry import load_registry  # noqa: E402
from aec_api.routers.reports import project_report_catalog  # noqa: E402

load_registry()
Base.metadata.create_all(engine)

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAILED.append(name)


PID, ALICE, BOB = "P-cat", "alice@example.com", "bob@example.com"

# Anti-vacuity on the built-in half: if REPORTS emptied, "both kinds present" could pass on saved
# views alone and the catalog would be quietly half a catalog.
builtin_n = len(reports.catalog())
check("the built-in registry is non-empty", builtin_n >= 20, f"{builtin_n} built-in reports")

db = SessionLocal()
try:
    db.add_all([
        SavedView(project_id=PID, module="rfi", user=ALICE, name="Alice private",
                  scope="private", config={}),
        SavedView(project_id=PID, module="rfi", user=ALICE, name="Team open",
                  scope="project", config={}),
        SavedView(project_id="P-other", module="rfi", user=ALICE, name="Elsewhere",
                  scope="project", config={}),
    ])
    db.commit()

    cat = project_report_catalog(PID, db=db, user=BOB)
    rows = cat["reports"]
    kinds = {r["kind"] for r in rows}
    names = {r["name"] for r in rows}

    check("the catalog carries BOTH kinds", kinds == {"built_in", "saved_view"}, str(sorted(kinds)))
    check("...and every built-in report appears", cat["built_in"] == builtin_n,
          f"{cat['built_in']} of {builtin_n}")
    check("the counts describe the list they came with",
          cat["built_in"] + cat["saved"] == len(rows), f"{cat['built_in']}+{cat['saved']} vs {len(rows)}")

    check("a project-scoped saved view reaches another user's catalog", "Team open" in names)
    check("...a private one does not", "Alice private" not in names, str(sorted(names & {"Alice private"})))
    check("...and another project's shared view does not", "Elsewhere" not in names)

    saved = [r for r in rows if r["kind"] == "saved_view"]
    check("a saved view says which module it replays against",
          all(r["module"] for r in saved), str([(r["name"], r["module"]) for r in saved]))
    check("a built-in report has no module, because it is code not a query",
          all(r["module"] is None for r in rows if r["kind"] == "built_in"))

    a_cat = project_report_catalog(PID, db=db, user=ALICE)
    a_names = {r["name"] for r in a_cat["reports"]}
    check("the author still sees her own private view", "Alice private" in a_names)
    check("...so the two callers genuinely differ", a_cat["saved"] == cat["saved"] + 1,
          f"alice {a_cat['saved']} vs bob {cat['saved']}")
finally:
    db.close()

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print(
    f"REPORT CATALOG OK - {builtin_n} built-in reports and the project's saved views answer one "
    "question in one list, each labelled by kind, with the saved half obeying the same scope rules "
    "as the register's own view list."
)
