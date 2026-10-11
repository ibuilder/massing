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

os.environ["DATABASE_URL"] = "sqlite:///./_sso_provision_race.db"
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

# =================================================================================================
# IS `DOORS` STILL THE WHOLE POPULATION?
#
# The roadmap's concurrency record predicted the exact failure this block exists to stop: *"a fourth
# sign-in path is the risk."* **The fourth path arrived and the prediction half came true** — SCIM
# auto-provisions at `routers/scim.py`, and it DOES route through `auth.get_or_create_sso_user`, so
# the code was fine. What was not fine is that everything above tested three doors by name and said
# so in its verdict line, which is *"a registry reports on what it contains, and its silence is
# indistinguishable from a clean bill"* — the sentence `test_gap_records` was built around, arriving
# here from the other direction: not a stale OPEN, but a population that quietly stopped being whole.
#
# So the population is derived twice, from two different angles, and neither needs a judgement-call
# exemption list:
#
#   1. every CALLER of the helper must be mapped to a door — a door added and wired correctly can no
#      longer go untested;
#   2. every site that CONSTRUCTS a `User` must be attributable: to a factory actually PASSED to the
#      helper, or to one of two declared exemptions whose truth is itself checked.
#
# **The first draft of this block satisfied neither claim, and review found it before a fifth door
# did.** It passed clean on both shapes a fifth door can take, by two unrelated mechanisms:
#
#   * **It exempted by MODULE.** `_stray` skipped any site whose module calls the helper *somewhere*,
#     so a new door added to `routers/auth.py` provisioning inline was exempt because `oauth_callback`
#     two screens up is wired correctly. *An exemption scoped wider than the thing it exempts is not
#     an exemption, it is a hole with a comment beside it.*
#   * **It keyed sites by `module.function`.** All four doors name their nested factory `_make_user`,
#     so a fifth one using the house convention **collapsed onto an existing key** — the site set
#     stayed at the identical seven entries, which the hardcoded floor of 7 could not see either.
#     *A key that merges two things cannot report that there are two.*
#
# And the cross-check that would have caught both was *written and never read*: `_via_helper` was
# computed into a module-scope name nothing consumed, so "reaches the helper" was never asked —
# `len(_sites) - len(BY_REQUEST)` simply **labelled** the remainder as helper-routed. Module scope, so
# ruff's F841 could not see it either. *A dead cross-check is worse than a missing one: the next
# reader sees the right idea in the file and assumes it runs.*
#
# Four further defects in that draft, each the same shape — a predicate deciding what to LOOK at:
#
#   * `_helper_callers` matched **attribute calls only**, so a door importing the helper by name was
#     not a caller at all. Measured on a fixture: a *correctly wired* new door redded with "a User is
#     constructed outside both the helper and the by-request set" — **the exact opposite of what it
#     does** — while the caller count stayed at 4 and the verdict still claimed "all 4 doors". The
#     docstring's "excluding the module that defines it" was not implemented either; it held by
#     accident of that same restriction.
#   * `User(...)` was matched as a bare `Name` only, so the `models.User(...)` spelling was invisible.
#   * A construction at module or class scope was **dropped silently** (`if not enclosing: continue`),
#     in a walk documented as failing closed.
#   * The floor of 7 counted `auth.require_admin_user`, a non-persisted LOCAL_MODE construction, so
#     refactoring it away would have redded the build with *"the AST walk under-counted"* —
#     **misdiagnosing a clean edit as a broken analyser.** *A hardcoded population floor reports the
#     one cause it was written for, whatever actually happened.*
#
# The repair: modules are keyed by their dotted path, not their stem (which conflated `auth.py`, the
# definer, with `routers/auth.py`, the OAuth door); sites are keyed by **qualname**; "helper-routed"
# means *this* site's qualname is a factory passed to the helper **from the scope that encloses the
# call**, not a name that appears in a module which calls it somewhere; the floor is derived; and
# every exemption must still resolve to a real site and still be true. Ten self-tests run first,
# over synthetic trees, and include the two shapes that slipped through as well as a CLEAN baseline —
# because *a check whose expected answer is zero is the easiest kind to break silently.* Nine
# mutations of the analyser were run against them and all nine red; the ninth is the one that taught
# something, and its lesson is written beside the fixture that now covers it.
# =================================================================================================
import ast as _ast  # noqa: E402
import pathlib  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import textwrap  # noqa: E402

_SRC = pathlib.Path(__file__).resolve().parent / "src" / "aec_api"
_HELPER = "get_or_create_sso_user"


def _called(func: _ast.expr) -> str | None:
    """The bare name of what a `Call` calls — `f()`, `mod.f()` and `a.b.f()` all answer ``f``.

    Matching `Attribute` alone is how the first draft could not see a door that did
    `from ..auth import get_or_create_sso_user`, and matching `Name` alone is how it could not see
    `models.User(...)`. Both spellings are in use in this tree for other symbols."""
    if isinstance(func, _ast.Name):
        return func.id
    if isinstance(func, _ast.Attribute):
        return func.attr
    return None


def _modname(f: pathlib.Path, root: pathlib.Path) -> str:
    """Dotted module path relative to the source root — `routers.auth`, not `auth`.

    The stem is NOT unique here: `aec_api/auth.py` defines the helper and `aec_api/routers/auth.py`
    is the OAuth door, and the first draft keyed both as ``auth``. That collision is why its
    "excluding the module that defines it" could not work and why `BY_REQUEST` entries read
    ambiguously."""
    parts = list(f.relative_to(root).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _scope_of(tree: _ast.AST) -> dict[_ast.AST, str]:
    """{node: dotted qualname of the function/class chain the node SITS IN} for every node.

    One downward walk, so a nested factory gets `route._make_user` and the route gets `route`. The
    first draft attributed by line range and took the innermost match, which is the same answer for
    the leaf but throws the chain away — and the chain is the whole point: `oauth_callback._make_user`
    and `device_callback._make_user` are two sites, not one."""
    out: dict[_ast.AST, str] = {tree: ""}
    stack: list[tuple[_ast.AST, str]] = [(tree, "")]
    while stack:
        node, qual = stack.pop()
        for child in _ast.iter_child_nodes(node):
            out[child] = qual  # the scope the child sits in, not the scope it opens
            if isinstance(child, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)):
                stack.append((child, f"{qual}.{child.name}" if qual else child.name))
            else:
                stack.append((child, qual))
    return out


def _analyse(root: pathlib.Path) -> dict:
    """Everything the checks below reason about, derived from one AST walk of `root`."""
    definers: set[str] = set()
    callers: set[str] = set()
    routed: set[str] = set()         # qualnames of factories actually PASSED to the helper
    unresolved: list[str] = []       # helper calls whose factory argument is not a plain name
    sites: dict[str, str] = {}       # "<module>.<qualname>" -> "<module>:<lineno>"
    module_level: set[str] = set()   # the subset of `sites` constructed outside any function
    node_site: dict[int, str] = {}   # id(User call node) -> its site key
    added_nodes: set[int] = set()    # id(User call node) passed DIRECTLY to `.add(...)`
    added_names: set[tuple] = set()  # (module, scope, name) passed to `.add(...)`
    assigned: dict[tuple, int] = {}  # (module, scope, name) -> id(the User call assigned to it)
    files = 0
    for f in sorted(root.rglob("*.py")):
        if "__pycache__" in f.parts:
            continue
        try:
            tree = _ast.parse(f.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        files += 1
        mod = _modname(f, root)
        scope = _scope_of(tree)
        # {scope qualname: names DEFINED in that scope}. Used to resolve the factory argument
        # LEXICALLY, which is the only sound reading: see the comment at the resolution below.
        defs_in: dict[str, set[str]] = {}
        for d_ in _ast.walk(tree):
            if isinstance(d_, (_ast.FunctionDef, _ast.AsyncFunctionDef, _ast.ClassDef)):
                defs_in.setdefault(scope.get(d_, ""), set()).add(d_.name)
        for n in _ast.walk(tree):
            if isinstance(n, (_ast.FunctionDef, _ast.AsyncFunctionDef)) and n.name == _HELPER:
                definers.add(mod)
                continue
            if not isinstance(n, (_ast.Call, _ast.Assign)):
                continue
            if isinstance(n, _ast.Assign):
                if isinstance(n.value, _ast.Call) and _called(n.value.func) == "User":
                    for t_ in n.targets:
                        if isinstance(t_, _ast.Name):
                            assigned[(mod, scope.get(n, ""), t_.id)] = id(n.value)
                continue
            name, here = _called(n.func), scope.get(n, "")
            if name == _HELPER:
                callers.add(mod)
                arg = n.args[2] if len(n.args) > 2 else next(
                    (k.value for k in n.keywords if k.arg == "make_user"), None)
                if isinstance(arg, _ast.Name):
                    # LEXICAL RESOLUTION, and nothing looser. The factory is the definition the
                    # calling scope would actually reach: walk out from the call's scope and take
                    # the FIRST scope that defines the name.
                    #
                    # Two earlier drafts were each wrong in the same direction. The first keyed
                    # sites `module.function`, so a fifth door using the house name `_make_user`
                    # collapsed onto an existing key. The second added the name under EVERY
                    # enclosing prefix including the empty one — so `<module>.<factory>` was always
                    # routed, and a fifth door provisioning inline through a module-level
                    # `_make_user` came back clean. *A loop over prefixes includes the one that
                    # means "anywhere".* Narrowing that to "the module defines this name at module
                    # scope" was still unsound, because a nested `def _make_user` in the wired
                    # route SHADOWS the module-level one: the name passed came from the route, and
                    # the guard admitted the module-level site anyway. *Two definitions of one name
                    # is not a question about the module, it is a question about scope.*
                    #
                    # A name no enclosing scope defines (a parameter, an import) resolves to
                    # nothing and is added to nothing, so a site matching it reads as a STRAY —
                    # fail CLOSED. Measured at 0 occurrences today.
                    _parts = here.split(".") if here else []
                    for _i in range(len(_parts), -1, -1):
                        _q = ".".join(_parts[:_i])
                        if arg.id in defs_in.get(_q, ()):
                            routed.add(f"{mod}.{_q}.{arg.id}" if _q else f"{mod}.{arg.id}")
                            break
                else:
                    unresolved.append(f"{mod}.{here or '<module>'}:{n.lineno}")
            elif name == "User":
                key = f"{mod}.{here}" if here else mod
                sites[key] = f"{mod}:{n.lineno}"
                node_site[id(n)] = key
                if not here:
                    module_level.add(key)
            elif name == "add":
                # The question is whether THIS User reaches a `.add(...)`, not whether the function
                # contains a call named `add`. The first draft asked the latter, so a `set.add(...)`
                # or an audit row appended in `require_admin_user` would have redded the build with
                # "it needs the 409 guard or the savepoint idiom" about a function that still
                # persists nothing. *A predicate named for the thing it is about, measured on
                # something else, produces a confident finding with the wrong remedy attached.*
                for a_ in n.args:
                    if isinstance(a_, _ast.Call) and _called(a_.func) == "User":
                        added_nodes.add(id(a_))
                    elif isinstance(a_, _ast.Name):
                        added_names.add((mod, here, a_.id))
    # A site is PERSISTED when its own `User(...)` reaches a `.add(...)`: directly as the argument,
    # or through a local name the same scope later adds. Resolved here rather than in the walk
    # because `u = User(...)` and `db.add(u)` are two statements and may be in either order.
    persisted = {node_site[i] for i in added_nodes if i in node_site}
    for keyed, node_id in assigned.items():
        if keyed in added_names and node_id in node_site:
            persisted.add(node_site[node_id])
    return {"definers": definers, "callers": callers - definers, "routed": routed,
            "unresolved": unresolved, "sites": sites, "module_level": module_level,
            "persisted": persisted, "files": files}


def _findings(a: dict, caller_to_door: dict[str, str], by_request: set[str],
              not_persisted: set[str]) -> list[str]:
    """Every way the derived population can disagree with what this file claims to cover.

    Deliberately a pure function of `_analyse`'s output and the three declarations, so the
    self-tests below can run it over a synthetic tree and mutate the declarations directly. The
    first draft's verdict was computed inline against module-scope names, which is why its one
    cross-check could be dead without any test noticing."""
    out: list[str] = []
    for mod in sorted(set(caller_to_door) - a["callers"]):
        out.append(f"STALE DOOR MAP: {mod} is mapped to door {caller_to_door[mod]!r} but no longer "
                   f"calls {_HELPER} ({len(a['callers'])} caller(s) found in {a['files']} file(s))")
    for mod in sorted(a["callers"] - set(caller_to_door)):
        out.append(f"NEW DOOR: {mod} calls {_HELPER} and this file does not know it — map it in "
                   "_CALLER_TO_DOOR and give it a DOORS arm (or declare it in NO_CALLBACK)")
    for where in sorted(a["unresolved"]):
        out.append(f"UNKNOWN: the factory argument to {_HELPER} at {where} is not a plain name, so "
                   "no construction site can be attributed to it — this check cannot rule")
    for key in sorted(a["sites"]):
        if key in a["routed"] or key in by_request or key in not_persisted:
            continue
        if key in a["module_level"]:
            out.append(f"UNKNOWN: a User is constructed at module or class scope at "
                       f"{a['sites'][key]} — outside any function, attributable to no door")
        else:
            out.append(f"STRAY: a User is constructed at {a['sites'][key]} ({key}), neither passed "
                       "to the helper nor covered by a declared exemption")
    for key in sorted(by_request | not_persisted):
        if key not in a["sites"]:
            out.append(f"STALE EXEMPTION: {key} is exempted here and constructs no User — delete "
                       f"the entry ({len(a['sites'])} site(s) found, so this is not a blind walk)")
    for key in sorted(not_persisted):
        if key in a["sites"] and key in a["persisted"]:
            out.append(f"EXEMPTION NO LONGER TRUE: {key} is exempted as never-persisted and now "
                       "adds its User to a session — it needs the 409 guard or the savepoint idiom")
    return out


# ---- self-tests: the analyser must find the two shapes that defeated the first draft -----------
# Synthetic trees rather than edits to the real one, so the proof-of-reach is not a dependency on
# anything outside this file. Each fixture carries its own declarations, because the defects being
# reproduced were in how a declaration was SCOPED, not in the walk.
_BASE_FILES = {
    "auth.py": """
        def get_or_create_sso_user(db, username, make_user):
            u = db.get(User, username)
            if u is None:
                u = make_user()
                db.add(u)
            return u
    """,
    # Imports the helper BY NAME: invisible to the first draft's attribute-only matcher.
    "routers/auth.py": """
        from ..auth import get_or_create_sso_user

        def require_admin_user(db):
            return User(username="local", role="admin")

        def register(db, username):
            if db.get(User, username):
                raise HTTPException(409, "username already taken")
            db.add(User(username=username))

        def oauth_callback(db, email):
            def _make_user():
                return User(username=email)
            return get_or_create_sso_user(db, email, _make_user)
    """,
    # Calls it as an attribute, which is what the real SAML/cloud/SCIM doors do.
    "routers/saml.py": """
        from .. import auth

        def saml_acs(db, email):
            def _make_user():
                return User(username=email)
            return auth.get_or_create_sso_user(db, email, _make_user)
    """,
}
_BASE_MAP = {"routers.auth": "oauth", "routers.saml": "saml"}
_BASE_BY_REQUEST = {"routers.auth.register"}
_BASE_NOT_PERSISTED = {"routers.auth.require_admin_user"}


def _fixture(extra: dict[str, str] | None = None,
             replace: dict[str, str] | None = None) -> pathlib.Path:
    """A synthetic source tree. Every source is dedented BEFORE anything is appended to it — the
    first draft dedented the concatenation, so an already-flush `extra` left the base block at its
    original eight-space indent and every fixture was an `IndentationError` the `except SyntaxError`
    in `_analyse` would have swallowed into a silently empty tree."""
    files = {rel: textwrap.dedent(src) for rel, src in _BASE_FILES.items()}
    for rel, src in (replace or {}).items():
        files[rel] = textwrap.dedent(src)
    for rel, src in (extra or {}).items():
        files[rel] = files.get(rel, "") + textwrap.dedent(src)
    root = pathlib.Path(tempfile.mkdtemp(prefix="sso_pop_"))
    for rel, src in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(src, encoding="utf-8")
        _ast.parse(src)  # `_analyse` skips a SyntaxError; a fixture must never reach it as one
    return root


def _probe(name: str, *, extra=None, replace=None, by_request=None, not_persisted=None,
           must=(), must_not=()) -> None:
    root = _fixture(extra, replace)
    try:
        found = _findings(_analyse(root), _BASE_MAP,
                          _BASE_BY_REQUEST if by_request is None else by_request,
                          _BASE_NOT_PERSISTED if not_persisted is None else not_persisted)
    finally:
        shutil.rmtree(root, ignore_errors=True)
    blob = " | ".join(found)
    missing = [m for m in must if m not in blob]
    present = [m for m in must_not if m in blob]
    if not must and not must_not:            # the CLEAN baseline
        check(f"[self-test] {name}", not found, f"findings={found}")
        return
    check(f"[self-test] {name}", not missing and not present,
          f"missing={missing} unexpected={present} findings={found}")


# A clean baseline FIRST: without it, every probe below could be passing because the analyser
# reports everything, which is the failure mode a zero-expected check cannot distinguish.
_probe("a correctly wired tree is CLEAN")

# SHAPE 1 — a fifth door inside an EXISTING door module, provisioning inline. The first draft
# exempted it twice over: by module stem, and by collapsing `_make_user` onto the OAuth door's key.
_probe("a fifth door provisioning INLINE in an existing door module is a STRAY",
       extra={"routers/auth.py": """

        def device_callback(db, email):
            def _make_user():
                return User(username=email)
            u = db.get(User, email)
            if u is None:
                u = _make_user()
                db.add(u)
            return u
       """},
       must=["STRAY", "routers.auth.device_callback._make_user"],
       must_not=["NEW DOOR"])

# SHAPE 2 — a fifth door wired CORRECTLY, importing the helper by name. The first draft reported
# this as a stray construction, which is the opposite of the truth; the only correct finding is
# that the door is unmapped, because an unmapped door is one nobody gave an arm.
_probe("a correctly wired new door is reported as UNMAPPED, not as a stray",
       extra={"routers/device.py": """
        from ..auth import get_or_create_sso_user

        def device_acs(db, email):
            def _make_user():
                return User(username=email)
            return get_or_create_sso_user(db, email, _make_user)
       """},
       must=["NEW DOOR", "routers.device"],
       must_not=["STRAY", "UNKNOWN"])

# The dropped shapes: module scope, and the attribute spelling of the model.
_probe("a User constructed at module scope is UNKNOWN, not skipped",
       extra={"routers/auth.py": '\n_SEED_ADMIN = User(username="root", role="admin")\n'},
       must=["UNKNOWN", "module or class scope"])
_probe("the models.User(...) spelling is seen",
       extra={"routers/jobs.py": """
        from .. import models

        def enqueue(db, who):
            db.add(models.User(username=who))
       """},
       must=["STRAY", "routers.jobs.enqueue"])

# A factory this analyser cannot resolve must be UNKNOWN, not silently helper-routed.
_probe("an unresolvable factory argument fails CLOSED",
       replace={"routers/saml.py": """
        from .. import auth

        def saml_acs(db, email):
            return auth.get_or_create_sso_user(db, email, lambda: User(username=email))
       """},
       must=["UNKNOWN", "not a plain name"])

# The exemptions are checked, not trusted — and the message must name the exemption rather than
# blaming the walk, which is exactly what the hardcoded floor of 7 did.
_probe("an exemption naming no real site is STALE, and says so",
       by_request=_BASE_BY_REQUEST | {"routers.auth.legacy_invite"},
       must=["STALE EXEMPTION", "routers.auth.legacy_invite"],
       must_not=["under-counted"])
_probe("a never-persisted exemption that starts persisting is refused",
       replace={"routers/auth.py": """
        from ..auth import get_or_create_sso_user

        def require_admin_user(db):
            u = User(username="local", role="admin")
            db.add(u)
            return u

        def register(db, username):
            if db.get(User, username):
                raise HTTPException(409, "username already taken")
            db.add(User(username=username))

        def oauth_callback(db, email):
            def _make_user():
                return User(username=email)
            return get_or_create_sso_user(db, email, _make_user)
       """},
       must=["EXEMPTION NO LONGER TRUE", "routers.auth.require_admin_user"])

# And the keying must distinguish two factories of the same name in the same module even when BOTH
# doors are correctly wired — otherwise shape 1 is caught by luck rather than by the key.
_probe("two correctly wired doors in one module, same factory name, both resolve",
       extra={"routers/auth.py": """

        def device_callback(db, email):
            def _make_user():
                return User(username=email)
            return get_or_create_sso_user(db, email, _make_user)
       """},
       must_not=["STRAY", "UNKNOWN"])

# The definer is not a door. `callers - definers` was the one branch the nine-way mutation run left
# GREEN: `aec_api/auth.py` does not call its own helper, so the subtraction was doing nothing
# measurable — which is precisely the position `_via_helper` was in before review found it dead.
# Defensive is not the same as exercised, so a fixture now calls the helper from the module that
# DEFINES it (a retry path is the realistic way that arrives) and the module must not be reported
# as a fifth door.
_probe("the module that DEFINES the helper is not itself a door",
       replace={"auth.py": """
        def get_or_create_sso_user(db, username, make_user, _retry=True):
            u = db.get(User, username)
            if u is None:
                u = make_user()
                db.add(u)
            if u is None and _retry:
                return get_or_create_sso_user(db, username, make_user, _retry=False)
            return u
       """},
       must_not=["NEW DOOR", "STRAY", "UNKNOWN"])

# SHAPE 1b — the same inline fifth door, with its factory at MODULE scope AND UNDER THE HOUSE NAME.
# Both halves are load-bearing. The second repair's prefix loop ran down to the empty prefix, so
# `routers.auth._make_user` was routed because `oauth_callback` passes a NESTED factory of that
# name; narrowing that to "the module defines this name" did not help, because the module here DOES
# define it — the nested def in the wired route simply SHADOWS it. The fixture deliberately reuses
# `_make_user`, since all four real doors use it: *a collision test spelled with a different name
# tests nothing, and the first draft of this fixture was spelled `_seed_user` and passed the hole
# it was written to catch.*
_probe("a fifth door whose MODULE-LEVEL factory never reaches the helper is a STRAY",
       extra={"routers/auth.py": """

        def _make_user(email):
            return User(username=email)

        def device_callback(db, email):
            u = db.get(User, email)
            if u is None:
                u = _make_user(email)
                db.add(u)
            return u
       """},
       must=["STRAY", "routers.auth._make_user"],
       must_not=["NEW DOOR"])

# ...and the narrowed module-scope spelling still RESOLVES when the module really defines it there
# and really passes it. Without this the repair above could be "never admit module scope", which
# would red a legitimate shared factory.
_probe("a MODULE-LEVEL factory that IS passed to the helper resolves",
       replace={"routers/saml.py": """
        from .. import auth

        def _make_user(email):
            return User(username=email)

        def saml_acs(db, email):
            return auth.get_or_create_sso_user(db, email, _make_user)
       """},
       must_not=["STRAY", "UNKNOWN", "NEW DOOR"])

# THE PERSISTENCE PREDICATE is about THIS User, not about any call named `add`. Asking the latter
# turned an audit append or a set insert into "it needs the 409 guard or the savepoint idiom" —
# a confident finding with the wrong remedy attached, about a function that persists nothing.
_probe("a never-persisted exemption may call .add() on something that is not its User",
       replace={"routers/auth.py": """
        from ..auth import get_or_create_sso_user

        def require_admin_user(db, seen, audit_rows):
            seen.add("local")
            audit_rows.add({"action": "admin.local"})
            return User(username="local", role="admin")

        def register(db, username):
            if db.get(User, username):
                raise HTTPException(409, "username already taken")
            db.add(User(username=username))

        def oauth_callback(db, email):
            def _make_user():
                return User(username=email)
            return get_or_create_sso_user(db, email, _make_user)
       """},
       must_not=["EXEMPTION NO LONGER TRUE"])

# Both persisting forms are caught: the two-statement one above, and the direct argument.
_probe("a never-persisted exemption that adds its User DIRECTLY is refused",
       replace={"routers/auth.py": """
        from ..auth import get_or_create_sso_user

        def require_admin_user(db):
            db.add(User(username="local", role="admin"))
            return db.get(User, "local")

        def register(db, username):
            if db.get(User, username):
                raise HTTPException(409, "username already taken")
            db.add(User(username=username))

        def oauth_callback(db, email):
            def _make_user():
                return User(username=email)
            return get_or_create_sso_user(db, email, _make_user)
       """},
       must=["EXEMPTION NO LONGER TRUE", "routers.auth.require_admin_user"])

# ---- the real tree ------------------------------------------------------------------------------
#: Sites that INSERT a user BY EXPLICIT REQUEST rather than auto-provisioning on sign-in. Both
#: guard with an explicit 409 and neither is a sign-in door, so the savepoint idiom does not apply.
#: (Their check-then-insert does degrade a 409 into a 500 under a true race — recorded in the
#: roadmap as low severity on purpose: unlike a sign-in, the loser's request is one that correctly
#: fails.) `register` carries the first-user bootstrap; the first draft of this list attributed that
#: bootstrap to `require_admin_user` and claimed a 409 for it, and **both halves were false** —
#: `require_admin_user` raises 403 and inserts nothing at all. *A justification repeated into a
#: roadmap entry is not evidence; it is the same sentence in two places.*
BY_REQUEST = {"routers.auth.register", "routers.auth.create_user"}

#: Sites that CONSTRUCT a `User` and never persist one. `require_admin_user` returns a synthetic
#: in-memory admin under `rbac.LOCAL_MODE`; there is no row and no race. This exemption is a
#: different category from `BY_REQUEST`, and conflating the two is what let the first draft's floor
#: of 7 punish a legitimate refactor. It is VERIFIED rather than asserted: `_findings` refuses it
#: the moment the function calls `.add(...)`.
NOT_PERSISTED = {"routers.auth.require_admin_user"}

_CALLER_TO_DOOR = {"routers.auth": "oauth", "routers.saml": "saml",
                   "routers.cloud": "cloud", "routers.scim": "scim"}

#: Doors that provision from a directory push rather than an interactive callback, and so have no
#: redirect to drive and no behavioural arm above. Declaring them is what keeps the verdict line
#: honest: the race properties are proved for the doors in `DOORS`, and a new door must either get
#: an arm or be declared here — it cannot simply raise the count in a sentence that claims them.
NO_CALLBACK = {"scim"}

_a = _analyse(_SRC)
_found = _findings(_a, _CALLER_TO_DOOR, BY_REQUEST, NOT_PERSISTED)

check("PRECONDITION: the walk read the tree and found the helper's definition",
      _a["files"] >= 100 and bool(_a["definers"]) and bool(_a["routed"]),
      f"{_a['files']} file(s), definer={sorted(_a['definers'])}, "
      f"{len(_a['routed'])} resolved factory qualname(s)")
check("every helper caller is a mapped door, and every mapped door still calls it",
      not [f for f in _found if f.startswith(("STALE DOOR MAP", "NEW DOOR"))],
      f"{len(_a['callers'])} caller(s): {sorted(_a['callers'])}")
#: Counted, not subtracted. The first draft of this line reported "N - len(BY_REQUEST)" as the
#: helper-routed total, which is the same arithmetic `_via_helper`'s absence left behind: it LABELS
#: the remainder instead of measuring it, so on the inline-fifth-door mutation it cheerfully said
#: "5 via the helper" one line above a finding that one of them is not.
_by_route = {"helper": 0, "by request": 0, "never persisted": 0, "unattributed": 0}
for _k in _a["sites"]:
    _by_route["helper" if _k in _a["routed"] else
              "by request" if _k in BY_REQUEST else
              "never persisted" if _k in NOT_PERSISTED else "unattributed"] += 1
check("every User construction is attributable to the helper or a declared exemption",
      not [f for f in _found if f.startswith(("STRAY", "UNKNOWN"))],
      f"{len(_a['sites'])} site(s): " + ", ".join(f"{v} {k}" for k, v in _by_route.items() if v))
check("every declared exemption still resolves to a real site and is still true",
      not [f for f in _found if f.startswith(("STALE EXEMPTION", "EXEMPTION NO LONGER"))],
      f"{sorted(BY_REQUEST | NOT_PERSISTED)}")

_arms = {d for d, _u, _s in DOORS}
_declared = set(_CALLER_TO_DOOR.values())
check("every door either has a behavioural arm or is declared callback-less",
      _declared == _arms | NO_CALLBACK and not (_arms & NO_CALLBACK),
      f"arms={sorted(_arms)} no_callback={sorted(NO_CALLBACK)} doors={sorted(_declared)}")

for _f in _found:
    print("      " + _f)

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print(
    f"SSO PROVISION RACE OK - all {len(_declared)} auto-provisioning doors "
    f"({', '.join(sorted(_declared))}) go through one helper whose INSERT sits in a SAVEPOINT, and "
    "the door list is DERIVED from the helper's callers with every User construction in the tree "
    f"attributed, so a fifth cannot arrive unseen. For the {len(_arms)} doors with an interactive "
    f"callback ({', '.join(sorted(_arms))}) this file proves the behaviour as well as the wiring: "
    "losing the seeding race hands back the winner's row instead of raising, the session stays "
    "usable so the sign-in audit entry still commits, exactly one account exists, and an "
    f"uncontested first sign-in still creates one. {', '.join(sorted(NO_CALLBACK))} provisions from "
    "a directory push with no callback to drive, and is covered by the derivation alone."
)
