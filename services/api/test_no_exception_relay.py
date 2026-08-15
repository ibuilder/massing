"""No exception text may reach a response body.

Three times now. `py/stack-trace-exposure` was fixed in v0.3.956 (`_unavailable(str(exc))` relaying
engine messages); the identical shape was written again in v0.3.961, in a module authored *after*
that fix, and CodeQL flagged it within the hour; grepping the same file then found a third instance
that had shipped for several releases and was never flagged at all, because **CodeQL's alert list is
diff-scoped** — it reports what a push changed, not what a file contains.

That last part is why this file exists rather than a note. A rule enforced by "remember the lesson"
has already failed twice, and the one check that might have caught the third only looks at diffs.

## What is flagged

An `except ... as <name>:` handler whose body **returns** a value built from `<name>` — `str(name)`,
an f-string interpolating it, or the name itself. That is narrow on purpose: raising, logging,
re-raising and storing are all fine, and only the return path puts the text where a caller reads it.

## What to do instead

Log it server-side (`logger.exception(...)`) and return a stable sentence you wrote. If the caller
genuinely needs to distinguish causes, add a code you control — never the exception's own words,
which come from whatever library raised and can carry paths, queries and internal state.
"""
from __future__ import annotations

import ast
from pathlib import Path

SRC = Path(__file__).resolve().parent / "src" / "aec_api"

#: Sites that relay exception text on purpose, each with the reason it is safe. **Not a suppression
#: list** — it is the debt, recorded, and the gate fails in BOTH directions: a new relay that is not
#: here fails, and an entry here that no longer relays fails too, so the list cannot become a
#: graveyard that quietly stops describing anything.
#:
#: The reasons were checked, not assumed. Every `connections.py` route carries
#: `Depends(require_admin_user)` — read from the file, not inferred from the path — so those are an
#: **administrator being shown the error from a connection string the administrator just typed**.
#: That is a different risk class from an anonymous caller receiving a driver's stack trace, and
#: removing the text would make "test this connection" useless at the one job it has.
#:
#: What is NOT allowed anywhere: relaying to a project-scoped or unauthenticated caller.
ALLOWED: dict[str, str] = {
    "calc_fields.py": "SyntaxError.msg from parsing the USER'S OWN formula — 'invalid syntax' is "
                      "feedback on their input and carries nothing of ours",
    "connectors.py": "admin-only (require_admin_user on every /connections route, verified in the "
                     "source); the admin typed the DSN whose error is being shown",
    "routers/connections.py": "same — admin-only, and an upstream ACC/QuickBooks failure is the "
                              "answer the admin asked for",
    "conntest.py": "admin-only credential test; 'APS auth failed: …' is the whole point of it",
    "license_cloud.py": "admin-facing licence check against our own service, class-name prefixed",
    "mailer.py": "admin-only SMTP test — an admin diagnosing mail needs the server's refusal",
    "speckle_bridge.py": "admin-facing connection status for a server the admin configured",
    "sheet_extract.py": "pypdf's complaint about a PDF THE CALLER uploaded",
}

_FAILURES: list[str] = []


def check(name: str, ok: bool, note: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}   {note}")
    if not ok:
        _FAILURES.append(name)


#: Attributes that ARE the exception's own words. `.args[0]` is the message; `.detail` is FastAPI's;
#: `.strerror` is the OS's. Anything else — `exc.cycle`, `exc.row`, `exc.code` — is a structured field
#: the raising code chose to expose, and returning one is the recommended alternative, not the defect.
_TEXT_ATTRS = {"args", "message", "detail", "reason", "strerror", "msg"}


def _relays_text(node: ast.AST, name: str) -> bool:
    """Does this expression carry the exception's *text* (as opposed to a structured field)?

    The distinction is the whole value of this gate. `str(exc)` hands the caller whatever library
    raised; `list(exc.cycle)` hands them a list of activity ids our own engine put there. A checker
    that cannot tell them apart flags every honest refusal path and gets switched off.
    """
    # `type(exc).__name__` is the exception's CLASS, not its message — "ValueError", never the path
    # or the query it was raised about. It is the recommended way to say what kind of thing failed,
    # so flagging it would push people back toward `str(exc)`.
    classname_only = {a for n in ast.walk(node)
                      if isinstance(n, ast.Call) and isinstance(n.func, ast.Name)
                      and n.func.id == "type" and len(n.args) == 1
                      for a in [n.args[0]] if isinstance(a, ast.Name)}
    for n in ast.walk(node):
        if n in classname_only:
            continue
        if isinstance(n, ast.Attribute) and isinstance(n.value, ast.Name) and n.value.id == name:
            if n.attr in _TEXT_ATTRS:
                return True
            continue                                     # a structured field — fine
        if isinstance(n, ast.Name) and n.id == name:
            # A bare name reached without going through an allowed attribute: `str(exc)`,
            # f"{exc}", repr(exc), "%s" % exc, or the exception object itself.
            parent_attrs = [p for p in ast.walk(node)
                            if isinstance(p, ast.Attribute) and p.value is n and p.attr not in _TEXT_ATTRS]
            if not parent_attrs:
                return True
    return False


def relays(tree: ast.AST) -> list[tuple[int, str]]:
    """(line, why) for every `return` that carries a caught exception's TEXT."""
    out: list[tuple[int, str]] = []
    for handler in (n for n in ast.walk(tree) if isinstance(n, ast.ExceptHandler)):
        if not handler.name:
            continue
        for node in ast.walk(handler):
            if isinstance(node, ast.Return) and node.value is not None \
                    and _relays_text(node.value, handler.name):
                out.append((node.lineno, f"returns the text of `{handler.name}`"))
    return out


#: A file that must fail. Without it, a `relays()` that silently returned `[]` — a rename, a walk
#: that stopped descending, an AST change — would make this gate pass on every file forever, which
#: is the failure mode a source scanner reaches first and shows least.
_BAD = '''
def f():
    try:
        g()
    except ValueError as exc:
        return {"ok": False, "why": str(exc)}
'''
_GOOD = '''
def structured():
    try:
        g()
    except CycleError as exc:
        return {"ok": False, "cycle": list(exc.cycle)}   # OUR field, not the library's words


def classname():
    try:
        g()
    except OSError as exc:
        return {"ok": False, "why": f"failed ({type(exc).__name__})"}   # the CLASS, not the message


def f():
    try:
        g()
    except ValueError:
        logger.exception("g failed")
        return {"ok": False, "why": "it did not work"}


def h():
    try:
        g()
    except ValueError as exc:
        logger.warning("g failed: %s", exc)     # logging is fine
        raise RuntimeError("nope") from exc     # so is chaining
'''


def main() -> int:
    # --- the detector detects, and does not fire on the correct shape ------------------------------
    check("the detector fires on a return that relays an exception",
          len(relays(ast.parse(_BAD))) == 1,
          "without this, an empty result set reads exactly like a clean tree")

    check("...and does NOT fire on logging, chaining, or a stable sentence",
          not relays(ast.parse(_GOOD)),
          "logging the cause server-side is the fix, so flagging it would push people to drop it")

    # --- the tree ----------------------------------------------------------------------------------
    files = sorted(SRC.rglob("*.py"))
    check("the scan actually reached the application tree",
          len(files) > 50, f"{len(files)} modules under aec_api/")

    hits: list[str] = []
    seen: set[str] = set()
    for path in files:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:                              # pragma: no cover — a broken file fails elsewhere
            continue
        found = relays(tree)
        key = path.relative_to(SRC).as_posix()
        if found:
            seen.add(key)
            if key in ALLOWED:
                continue
            rel = path.relative_to(SRC.parent.parent.parent)
            hits += [f"{rel.as_posix()}:{line} — {why}" for line, why in found]

    check("no UNRECORDED handler returns the text of the exception it caught",
          not hits,
          (f"{len(hits)} new relay(s) — log the cause and return a sentence you wrote, or record it "
           "in ALLOWED with the reason:\n        " + "\n        ".join(hits)) if hits
          else f"{len(files)} modules scanned, {len(ALLOWED)} recorded, no new relays")

    # The ratchet's other direction. Without it ALLOWED becomes a graveyard of names that were fixed
    # long ago, and it stops describing anything — the same failure `test_vendor_reachable` guards.
    stale = sorted(set(ALLOWED) - seen)
    check("...and the allowance list has no stale entries",
          not stale,
          f"these no longer relay — delete them from ALLOWED: {', '.join(stale)}" if stale
          else "every recorded allowance is still a live relay")

    if _FAILURES:
        print(f"FAILED: {', '.join(_FAILURES)}")
        return 1
    print("test_no_exception_relay OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
