"""R43-CSRF-GET — no route may change state on a GET, because Lax is our entire CSRF defence.

The session cookie is set `samesite="lax"` in `routers/auth.py` and `routers/saml.py`, and there is
no CSRF middleware anywhere in the app. Lax withholds the cookie on a cross-site POST/PATCH/DELETE
**but sends it on a top-level GET**, so a mutating GET is triggerable by a link in an email. The
whole protection is therefore a property of the route table, and nothing was watching the route
table.

Audited 2026-08-09 and re-audited 2026-08-25: **no mutating GET is cookie-triggerable today.** Nine
GET handlers touch the DB session and every one is accounted for below — six at the first audit,
plus the four `cloud.py` routes the helper-following scan revealed (one of which replaced an
`auth.py` entry's shape). That result is why this file is a ratchet and not a fix — the
finding was never "there is a bug", it was "nothing would stop one", and only a check that fails on
the next one closes that.

Deliberately NOT an allowlist that grows. The baseline is the exact set of (module, path, ops); any
new GET that touches the session fails here until a human writes it down with a reason, and the
second check refuses a reason short enough to be a rubber stamp. An allowlist appended to during a
red run is the failure mode this repo has hit before.

The scan reads the AST, not a grep, because a route's decorator and its writes are lines apart and a
line-oriented pattern cannot join them.

**It also follows same-module helper calls, and it did not until 2026-08-25.** Walking only the
route function's own body means *any* write moved one call away leaves the gate's remit — and one
already had. `GET /auth/cloud/callback` delegates everything to `_link_account()`, which does
`db.add` and `db.commit`; the route body itself touches the session **not at all**, so a GET that
creates a user was invisible here from the day the massing.cloud door shipped. The assertion
"no GET route touches the DB session without a written reason" was passing over it.

It was found the way these things get found: an unrelated refactor moved `db.add` out of the OAuth
callback into a shared helper, this ratchet went red about the *change*, and following that led to
the route it could never have gone red about at all. **A ratchet noticed the wrong thing loudly
enough to expose the right one.**

Resolution is depth-limited and same-module only: a route's writes are attributed to it if they
happen in a module-level function it calls, transitively, within `_MAX_DEPTH`. Cross-module calls
are still invisible, and that is a stated limit rather than a solved problem — widening it means
resolving imports, and a scanner that guesses which `foo()` it is would be worse than one whose
blind spot is written down.
"""
from __future__ import annotations

import ast
import pathlib
import sys

# The session methods worth noticing. `execute` is included on purpose even though it is usually a
# SELECT — telling the two apart needs the statement, and a heuristic that guessed would quietly
# wave through `db.execute(update(...))`. Six entries reviewed by hand is the cheaper honesty.
SESSION_WRITES = {"commit", "add", "delete", "flush", "merge", "execute"}
SESSION_NAMES = {"db", "session", "s"}

_SCIM_WHY = (
    "Read-only. scim.py:145-146 are select(func.count()) and select(User).order_by(...) — a count "
    "and a page, no INSERT/UPDATE/DELETE reachable from the handler."
)
_VERIF_SUMMARY_WHY = (
    "Read-only. verification.py:40 is db.execute(stmt).scalars() over a select — the summary list. "
    "Nothing in the handler writes."
)
_VERIF_COVERAGE_WHY = (
    "Read-only. verification.py:66 selects status/guid columns and rolls them up in Python, so the "
    "aggregation happens after the fetch and nothing is written."
)
_VERIF_DEVIATIONS_WHY = (
    "Read-only. verification.py:112 is the same db.execute(stmt).scalars() shape as the summary "
    "route, filtered to deviations. No write."
)
_OAUTH_WHY = (
    "OAuth redirect-back; it MUST be a GET because the provider chooses the method. It does create "
    "a user, but the authority is the provider's one-time code, not our cookie — a forged link "
    "carries no valid code and gets a 403. Not cookie-triggerable. NOTE the ops shrank from "
    "('add','commit') to ('commit',) on 2026-08-25: the INSERT moved into "
    "`auth.get_or_create_sso_user` (the seeding-race fix). The route still creates a user — the "
    "helper does it now — so this shape change is bookkeeping, not a reduction in what the route "
    "does, and it is written down because the two are indistinguishable from the ops tuple alone."
)
_CLOUD_CALLBACK_WHY = (
    "The massing.cloud broker's redirect-back, and the same argument as the OAuth callback above: "
    "it MUST be a GET because the broker chooses the method, and the authority is the broker's "
    "one-time code plus the PKCE state, not our cookie. A forged link carries neither and is "
    "refused before any write. It creates a user and writes the CloudIdentity link, entirely inside "
    "`_link_account()` — which is exactly why it was INVISIBLE here until the scan learned to "
    "follow same-module helpers on 2026-08-25."
)
_CLOUD_LIBRARY_WHY = (
    "Read-only to the application's own state. The single write is `_fresh_access_token()` rotating "
    "the CALLER'S OWN massing.cloud token when it is at or near expiry and persisting the rotated "
    "pair — refresh tokens rotate on use, so not storing the new one would strand the link. Nothing "
    "an attacker supplies is written and no project data changes. The residual, stated rather than "
    "waved away: a cross-site GET does reach it with the Lax cookie and can force a rotation, whose "
    "worst case is the victim's own link needing a re-sign-in (`401 massing.cloud session expired`). "
    "That is a self-inflicted nuisance, not an escalation, and making these POSTs would break the "
    "library being browsable."
)

# module -> path -> (ops, why this GET is allowed to touch the session)
BASELINE: dict[str, dict[str, tuple[tuple[str, ...], str]]] = {
    "aec_api/routers/auth.py": {
        "/auth/oauth/{provider}/callback": (("commit",), _OAUTH_WHY),
    },
    "aec_api/routers/cloud.py": {
        "/auth/cloud/callback": (("add", "commit"), _CLOUD_CALLBACK_WHY),
        "/cloud/library/projects": (("commit",), _CLOUD_LIBRARY_WHY),
        "/cloud/library/projects/{project_id}": (("commit",), _CLOUD_LIBRARY_WHY),
        "/cloud/library/models/{model_id}": (("commit",), _CLOUD_LIBRARY_WHY),
    },
    "aec_api/routers/scim.py": {
        "/scim/v2/Users": (("execute",), _SCIM_WHY),
    },
    "aec_api/routers/verification.py": {
        "/projects/{pid}/verification": (("execute",), _VERIF_SUMMARY_WHY),
        "/projects/{pid}/verification/coverage": (("execute",), _VERIF_COVERAGE_WHY),
        "/projects/{pid}/verification/deviations": (("execute",), _VERIF_DEVIATIONS_WHY),
    },
}


#: How far to follow same-module helper calls. 3 covers route -> helper -> helper, which is deeper
#: than anything in this tree today; the cap exists so a cycle or a deep utility chain cannot make
#: the scan quadratic, not because depth 4 would be acceptable.
_MAX_DEPTH = 3


def _direct_ops(fn: ast.AST) -> set[str]:
    """Session methods called on `db`/`session`/`s` in this function's own body."""
    ops: set[str] = set()
    for node in ast.walk(fn):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr in SESSION_WRITES
                and getattr(node.func.value, "id", None) in SESSION_NAMES):
            ops.add(node.func.attr)
    return ops


def _called_names(fn: ast.AST) -> set[str]:
    """Bare `foo(...)` calls — candidates for same-module helpers. Attribute calls (`x.foo()`) are
    excluded: resolving those needs to know what `x` is, which is the import problem this
    deliberately does not attempt."""
    return {n.func.id for n in ast.walk(fn)
            if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)}


def _ops_with_helpers(fn: ast.AST, module_fns: dict[str, ast.AST],
                      depth: int = 0, seen: frozenset[str] = frozenset()) -> set[str]:
    """`fn`'s own session ops, plus those of the same-module functions it calls, transitively.

    `seen` makes recursion (direct or mutual) terminate on its own rather than relying on the depth
    cap to paper over it.
    """
    ops = _direct_ops(fn)
    if depth >= _MAX_DEPTH:
        return ops
    for name in _called_names(fn):
        helper = module_fns.get(name)
        if helper is None or name in seen:
            continue
        ops |= _ops_with_helpers(helper, module_fns, depth + 1, seen | {name})
    return ops


def _scan(root: pathlib.Path) -> dict[str, dict[str, tuple[str, ...]]]:
    found: dict[str, dict[str, tuple[str, ...]]] = {}
    for path in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(open(path, encoding="utf-8").read())
        except SyntaxError:
            continue
        rel = path.relative_to(root).as_posix()
        module_fns: dict[str, ast.AST] = {
            n.name: n for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            gets = [d for d in fn.decorator_list
                    if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                    and d.func.attr == "get"]
            if not gets:
                continue
            ops = _ops_with_helpers(fn, module_fns, seen=frozenset({fn.name}))
            if not ops:
                continue
            arg = gets[0].args[0] if gets[0].args else None
            route = arg.value if isinstance(arg, ast.Constant) else "<computed:" + fn.name + ">"
            found.setdefault(rel, {})[route] = tuple(sorted(ops))
    return found


FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAILED.append(name)


_root = pathlib.Path(__file__).parent / "src"
_found = _scan(_root)
_total = sum(len(v) for v in _found.values())
_files = len(list(_root.rglob("*.py")))

# Silence is not a signal: a scan that finds nothing has broken, not passed. Five is below the
# audited six on purpose — one route may legitimately be deleted without this becoming a tripwire —
# but a sudden zero means the AST walk stopped matching, not that the routers emptied overnight.
check("the scan reached the routers at all", _total >= 5,
      str(_total) + " GET handler(s) touch the session across " + str(_files) + " files")

_expected = {(m, p) for m, routes in BASELINE.items() for p in routes}
_actual = {(m, p) for m, routes in _found.items() for p in routes}

_new = sorted(_actual - _expected)
check("no GET route touches the DB session without a written reason", not _new,
      "; ".join(m + " " + p + " " + str(_found[m][p]) for m, p in _new))
if _new:
    print("\n  Our session cookie is samesite=lax and there is no CSRF middleware, so Lax is the"
          "\n  entire defence — and Lax does NOT withhold the cookie on a top-level GET. If the"
          "\n  route above changes state, make it a POST. If it only reads (or only writes an audit"
          "\n  row), add it to BASELINE **with the reason written out** — the reason IS the review.\n")

_gone = sorted(_expected - _actual)
check("BASELINE carries no dead entries", not _gone,
      "" if not _gone else str(_gone) + " — a baseline with dead entries stopped being derived")

_drift = [m + " " + p + ": " + str(ops) + " was " + str(BASELINE[m][p][0])
          for m, routes in _found.items() for p, ops in routes.items()
          if (m, p) in _expected and ops != BASELINE[m][p][0]]
check("no reviewed route changed how it touches the session", not _drift, "; ".join(_drift))

# The twin. Without it every check above passes on a BASELINE of bare entries, which is an allowlist
# wearing a review's clothes. 60 chars is not a quality bar — it is a floor under "ok".
_thin = [m + " " + p + " (" + str(len(why)) + " chars)"
         for m, routes in BASELINE.items() for p, (ops, why) in routes.items()
         if not ops or len(why) <= 60]
check("every BASELINE entry carries a real reason, not a word", not _thin, "; ".join(_thin))

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_mutating_get OK")
