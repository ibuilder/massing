"""A concurrent SCIM POST for one `userName` must fold into the existing row, not 500 at the IdP.

THE DEFECT. `scim_create_user` read `db.get(User, uname)`, branched on it, and INSERTed in the
`None` arm — *"read state, decide, write, with nothing holding the world still in between"*, which
is the exact shape the 2026-08-25 concurrency sweep named and then fixed at the three SIGN-IN doors
(`auth.get_or_create_sso_user`). SCIM was a fourth seeding path and did not call it.

`User.username` is the PRIMARY KEY. Two concurrent POSTs for one `userName` both read `None`, both
INSERT, and the loser's `commit()` raises `IntegrityError` — a **500 returned to the IdP for a
request that was correct**.

WHY SCIM IS A WORSE PLACE FOR IT THAN A SIGN-IN, not a better one: a human racing themselves needs
two tabs, but an IdP retries on timeout and runs parallel sync workers, so a duplicate POST for one
`userName` is ordinary traffic. Okta and Entra read a 500 as a provisioning failure.

WHY THE FIX IS SMALL. Losing the race and being a re-provision are the SAME OUTCOME: the row
exists and this request must fold into it. `get_or_create_sso_user` already returns `created`, so
the loser takes the rehire branch that was there all along and answers 200 — which is what SCIM
wanted anyway. No new semantics, one fewer copy of the idiom.

HOW THE RACE IS FORCED — the same idiom as `test_sso_provision_race.py`, because a thread schedule
is not reproducible and a test that cannot fail is not evidence. A competitor commits the row on
its own connection; only the handler's FIRST `Session.get` for that username is faked to `None`.
Everything after is real: a real INSERT, a real primary-key collision, a real `IntegrityError`, a
real savepoint rollback.

**Both directions are asserted.** The race case must answer 200, and an ordinary first create must
still answer 201 — without that twin this file would pass against a handler that 200s everything,
which is a no-op wearing a green tick.

Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_scim_provision_race.py
"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_scim_race.db"
os.environ["STORAGE_DIR"] = "./test_storage_scim_race"
os.environ["AEC_SCIM_TOKEN"] = "scim-race-token"
os.environ.pop("AEC_RBAC", None)

for _f in ("./test_scim_race.db",):
    if os.path.exists(_f):
        os.remove(_f)

import sys  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy.orm import Session  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import User  # noqa: E402

TOK = {"Authorization": "Bearer scim-race-token"}
BASE = "/scim/v2/Users"
RACED = "raced@example.com"
FRESH = "fresh@example.com"
FAILED = []


def check(name, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {name}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(name)


def _competitor(username, sentinel):
    """Another SCIM worker wins the seeding race, in its own committed transaction."""
    other = SessionLocal()
    try:
        other.add(User(username=username, password_hash=sentinel, role="user",
                       email=username, provisioned=True))
        other.commit()
    finally:
        other.close()


with TestClient(app) as c:
    # --- the twin, FIRST: an uncontended create still reports 201 -------------------------------
    r_new = c.post(BASE, headers=TOK, json={"userName": FRESH, "active": True})
    check("an ordinary first provision still answers 201 — the twin, so a handler that 200s "
          "everything cannot pass this file",
          r_new.status_code == 201, f"status={r_new.status_code}")

    # --- the lost race --------------------------------------------------------------------------
    _competitor(RACED, "winner-sentinel")

    _real_get = Session.get
    seen = {"n": 0}

    def _racing_get(self, entity, ident, *a, _real=_real_get, **kw):
        """Answer None for the handler's FIRST lookup of the raced username, then get out of the way."""
        if entity is User and ident == RACED:
            seen["n"] += 1
            if seen["n"] == 1:
                return None
        return _real(self, entity, ident, *a, **kw)

    Session.get = _racing_get  # type: ignore[method-assign]
    r_race = None
    raised: Exception | None = None
    try:
        # TestClient re-raises server exceptions by default, so against the UNFIXED handler this
        # does not return 500 - it throws IntegrityError straight into the test process. Catching
        # it keeps the mutation run legible: a FAIL line naming the defect reads better in the
        # runner's output than a traceback, which is easy to mistake for a poisoned run.
        r_race = c.post(BASE, headers=TOK, json={"userName": RACED, "active": True})
    except Exception as e:  # noqa: BLE001 - the whole point is that nothing escapes the handler
        raised = e
    finally:
        Session.get = _real_get  # type: ignore[method-assign]

    check("losing the seeding race does not escape as a server exception",
          raised is None,
          "" if raised is None else f"{type(raised).__name__}: {str(raised)[:90]}")
    check("losing the seeding race does not 500 the IdP",
          r_race is not None and r_race.status_code != 500,
          f"status={getattr(r_race, 'status_code', 'raised')}")
    check("...it folds into the existing row and answers 200, the re-provision result",
          r_race is not None and r_race.status_code == 200,
          f"status={getattr(r_race, 'status_code', 'raised')}")
    check("the faked lookup was used exactly once — the INSERT and the collision after it are real",
          seen["n"] >= 2, f"Session.get called {seen['n']}x for {RACED}")

    # --- the winner's row is the one that survives ----------------------------------------------
    db = SessionLocal()
    try:
        row = db.get(User, RACED)
        check("the WINNER's row survives — the loser did not overwrite it with its own",
              row is not None and row.password_hash == "winner-sentinel",
              f"password_hash={getattr(row, 'password_hash', None)!r}")
        check("exactly one row exists for the raced username",
              len([u for u in db.query(User).all() if u.username == RACED]) == 1)
    finally:
        db.close()

    # --- and the surface still works afterwards: the session was not left poisoned ---------------
    r_after = c.get(f"{BASE}/{RACED}", headers=TOK)
    check("the raced account is readable afterwards — the savepoint kept the session usable",
          r_after.status_code == 200, f"status={r_after.status_code}")

print()
if FAILED:
    print(f"FAILED: {'; '.join(FAILED)}")
    sys.exit(1)
print("scim provision race OK — a concurrent duplicate POST folds into the winner's row and "
      "answers 200 instead of 500, and an uncontended create still answers 201")
