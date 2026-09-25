"""Does a screen that reads a SUBSET VERDICT also read what the engine could not evaluate?

THE CLASS, FOUND FIVE TIMES BY HAND BEFORE IT WAS WORTH DERIVING
---------------------------------------------------------------
An engine evaluates what it can, reports a boolean about that, and reports separately what it could
not reach. The boolean is true of a SUBSET. A screen that renders the boolean and not the subset
size manufactures confidence out of an absence of inputs:

    soft_clash      `coordinated`      over a page of the matrix     (CLASH-TRUNC, 2026-09-24)
    rent_scrub      `clean`            `bool(ran) and not failed`    — 1 of 7 checks ran
    t12             `tie_out.reconciles` reference derived from the answer
    covenants       `clean`, `at_risk` counts zero for want of inputs
    sequence_clash  `clean`            over the activities that had a date and a location

Every one of those engines is careful. Each hands the caller the coverage beside the verdict and
three of them attach a sentence explaining why it matters — `rent_scrub.py`: *"a scrub that reports
'no findings' because half its inputs were missing is worse than no scrub — it launders absent data
into apparent confidence."* The defect is always in the consumer, and for four of the five there was
no consumer, so nothing was wrong until somebody wrote one. **Finding it a sixth time by hand is what
this file exists to prevent.**

THE RULE
--------
* A **subset verdict** is a dict key whose value is `bool(A) and (all(…)/any(…) | not B)`. The
  `bool(A)` guard is the author writing down that the subset can be empty — which is exactly the
  case where the verdict means nothing.
* Its **coverage** is a sibling key (including nested ones) whose name *by itself* says something was
  not evaluated.
* A **consumer** is a web file that calls the client method whose declared response type carries the
  verdict plus at least three of its siblings.
* Every consumer must READ at least one coverage field.

FIVE THINGS THE FIRST DRAFTS GOT WRONG, EACH MEASURED RATHER THAN REASONED ABOUT
-------------------------------------------------------------------------------
1.  **Matching coverage-ish WORDS** (`coverage`, `skipped`, `truncated`) against client response
    types returned **24 methods**, most of them unrelated senses of the word: a sprinkler's
    `max_coverage_m2_per_head`, a `dry_run` flag, `ok`/`writes` beside a `truncated` list. *A rule
    that needs an exemption list is a rule whose population is wrong*, so the population moved to the
    structural form above, which returns **5 with no exemptions** — and three of those five were
    instances nobody had found by hand.
2.  **Linking consumers by shared VOCABULARY** (verdict + ≥2 sibling names) cross-talks, because the
    sibling names are ordinary words. It reported `proforma/rentRollQuality.ts` — a net-effective-rent
    card — as a consumer of `sequence_clash`, on the strength of `skipped`, `skipped_count` and
    `findings`. The link is the **call site of the owning client method**; nothing else claims *this
    file reads THIS response*.
3.  **Treating `not_` as a coverage prefix** matched `sequence_clash.not_covered`, which is a prose
    note about a *different dimension* (whether directed support pairs were supplied). It would have
    blessed the one consumer this rule exists to catch. The vocabulary is anchored whole-word now.
4.  **Detecting a read as `.name`** missed `const { not_applicable: notRun } = s.counts` and reported
    a card that reads its coverage carefully as BARE. *A detector keyed on one spelling cannot see the
    same read written another way.*
5.  **Widening that to a bare word boundary** then matched the English word *"skipped"* inside an
    unrelated prose string in the same file — the opposite error, one line later. A read is `.name`,
    `["name"]` or `name:`, and nothing else.

WHAT THIS DOES NOT PROVE, stated because mutation-checking it is what surfaced the limit
----------------------------------------------------------------------------------------
It is a SOURCE-level check: it proves the consumer reads the field somewhere in its source, not that
the read reaches a screen. Wrapping the coverage render in `if (false)` leaves the text in place and
passes — measured, not assumed. That is the same bargain `test_route_reachability` makes for URL
literals, and the complement is the consumer's own test: `proforma/rentRollQuality.test.ts` and
`proforma/covenantCard.test.ts` assert the coverage is RENDERED, with mutations. This file's job is
to make sure a new consumer cannot be written without one.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_verdict_coverage.py
"""
import ast
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
API = HERE / "src" / "aec_api"
WEB = HERE.parents[1] / "apps" / "web" / "src"
WEBAPI = WEB / "api"

FAILED: list[str] = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


#: Names that, on their own, say "this was not evaluated". Anchored whole-word: `not_` as a prefix
#: matched `not_covered`, a note about a different dimension — see lesson 3.
COVERAGE_NAME = re.compile(
    r"^(untested|unmapped|unpriced|unmeasured|uncomputable|uncovered"
    r"|skipped\w*|not_applicable|not_computable|not_run|not_tested)$")


def is_subset_verdict(value: ast.expr) -> bool:
    """`bool(A) and (all(…)/any(…) | not B)` — a verdict true of a subset, guarded because it can be empty.

    The guard is the load-bearing half. `truncated`, `ok` and `dry_run` are booleans too and are not
    verdicts about a subset; requiring `bool(<name>)` beside a quantifier is what separates them
    without a list of names to maintain.
    """
    if not (isinstance(value, ast.BoolOp) and isinstance(value.op, ast.And)):
        return False
    guarded = quantified = False
    for part in value.values:
        if isinstance(part, ast.Call) and isinstance(part.func, ast.Name):
            if part.func.id == "bool" and part.args and isinstance(part.args[0], ast.Name):
                guarded = True
            elif part.func.id in ("all", "any") and part.args:
                quantified = True
        elif isinstance(part, ast.UnaryOp) and isinstance(part.op, ast.Not):
            quantified = True
    return guarded and quantified


def keys_deep(node: ast.Dict) -> set[str]:
    """Every string key in a dict literal, including nested ones — `rent_scrub`'s coverage lives in
    `counts.not_applicable`, so a top-level-only walk would report that response as having none."""
    out: set[str] = set()
    for k, v in zip(node.keys, node.values):
        if isinstance(k, ast.Constant) and isinstance(k.value, str):
            out.add(k.value)
            if isinstance(v, ast.Dict):
                out |= keys_deep(v)
    return out


def subset_verdicts(root: Path) -> list[tuple[str, str, set[str], set[str]]]:
    """`(module, verdict, top-level siblings, all siblings)` for every subset verdict under `root`."""
    out = []
    for path in sorted(root.rglob("*.py")):
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:  # pragma: no cover — a syntax error reds the suite elsewhere
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.Dict):
                continue
            deep = keys_deep(node)
            top = {k.value for k in node.keys
                   if isinstance(k, ast.Constant) and isinstance(k.value, str)}
            for k, v in zip(node.keys, node.values):
                if isinstance(k, ast.Constant) and isinstance(k.value, str) and is_subset_verdict(v):
                    out.append((str(path.relative_to(root)), k.value,
                                top - {k.value}, deep - {k.value}))
    return out


def client_methods() -> dict[str, set[str]]:
    """`{method: declared response field names}` for every `ApiClient` method that fetches JSON."""
    out: dict[str, set[str]] = {}
    for path in sorted(WEBAPI.glob("*.ts")):
        if path.name.endswith(".test.ts") or path.name == "schema.d.ts":
            continue
        src = path.read_text(encoding="utf-8")
        for m in re.finditer(r"^  (\w+)\(", src, re.M):
            start = m.end()
            end = src.find("\n  }", start)
            if end < 0 or "this.json<" not in src[start:end]:
                continue
            out[m.group(1)] = set(re.findall(r"\b(\w+)\s*\??\s*:", src[start:end]))
    return out


def reads(src: str, name: str) -> bool:
    """`r.skipped_count`, `r["skipped"]` and `{ not_applicable: x }` are reads. The word `skipped`
    inside a prose string is not — see lessons 4 and 5, which this one line is the repair for."""
    n = re.escape(name)
    return re.search(rf'(?:\.{n}\b)|(?:\[["\']{n}["\']\])|(?:\b{n}\s*:)', src) is not None


def web_files() -> list[Path]:
    """Application sources: not tests, not vendored, not the client layer itself."""
    return [p for p in sorted(WEB.rglob("*.ts"))
            if not p.name.endswith(".test.ts") and "vendor" not in p.parts and p.parent != WEBAPI]


def bare_consumers(sources=None):
    """`(file, module, verdict, coverage)` for every consumer reading a verdict without its coverage.

    Takes `(label, source)` pairs so the replay below can hand it a frozen fixture instead of the
    tree — the same reason `test_gap_records` embeds its pre-fix subject rather than fetching it with
    `git show`, which works locally and not in CI's shallow checkout.
    """
    methods = client_methods()
    files = sources if sources is not None else [
        (str(p.relative_to(WEB)), p.read_text(encoding="utf-8")) for p in web_files()]
    out = []
    for mod, verdict, top, deep in subset_verdicts(API):
        coverage = sorted(k for k in deep if COVERAGE_NAME.match(k))
        if not coverage:
            continue
        owners = [n for n, declared in methods.items()
                  if verdict in declared and len(top & declared) >= 3]
        for owner in owners:
            call = re.compile(rf"\.{re.escape(owner)}\(")
            for label, src in files:
                if not call.search(src):
                    continue
                if not any(reads(src, c) for c in coverage):
                    out.append((label, mod, verdict, coverage))
    return out


# ---------------------------------------------------------------------------------------------
# PRECONDITIONS — each is a way this file could report a clean tree while seeing nothing.

_VERDICTS = subset_verdicts(API)
_METHODS = client_methods()

check(f"the AST walk found subset verdicts ({len(_VERDICTS)})",
      len(_VERDICTS) >= 4,
      f"only {len(_VERDICTS)} found under {API} — the rule below would be a statement about an "
      "empty population, which reads exactly like a clean tree")

check(f"the client surface parsed ({len(_METHODS)} methods)",
      len(_METHODS) >= 200,
      f"only {len(_METHODS)} client methods parsed out of {WEBAPI} — with no owners the consumer "
      "check can never fire")

_NAMES = {(m, v) for m, v, _, _ in _VERDICTS}
_MUST_FIND = {("covenants.py", "clean"), ("rent_scrub.py", "clean"),
              ("sequence_clash.py", "clean")}
check("the walk re-finds the three known subset verdicts",
      _MUST_FIND <= _NAMES,
      f"missing {sorted(_MUST_FIND - _NAMES)} — these are the instances the rule was derived from, "
      "so a walk that cannot see them is measuring something else")

# A plain boolean is NOT a subset verdict. `truncated` is the counter-example that matters: it is a
# bool, it sits beside coverage-ish siblings, and it was what made the word-based population 24 wide.
_SYNTH_PLAIN = ast.parse("x = {'truncated': len(rows) > cap, 'skipped': 3}").body[0].value
_SYNTH_SUBSET = ast.parse("x = {'clean': bool(ran) and not failed, 'skipped': 3}").body[0].value
check("SELF-TEST: a plain boolean is not a subset verdict…",
      not any(is_subset_verdict(v) for v in _SYNTH_PLAIN.values),
      "`truncated: len(rows) > cap` was read as a subset verdict — the population widens to every "
      "boolean and the rule needs an exemption list")
check("SELF-TEST: …and a guarded, quantified one is",
      any(is_subset_verdict(v) for v in _SYNTH_SUBSET.values),
      "`bool(ran) and not failed` was NOT read as a subset verdict, so the walk above is finding "
      "its three by accident")

_SRC_DOT = "const n = r.skipped_count;"
_SRC_DESTRUCT = "const { not_applicable: notRun } = s.counts;"
_SRC_INDEX = 'const n = r["skipped"];'
_SRC_PROSE = "resultNote(`3 space(s) have no area and were skipped — add areas.`)"
check("SELF-TEST: a read is found in all three spellings…",
      reads(_SRC_DOT, "skipped_count") and reads(_SRC_DESTRUCT, "not_applicable")
      and reads(_SRC_INDEX, "skipped"),
      "a spelling of a read went undetected — which is how the first draft reported a card that "
      "reads its coverage carefully as BARE")
check("SELF-TEST: …and the same word in PROSE is not a read",
      not reads(_SRC_PROSE, "skipped"),
      "the English word `skipped` in a string counted as reading the field — the opposite error, "
      "and the one that would bless the consumer this rule exists to catch")

check("SELF-TEST: `not_covered` is not a coverage name",
      not COVERAGE_NAME.match("not_covered"),
      "a `not_` prefix rule matched a prose note about a different dimension, which is how this "
      "gate would have passed the very file it found")
check("SELF-TEST: …while the real ones are",
      all(COVERAGE_NAME.match(n) for n in ("untested", "skipped", "skipped_count", "not_applicable")),
      "a coverage name the rule exists for is unmatched")

# REPLAY — the shape this gate was written from, and its repair. Frozen rather than read out of
# history: `viewer/tools/analyseSection.ts` at the commit before the fix called `.sequenceClash(`,
# rendered `clean`, `analyzed` and `finding_count`, and read neither `skipped` nor `skipped_count`.
_REPLAY_BARE = ("replay/analyseSection.pre-fix.ts", """
  let r; r = await api.sequenceClash(pid);
  const n = r.finding_count + r.support_finding_count;
  out.textContent = n ? `${n} sequence clashes` : (r.clean ? "clean" : "checked");
  body.appendChild(resultNote(`${r.analyzed} dated locatable activities.`, n ? "bad" : "ok"));
""")
_REPLAY_OK = (_REPLAY_BARE[0].replace("pre-fix", "fixed"),
              _REPLAY_BARE[1] + '  if (r.skipped_count) body.appendChild(resultNote("not checked"));\n')

_FOUND = bare_consumers([_REPLAY_BARE])
check("the replay finds the pre-fix consumer it was written from",
      [f for f, _m, v, _c in _FOUND if v == "clean"] == [_REPLAY_BARE[0]],
      f"replaying the pre-fix source reported {_FOUND or 'nothing'} — the rule cannot re-find the "
      "instance it was derived from, so a green verdict below is about something else")

check("  …and its repair is clean",
      not bare_consumers([_REPLAY_OK]),
      "the fixed source still reads as bare, so the rule cannot be satisfied by fixing the defect")

# ---------------------------------------------------------------------------------------------
# THE VERDICT

_BARE = bare_consumers()
_DETAIL = "; ".join(f"{f} reads {m}::{v} and none of {c}" for f, m, v, c in _BARE)
check(f"every consumer of a subset verdict also reads its coverage ({len(_VERDICTS)} verdicts)",
      not _BARE,
      f"{len(_BARE)}: {_DETAIL} — the verdict is true of what the engine could evaluate, and a "
      "screen that shows it without the size of what it could not turns an absence of inputs into "
      "an appearance of confidence. Render the coverage beside the verdict")

print()
if FAILED:
    print(f"verdict_coverage: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print(f"verdict_coverage: all checks passed — {len(_VERDICTS)} subset verdict(s), "
      f"{len(_METHODS)} client methods, 0 consumers reading a verdict without its coverage")
