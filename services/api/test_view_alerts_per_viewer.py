"""A shared saved view alerts EVERY reader, each from their own last visit.

R22-REPORT-BUILDER item 4 shipped `SavedView.scope` so a view could be read by the project, and
stopped deliberately short of alerting anyone but the author. Its own note said why, and the reason
was good: `saved_views.last_seen_at` was ONE column on ONE row, so a shared view in a second person's
🔔 feed would have computed *their* "new since" from **the author's** last visit — the same
confidently-wrong-number shape as the filter miscount item 3 had just removed one layer down.

    a shared view only alerted its author, and nobody else could clear it either:
    `mark_view_seen` required `v.user == user`, so the one person the feed showed it to
    was the only person allowed to say they had seen it.

`SavedViewSeen` is the per-viewer timestamp that item named. One row per (view, viewer), unique on
the pair — two rows would make "when did I last look at this" ambiguous and the feed would answer
with whichever the query returned first.

## What is actually load-bearing here

Not "a shared view shows up in Bob's feed" — that is the easy half and a `scope == "project"` filter
alone would satisfy it. The half that matters is that **Bob's count is Bob's**: marking a view seen
as Alice must not clear Bob's alert, and marking it seen as Bob must not clear Alice's. Those two
assertions are what a single shared column cannot satisfy, so they are the ones that fail if this is
ever collapsed back.

Run: cd services/api && PYTHONPATH=src:../data/src ./.venv/bin/python test_view_alerts_per_viewer.py
"""
from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta, timezone

os.environ.setdefault("DATABASE_URL", "sqlite:///./_view_alerts_pv.db")
os.environ.setdefault("STORAGE_DIR", "./_storage_view_alerts_pv")
for _f in ("./_view_alerts_pv.db",):
    if os.path.exists(_f):
        os.remove(_f)

from aec_api import modules as mod  # noqa: E402
from aec_api.db import SessionLocal, engine  # noqa: E402
from aec_api.models import Base, SavedView, SavedViewSeen  # noqa: E402
from aec_api.modules_registry import load_registry  # noqa: E402

load_registry()
Base.metadata.create_all(engine)

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAILED.append(name)


def alerts(db, user: str) -> dict[str, dict]:
    return {a["name"]: a for a in mod.view_alerts(db, PID, user)}


def mark_seen(db, view_id: str, user: str, when: datetime) -> None:
    """What the `/seen` route does, at a chosen instant so the test is not a race."""
    row = db.query(SavedViewSeen).filter(SavedViewSeen.view_id == view_id,
                                         SavedViewSeen.user == user).one_or_none()
    if row is None:
        db.add(SavedViewSeen(view_id=view_id, user=user, last_seen_at=when))
    else:
        row.last_seen_at = when
    db.commit()


KEY = "rfi"
PID = "P-alerts-pv"
ALICE, BOB = "alice", "bob"

db = SessionLocal()
try:
    # ---- two records, created at instants we can straddle ------------------------------------------
    old = datetime.now(timezone.utc) - timedelta(days=2)
    for i, disc in enumerate(("Structural", "Mechanical")):
        mod.create_record(db, KEY, PID,
                          {"data": {"subject": f"{disc} RFI", "question": "q?", "discipline": disc}},
                          ALICE, None)
    db.commit()
    # Backdate the first so "since" can separate them. Without this both land in the same instant and
    # every since-based count returns the same number, which would make the assertions below vacuous.
    t = mod.TABLES[KEY]
    ids = [r[0] for r in db.execute(t.select().with_only_columns(t.c.id)).all()]
    db.execute(t.update().where(t.c.id == ids[0]).values(created_at=old))
    db.commit()

    shared = SavedView(project_id=PID, module=KEY, user=ALICE, name="Open RFIs",
                       scope="project", config={})
    private = SavedView(project_id=PID, module=KEY, user=ALICE, name="Alice only",
                        scope="private", config={})
    db.add_all([shared, private])
    db.commit()

    total = mod.count_records(db, KEY, PID)
    check("the fixture has records to count", total == 2, f"{total} records")

    # ---- the shared view reaches a second person's feed at all ------------------------------------
    a = alerts(db, ALICE)
    b = alerts(db, BOB)
    check("the author sees their own shared view", "Open RFIs" in a)
    check("a project-scoped view now reaches a second reader's feed", "Open RFIs" in b, f"{list(b)}")
    check("...and a PRIVATE view still does not", "Alice only" in a and "Alice only" not in b,
          f"bob sees {list(b)}")
    check("the feed says whose view it is", b["Open RFIs"]["mine"] is False
          and b["Open RFIs"]["owner"] == ALICE and a["Open RFIs"]["mine"] is True)

    # ---- never opened by either: everything is new, to both ----------------------------------------
    check("unopened, the author counts every match as new", a["Open RFIs"]["new"] == total,
          f"new={a['Open RFIs']['new']} total={total}")
    check("unopened, the second reader counts every match as new too",
          b["Open RFIs"]["new"] == total, f"new={b['Open RFIs']['new']}")

    # ---- THE assertion: Alice reading it does not clear Bob's alert ---------------------------------
    # A single shared column cannot satisfy this. Alice marks seen between the two records, so her
    # "new" drops to the one created after her visit while Bob's stays at everything.
    between = old + timedelta(days=1)
    mark_seen(db, shared.id, ALICE, between)
    a = alerts(db, ALICE)
    b = alerts(db, BOB)
    check("the author's count drops to what arrived since THEIR visit",
          a["Open RFIs"]["new"] == 1, f"new={a['Open RFIs']['new']} (expected 1 of {total})")
    check("...and the second reader's count is UNTOUCHED by the author reading it",
          b["Open RFIs"]["new"] == total,
          f"new={b['Open RFIs']['new']} (expected {total}) — a shared last_seen_at would say 1 here")

    # ---- and the reverse, so the rule is symmetric rather than a special case ------------------------
    mark_seen(db, shared.id, BOB, datetime.now(timezone.utc))
    a = alerts(db, ALICE)
    b = alerts(db, BOB)
    check("the second reader can clear their OWN alert", b["Open RFIs"]["new"] == 0,
          f"new={b['Open RFIs']['new']}")
    check("...without touching the author's", a["Open RFIs"]["new"] == 1,
          f"new={a['Open RFIs']['new']} (expected 1)")

    # ---- one row per (view, viewer) -----------------------------------------------------------------
    mark_seen(db, shared.id, BOB, datetime.now(timezone.utc))
    rows = db.query(SavedViewSeen).filter(SavedViewSeen.view_id == shared.id,
                                          SavedViewSeen.user == BOB).all()
    check("marking seen twice updates one row rather than adding a second", len(rows) == 1,
          f"{len(rows)} rows for (view, bob)")

    # ---- totals are the view's, not the viewer's ----------------------------------------------------
    # `new` is per viewer; `total` is a property of the view and must NOT diverge between readers, or
    # two people looking at the same shared report would disagree about how many rows it has.
    check("both readers see the same TOTAL for one shared view",
          a["Open RFIs"]["total"] == b["Open RFIs"]["total"] == total,
          f"alice={a['Open RFIs']['total']} bob={b['Open RFIs']['total']}")
    # ---- you must be able to CLEAR what you can SEE -------------------------------------------------
    # Review finding, 2026-08-26. `/views/alerts` is gated at `viewer` and `/views/{vid}/seen` was at
    # `reviewer`. That mismatch was unreachable while a viewer's feed only ever held their own views;
    # per-viewer alerts made it reachable, and a viewer would have seen shared views they got a 403
    # trying to clear — a permanent "N new" badge, with the 403 swallowed by the UI.
    #
    # Asserted as the INVARIANT rather than as two literals: whatever role shows a view in the feed
    # must also be enough to record having read it. Pinning both to the string "viewer" would pass
    # just as well if somebody raised one of them.
    import inspect  # noqa: PLC0415

    from aec_api.routers import modules as mod_routes  # noqa: PLC0415

    def role_gate(fn) -> str | None:
        """The `min_role` a handler's `require_role` dependency was built with.

        Read off the FUNCTION rather than off `app.routes`: this API mounts its routers lazily, so a
        freshly imported `app` carries 74 routes and neither of these two. A lookup that silently
        finds nothing is exactly what the guard above exists to catch.
        """
        for prm in inspect.signature(fn).parameters.values():
            dep = getattr(prm.default, "dependency", None)
            gate = getattr(dep, "_role_gate", None)
            if gate:
                return gate
        return None

    feed = role_gate(mod_routes.view_alerts)
    clear = role_gate(mod_routes.mark_view_seen)
    check("both routes were found, so the comparison is not vacuous",
          feed is not None and clear is not None, f"feed={feed!r} clear={clear!r}")
    check("the role that SHOWS a view in the feed can also clear it", feed == clear,
          f"feed requires {feed!r}, clearing requires {clear!r}")
finally:
    db.close()

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("PER-VIEWER ALERTS OK - a project-scoped view reaches every reader's feed and each 'new' count "
      "is computed from that reader's own last visit: the author clearing their alert leaves the "
      "second reader's untouched and vice versa, which is exactly what one shared last_seen_at "
      "column could not do. Totals stay a property of the view.")
