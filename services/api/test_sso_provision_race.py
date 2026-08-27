"""The three SSO doors survive a concurrent FIRST sign-in, and their audit row survives with them.

## The defect

OAuth (`routers/auth.py`), SAML (`routers/saml.py`) and the massing.cloud broker
(`routers/cloud.py`) each auto-provision a local account on first sign-in, and each did it the
same unguarded way::

    u = db.get(User, email)
    if u is None:
        u = User(username=email, ...)
        db.add(u)

`User.username` is the PRIMARY KEY. Two concurrent *first* sign-ins for one person — two tabs, two
devices, a retried callback — both read `None`, both INSERT the same key, and the loser's
`commit()` raises `IntegrityError`. **The person who did nothing wrong gets a 500 on a legitimate
login**, and a retry then succeeds because the winner's row exists by then, which is exactly what
makes it easy to dismiss as a blip rather than find.

Seeding is the one moment no row-level mechanism can protect, because there is no row yet — the
same sentence `modules._next_ref` carries about its ref counter, and the third instance of the
pattern after `rbac.consume_stepup`. `auth.get_or_create_sso_user` is the shared fix.

## Why this test is shaped the way it is

**A sequential "call it twice" test would pass against the broken code**, because the second call
takes the `u is not None` branch and never inserts. That is the trap `test_stepup_race` records
about its own predecessor: *"a sequential replay is satisfied by a plain read-then-write, which is
precisely the implementation the docstring says would be wrong"*.

**The first draft of THIS file fell into a second version of the same trap, and only the mutation
run found it.** It committed the competing row *before* calling the helper — so the helper's own
`db.get` already saw the winner, returned early, and never reached the insert. Every assertion
passed, and it passed **identically against the unguarded code**. A test that cannot fail is not
evidence, however many PASS lines it prints.

**SQLite serialises writers, so the parallelism itself cannot be reproduced here** — the constraint
`test_race_conditions` names in its own docstring. Committing the competing row from a second
connection *while this session's transaction is open* does not race, it deadlocks:
`OperationalError: database is locked`. (Tried, in this file's second draft.)

So this reproduces the **state** a lost race leaves behind rather than the concurrency that causes
it, which is what `test_race_conditions` settled on for the same reason. The winner's row is
committed first, and the loser's session is made to *read as though it had looked before that
commit* — its first `Session.get` for that username returns `None` once. Everything after is real:
a genuine INSERT against a genuinely present primary key, a genuine `IntegrityError`, and a genuine
savepoint rollback.

Against the fix the refusal is caught and the winner's row comes back. Against the unguarded
original the `IntegrityError` escapes — which is what the mutation run shows, and what the first
two drafts of this file could not show at all.

**That last clause is a separate assertion on purpose.** Without the savepoint the loser's session
enters `PendingRollbackError` and the caller's other staged rows are lost — including the
`auth.sso_login` audit entry. A test that only checked "no exception" would miss a sign-in path
that silently stops recording who signed in. `rbac.consume_stepup`'s docstring makes the same point
about its own audit row, and says neither assertion should be simplified away.

Run: cd services/api && PYTHONPATH=src:../data/src ./.venv/bin/python test_sso_provision_race.py
"""
from __future__ import annotations

import os
import sys

os.environ.setdefault("DATABASE_URL", "sqlite:///./_sso_provision_race.db")
os.environ.setdefault("STORAGE_DIR", "./_storage_sso_provision_race")
os.environ.pop("AEC_OAUTH_NO_AUTOPROVISION", None)

for _f in ("./_sso_provision_race.db",):
    if os.path.exists(_f):
        os.remove(_f)

from aec_api import auth  # noqa: E402
from aec_api.db import SessionLocal, engine  # noqa: E402
from aec_api.models import AuditLog, Base, User  # noqa: E402

Base.metadata.create_all(engine)

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAILED.append(name)


def _competitor(username: str, pw: str) -> None:
    """Another worker wins the seeding race, in its own committed transaction."""
    other = SessionLocal()
    try:
        other.add(User(username=username, password_hash=pw, role="user", email=username))
        other.commit()
    finally:
        other.close()


# ---- the three doors, each with the password-hash sentinel its own router uses -----------------
# The sentinel is what distinguishes the winner's row from the loser's: if the caller were handed
# its OWN unsaved object, the assertion below would read "loser" and pass a weaker test.
DOORS = [
    ("oauth", "oauth-race@example.com", "oauth!google"),
    ("saml", "saml-race@example.com", "saml!deadbeef"),
    ("cloud", "cloud-race@example.com", "cloud!massing"),
]

for door, username, sentinel in DOORS:
    db = SessionLocal()
    try:
        # The winner commits first, on its own connection, while this session is still idle —
        # no lock contention, because nothing has been staged here yet.
        _competitor(username, f"winner-{door}")

        # A row the caller has staged and has every right to keep — this stands in for the
        # `auth.sso_login` audit entry each door writes before its commit.
        db.add(AuditLog(action=f"auth.sso_login.{door}", actor=username, method="GET",
                        path=f"/auth/{door}/callback"))

        # ...and this is the lost race, as a state rather than as a schedule: the loser's FIRST
        # lookup answers None, because it happened before the winner committed. Only that one
        # answer is faked — the INSERT that follows is real, the primary key it collides with is
        # really there, and the IntegrityError is the database's own.
        _real_get = db.get
        _seen = {"n": 0}

        # Every captured name is bound as a default argument, not closed over: these are defined
        # inside a loop, and a late-binding closure would make each door assert about the last
        # door's values. ruff's B023 catches it; correctness here does not depend on that catch.
        def _racing_get(entity, ident, *a, _real=_real_get, _u=username, _s=_seen, **kw):
            if entity is User and ident == _u:
                _s["n"] += 1
                if _s["n"] == 1:
                    return None
            return _real(entity, ident, *a, **kw)

        def _make_loser(_u=username, _h=sentinel) -> User:
            return User(username=_u, password_hash=_h, role="user", email=_u, tier="free")

        db.get = _racing_get  # type: ignore[method-assign]

        raised: Exception | None = None
        u = None
        created = None
        try:
            u, created = auth.get_or_create_sso_user(db, username, _make_loser)
        except Exception as e:  # noqa: BLE001 - the whole point is that nothing escapes
            raised = e

        check(f"[{door}] losing the seeding race does not raise", raised is None,
              "" if raised is None else f"{type(raised).__name__}: {raised}")
        check(f"[{door}] the caller is handed the WINNER's row, not its own",
              u is not None and u.password_hash == f"winner-{door}",
              f"password_hash={getattr(u, 'password_hash', None)!r} (expected 'winner-{door}')")
        db.get = _real_get  # type: ignore[method-assign]
        check(f"[{door}] ...and reports created=False", created is False, f"created={created}")
        check(f"[{door}] the faked lookup was used exactly once — the rest is real",
              _seen["n"] >= 2, f"Session.get called {_seen['n']}x for this username")

        # The session must still be usable. Without the savepoint this commit raises
        # PendingRollbackError and the audit row is gone — a sign-in path that stops recording
        # sign-ins while still reporting success.
        commit_error: Exception | None = None
        try:
            db.commit()
        except Exception as e:  # noqa: BLE001
            commit_error = e
        check(f"[{door}] the session survives, so staged rows commit", commit_error is None,
              "" if commit_error is None else f"{type(commit_error).__name__}: {commit_error}")

        kept = db.query(AuditLog).filter(AuditLog.action == f"auth.sso_login.{door}").count()
        check(f"[{door}] the sign-in audit row survives the lost race", kept == 1, f"{kept} row(s)")

        rows = db.query(User).filter(User.username == username).count()
        check(f"[{door}] exactly one account exists afterwards", rows == 1, f"{rows} row(s)")
    finally:
        db.close()

# ---- the inverse: an UNCONTESTED first sign-in must still create ------------------------------
# Without this, the cheapest way to make everything above pass is a helper that never inserts, and
# the suite would applaud while nobody could ever sign in for the first time.
db = SessionLocal()
try:
    fresh = "fresh-signin@example.com"
    u, created = auth.get_or_create_sso_user(
        db, fresh,
        lambda: User(username=fresh, password_hash="oauth!google", role="user",
                     email=fresh, tier="free"))
    db.commit()
    check("an uncontested first sign-in still CREATES the account", created is True,
          f"created={created}")
    check("...and the account is really persisted", db.get(User, fresh) is not None)
    # And a second, uncontested call is a plain find — not a duplicate insert.
    _u2, c2 = auth.get_or_create_sso_user(
        db, fresh, lambda: User(username=fresh, password_hash="should-not-be-used", role="user"))
    check("a later sign-in finds the existing account", c2 is False, f"created={c2}")
finally:
    db.close()

# ---------------------------------------------------------------------------------------------
# THE SECOND SEEDED ROW, which the User fix did not cover.
#
# The massing.cloud callback calls `get_or_create_sso_user` for its `User` and then, FOUR LINES
# LATER, seeded a `CloudIdentity` with the same unguarded read-decide-insert. `CloudIdentity`s
# `username` is also a PRIMARY KEY, so two concurrent FIRST cloud sign-ins both read None, both
# INSERT, and the loser still got a 500 on a legitimate login - one row after the row that had just
# been made safe. One request, one function, the rule applied to one of its two seeded rows.
#
# This asserts the generic helper on a SECOND model, which is the whole point of extracting it: the
# protection is a property of the idiom now, not of the `User` table.
from aec_api.models import CloudIdentity  # noqa: E402

CLOUD_USER = "cloud-link-race@example.com"
db = SessionLocal()
try:
    # The account must exist first: `cloud_identities.username` is an FK into `users`.
    db.add(User(username=CLOUD_USER, password_hash="cloud!massing", role="user", email=CLOUD_USER))
    db.commit()

    # A competitor links the identity on its own connection, and commits.
    other = SessionLocal()
    try:
        other.add(CloudIdentity(username=CLOUD_USER, cloud_sub="winner-sub"))
        other.commit()
    finally:
        other.close()

    # ...and this session's first lookup still answers None, exactly as it would have before the
    # competitor committed. Only that one answer is faked; the INSERT after it is real.
    _real = db.get
    seen = {"n": 0}

    def _racing_get(entity, ident, *a, _r=_real, _s=seen, **kw):
        if entity is CloudIdentity and ident == CLOUD_USER:
            _s["n"] += 1
            if _s["n"] == 1:
                return None
        return _r(entity, ident, *a, **kw)

    db.get = _racing_get  # type: ignore[method-assign]
    raised_link = None
    link = None
    made = None
    try:
        link, made = auth.get_or_create_by_pk(
            db, CloudIdentity, CLOUD_USER,
            lambda: CloudIdentity(username=CLOUD_USER, cloud_sub="loser-sub"))
    except Exception as e:  # noqa: BLE001 - nothing may escape
        raised_link = e
    finally:
        db.get = _real  # type: ignore[method-assign]

    check("[cloud-link] losing the CloudIdentity seeding race does not raise", raised_link is None,
          "" if raised_link is None else f"{type(raised_link).__name__}: {raised_link}")
    check("[cloud-link] the caller is handed the WINNER's link, not its own",
          link is not None and link.cloud_sub == "winner-sub",
          f"cloud_sub={getattr(link, 'cloud_sub', None)!r}")
    check("[cloud-link] ...and reports created=False", made is False, f"created={made}")
    check("[cloud-link] the faked lookup was used exactly once - the collision after it is real",
          seen["n"] >= 2, f"Session.get called {seen['n']}x")

    commit_err = None
    try:
        db.commit()
    except Exception as e:  # noqa: BLE001
        commit_err = e
    check("[cloud-link] the session survives, so the sign-in audit row still commits",
          commit_err is None,
          "" if commit_err is None else f"{type(commit_err).__name__}: {commit_err}")
finally:
    db.close()

# ---------------------------------------------------------------------------------------------
# A THIRD MODEL, to keep the helper honest as a GENERIC guarantee rather than a User-shaped one.
#
# `settings_store.set_value` had the same read-decide-insert against `app_settings.key`, which is
# also a PRIMARY KEY. It is lower severity than the sign-in doors and that is worth stating: it
# needs two admins (or a double-clicked Save) on ONE key, and the retry succeeds. It was converted
# anyway, because the helper existed and "one rule applied at some of the sites" is the shape this
# repository keeps re-finding.
#
# `set_value` does NOT commit - the caller does - so before the fix the IntegrityError surfaced one
# frame away from the code that caused it, which is what makes this kind hard to attribute in a log.
from aec_api import settings_store  # noqa: E402
from aec_api.models import AppSetting  # noqa: E402

SKEY = "SEEDING_RACE_PROBE"
db = SessionLocal()
try:
    other = SessionLocal()
    try:
        other.add(AppSetting(key=SKEY, value="winner"))
        other.commit()
    finally:
        other.close()

    _real = db.get
    seen_s = {"n": 0}

    def _racing_settings_get(entity, ident, *a, _r=_real, _s=seen_s, **kw):
        if entity is AppSetting and ident == SKEY:
            _s["n"] += 1
            if _s["n"] == 1:
                return None
        return _r(entity, ident, *a, **kw)

    db.get = _racing_settings_get  # type: ignore[method-assign]
    set_exc = None
    try:
        settings_store.set_value(db, SKEY, "loser")
        db.commit()          # the CALLER commits - this is where it used to blow up
    except Exception as e:   # noqa: BLE001
        set_exc = e
    finally:
        db.get = _real  # type: ignore[method-assign]

    check("[settings] losing the app_settings seeding race does not raise at the CALLER's commit",
          set_exc is None,
          "" if set_exc is None else f"{type(set_exc).__name__}: {str(set_exc)[:90]}")
    check("[settings] the faked lookup was exercised - the collision after it is real",
          seen_s["n"] >= 2, f"Session.get called {seen_s['n']}x")
    check("[settings] exactly one row exists for the key",
          len([r for r in db.query(AppSetting).all() if r.key == SKEY]) == 1)
finally:
    db.get = _real  # type: ignore[method-assign]
    db.close()
    settings_store._cache.pop(SKEY, None)

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print(
    f"SSO PROVISION RACE OK - all {len(DOORS)} auto-provisioning doors (OAuth, SAML, massing.cloud) "
    "go through one helper whose INSERT sits in a SAVEPOINT: losing the seeding race hands back the "
    "winner's row instead of raising, the session stays usable so the sign-in audit entry still "
    "commits, exactly one account exists, and an uncontested first sign-in still creates one."
)
