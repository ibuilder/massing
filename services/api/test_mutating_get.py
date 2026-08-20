"""R43-CSRF-GET — no route may change state on a GET, because Lax is our entire CSRF defence.

The session cookie is set `samesite="lax"` in `routers/auth.py` and `routers/saml.py`, and there is
no CSRF middleware anywhere in the app. Lax withholds the cookie on a cross-site POST/PATCH/DELETE
**but sends it on a top-level GET**, so a mutating GET is triggerable by a link in an email. The
whole protection is therefore a property of the route table, and nothing was watching the route
table.

Audited 2026-08-09: **no mutating GET exists today.** Six GET handlers touch the DB session and
every one is accounted for below. That result is why this file is a ratchet and not a fix — the
finding was never "there is a bug", it was "nothing would stop one", and only a check that fails on
the next one closes that.

Deliberately NOT an allowlist that grows. The baseline is the exact set of (module, path, ops); any
new GET that touches the session fails here until a human writes it down with a reason, and the
second check refuses a reason short enough to be a rubber stamp. An allowlist appended to during a
red run is the failure mode this repo has hit before.

The scan reads the AST, not a grep, because a route's decorator and its writes are lines apart and a
line-oriented pattern cannot join them.
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
    "carries no valid code and gets a 403. Not cookie-triggerable."
)

# module -> path -> (ops, why this GET is allowed to touch the session)
BASELINE: dict[str, dict[str, tuple[tuple[str, ...], str]]] = {
    "aec_api/routers/auth.py": {
        "/auth/oauth/{provider}/callback": (("add", "commit"), _OAUTH_WHY),
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


def _scan(root: pathlib.Path) -> dict[str, dict[str, tuple[str, ...]]]:
    found: dict[str, dict[str, tuple[str, ...]]] = {}
    for path in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(open(path, encoding="utf-8").read())
        except SyntaxError:
            continue
        rel = path.relative_to(root).as_posix()
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            gets = [d for d in fn.decorator_list
                    if isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                    and d.func.attr == "get"]
            if not gets:
                continue
            ops = set()
            for node in ast.walk(fn):
                if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                        and node.func.attr in SESSION_WRITES
                        and getattr(node.func.value, "id", None) in SESSION_NAMES):
                    ops.add(node.func.attr)
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
