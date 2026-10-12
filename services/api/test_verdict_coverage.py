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

THREE BLIND SPOTS IN THE SHAPE PREDICATE — ONE CLOSED, TWO MEASURED AND DELIBERATELY NOT
-----------------------------------------------------------------------------------------
**The third was closed the same day it was found, and the difference is the measurement, not the
enthusiasm.** TURNOVER-UNGATED found an eighth instance by hand — `quality_chain.turnover_readiness`,
`"ready": not blocking and not silent and c["any_attached"]` — a presence guard in place of
`bool(<name>)`. Dict values tree-wide with ≥1 negated operand, ≥1 plain truthiness operand and no
`Compare`/`Call`: **exactly 1**, the instance itself. So it cost no exemptions, no noise and one
vocabulary entry (`unrecorded`, whose four sites are all genuinely "no record exists"). Shapes 1 and
3 are now both admitted; shape 2 still measures at 16 and still needs the vocabulary pointed the
wrong way, so it stays out. *Widening a rule because an instance measured at one is not the same act
as widening it because an instance exists.*

A fourth blind spot was closed with it, in the consumer rule rather than the shape: a read that has
been EXTRACTED into a sibling module. See `delegated` — the first instance was TURNOVER-UNGATED's own
fix, and this codebase's line ratchet pushes every panel to do exactly that.

TWO BLIND SPOTS IN THE SHAPE PREDICATE, MEASURED 2026-10-12 AND DELIBERATELY NOT CLOSED
---------------------------------------------------------------------------------------
EVM-COVERAGE found a sixth and a seventh instance of this class by hand (`evm.model_ev`'s
`front_loaded_flag` and `wip.model_progress`'s `flag`), and **this gate saw neither.** Both halves of
why were measured rather than guessed:

1.  **A verdict computed into a LOCAL VARIABLE is invisible.** The walk reads dict *literals* and
    tests the value expression in place, so `{"front_loaded_flag": flag}` tests a bare `ast.Name`.
    Measured: **11** dict values are a bare name resolving to a verdict-shaped expression in the same
    function, against **7** the walk sees inline. Complexity is exactly what makes an author give a
    verdict its own line, and complexity is what correlates with having coverage to report.
2.  **The shape is `bool(A) and (all(…)|not B)`, and these are `bool(A and B and <compare>)`** — a
    presence guard beside a magnitude threshold rather than a quantifier. Measured: **16** instances
    of that second shape (5 inline, 11 indirect).

**Neither was closed, and the measurement is the reason.** Resolving the indirection while keeping
the shipped shape adds **0** instances to the population today — the 11 are all the second shape, so
the reach fix alone is a precondition repair with no present effect. And admitting the second shape
needs the coverage vocabulary widened to positively-named counts (`coverage_pct`,
`determined_elements`, `tracked_elements`), which is lesson 1 above, in the other direction: the
negatively-named vocabulary is tight because "untested" cannot mean anything else, and "coverage" can
— it already matched a sprinkler's `max_coverage_m2_per_head`. *Widening a rule until it covers the
instance in front of you is how a gate acquires an exemption list, and an exemption list is where the
next instance hides.*

What the two new sites have instead is a **declared band** — `model_percent_complete` beside
`model_percent_complete_max`, `ev_model` beside `ev_model_max` — which is purely structural and needs
no vocabulary at all. Measured population of `X` beside `X_max`/`X_min` across the whole API: **7
pairs in 2 modules, every one of them introduced by EVM-COVERAGE itself.** So a band gate would guard
only its author's own fields and would be the only check on nothing else; both consumers already pin
both ends in their own tests (`apps/web/src/portal/panels/modelEvReading.test.ts`). *A check earns
its place from where it is the ONLY one, not from the worst case it can be described as catching* —
so this is written down, with its numbers, instead of built. Re-measure before building it: a third
module declaring a band is the signal that it has stopped being prospective.

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
#:
#: `unrecorded\w*` joined 2026-10-12 (TURNOVER-UNGATED) because shape 3 below needs it, and the
#: other candidates were MEASURED rather than waved in:
#:
#:   | candidate | sites | admitted? |
#:   |---|---|---|
#:   | `unrecorded` | 4 (`quality_chain` ×2, `approval_conditions`, `takeoff2d`) | **yes** — "un-" + "recorded" can only mean no record exists |
#:   | `unverified` | 1 (`quality_chain.unverified_hold_points`) | **no** — an unverified hold point is an OPEN FINDING, evaluated and not signed off, not absent coverage. Admitting it is lesson 3 again: `not_covered` was refused for being about a different dimension, and this is the same error with a different prefix. |
#:   | `unassessed` | 3 (`lean`, `pull_plan`, `schedule_lastplanner`) | **no** |
#:   | `unanchored` | 2 (`coordination_fresh`) | **no** |
#:   | `unreachable` | 3 (`egress_route`, `workflow_config` ×2) | **no** |
#:
#: The last three are correct senses of "not evaluated" and were still left out, because of which
#: DIRECTION this vocabulary points: it widens what COUNTS AS coverage for a consumer, so every
#: entry makes the consumer check easier to satisfy. An entry with no verdict needing it loosens the
#: rule for nothing. *A vocabulary that grows because a word fits is a vocabulary that stops
#: discriminating* — re-measure and add one when a verdict actually needs it.
COVERAGE_NAME = re.compile(
    r"^(untested|unmapped|unpriced|unmeasured|uncomputable|uncovered|unrecorded\w*"
    r"|skipped\w*|not_applicable|not_computable|not_run|not_tested)$")


def is_presence_guarded_verdict(value: ast.expr) -> bool:
    """`not A and not B … and <plain truthiness>` — shape 3, admitted 2026-10-12 after measuring it.

    `quality_chain.turnover_readiness` is

        "ready": not blocking and not silent and c["any_attached"]

    which is the same class as the five this gate was derived from — a verdict true of a subset,
    guarded by the author writing down that the subset can be empty — spelled with a **presence
    guard** rather than `bool(<name>)`. TURNOVER-UNGATED found it by hand, as the eighth instance,
    and this gate saw nothing.

    **It was measured before it was admitted, and that is why it is here while shape 2 is not.**
    Dict values tree-wide with ≥1 negated operand, ≥1 plain truthiness operand and no `Compare` or
    `Call` operand: **exactly 1** — the instance above. So this costs no exemptions and no noise. The
    `Compare`/`Call` refusal is what keeps it from drifting into shape 2 (`bool(A and B and
    <compare>)`), which measures at **16** and stays out for the reason recorded in the header: it
    needs the coverage vocabulary widened to positively-named counts, and that is lesson 1 pointing
    the other way.
    """
    if not (isinstance(value, ast.BoolOp) and isinstance(value.op, ast.And)):
        return False
    neg = plain = 0
    for part in value.values:
        if isinstance(part, ast.UnaryOp) and isinstance(part.op, ast.Not):
            neg += 1
        elif isinstance(part, (ast.Compare, ast.Call)):
            return False
        else:
            plain += 1
    return neg >= 1 and plain >= 1


def is_subset_verdict(value: ast.expr) -> bool:
    """Either admitted shape. See `is_presence_guarded_verdict` for the second and its measurement."""
    return _is_guarded_quantified(value) or is_presence_guarded_verdict(value)


def _is_guarded_quantified(value: ast.expr) -> bool:
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


#: `const x = await ….<owner>(` — the binding that holds one owner method's response.
_HOLDER = r"(?:const|let|var)\s+(\w+)\s*=\s*await\s+[^;]*?\.{owner}\("
#: An `import { a, b as c }` whose specifier begins with a dot — a RELATIVE import only; a package
#: cannot be a local reading. The example is written in prose rather than quoted, because
#: `services/api/test_scratch_ignored.py` reads every `"./<name>"` literal in this directory as a
#: scratch directory and an illustration is not worth an exemption.
_REL_IMPORT = re.compile(r'import\s*\{([^}]*)\}\s*from\s*"(\.[^"]*)"')


def delegated(src: str, path: "Path | None", owner: str) -> str:
    """The source of any sibling module this file HANDS the owner's response to.

    The consumer rule is file-local, and that was a blind spot the moment a consumer did what this
    codebase's line ratchet pushes every panel to do: extract the reading into its own module. The
    first instance was TURNOVER-UNGATED's own fix — `operations.ts` awaits
    `qualityTurnoverReadiness` and hands it to `qualityReading(qt)` in `./qualityCloseout`, which
    reads four coverage fields. File-locally that reads as a BARE consumer. *A detector keyed on
    where the read usually sits cannot see a read that moved, and this repository moves them on
    purpose.*

    Deliberately narrow, and the narrowness is the whole of its safety:

    * ONE hop, and only through a **relative** import — a package cannot hold this project's reading;
    * only a module whose imported binding is **called with the variable that holds this owner's
      response**, so an unrelated helper that happens to mention `skipped` cannot bless anything;
    * and it only ever ADDS text to look in, so it cannot turn a passing tree red.

    That last point is also why it was safe to land: with zero bare consumers today it hides no
    present defect, and the frozen replay below has no imports at all, so the proof-of-reach is
    untouched by it.
    """
    if path is None:
        return ""
    holders = set(re.findall(_HOLDER.format(owner=re.escape(owner)), src))
    if not holders:
        return ""
    out = []
    for names, rel in _REL_IMPORT.findall(src):
        bound = [n.strip().split(" as ")[-1].strip() for n in names.split(",") if n.strip()]
        if not any(re.search(rf"\b{re.escape(fn)}\(\s*{re.escape(v)}\b", src)
                   for fn in bound for v in holders):
            continue
        target = (path.parent / (rel + ".ts")).resolve()
        if target.is_file():
            out.append(target.read_text(encoding="utf-8"))
    return "\n" + "\n".join(out) if out else ""


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
        (str(p.relative_to(WEB)), p.read_text(encoding="utf-8"), p) for p in web_files()]
    files = [(f + (None,))[:3] for f in files]      # the replay passes (label, src) pairs
    out = []
    for mod, verdict, top, deep in subset_verdicts(API):
        coverage = sorted(k for k in deep if COVERAGE_NAME.match(k))
        if not coverage:
            continue
        owners = [n for n, declared in methods.items()
                  if verdict in declared and len(top & declared) >= 3]
        for owner in owners:
            call = re.compile(rf"\.{re.escape(owner)}\(")
            for label, src, path in files:
                if not call.search(src):
                    continue
                look = src + delegated(src, path, owner)
                if not any(reads(look, c) for c in coverage):
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
              ("sequence_clash.py", "clean"),
              # Shape 3, added 2026-10-12. The eighth instance of this class, found by hand while
              # this gate reported a clean tree — so it is a proof of reach, not a nicety.
              ("quality_chain.py", "ready")}
check(f"the walk re-finds the {len(_MUST_FIND)} known subset verdicts",
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

# SHAPE 3's own self-tests. The first says the shape is recognised; the second and third are the
# bounds that keep it from becoming shape 2 by accident, which is the thing the header refused.
_S3 = ast.parse("x = {'ready': not a and not b and c['any_attached'], 'unrecorded_count': 1}"
                ).body[0].value
_S3_PLAIN = ast.parse("x = {'ok': a and b, 'unrecorded_count': 1}").body[0].value
_S3_CMP = ast.parse("x = {'flag': not a and b > 0, 'unrecorded_count': 1}").body[0].value
check("SELF-TEST: shape 3 (`not A and not B and <presence>`) is a subset verdict…",
      is_subset_verdict(_S3.values[0]),
      "the shape TURNOVER-UNGATED found by hand is still invisible, so admitting it did nothing")
check("SELF-TEST: …a plain conjunction is not…",
      not is_subset_verdict(_S3_PLAIN.values[0]),
      "`a and b` read as a subset verdict — the population widens to every conjunction")
check("SELF-TEST: …and a THRESHOLD operand is refused, so shape 3 cannot drift into shape 2",
      not is_subset_verdict(_S3_CMP.values[0]),
      "`not a and b > 0` was admitted, which quietly pulls in the 16 instances the header "
      "deliberately left out and the vocabulary widening they would need")

# The delegation hop: a read HANDED to a sibling module counts, and one merely sitting in an
# unrelated import does not.
_DEL_SRC = ('import { qualityReading } from "./qualityCloseout";\n'
            'const qt = await ctx.host.api.qualityTurnoverReadiness(pid);\n'
            'const r = qualityReading(qt);\n')
check("SELF-TEST: the delegation hop finds the response's holder and its callee",
      set(re.findall(_HOLDER.format(owner="qualityTurnoverReadiness"), _DEL_SRC)) == {"qt"}
      and _REL_IMPORT.findall(_DEL_SRC) == [(" qualityReading ", "./qualityCloseout")],
      "the hop cannot identify the variable or the import, so it degrades to the file-local rule "
      "and the blind spot it was added for is still open")
check("SELF-TEST: …and it looks at NOTHING when the response is not handed anywhere",
      delegated('const qt = await ctx.host.api.qualityTurnoverReadiness(pid);\n',
                Path(__file__), "qualityTurnoverReadiness") == "",
      "the hop widened the search without the response reaching the module, which is how an "
      "unrelated helper mentioning `skipped` would bless a bare consumer")

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

# SHAPE 3's replay, and the most useful thing in this file is what it proves NEGATIVE.
#
# This is `operations.ts`'s quality card EXACTLY as it shipped before TURNOVER-UNGATED, not a
# simplification of it — the first draft of this fixture printed only `ready` and was duly reported
# BARE, which would have been a proof of reach against a strawman. *A replay is a claim about a
# moment, and a fixture that is not that moment is a claim about nothing.* The real card read
# `outstanding_count`, `unrecorded_count` and `coverage_pct`, so the widened rule reports it CLEAN.
#
# **So shape 3 did not buy the instance that existed; it bought the next one.** `quality_chain::ready`
# is now in the population, so a consumer that renders `ready` alone fails here — and the one that
# shipped would not have, because it printed every number and **gated nothing on them**. Reading a
# coverage field and acting on it are different things, and this file only ever claimed the first
# (see "WHAT THIS DOES NOT PROVE"). The acting-on-it half is
# `apps/web/src/portal/panels/qualityCloseout.test.ts`, which drives the certify decision and fails
# when the gate is computed and ignored.
#
# Asserted as CLEAN rather than deleted, because the bound is the finding: a future reader
# wondering whether this gate would have caught TURNOVER-UNGATED can run it and see that it would
# not have.
_REPLAY_SHAPE3_SHIPPED = ("replay/operations.pre-fix.ts", """
  void ctx.host.api.qualityTurnoverReadiness(pid).then((qt) => {
    const qdiv = el("div", "dash-card"); qdiv.style.marginBottom = "8px";
    const qm = el("div", "meta");
    qm.textContent = qt.ready
      ? "Quality evidence exists and is resolved."
      : `${qt.outstanding_count} outstanding \u00b7 ${qt.unrecorded_count} never inspected \u00b7 coverage ${qt.coverage_pct}%`;
    qdiv.append(qh, qm);
    body.insertBefore(qdiv, rdiv.nextSibling);
  }).catch(() => { /* quality registers may be empty */ });
""")
check("the shipped pre-fix quality card reads its coverage, so this gate would NOT have caught it",
      not bare_consumers([_REPLAY_SHAPE3_SHIPPED]),
      "the pre-fix card was reported bare, which contradicts the bound stated above — either the "
      "fixture is no longer what shipped or the vocabulary changed, and the paragraph above is now "
      "wrong about what shape 3 bought")

# ...and the shape IS reaching `quality_chain::ready`, which is what admitting it bought. Without
# this the check above passes just as happily when the verdict is invisible to the walk.
_REPLAY_SHAPE3_BARE = ("replay/operations.verdict-only.ts", """
  void ctx.host.api.qualityTurnoverReadiness(pid).then((qt) => {
    const qm = el("div", "meta");
    qm.textContent = qt.ready ? "Quality evidence exists and is resolved." : "not ready";
    qdiv.append(qh, qm);
  }).catch(() => {});
""")
check("…while a consumer that renders only the verdict IS reported bare — the reach shape 3 bought",
      [v for _f, _m, v, _c in bare_consumers([_REPLAY_SHAPE3_BARE])] == ["ready"],
      "a card rendering `ready` alone was not reported, so shape 3 or the `unrecorded` vocabulary "
      "is not reaching `quality_chain::ready` and admitting them bought nothing at all")

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
