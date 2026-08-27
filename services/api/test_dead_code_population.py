"""R37-TRIAGE — the dead-code population, with the reference rule that stops being wrong.

## Why this file exists, and what it is really measuring

The roadmap records this population being corrected twice: **877 → 35 → 13**, without moving a single
threshold. Every reduction was a fix to *what counts as a caller*. That history is the whole point of
the entry, and it has an obvious implication nobody drew: **a rule corrected twice is not a rule
that has finished being wrong.**

It had not. Reading all 13 by hand on 2026-08-17 found **eight live symbols**, missed for three
*distinct* reasons the previous rule could not see:

| blind spot | example | what deleting it would have done |
|---|---|---|
| **aliased imports** — `from .x import f as _f` then `_f(...)` | `search_filter`, `project_with_source` | broken module search and three authoring routers |
| **Python files that are not `.py`** | `excluded_import_names`, read by `desktop.spec` + `sidecar.spec` | broken the PyInstaller desktop **and** sidecar builds |
| **methods reached through an instance** — `api.register_recipe(...)` | `register_recipe` | broken the documented third-party **plugin API** |

The `.spec` case is the sharpest: the symbol *is* imported, by name, unaliased — the scanner simply
never opened the file, because its glob was `*.py`. **A gate's scope is part of its claim**, and a
population derived over the wrong file set is not a conservative estimate, it is a confident wrong
answer. `excluded_import_names` sat one careless deletion away from breaking both desktop builds,
and no test in this repository would have gone red.

So the rule is written down here as executable code rather than as a number in a document, and it
counts all three. What remains after applying it is a **ratchet at zero**: any new public function in
`aec_api` that nothing reaches fails this, at the commit that adds it, rather than accumulating until
someone re-derives a population and gets it wrong a fourth time.

## What "referenced" means here

A bare name, an attribute access (`mod.f(...)`, `self.f`), an import alias (`import f as _f`), and a
string literal — registries dispatch on strings. Across `.py`, `.spec`, `.json`, `.ts`, `.cfg`,
`.toml` and `.yml`, in `aec_api`, `aec_data`, the backend test tree, `plugins/` and the web app.
Comments, docstrings and `.md` do **not** count: documentation is not a caller.

**This rule took four corrections and cost two real deletions of live code. Read `_py_names` and
`_reference_counts` before trusting a number out of it.** The failures were not variations on one
mistake — they were four different ones, and the last three each survived the fix for the one before:

| # | defect | how it surfaced |
|---|---|---|
| 1 | `ast.walk` counted nested closures as public API; same-file callers discarded | 69 flagged vs the roadmap's 12 |
| 2 | reference matching counted **prose**, so the gate could not go red at all | passed with zero, while `evm.quadrant` was "reached" by a TS comment |
| 3 | the **TypeScript** block-comment regex ran on `.py`; `modules/*/module.json` holds a literal `/*` and `*/`, eating the imports | `validate_dir` deleted; the full suite caught it |
| 4 | triple-quote pairing shifts when an earlier `#`-strip removes one, swallowing code to EOF | `get_meta` deleted; only an **untruncated** grep caught it |

*(That row cannot spell its own subject: a literal triple quote inside this docstring ends it, which is the same pairing hazard one level up. `ruff` caught it.)*

Two design conclusions are load-bearing and easy to get backwards:

- **Over-stripping is not the safe direction.** In a dead-code gate a false death is an instruction
  to delete working code. Strip per language, and parse rather than regex where a parser exists.
- **Changing how references are gathered changes what must be discounted.** The `def`-line
  subtraction was correct for regex and *wrong* for `ast`, which never collects a definition's own
  name — it silently deleted real same-file calls (`build_payload`, `parse_csv`, `capital_stack`).

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_dead_code_population.py
"""
from __future__ import annotations

import ast
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
PKG = os.path.join(HERE, "src", "aec_api")

FAILURES: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {name}   {detail}")
    if not ok:
        FAILURES.append(name)


#: Trees searched for a reference. `services/data` and the test tree were added by the 35 -> 13
#: correction; the repo-root non-.py files are added here, and are what the `.spec` case needed.
SEARCH_ROOTS = [
    os.path.join(HERE, "src"),
    os.path.join(HERE, "..", "data", "src"),
    HERE,                                   # the backend test tree + desktop.spec / sidecar.spec
    os.path.join(ROOT, "plugins"),          # third-party plugin examples call the plugin API
    os.path.join(ROOT, "apps", "web", "src"),
]

#: Every extension that can hold a CALL. `.spec` is a PyInstaller build script -- Python source
#: under a different name, which is exactly how it escaped a `*.py` scan.
#:
#: **`.md` is deliberately absent, and comments are stripped below.** The first draft counted prose
#: and passed with zero unreferenced -- but `evm.quadrant` was "reached" only by the words "CPI-SPI
#: quadrant" in a TypeScript *comment*, and `plugins/README.md` documenting `register_recipe` was
#: counted as a caller. A rule that generous cannot go red: every plausible name appears in prose
#: somewhere, so the check would have vouched for the codebase without being able to fail.
#: This repo has been bitten by exactly this before -- a source-grep gate must strip comments, or it
#: reads its own documentation as evidence. Documentation is not a caller; the example plugin that
#: actually *calls* `api.register_recipe(...)` is, and that is `.py`.
SEARCH_EXTS = (".py", ".spec", ".json", ".ts", ".cfg", ".toml", ".yml", ".yaml")

#: Comment strippers, applied PER LANGUAGE. The "crude on purpose, over-stripping is the safe
#: direction" version of this comment was wrong, and it cost a real deletion of live code.
#:
#: **What happened, 2026-08-17.** The TypeScript block-comment pattern `/\*.*?\*/` was applied to
#: every file including `.py`. `test_module_config.py` contains `modules/*/module.json` -- which
#: holds a literal `/*` and a literal `*/` -- so the "comment" swallowed the file's imports, and
#: `from aec_api.module_schema import validate_dir` vanished before matching. The gate reported
#: `validate_dir` dead, it was deleted, and `test_module_config` went red in the full suite.
#:
#: **Over-stripping is NOT the safe direction.** It manufactures false deaths, and a false death in
#: a dead-code gate is an instruction to delete working code. Strip only patterns that belong to the
#: file's own language.
#: **And regex is the wrong tool for Python entirely** -- the per-language split above fixed the
#: `.py`-eats-`/*` case and a SECOND false death survived it. `"""(?:.|\n)*?"""` pairs every triple
#: quote 1-2, 3-4, ...; `routers/standards.py` holds 120 of them, and stripping `#` comments first
#: can remove one that lived inside a comment, shifting the pairing and swallowing real code from
#: there to the end of the file. That is how `get_meta` -- imported and called at
#: `routers/standards.py:810` -- was reported dead, deleted, and only caught by an untruncated grep.
#: Python is parsed with `ast` instead: names, attributes and import aliases are collected exactly,
#: docstrings are skipped by identity, and every OTHER string literal is kept because registries
#: dispatch on strings. Regex stripping now applies only to `.ts`, where it is sound.
_STRIP_TS = [
    re.compile(r"^\s*//.*$", re.M),         # ts line comments
    re.compile(r"/\*.*?\*/", re.S),         # ts block comments -- TS FILES ONLY
]
_STRIP_HASH = re.compile(r"^\s*#.*$", re.M)   # yaml / toml / cfg


#: A string literal counts as a reference only when it is shaped like a **dispatch key** -- one
#: identifier, or a dotted/colon/slash/dash path of them. `"add_wall"`, `"cost_per_sf"` and
#: `"drawings.markups.rekey_storeys"` match; an English sentence does not.
#:
#: **ADDED 2026-08-27, after finding by hand a function this gate scored SIXTY references for.**
#: `deal_memory.beside()` -- the function R35-DEAL-MEMORY exists to put on a screen -- had no route,
#: no client method and no screen, and most of those sixty were the English word *beside* in prose,
#: including plain string literals held as payload text (`deal_funnel.py` returns a note reading
#: "…is shown beside it rather than folded into it").
#:
#: **That is `quadrant` a second time, and the fix belongs here — but it is NOT why `beside` was
#: missed, and saying so would be this gate making the same kind of claim it exists to catch.**
#: Measured: under the tightened rule `beside` still has two references, and one of them is
#: `test_deal_memory.py`, which has imported it since the engine shipped in PR #180. **The test tree
#: counts as callers by design** — that is the 35 → 13 correction this file's header describes — so
#: "tested but wired to nothing" is invisible to this gate on purpose, and no string rule reaches it.
#: The gap is real and measured: **20 public functions in `aec_api` are referenced only by tests**
#: (2026-08-27), `beside` having been the 21st. Recorded as its own roadmap item rather than
#: smuggled in here, because each of the 20 needs reading — several are legitimately test-only
#: surface, and R37-TRIAGE's whole lesson is that the reading is the value, not the number.
#:
#: What this rule DOES fix is the prose mask, and it is worth fixing on its own: counting every
#: string literal was right about registries and wrong about prose, and the two are distinguishable
#: by shape. A key is a token; a sentence has spaces.
#:
#: Measured before and after, because this file's own history is four corrections to a population
#: rule: **0 unreferenced → 1**, and the one is `sync_property`, which the roadmap already documents
#: as genuinely uncalled and masked by its own `NotImplementedError` string. It moves from invisible
#: to explicitly exempted below, which is the direction that matters.
_KEY_SHAPED = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:[.:/-][A-Za-z0-9_]+)*$")


def _py_names(text: str) -> str:
    """Every identifier a Python file actually *uses*, via the parser rather than a regex.

    Returns a space-joined bag of words, so the caller's tokeniser sees the same shape it does for
    other file types. Falls back to the raw text on a syntax error -- a file we cannot parse must
    not silently contribute zero references, because "unparseable" and "calls nothing" are the same
    to a counter and only one of them is true.
    """
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return text
    docstrings = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = getattr(node, "body", None)
            if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
                    and isinstance(body[0].value.value, str):
                docstrings.add(id(body[0].value))
    out: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            out.append(node.id)
        elif isinstance(node, ast.Attribute):
            out.append(node.attr)
        elif isinstance(node, ast.alias):
            out.append(node.name.split(".")[-1])
            if node.asname:
                out.append(node.asname)
        elif isinstance(node, ast.keyword) and node.arg:
            out.append(node.arg)
        elif isinstance(node, ast.Constant) and isinstance(node.value, str) \
                and id(node) not in docstrings and _KEY_SHAPED.match(node.value.strip()):
            out.append(node.value)          # string dispatch is a real reference -- a SENTENCE is not
    return " ".join(out)


def _code_only(text: str, ext: str) -> str:
    if ext in (".py", ".spec"):
        return _py_names(text)
    if ext == ".ts":
        for pat in _STRIP_TS:
            text = pat.sub(" ", text)
        return text
    return _STRIP_HASH.sub(" ", text)

SKIP_DIRS = {"__pycache__", "node_modules", ".git", ".venv", "dist", "build", ".mypy_cache"}


def _sources() -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for root in SEARCH_ROOTS:
        root = os.path.abspath(root)
        if not os.path.isdir(root):
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
            for fn in filenames:
                if not fn.endswith(SEARCH_EXTS):
                    continue
                p = os.path.join(dirpath, fn)
                # THIS FILE IS NOT A CALLER. It names symbols to talk about them -- the blind-spot
                # table, the deleted-for-cause list, and (since 2026-08-27) the deliberately-uncalled
                # exemptions, whose keys are identifier-shaped by construction and therefore survive
                # the key-shape filter that every other prose mention now fails.
                #
                # Found the moment the exemption list was written: adding `"sync_property"` as a dict
                # key made `sync_property` referenced, the ratchet went back to zero, and the entry
                # documenting it read as stale. **An exemption list that satisfies the check it is
                # exempting from is the gate measuring itself** -- the same shape as the `specPane`
                # string that made `canvasMode.test.ts` too weak, and as an allowlist entry that
                # vouches for its own route.
                if os.path.abspath(p) == os.path.abspath(__file__):
                    continue
                try:
                    ext = os.path.splitext(fn)[1]
                    out.append((p, _code_only(open(p, encoding="utf-8", errors="replace").read(), ext)))
                except OSError:
                    continue
    return out


def _defined_public() -> dict[str, str]:
    """Public **module-level** functions and public **methods** in `aec_api`, name -> defining file.

    ## Two corrections this function had to make to itself, which is the lesson repeating

    The first draft walked the whole AST with `ast.walk` and reported **69** unreferenced names
    against the roadmap's 12. That gap was not a discovery, it was two defects in *this* rule:

    1. **`ast.walk` descends into nested functions.** A closure defined inside another function --
       `deco` inside a decorator factory, `col_map` inside a parser -- is not module API and can
       never be "called by name" from anywhere. Only direct children of the `Module`, plus methods
       one level down inside a `ClassDef`, are reachable surface.
    2. **Same-file callers were being discarded.** The defining file was skipped wholesale, so a
       module-private helper used three times by its own neighbours scored zero, and every method
       called as `self.foo()` inside its own class scored zero.

    Methods are in scope deliberately: `register_recipe` is one, and the previous rule flagged it
    while `plugins/README.md` documented it as the public plugin API.

    This is the same failure the entry is about, one level down -- a population rule that looks
    reasonable and is wrong until you read what it actually selected. The number it produces is
    worthless without that reading, which is why the rule lives in code with its reasoning attached
    rather than as "13" in a document.
    """
    found: dict[str, str] = {}
    for dirpath, dirnames, filenames in os.walk(PKG):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fn in filenames:
            if not fn.endswith(".py"):
                continue
            p = os.path.join(dirpath, fn)
            try:
                tree = ast.parse(open(p, encoding="utf-8").read(), filename=p)
            except SyntaxError:
                continue
            rel = os.path.relpath(p, ROOT).replace("\\", "/")

            def _take(node: ast.AST, rel: str = rel) -> None:
                if not isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef):
                    return
                if node.name.startswith("_"):
                    return
                # A decorated function is reached BY the decorator (FastAPI routes, registry
                # entries), never by name -- this was the 877 -> 35 correction.
                if node.decorator_list:
                    return
                found.setdefault(node.name, rel)

            for node in ast.iter_child_nodes(tree):        # module-level functions
                _take(node)
                if isinstance(node, ast.ClassDef):          # ...and their methods, one level down
                    for sub in ast.iter_child_nodes(node):
                        _take(sub)
    return found


def _reference_counts(names: set[str], sources: list[tuple[str, str]]) -> dict[str, int]:
    """How many times each name is reached, across every tree searched.

    Each file is tokenised ONCE into identifier-shaped words, then intersected with the names we
    are looking for. The obvious implementation -- one regex per name per file -- is ~1,000 x
    ~7,000 searches and took the run past seven minutes, which is a check nobody keeps. Same
    answer, two orders of magnitude cheaper.

    A word match catches a bare call, an attribute access (`mod.NAME(`), an aliased import
    (`import NAME as _x` -- the *import* still names it), a string literal, and a mention in a
    plugin README. Deliberately generous: see the module docstring on why the two error directions
    are not symmetric.

    In the DEFINING file a name always appears at least once -- on its own `def` line -- so that
    one occurrence is subtracted rather than the whole file being skipped. Skipping the file was
    the second defect: a module-private helper called by its own neighbours, and every method
    invoked as `self.foo()`, both scored zero while being plainly alive.
    """
    word = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
    counts = dict.fromkeys(names, 0)
    for _path, text in sources:
        words = word.findall(text)
        seen = set(words)
        tally: dict[str, int] = {}
        for w in words:
            if w in names:
                tally[w] = tally.get(w, 0) + 1
        for n in names & seen:
            # NO subtraction for the defining file. The regex era needed one, because the `def` line
            # itself contributed an occurrence. `ast` never collects a definition's own name, so
            # subtracting here deletes a REAL same-file call -- which is exactly what it did:
            # `build_payload` (webhooks.py:143), `parse_csv` (comps.py:75) and `capital_stack`
            # (report.py:567, via `self.`) are all called inside their own module and all three were
            # reported dead. Changing how references are gathered changes what must be discounted.
            counts[n] += tally.get(n, 0)
    return counts


defs = _defined_public()
sources = _sources()
counts = _reference_counts(set(defs), sources)
unreferenced = sorted(n for n, c in counts.items() if c == 0)

check(
    "the corrected rule actually reads the trees it claims to",
    len(sources) > 500 and any(p.endswith(".spec") for p, _ in sources),
    f"{len(sources)} files, {sum(1 for p, _ in sources if p.endswith('.spec'))} .spec — a rule that "
    "silently reads nothing passes every population check ever written",
)

check(
    "the population is large enough to be the real one",
    len(defs) > 900,
    f"{len(defs)} public undecorated functions/methods in aec_api",
)

# The ratchet. Zero, because R37-TRIAGE deleted the three that survived reading:
#   evm.quadrant        -- a SECOND implementation of the CPI-SPI points `evm.ts` already derives,
#                          under a docstring claiming "Used for the quadrant scatter on the dashboard"
#   cde.scorecard_inputs-- a wrapper "so the KPI engine has one import", which `bim_kpi.py` bypasses
#                          by calling the two functions it wraps
#   classification.discipline_names -- an option list nothing offered
# Each was deleted for saying something false about itself, not merely for being uncalled.
#: Uncalled ON PURPOSE, each with the reason. **Not a convenience list** -- an entry here is a claim
#: that deleting the function would remove something the codebase needs, and it is checked in both
#: directions below, so it cannot rot into a fiction.
#:
#: `sync_property` arrived here on 2026-08-27 and was NOT newly dead. It has been uncalled the whole
#: time; the roadmap entry for R37-TRIAGE says so in as many words, and adds the part that matters:
#: *"the gate counts it as referenced because that error string names it -- a limitation, stated
#: rather than hidden"*. Tightening the string rule above removed the mask. **An exemption anybody
#: can read beats a mask nobody can see**, and the two look identical from the outside: both are a
#: green run over a function nothing calls.
DELIBERATELY_UNCALLED: dict[str, str] = {
    "sync_property": (
        "a refusal stub. It raises NotImplementedError and names ITSELF as the place to implement "
        "the credentialed ENERGY STAR exchange. Deleting it would remove the documented extension "
        "point from a module whose whole contract is 'never fabricate a score' — the docstring is "
        "the deliverable, not the body."),
}

surprises = sorted(set(unreferenced) - set(DELIBERATELY_UNCALLED))
check(
    "no public function in aec_api is unreachable under the corrected rule",
    not surprises,
    ", ".join(surprises) if surprises
    else f"0 unreferenced beyond the {len(DELIBERATELY_UNCALLED)} kept on purpose — add one and this "
         "fails at the commit that adds it, which is the point",
)

# The other direction, because an exemption list that only ever grows is the failure this file was
# written about one level up: `test_route_reachability` learned the same thing, and its comment
# ("an allowlist entry that outlives its reason reads as a deliberate exemption forever") is the
# reason this is a check rather than a note.
stale = sorted(n for n in DELIBERATELY_UNCALLED if n not in unreferenced)
check(
    "every deliberately-uncalled entry is still uncalled — the list cannot rot",
    not stale,
    f"{stale} — now referenced, or renamed/deleted. Either way remove the entry: a kept name that "
    "no longer means anything pre-authorises whatever reuses it.",
)

# The three blind spots, asserted individually. Without these the ratchet above could pass because
# the rule got LOOSER, not because the code got cleaner -- and a check cannot tell those apart.
BLIND_SPOTS = {
    "excluded_import_names": ("desktop.spec", "a Python file that is not .py"),
    "search_filter": ("modules_query.py", "an aliased import, `as _search_filter`"),
    "register_recipe": ("plugin.py", "a method reached through an instance"),
}
missed = []
for name, (where, why) in BLIND_SPOTS.items():
    hits = [os.path.basename(p) for p, t in sources if re.search(rf"\b{name}\b", t)]
    if where not in hits:
        missed.append(f"{name}: expected a hit in {where} ({why}); saw {hits[:4]}")
check(
    "each of the three blind spots is still covered by name",
    not missed,
    "; ".join(missed) or "aliased import · non-.py Python · instance method — all three reached",
)

print()
if FAILURES:
    print("FAILED:", ", ".join(FAILURES))
    sys.exit(1)
print("test_dead_code_population OK")
