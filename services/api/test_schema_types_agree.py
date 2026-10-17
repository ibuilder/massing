"""Does the committed `apps/web/src/api/schema.d.ts` describe the API this server actually serves?

`apps/web/src/api/schema.d.ts` is generated from the FastAPI spec by `openapi-typescript` and is
**committed**, so it is a claim about the server checked in beside the client. Nothing was checking
the claim, and it was false by a wide margin on the day it was written.

MEASURED 2026-09-25, before this gate existed:

    paths the app serves                947
    paths `schema.d.ts` declared        500
    missing                             448, scattered across 165 of 203 path groups
    declared but no longer served         1

**It is NOT staleness, and the name it was filed under ("SCHEMA-STALE") pointed the next reader at
the one action that could not fix it.** Stale implies it was once right. `schema.d.ts` and the
`apps/web/.gitignore` line hiding its input were last written in the SAME commit (`8432a88`,
2026-09-11), and the app has *fewer* route decorators today — 1016 against 1022 at that commit — so
drift cannot account for a 448-path gap in the direction it runs. The types were already half the
API when they were generated. Re-running the generator as documented would have reproduced the same
file, because:

**The generator's input was a file nobody tracked.** `package.json` ran
`openapi-typescript src/api/openapi.json -o src/api/schema.d.ts`, and `apps/web/.gitignore` ignores
`src/api/openapi.json`. On a fresh clone the command fails for want of an input; on a machine that
has one it regenerates from whatever dump is sitting there, prints a green tick and writes the same
stale file. *"Regenerate the types" did not mean "read the server", and nothing said so.* Fixed in
the same change: `apps/web/scripts/gen-api-types.mjs` dumps the spec from `aec_api.main:app` into a
temp file it deletes, so there is no persistent input left to be stale.

WHY A GATE AND NOT JUST THE GENERATOR FIX
    A generator can only be *run*. Nothing makes anyone run it, and the failure this file exists to
    catch is precisely the one that produces no symptom: a route added on the Python side, no type
    error anywhere, `npm run build` green, and a committed file that quietly describes a different
    server. **The gap was invisible for a fortnight because every audit in the tree exempts this file
    by name** — `deadFieldScope`, `docComments`, `unfiledMap`, `deadFieldTyped`, `noRespelledShapes`,
    `test_route_reachability` and `test_file_sizes` all skip it, each for a good reason of its own.
    Seven exemptions and no owner is how an artifact stops being checked by anybody.

    (`test_route_reachability`'s exemption is the sharpest of the seven and worth reading beside this
    one: it used to count `schema.d.ts` as client code, so **29 routes were "called" by a generated
    file restating the server's own route table**. That is the opposite error — treating the artifact
    as evidence *about* the client. This gate treats it as a claim about the SERVER, which is the one
    thing it genuinely is.)

WHY THIS GATE LIVES IN PYTHON, IN `services/api`
    It needs the live app, which means the backend venv. It does NOT need node: the declared set is
    read out of the committed `schema.d.ts` by parsing it, so nothing has to be generated, no artifact
    passes between CI jobs, and `api-tests` — which already imports the app — is the only job
    involved.

HOW IT FAILS CLOSED
    Every path group in the file must parse into a set of method verdicts. A group whose body the
    parser cannot classify raises rather than being skipped, because the two blind spots this
    repository has paid for twice were both *a predicate deciding what to LOOK at* — and everything
    such a predicate excludes is invisible to its own output, so the count looks complete.

    Five preconditions run BEFORE any verdict is printed, one per way of being silently wrong:

      1.  The parse reaches. A floor on paths and on declared operations, on both sides, so a parser
          that matched nothing cannot report a clean tree.
      2.  Deleting a whole path group from a copy must be FOUND as missing.
      3.  Flipping one `get: operations[...]` to `get?: never` must be FOUND as missing — the
          method-level arm. A path-level check alone passes a file that declares the URL and none of
          its verbs, which is the shape a partially-regenerated file actually has.
      4.  Removing a verb LINE must be REFUSED rather than parsed into a smaller set, because a
          silently-narrowed group is reported as an absent declaration, which reads as "regeneration
          due" rather than "the parser no longer understands this file".
      5.  No route may be registered under an `if`. The whole comparison assumes the app serves the
          same routes here, in CI and on the machine that last ran the generator — and that
          assumption is a precondition, so it is asserted rather than believed. The scanner is shown
          finding a synthetic gated registration first, because a check whose expected answer is zero
          is the easiest kind to break silently.

    Mutation 3 is not a hypothetical: `openapi-typescript` emits all eight HTTP verbs for every path
    and marks the unserved ones `?: never`, so "declared" and "present in the file" are different
    questions and only one of them is the right one.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_schema_types_agree.py
"""
import ast
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, "src")

os.environ["DATABASE_URL"] = "sqlite:///./_schema_types.db"
os.environ.setdefault("STORAGE_DIR", "./_schema_types_store")

from aec_api.main import app  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


HERE = Path(__file__).resolve().parent
SCHEMA = HERE.parents[1] / "apps" / "web" / "src" / "api" / "schema.d.ts"

#: The verbs OpenAPI (and so the generated file) can key a path group on.
_VERBS = ("get", "put", "post", "delete", "options", "head", "patch", "trace")

#: There is deliberately NO carve-out for head/options/trace. An earlier draft excluded them from
#: both sides as "verbs nobody writes" — measured: the live spec emits 0 of all three. So the
#: exclusion bought nothing and silently shrank the population, which is how *a list of known cases
#: becomes a list somebody stopped widening*: an explicit `@router.head` would be skipped on both
#: sides, and a missing declaration for it would read as a clean tree. All eight are compared.


class Unparsable(Exception):
    """Raised when a path group cannot be ruled on. Never caught into a skip."""


def declared(src: str) -> dict[str, set[str]]:
    """`{path: {VERB, ...}}` — every (path, method) the committed `schema.d.ts` says the server serves.

    A verb counts as DECLARED only when it maps to an `operations[...]` entry. `get?: never` is the
    generator saying *this path does not answer GET*, which is a claim to be checked, not an absence
    to be ignored — so parsing "does the word `get` appear in this group" would pass a file that
    declares all 947 URLs and not one of their verbs.
    """
    m = re.search(r"^export interface paths \{\n(.*?)^\}$", src, re.S | re.M)
    if not m:
        raise Unparsable("no `export interface paths` block — the generator's output shape changed")
    body = m.group(1)

    out: dict[str, set[str]] = {}
    # Groups are emitted at exactly four spaces of indent, opening on the quoted path and closing on
    # a `    };` line. Anchoring on the indent is what makes the group boundary unambiguous without a
    # brace counter that would have to understand string literals inside the doc comments.
    for gm in re.finditer(r'^    "([^"]+)": \{\n(.*?)^    \};$', body, re.S | re.M):
        path, group = gm.group(1), gm.group(2)
        if path in out:
            raise Unparsable(f"path {path!r} appears twice in the generated file")
        verbs: set[str] = set()
        for verb in _VERBS:
            # One line per verb, at eight spaces, either `verb: operations["id"];` or `verb?: never;`.
            hit = re.search(rf'^        {verb}(\?)?: (operations\["[^"]+"\]|never);$', group, re.M)
            if hit is None:
                raise Unparsable(
                    f"path {path!r} declares no line for {verb!r} — the generator emits all eight "
                    f"verbs for every group, so this file was hand-edited or the shape changed"
                )
            if hit.group(2) != "never":
                verbs.add(verb.upper())
        out[path] = verbs

    # DERIVE THE POPULATION *AND* PROVE THE DERIVATION REACHES IT. `finditer` yields nothing for a
    # group whose shape it cannot match, silently — and a path absent from `out` is reported below as
    # "served but undeclared", which reads as *regenerate* rather than *the parser broke*. Counting
    # the path keys independently of the group bodies is what makes those two outcomes distinguishable.
    #
    # The key count is derived by a DELIBERATELY CRUDER shape than the group match — any line at four
    # spaces opening a quoted key. A first draft counted `^    "…": \{$`, which fails in exactly the
    # same way the group regex does (both anchor the brace at end of line), so a mutation that broke
    # one broke the other and the counts stayed equal: *a parity check between two derivations that
    # share a failure mode is not a check.* Verified by mutation — trailing whitespace after the brace
    # defeats the strict pair and is caught by this one.
    keys = re.findall(r'^    "([^"]+)":', body, re.M)
    if len(keys) != len(out):
        missed = sorted(set(keys) - set(out))
        raise Unparsable(
            f"{len(keys)} path keys but {len(out)} groups parsed — the group regex did not match "
            f"{missed[:5]}. Every unmatched group would be reported as an undeclared path, so this "
            f"is a parser failure wearing the costume of a stale file")
    return out


def live() -> dict[str, set[str]]:
    """`{path: {VERB, ...}}` from the app's own OpenAPI document — the same document the generator reads."""
    out: dict[str, set[str]] = {}
    for path, group in app.openapi()["paths"].items():
        out[path] = {v.upper() for v in group if v in _VERBS}
    return out


class _CondScan(ast.NodeVisitor):
    """Collects route registrations that sit under an `if`, in one module's AST."""

    _VERBS = ("get", "post", "put", "patch", "delete", "api_route")
    _CALLS = ("include_router", "add_api_route")

    def __init__(self, label: str):
        self.label = label
        self.depth = 0
        self.hits: list[str] = []

    def visit_If(self, node):
        self.depth += 1
        self.generic_visit(node)
        self.depth -= 1

    def visit_FunctionDef(self, node):
        if self.depth:
            for dec in node.decorator_list:
                src = ast.unparse(dec)
                if any(f".{v}(" in src for v in self._VERBS):
                    self.hits.append(f"{self.label}:{node.lineno} {src[:60]}")
        self.generic_visit(node)

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node):
        if (self.depth and isinstance(node.func, ast.Attribute)
                and node.func.attr in self._CALLS):
            self.hits.append(f"{self.label}:{node.lineno} {ast.unparse(node)[:60]}")
        self.generic_visit(node)


def conditional_sites(src: str, label: str) -> list[str]:
    """Route registrations under an `if` in `src` — i.e. a route set that depends on the environment.

    **This is a precondition, not a style rule, and it is written down because the alternative is
    believing it.** The comparison below assumes the app serves the same routes here, in CI and on the
    machine that last ran the generator. One `if settings.FEATURE:` around a decorator breaks that, and
    it breaks the expensive way: this gate would red with *"N served but undeclared — regenerate"*, a
    reader would regenerate, and the file would then disagree in the other direction on the next
    machine. *A check whose failure message can misdiagnose is worse than one that stays silent,
    because somebody acts on it.*

    Takes SOURCE rather than a path so the self-test below can hand it a synthetic module: a scanner
    that can only read the real tree, whose expected answer is zero, is the easiest kind of check to
    break silently.
    """
    scan = _CondScan(label)
    scan.visit(ast.parse(src))
    return scan.hits


def conditionally_registered() -> tuple[list[str], int]:
    """`(sites, modules_scanned)` over every module in `src/aec_api`.

    Measured 0 sites on 2026-09-25, so this costs no exemptions today — and if it ever stops being 0,
    the repair is a named env axis in this file, not a looser comparison.

    **The module count is returned, not discarded, and the tree is anchored on `__file__`.** A bare
    `Path("src")` resolves against the working directory: `run_tests.py` sets `cwd=services/api` so it
    would have worked under the runner, and `ci.yml` invokes `python services/api/run_tests.py` from
    the repo ROOT, where the same literal names nothing. `rglob` over a missing directory yields
    nothing and raises nothing, so the precondition would have reported a clean tree from the wrong
    question — the failure `test_scratch_ignored` paid for twice, asked from `services/` instead of the
    repo root. *A wrong question returns a confident number.* So the count is asserted against a floor
    beside the verdict, and the path cannot depend on where anybody stood.
    """
    out: list[str] = []
    n = 0
    for path in sorted((HERE / "src" / "aec_api").rglob("*.py")):
        try:
            out += conditional_sites(path.read_text(encoding="utf-8"), str(path.relative_to(HERE)))
        except SyntaxError:  # pragma: no cover — a syntax error reds the suite elsewhere
            continue
        n += 1
    return out, n


def disagreement(decl: dict[str, set[str]], srv: dict[str, set[str]]) -> tuple[list[str], list[str]]:
    """`(missing, extra)` as `"VERB path"` strings — served-but-undeclared, declared-but-not-served."""
    missing = [f"{v} {p}" for p, vs in sorted(srv.items()) for v in sorted(vs - decl.get(p, set()))]
    extra = [f"{v} {p}" for p, vs in sorted(decl.items()) for v in sorted(vs - srv.get(p, set()))]
    return missing, extra


def _sample(xs, n=12):
    """Cap a failure detail. A 39 KB message is one nobody reads to the end — measured: the first run
    of this gate against the file as shipped printed every one of 481 undeclared operations twice."""
    xs = sorted(xs)
    return ", ".join(xs[:n]) + (f" … and {len(xs) - n} more" if len(xs) > n else "")


# ---------------------------------------------------------------------------------------------
# PRECONDITIONS — each is one way this gate could report a clean tree while seeing nothing.

if not SCHEMA.is_file():
    print(f"FAIL  the generated types are at {SCHEMA} — file not found")
    sys.exit(1)

_SRC = SCHEMA.read_text(encoding="utf-8")
_DECL = declared(_SRC)
_LIVE = live()
_DECL_OPS = sum(len(v) for v in _DECL.values())

check(f"the parse reaches the generated file ({len(_DECL)} paths, {_DECL_OPS} declared operations)",
      len(_DECL) >= 900 and _DECL_OPS >= 950,
      f"{len(_DECL)} paths / {_DECL_OPS} operations parsed out of {SCHEMA.name} — below the floor, so "
      "a parser that matched nothing would report this tree clean")

check(f"the app's own spec reaches ({len(_LIVE)} paths, {sum(len(v) for v in _LIVE.values())} operations)",
      len(_LIVE) >= 900 and sum(len(v) for v in _LIVE.values()) >= 950,
      "the live spec came back implausibly small — the comparison below would be vacuous")

# Mutation 1 — a whole path group deleted must be FOUND. Picks the subject from the file rather than
# naming one, so a route legitimately renamed cannot break this precondition with a message that
# blames the wrong cause.
_VICTIM = next(p for p, vs in sorted(_LIVE.items()) if vs and p in _DECL)
_CUT = {p: vs for p, vs in _DECL.items() if p != _VICTIM}
_CUT_MISSING, _ = disagreement(_CUT, _LIVE)
check(f"a DELETED path group is found ({_VICTIM})",
      sorted(_CUT_MISSING) == sorted(f"{v} {_VICTIM}" for v in _LIVE[_VICTIM]),
      f"deleting {_VICTIM} from the declared set reported {_sample(_CUT_MISSING) or 'nothing'} — "
      "the comparison is not looking at paths")

# Mutation 2 — the method-level arm. A path declared with its verbs turned off must be FOUND, or a
# half-regenerated file passes: `openapi-typescript` writes every URL and marks unserved verbs
# `?: never`, so URL presence is not the question.
_VERB = sorted(_LIVE[_VICTIM])[0]
_FLIPPED = dict(_DECL) | {_VICTIM: _DECL[_VICTIM] - {_VERB}}
_FLIP_MISSING, _ = disagreement(_FLIPPED, _LIVE)
check(f"a verb flipped to `never` is found ({_VERB} {_VICTIM})",
      _FLIP_MISSING == [f"{_VERB} {_VICTIM}"],
      f"turning off {_VERB} {_VICTIM} reported {_sample(_FLIP_MISSING) or 'nothing'} — the "
      "comparison is path-level, so a file declaring every URL and no verb would pass")

# Mutation 3a — the group-count parity arm. A path group whose SHAPE the group regex cannot match is
# absent from `declared()` silently, and would be reported as "served but undeclared" — a parser
# failure wearing the costume of a stale file. Two shapes, because the first draft of the parity check
# counted keys with `^    "…": \{$` and so failed in exactly the same way the group regex does: the
# trailing-whitespace mutation broke both and the counts stayed equal. *A parity check between two
# derivations that share a failure mode is not a check.*
_SHAPE_MUTANTS = {
    "trailing whitespace after a group's opening brace":
        (f'    "{_VICTIM}": {{\n', f'    "{_VICTIM}": {{  \n'),
    "a group's closing brace indented one space too far":
        ("        trace?: never;\n    };\n", "        trace?: never;\n     };\n"),
}
for _name, (_a, _b) in _SHAPE_MUTANTS.items():
    _m = _SRC.replace(_a, _b, 1)
    _applied = _m != _SRC
    try:
        declared(_m)
        _refused = False
    except Unparsable:
        _refused = True
    check(f"a group the regex cannot match is REFUSED — {_name}",
          _applied and _refused,
          "the mutation did not apply, so this proves nothing" if not _applied else
          "the parser returned a SMALLER set instead of refusing — every group it silently drops is "
          "reported as an undeclared path, which reads as 'regenerate' rather than 'the parser broke'")

# Mutation 3 — the parser must REFUSE a group it cannot rule on, rather than returning a smaller set.
# `declared()` raising is the whole of failing closed; a parser that skipped the group would simply
# report that path as missing everything, which reads like a regeneration being due.
_MANGLED = re.sub(rf'^        {_VERB.lower()}(\?)?: [^\n]+$', "", _SRC, count=1, flags=re.M)
try:
    declared(_MANGLED)
    _REFUSED = False
except Unparsable:
    _REFUSED = True
check("a group missing a verb line is REFUSED, not silently narrowed",
      _REFUSED,
      "the parser accepted a path group with a verb line removed — an unparsable group would be "
      "reported as an absent declaration, which reads as 'regeneration due' rather than 'the parser "
      "no longer understands this file'")

# Precondition 4 — the route set must not depend on the environment, or the comparison is between two
# different apps and its failure message would send a reader to regenerate for the wrong reason.
_SYNTH_COND = '''
if flag:
    @router.get("/x")
    async def x(): ...
    app.include_router(other)
'''
_SYNTH_PLAIN = '''
@router.get("/x")
async def x(): ...
app.include_router(other)
'''
check("SELF-TEST: the scanner finds a route registered under an `if`…",
      len(conditional_sites(_SYNTH_COND, "synth")) == 2,
      f"a synthetic module with a gated decorator AND a gated include_router reported "
      f"{conditional_sites(_SYNTH_COND, 'synth')} — a scanner whose expected answer is zero is the "
      "easiest kind to break silently, so it must be shown finding one")

check("SELF-TEST: …and passes the same two registered unconditionally",
      conditional_sites(_SYNTH_PLAIN, "synth") == [],
      f"flagged {conditional_sites(_SYNTH_PLAIN, 'synth')} — the scanner is matching the "
      "registration, not the `if`")

_COND, _MODULES = conditionally_registered()
check(f"the conditional-registration scan reached the package ({_MODULES} modules)",
      _MODULES >= 100,
      f"only {_MODULES} module(s) under {HERE / 'src' / 'aec_api'} — `rglob` over a missing directory "
      "yields nothing and raises nothing, so the check below would report a clean tree from the wrong "
      "question")

check("no route is registered under an `if`, so the served set is the same here and in CI",
      not _COND,
      f"{len(_COND)} conditional registration(s): {'; '.join(_COND[:6])} — the committed types can "
      "only agree with ONE route set, so an env-gated route makes this gate's verdict a fact about "
      "this machine. Name the env axis here rather than loosening the comparison")

# ---------------------------------------------------------------------------------------------
# THE VERDICT

_MISSING, _EXTRA = disagreement(_DECL, _LIVE)


check(f"every served (path, method) is declared in schema.d.ts ({sum(len(v) for v in _LIVE.values())} operations)",
      not _MISSING,
      f"{len(_MISSING)} served but undeclared: {_sample(_MISSING)} — the committed types describe a "
      "different server than the one this branch runs. Regenerate with `npm run gen:api-types` from "
      "apps/web (it reads the app, not a file) and commit the result")

check("no declared (path, method) has stopped being served",
      not _EXTRA,
      f"{len(_EXTRA)} declared but gone: {_sample(_EXTRA)} — a client typed off these would compile "
      "against routes that 404. Regenerate with `npm run gen:api-types` from apps/web")

print()
if FAILED:
    print(f"schema_types_agree: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print(
    f"schema_types_agree: all checks passed — {len(_LIVE)} paths / "
    f"{sum(len(v) for v in _LIVE.values())} operations served, all declared, 0 declared-but-gone"
)
