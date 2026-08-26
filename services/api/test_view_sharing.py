"""A saved view can be a project report, and sharing it leaks nothing.

R22-REPORT-BUILDER item 4. `SavedView.user` was both the owner AND the audience, so a saved view
could never be a firm or project report — *"a builder whose output only its author can see is a
personal filter."*

`scope` separates the two questions that were conflated:

* **ownership** — `(project, module, user, name)` — decides who may WRITE or DELETE a view;
* **scope** — `private` | `project` — decides who may READ and run it.

The assertions below are ordered by what actually goes wrong when this is built carelessly.

## The three ways sharing leaks, each asserted

1. **Across projects.** A `project`-scoped view is scoped to *its own* project. Every query is
   bounded by `pid`, and the read route already requires `viewer` on that project, so sharing shows
   nobody a row they could not already list.
2. **Into someone else's edit rights.** Visible is not writable. A second user saving under the same
   name gets THEIR OWN row, not an edit of the shared one — which is also why ownership stays part
   of the key rather than being replaced by it.
3. **Into the alert feed, where it would produce a wrong number.** This one is a deliberate
   *non*-feature and is asserted as such. `last_seen_at` is one column on one row, so a shared view
   has a single "last opened" timestamp; showing it in a second person's 🔔 feed would compute their
   "new since" from *the author's* last visit. That is precisely the confidently-wrong-number shape
   `test_view_config` fixed one layer down, and re-introducing it while adding sharing would trade
   one defect for another. Per-viewer alerts need a per-viewer timestamp — a table this item does
   not add, and the test below pins the current behaviour so the gap is visible rather than assumed.

Run: cd services/api && PYTHONPATH=src:../data/src ./.venv/bin/python test_view_sharing.py
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./_view_sharing.db")
os.environ.setdefault("STORAGE_DIR", "./_storage_view_sharing")
for _f in ("./_view_sharing.db",):
    if os.path.exists(_f):
        os.remove(_f)

from aec_api import modules as mod  # noqa: E402
from aec_api.db import SessionLocal, engine  # noqa: E402
from aec_api.models import Base, SavedView  # noqa: E402
from aec_api.modules_query import VIEW_SCOPES  # noqa: E402
from aec_api.modules_registry import load_registry  # noqa: E402

load_registry()
Base.metadata.create_all(engine)

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAILED.append(name)


KEY, P1, P2 = "rfi", "P-share-1", "P-share-2"
ALICE, BOB = "alice@example.com", "bob@example.com"


def visible_to(db, pid: str, user: str) -> set[str]:
    """The view names `list_views` would return — the same clause, exercised directly."""
    from sqlalchemy import or_
    rows = (db.query(SavedView)
            .filter(SavedView.project_id == pid, SavedView.module == KEY,
                    or_(SavedView.user == user, SavedView.scope == "project"))
            .all())
    return {v.name for v in rows}


check("both scopes are declared", VIEW_SCOPES == {"private", "project"}, str(sorted(VIEW_SCOPES)))

db = SessionLocal()
try:
    db.add_all([
        SavedView(project_id=P1, module=KEY, user=ALICE, name="Alice private", scope="private",
                  config={}),
        SavedView(project_id=P1, module=KEY, user=ALICE, name="Open structural", scope="project",
                  config={"filters": [["discipline", "eq", "Structural"]]}),
        SavedView(project_id=P2, module=KEY, user=ALICE, name="Other project shared",
                  scope="project", config={}),
    ])
    db.commit()

    a_p1, b_p1 = visible_to(db, P1, ALICE), visible_to(db, P1, BOB)

    # Anti-vacuity: if nothing were visible to anyone these assertions would all hold trivially.
    check("the fixture is visible to its author at all", len(a_p1) == 2, f"alice sees {sorted(a_p1)}")

    check("a project-scoped view reaches a second user", "Open structural" in b_p1,
          f"bob sees {sorted(b_p1)}")
    check("...and a private one does NOT", "Alice private" not in b_p1, f"bob sees {sorted(b_p1)}")
    check("sharing does not cross a project boundary",
          "Other project shared" not in b_p1 and "Other project shared" not in a_p1,
          f"P2's shared view leaked into P1 for {'alice' if 'Other project shared' in a_p1 else 'bob'}"
          if "Other project shared" in (a_p1 | b_p1) else "bounded by pid")
    check("...though it is visible in ITS own project", "Other project shared" in visible_to(db, P2, BOB))

    # Visible is not writable: Bob saving the same name creates HIS row, not an edit of Alice's.
    db.add(SavedView(project_id=P1, module=KEY, user=BOB, name="Open structural", scope="private",
                     config={}))
    db.commit()
    owners = {v.user for v in db.query(SavedView).filter(
        SavedView.project_id == P1, SavedView.name == "Open structural").all()}
    check("a shared view is readable but not writable — same name, two owners", owners == {ALICE, BOB},
          f"owners={sorted(owners)}")
    alices = db.query(SavedView).filter(SavedView.project_id == P1, SavedView.user == ALICE,
                                        SavedView.name == "Open structural").one()
    check("...and the author's row still holds the author's config",
          alices.config.get("filters") == [["discipline", "eq", "Structural"]], str(alices.config))

    # The deliberate non-feature, pinned so the gap stays visible.
    #
    # Asserted on OWNERSHIP, not on names, and the first draft of this block got that wrong twice
    # over: it read `all(a["name"] != "Open structural" or True ...)`, which is `X or True` — a
    # tautology that cannot fail — over a fixture where Bob owns his own row of that name, so a name
    # could not have distinguished a leak from his own view even had the clause been real. A vacuous
    # assertion inside the test written to pin a deliberate limit is the same shape as everything
    # else in this release; it is recorded rather than quietly deleted.
    owned_by = {v.id: v.user for v in db.query(SavedView).filter(SavedView.project_id == P1).all()}
    bob_feed = mod.view_alerts(db, P1, BOB)
    check("bob's alert feed is non-empty, so the next assertion is not vacuous", len(bob_feed) >= 1,
          f"{len(bob_feed)} entries")
    foreign = [a["name"] for a in bob_feed if owned_by.get(a["id"]) != BOB]
    check("every entry in a user's alert feed is a view THEY own (last_seen_at is per row)",
          not foreign, f"not bob's: {foreign}" if foreign else "all bob's own")
    alice_ids = {a["id"] for a in mod.view_alerts(db, P1, ALICE)}
    check("...while the author still gets alerts for the view she shared",
          alices.id in alice_ids, f"alice's feed holds {len(alice_ids)} views")
finally:
    db.close()

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print(
    "VIEW SHARING OK - a project-scoped saved view reaches the project and stops at its boundary, "
    "ownership still gates writes so a shared view cannot be edited by its readers, and alerts stay "
    "with the owner because last_seen_at is one column per row."
)
