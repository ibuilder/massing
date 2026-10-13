"""Can a recipient REACH the public write routes built for them? — PORTAL-TXN-DARK.

`POST /shared/{token}/decision` and `POST /shared/{token}/comment` are public by design: the token in
the URL is the credential, inputs are whitelisted and length-capped, each token carries a hard cap,
and an unknown or revoked token 404s. Both are careful and both were **unreachable** — the page a
client actually opens, `client_portal.to_html`, had no `<form`, no `<button`, no `fetch(` and no
mention of either path. The whole transaction had neither end built.

**The telling detail is that the page had already promised otherwise.** Its conversation card ended
with *"Messages posted through this link reach the project team; their replies appear here"* — on a
page with nothing that could post one. *A surface can carry the sentence describing a capability it
does not have, and the sentence is what a reviewer reads.*

### What this gate asks, and the two arms are different questions

1. **Every public write route on `/shared/{token}` is posted to by the page.** The population is
   derived from the routers by AST — not a list here — so a third public write route added tomorrow
   must either be reachable from the page or red this build. It runs in **both directions**: a page
   posting to a path no router serves is also a finding, which is the typo nobody would otherwise
   see until a client clicked.

2. **Every hook the page's script reaches for exists in the page's markup.** The script and the
   markup are written in two different functions and nothing but this ties them together: rename
   `id="comment-send"` and the page still renders, still looks complete, and silently does nothing.
   Arm 1 cannot see that — it only reads the script — which is why both arms are here.

The hook population is derived with **no exemption list**, and that is deliberate after what
COURT-SPLIT and `noRespelledShapes` paid to learn. A kebab-case literal (lowercase, at least one
hyphen, no `/`, `[`, space or `_`) is an id or an attribute name and nothing else; every other
literal the script holds is a verb (`"click"`), a header (`"Content-Type"`), a media type
(`"application/json"`), a selector (`"button[data-action]"`), a path (`"/decision"`) or an English
sentence, and each is excluded by the SHAPE of the literal rather than by being named here. Measured
on today's script: 11 hooks derived, 0 false positives. *A rule that needs an exemption list is a
rule whose population is wrong.*

### Nothing is ever interpolated into the script, and arm 3 makes that structural

`esc()` is an HTML escaper. A value escaped with it is **not** safe inside a `<script>`, so the only
sound rule is that no value is ever put there — which is why `_PAGE_JS` is a module constant with no
placeholders instead of part of the f-string that builds the page, and why the script derives its own
endpoints from `location.pathname` rather than being handed the token. Arm 3 asserts the constant is
a plain string (not an f-string) and that the module never formats it.

### Why it is a source-level check, said plainly

This reads the rendered page, so it proves the control is THERE; it cannot prove clicking it works.
Wrapping the whole script in `if (false)` passes — the same bargain `test_route_reachability` makes
for URL literals, and `test_verdict_coverage` for a coverage render. The complement is
`test_portal_txn.py`, which drives both routes over HTTP. Written down here rather than discovered
later.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_portal_public_reach.py
"""
from __future__ import annotations

import ast
import os
import re
import sys
from pathlib import Path
from typing import Any

HERE = Path(__file__).resolve().parent
#: Anchored on `__file__`, never on the working directory. `run_tests.py` chdirs into `services/api`
#: and `ci.yml` invokes `python services/api/run_tests.py` from the repo ROOT — and a `rglob` over a
#: directory that is not there yields nothing and raises nothing, so a relative anchor would have
#: reported a clean tree under CI and nowhere else. That is exactly what `test_schema_types_agree`
#: shipped and had to fix; this file was written after reading that lesson.
ROUTERS = HERE / "src" / "aec_api" / "routers"
PORTAL_SRC = HERE / "src" / "aec_api" / "client_portal.py"

os.environ.setdefault("DATABASE_URL", "sqlite:///./test_portal_public_reach.db")
os.environ.setdefault("STORAGE_DIR", "./test_storage_portalreach")

sys.path.insert(0, str(HERE / "src"))
sys.path.insert(0, str(HERE.parent / "data" / "src"))

FAILED: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


class Unclassified(Exception):
    """Raised when the walk meets a route it cannot rule on. Never caught into a skip.

    It FAILS CLOSED because the two blind spots `test_seeding_sweep` paid for were both a predicate
    deciding what to LOOK at: a route whose authentication this cannot classify would otherwise be
    dropped from the population silently, and a population smaller than it looks reports a clean
    tree in exactly the same words as a clean tree.
    """


# ---------------------------------------------------------------------------------------------
# ARM 1 — the population: public write routes under /shared/{token}

#: Dependencies that DO authenticate. A route carrying one of these is not public and not ours.
_AUTH_DEPS = {"require_role", "require_admin", "current_user", "require_scope", "require_plan",
              "api_actor", "current_actor"}
#: Dependencies that carry no authority at all. Everything else reds the build.
_OPEN_DEPS = {"get_db", "get_session", "Request", "Response"}
_WRITE_METHODS = ("post", "put", "patch", "delete")


def _depends_callees(fn: ast.FunctionDef) -> list[str]:
    """Every name passed to a `Depends(...)` in this function's signature, outermost call included.

    `Depends(require_role("editor"))` yields `require_role`, `Depends(get_db)` yields `get_db`.
    """
    out: list[str] = []
    for d in list(fn.args.defaults) + [k for k in fn.args.kw_defaults if k is not None]:
        if not (isinstance(d, ast.Call) and isinstance(d.func, ast.Name) and d.func.id == "Depends"):
            continue
        if not d.args:
            raise Unclassified(f"{fn.name}: Depends() with no argument")
        a = d.args[0]
        if isinstance(a, ast.Name):
            out.append(a.id)
        elif isinstance(a, ast.Call) and isinstance(a.func, ast.Name):
            out.append(a.func.id)
        elif isinstance(a, ast.Attribute):
            out.append(a.attr)
        else:
            raise Unclassified(f"{fn.name}: Depends({ast.dump(a)[:60]}…) is not a name or a call")
    return out


def public_write_paths(src: str, where: str = "<src>") -> set[str]:
    """Paths of the PUBLIC write routes registered under `/shared/`, by AST over a router module.

    A route is public when every one of its `Depends` is in `_OPEN_DEPS`; it is authenticated when
    any is in `_AUTH_DEPS`; anything else raises `Unclassified`.
    """
    found: set[str] = set()
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        for dec in node.decorator_list:
            if not (isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute)):
                continue
            if dec.func.attr not in _WRITE_METHODS:
                continue
            if not (dec.args and isinstance(dec.args[0], ast.Constant)
                    and isinstance(dec.args[0].value, str)):
                raise Unclassified(f"{where}:{node.name}: route path is not a literal")
            path = dec.args[0].value
            if not path.startswith("/shared/"):
                continue
            deps = _depends_callees(node)  # type: ignore[arg-type]
            if any(d in _AUTH_DEPS for d in deps):
                continue
            unknown = [d for d in deps if d not in _OPEN_DEPS]
            if unknown:
                raise Unclassified(
                    f"{where}:{node.name} ({path}) depends on {unknown} — neither a known authoriser "
                    f"nor a known open dependency. Add it to _AUTH_DEPS or _OPEN_DEPS; a route this "
                    f"cannot classify must never be dropped from the population silently")
            found.add(path)
    return found


def _suffix(path: str) -> str:
    """`/shared/{token}/decision` → `/decision`. The script builds `location.pathname + suffix`."""
    head = "/shared/{token}"
    if not path.startswith(head):
        raise Unclassified(f"{path} is under /shared/ but not under {head}")
    return path[len(head):]


# ---------------------------------------------------------------------------------------------
# The served page, split into its script and its markup

_SCRIPT_RE = re.compile(r"<script>(.*?)</script>", re.S)


def split_page(html: str) -> tuple[str, str]:
    """(markup, script). The markup has every script block REMOVED, deliberately: arm 2 asks whether
    the page DECLARES the hook, and a script mentioning its own id must not answer for it."""
    scripts = "\n".join(_SCRIPT_RE.findall(html))
    return _SCRIPT_RE.sub("", html), scripts


_POST_RE = re.compile(r'\bpost\(\s*"(/[a-z][a-z0-9/_-]*)"')
#: Lowercase kebab-case: an id or an attribute name, and nothing else the script holds has this shape.
_HOOK_RE = re.compile(r'"([a-z][a-z0-9]*(?:-[a-z0-9]+)+)"')


def script_posts(script: str) -> set[str]:
    return set(_POST_RE.findall(script))


def script_hooks(script: str) -> set[str]:
    return set(_HOOK_RE.findall(script))


def missing_hooks(markup: str, script: str) -> list[str]:
    """Hooks the script reaches for that the markup does not declare, as an id or an attribute."""
    return sorted(h for h in script_hooks(script)
                  if f'id="{h}"' not in markup and f'{h}="' not in markup)


def reach_verdict(serves: set[str], posts: set[str]) -> tuple[list[str], list[str]]:
    """(unreachable routes, posts to nothing). A SEPARATE function from the reporting, because
    `test_unique_read_guard`'s own first draft asserted that its analyser still REPORTED a site and a
    mutation routing every verdict to "safe" passed. Reporting a site and ruling on it are two
    questions; this is the one to mutate."""
    return sorted(serves - posts), sorted(posts - serves)


# ---------------------------------------------------------------------------------------------
# PRECONDITIONS AND MUTATIONS — before any verdict is printed

#: The page as it SHIPPED, frozen. Faithful in the one respect that matters: the conversation card
#: carries the sentence promising a message reaches the team, and there is nothing to send one with.
#: Frozen in-tree rather than fetched with `git show`, because CI's checkout is shallow and
#: `test_gap_records` failed closed on every build learning that. A truncated fixture reds the build
#: rather than letting the replay pass by having nothing to find.
_PRE_FIX_PAGE = (
    '<!doctype html><html><head><title>Acme — readiness</title></head><body><main>'
    '<h1>Acme</h1><div class="muted">Project readiness · read-only shared digest</div>'
    '<div class="card"><b>Readiness</b><span>62%</span></div>'
    '<div class="card"><b>Master Builder Protocol</b><ul><li>1. Place</li></ul></div>'
    '<div class="card"><b>Conversation</b><ul><li>hello</li></ul>'
    '<div class="muted">Messages posted through this link reach the project team; '
    'their replies appear here.</div></div>'
    '<div class="muted">Read-only shared project digest.</div>'
    '</main></body></html>')

_SERVES = set()
for _f in sorted(ROUTERS.glob("*.py")):
    _SERVES |= public_write_paths(_f.read_text(encoding="utf-8"), _f.name)
_SUFFIXES = {_suffix(p) for p in _SERVES}

check("the router walk found the public write surface it exists to watch",
      len(_SERVES) >= 2,
      f"only {len(_SERVES)} public write route(s) under /shared/: {sorted(_SERVES)} — a population "
      "this small means the walk broke, not that the surface shrank; its verdict below would be "
      "'clean' either way")

from aec_api.client_portal import to_html  # noqa: E402

_DIGEST: dict[str, Any] = {
    "project": "Acme", "jurisdiction": "Miami-Dade, FL", "readiness_pct": 62,
    "ready_steps": 5, "gap_steps": 3, "step_count": 8,
    "steps": [{"n": 1, "title": "Place & context", "status": "ready"}],
    "activity": [], "conversation": [], "note": "Shared project digest.",
}
_PAGE = to_html(_DIGEST)
_MARKUP, _SCRIPT = split_page(_PAGE)

check("the page split found a script to analyse",
      len(_SCRIPT) > 400 and len(_MARKUP) > 800,
      f"script {len(_SCRIPT)} chars, markup {len(_MARKUP)} chars — with either empty both arms "
      "below report nothing and read as a clean page")
check("the hook derivation found the page's controls",
      len(script_hooks(_SCRIPT)) >= 4,
      f"only {sorted(script_hooks(_SCRIPT))} derived — the kebab-case rule stopped matching, and an "
      "arm that derives nothing passes every page")

# REPLAY — the page as shipped must be re-found, and the verdict is what is asserted, not the parse.
_pre_markup, _pre_script = split_page(_PRE_FIX_PAGE)
_pre_unreachable, _pre_orphan = reach_verdict(_SUFFIXES, script_posts(_pre_script))
check("replays the shipped page and finds BOTH write routes unreachable from it",
      set(_pre_unreachable) == {"/comment", "/decision"} and not _pre_orphan,
      f"re-found {_pre_unreachable} (orphans {_pre_orphan}), expected both /comment and /decision — "
      "the fixture or the derivation drifted, and a replay that finds nothing cannot vouch for a "
      "clean verdict on today's page")
check("the frozen fixture still carries the promise that made it a defect",
      "reach the project team" in _PRE_FIX_PAGE and "<script>" not in _PRE_FIX_PAGE,
      "the fixture was truncated or edited — it is evidence of a moment, not a sample page")

# MUTATION 1 — rename one id in the MARKUP only. Arm 1 cannot see this; arm 2 must.
_renamed = _MARKUP.replace('id="comment-send"', 'id="comment-sent"')
check("a renamed markup id is caught by arm 2 (and is invisible to arm 1)",
      _renamed != _MARKUP and "comment-send" in missing_hooks(_renamed, _SCRIPT)
      and not reach_verdict(_SUFFIXES, script_posts(_SCRIPT))[0],
      f"mutation changed the markup={_renamed != _MARKUP}, arm 2 reported "
      f"{missing_hooks(_renamed, _SCRIPT)} — a page whose script reaches for an id the markup does "
      "not declare renders, looks complete and does nothing")

# MUTATION 2 — delete one post target from the SCRIPT. Arm 1 must fire.
_cut = re.sub(r'post\("/comment",[^;]*;', "", _SCRIPT)
check("a deleted post target is caught by arm 1",
      _cut != _SCRIPT and reach_verdict(_SUFFIXES, script_posts(_cut))[0] == ["/comment"],
      f"mutation changed the script={_cut != _SCRIPT}, arm 1 reported "
      f"{reach_verdict(_SUFFIXES, script_posts(_cut))[0]}")

# MUTATION 3 — the verdict function itself, routed to "everything is fine".
check("the verdict is what the mutations above are asserting, not merely the parse",
      reach_verdict({"/decision"}, set()) == (["/decision"], [])
      and reach_verdict(set(), {"/nope"}) == ([], ["/nope"]),
      "reach_verdict no longer distinguishes an unreachable route from an orphan post")

# FAIL CLOSED — a route this cannot classify must raise, never be dropped.
_SYNTH_UNKNOWN = '''
@router.post("/shared/{token}/wire")
def wire(token: str, db: Session = Depends(get_db), who: str = Depends(mystery_gate)):
    return {}
'''
try:
    public_write_paths(_SYNTH_UNKNOWN, "<synth>")
    _closed = False
except Unclassified:
    _closed = True
check("a route with an unclassifiable dependency reds the build instead of leaving the population",
      _closed,
      "public_write_paths accepted an unknown Depends — every route it cannot rule on would be "
      "invisible to its own output, which is the shape of both blind spots test_seeding_sweep paid for")


# ---------------------------------------------------------------------------------------------
# ARM 3 — nothing is interpolated into the script

def page_js_is_literal(src: str) -> tuple[bool, str]:
    """(ok, why). `_PAGE_JS` must be a plain string constant and must never be formatted."""
    tree = ast.parse(src)
    node = None
    for n in ast.walk(tree):
        if isinstance(n, ast.Assign) and any(
                isinstance(t, ast.Name) and t.id == "_PAGE_JS" for t in n.targets):
            node = n.value
    if node is None:
        return False, "_PAGE_JS is not assigned in client_portal.py"
    if isinstance(node, ast.JoinedStr):
        return False, "_PAGE_JS is an f-string — a value interpolated into a SCRIPT context is not "\
                      "made safe by esc(), which is an HTML escaper"
    if not (isinstance(node, ast.Constant) and isinstance(node.value, str)):
        return False, f"_PAGE_JS is {type(node).__name__}, not a plain string constant"
    for n in ast.walk(tree):
        if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and isinstance(n.func.value, ast.Name) and n.func.value.id == "_PAGE_JS"
                and n.func.attr in ("format", "format_map", "replace")):
            return False, f"_PAGE_JS.{n.func.attr}(...) is called — the constant is being templated"
        if (isinstance(n, ast.BinOp) and isinstance(n.op, ast.Mod)
                and isinstance(n.left, ast.Name) and n.left.id == "_PAGE_JS"):
            return False, "_PAGE_JS % (...) is applied — the constant is being templated"
    return True, ""


_PORTAL = PORTAL_SRC.read_text(encoding="utf-8")
_ok3, _why3 = page_js_is_literal(_PORTAL)
check("the page's script is a plain constant nothing is interpolated into", _ok3, _why3)
# Both directions, so the arm is not satisfied by a parser that answers yes to everything.
_fstr_ok, _ = page_js_is_literal('_PAGE_JS = f"var x = {token};"')
_fmt_ok, _ = page_js_is_literal('_PAGE_JS = "var x = {};"\nx = _PAGE_JS.format(token)')
check("arm 3 refuses an f-string and a .format() — it is not answering yes to everything",
      not _fstr_ok and not _fmt_ok,
      f"f-string accepted={_fstr_ok}, .format accepted={_fmt_ok}")


# ---------------------------------------------------------------------------------------------
# THE VERDICT

_unreachable, _orphan = reach_verdict(_SUFFIXES, script_posts(_SCRIPT))
check(f"every public write route under /shared/{{token}} is reachable from the page it serves "
      f"({len(_SERVES)} route(s))",
      not _unreachable,
      f"{_unreachable} served but unreachable — the endpoint is complete, careful and public, and "
      "no client can exercise it. Put a control on the page (client_portal.to_html), not a second "
      "endpoint")
check("the page posts to nothing the routers do not serve",
      not _orphan,
      f"the page posts to {_orphan}, which no router registers — a client clicking that control "
      "gets a 404 and the page tells them to ask for a fresh link")

_missing = missing_hooks(_MARKUP, _SCRIPT)
check(f"every hook the page's script reaches for is declared in its markup "
      f"({len(script_hooks(_SCRIPT))} hook(s))",
      not _missing,
      f"{_missing} is looked up by the script and declared nowhere in the page — the control renders "
      "and does nothing, which is the one failure mode arm 1 cannot see")

print()
if FAILED:
    print(f"portal_public_reach: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print(f"portal_public_reach: all checks passed — {len(_SERVES)} public write route(s), "
      f"{len(script_hooks(_SCRIPT))} hooks, 0 unreachable")
