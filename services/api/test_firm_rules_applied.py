"""FIRM-RULES-OPTIONAL — the firm's standards were authored, stored, validated, and evaluated by
nothing; and a project with no library of its own reported a PASS against three samples.

`firm_standards.py` exists so a standard can outlive a project. Its own docstring names the failure
mode: *"A firm rule that a project silently replaces is how a firm's standards stop being
standards… the failure here is not a wrong answer, it is a firm discovering its standards were
quietly optional."* `effective_rules` — the function that answers *what applies here* — had exactly
**one** consumer in the whole tree: its own route, `/projects/{pid}/rules/effective`, which
`services/api/test_route_reachability.py` carried as a route no screen reaches.

Meanwhile both things that actually CHECK a model read the project library directly:

    rules = rule_library.load(pid) or rule_library.STARTER_RULES      # model_ci._rules_check
    stored = rule_library.load(pid) or rule_library.STARTER_RULES     # routers/standards.rules_run

Two consequences, and the second is the one with a stored artifact behind it:

  ① **A firm rule a project inherits was evaluated by nothing.** The firm authors a standard, every
     project lists it as inherited on a page nobody can open, and both checks ignore it.
  ② **A project with no library was checked against three SAMPLE rules and the clean result was
     reported as a pass** — stored by `model_ci` as that project's quality badge. `GET
     /projects/{pid}/rules` has always returned `seeded: not stored` for exactly this fallback, so
     the honest flag existed **one route away from the two consumers that needed it**.

THE ASYMMETRY IS THE CORRECTION, AND THE FIRST DRAFT GOT IT WRONG
----------------------------------------------------------------
Making the whole starter result `skip` is a regression, not a fix, and `services/api/test_model_ci.py`
is what measures that: its `IDX_FAIL` fixture is a door with no fire rating, the high-severity starter
rule catches it, and the check reported `fail` → badge **FAIL**. Folding samples into `skip` wholesale
turns that real finding into a non-finding and the badge into PASS. So a FAILURE a sample rule finds
is still a failure — the defect is real whoever wrote the rule — while a CLEAN result over rules
nobody adopted is `skip`. *A finding is a finding; the absence of one is a pass only against a
standard somebody chose.*

WHAT THE SWEEP DERIVES
----------------------
The rule is function-level and has no exemptions: **a function that calls `rule_library.run(` must not
also reach the library directly.** Going through `firm_standards.applicable_rules` is the only way to
get the project's rules, because that is the only place that knows about the firm's. Derived by AST for
function boundaries, so a fourth evaluator cannot be born with the defect without redding this.

Its blind spot is stated rather than discovered later: a function that calls a HELPER which loads the
library would read clean. The second arm covers the only such helper shape that matters —
`rule_library.STARTER_RULES` may be referenced from exactly two functions, `applicable_rules` (which
labels it) and `rules_get` (which flags it as `seeded`). A third reference reds and forces a read.

**SCOPED TO MODULES THAT CAN SEE `rule_library`, since 2026-10-14.** The arm matched the bare
identifier `STARTER_RULES` anywhere in the tree, and `aec_api/cost_rules.py` redded it on the day it
was born — a COST rule set naming its own starter rates, which is a different vocabulary answering a
different question. *A rule applied outside the population it was reasoned about does not degrade
gracefully; it produces confident findings about code it has no view of.* The PRINCIPLE does carry
over, and is honoured there by a different mechanism: a cost estimate has no `skip` state, so
instead of folding a sample result away, the route carries `rules_seeded` beside the total and the
screen refuses to present it as the firm's number. *A total computed from rates nobody chose is the
same claim as a clean result over rules nobody adopted.*

Run: cd services/api && PYTHONPATH="src:../data/src" ./.venv/bin/python test_firm_rules_applied.py
"""
import ast
import os
import pathlib
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_firm_rules_applied.db"
os.environ["STORAGE_DIR"] = "./test_storage_firm_rules_applied"
os.environ.pop("AEC_RBAC", None)
if os.path.exists("./test_firm_rules_applied.db"):
    os.remove("./test_firm_rules_applied.db")

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

from aec_api import firm_standards as fs  # noqa: E402
from aec_api import model_ci, rule_library  # noqa: E402

FAILED: list[str] = []


def ok(cond, label):
    print(("PASS  " if cond else "FAIL  ") + label)
    if not cond:
        FAILED.append(label)


PID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
FIRM = [{"id": "fire90", "name": "L1 doors are fire-rated", "scope": "IfcDoor",
         "require": "Pset_DoorCommon.FireRating=90", "severity": "high"}]
OWN = [{"id": "named", "name": "Walls are named", "scope": "IfcWall",
        "require": "name", "severity": "low"}]

# A model that SATISFIES the firm rule, so a failure can only come from the rule being evaluated.
# `psets` on the wall is NOT incidental: the starter set's `loadbearing-declared` scopes every
# IfcWall and requires `Pset_WallCommon.LoadBearing`, so a bare wall makes this fixture fail at LOW
# severity and the "clean over samples" check below reads `warn` instead of `skip` — which is what
# the first run of this gate reported. *A fixture meant to be clean has to be clean against the
# rules that will actually run on it, and the starter set is three rules, not one.*
IDX_OK = {"g1": {"ifc_class": "IfcDoor", "name": "D1",
                 "psets": {"Pset_DoorCommon": {"FireRating": "90"}}},
          "g2": {"ifc_class": "IfcWall", "name": "W1",
                 "psets": {"Pset_WallCommon": {"LoadBearing": "false"}}}}
IDX_BREACH = {"g1": {"ifc_class": "IfcDoor", "name": "D1",
                     "psets": {"Pset_DoorCommon": {"FireRating": "30"}}},
              "g2": {"ifc_class": "IfcWall", "name": "W1", "psets": {}}}


def seed(firm, own):
    fs.save_rules(firm)
    rule_library.save(PID, own)


# ── ① the firm's rules are in what gets run ──────────────────────────────────────────────────────
seed(FIRM, OWN)
app = fs.applicable_rules(PID)
ids = {r["id"] for r in app["rules"]}
ok(ids == {"fire90", "named"},
   f"an inherited firm rule is IN the set that gets evaluated — got {sorted(ids)}")
ok({r["id"]: r["source"] for r in app["rules"]} == {"fire90": "firm", "named": "project"},
   "...and every rule says where it came from")
ok(app["provenance"]["inherited_count"] == 1 and not app["provenance"]["using_starter"],
   "the provenance counts the inheritance and does not claim the samples")

# the override, which must not reinstate the firm's version alongside it
seed(FIRM, [{"id": "fire90", "name": "Client standard: 60 min", "scope": "IfcDoor",
             "require": "Pset_DoorCommon.FireRating=60", "severity": "high"}])
app_o = fs.applicable_rules(PID)
ok(len(app_o["rules"]) == 1 and app_o["rules"][0]["source"] == "project",
   "an override replaces the firm rule rather than running beside it")
ok((app_o["rules"][0].get("overrides") or {}).get("require")
   == "Pset_DoorCommon.FireRating=90",
   "...and carries the firm version it displaced, so the override is visible AS an override")

# ── ② the starter fallback is labelled, not silently mixed in ────────────────────────────────────
seed([], [])
app_s = fs.applicable_rules(PID)
ok(app_s["provenance"]["using_starter"] is True,
   "with nothing authored anywhere, the payload SAYS the rules are samples")
ok({r["source"] for r in app_s["rules"]} == {"starter"},
   "...and every sample row is labelled `starter`, not left to look authored")
ok(len(app_s["rules"]) == len(rule_library.STARTER_RULES),
   "the fallback is still the starter set — an empty library would be a vacuous pass")

# ── provenance is matched by ID, not by position ─────────────────────────────────────────────────
res = {"rules": [{"id": "named"}, {"id": "fire90"}]}          # deliberately the OTHER order
seed(FIRM, OWN)
fs.attach_provenance(res, fs.applicable_rules(PID)["rules"])
ok([r["source"] for r in res["rules"]] == ["project", "firm"],
   "attach_provenance matches on id — a positional match would blame the wrong owner")
ok(fs.attach_provenance({"rules": [{"id": "ghost"}]}, app["rules"])["rules"][0]["source"] is None,
   "a row whose id matches nothing is left None rather than guessed at")

# ── ③ model_ci: the asymmetry, which is where the first draft was wrong ──────────────────────────
seed([], [])
clean = model_ci._rules_check(None, PID, IDX_OK)
ok(clean["status"] == "skip",
   f"a CLEAN result over sample rules is unassessable, not a pass — got {clean['status']!r}")
ok("not a pass" in clean["summary"] or "no rule library" in clean["summary"],
   "...and the summary says why, because this verdict is STORED as the project's badge")

breach = model_ci._rules_check(None, PID, {
    "g1": {"ifc_class": "IfcDoor", "name": "D1", "psets": {"Pset_DoorCommon": {}}}})
ok(breach["status"] == "fail",
   "a HIGH-severity failure a sample rule finds is still a failure — the first draft of this "
   f"change reported it as skip and turned `test_model_ci`'s FAIL badge into PASS; got "
   f"{breach['status']!r}")

seed(FIRM, OWN)
ok(model_ci._rules_check(None, PID, IDX_OK)["status"] == "pass",
   "an authored library that the model satisfies is a pass")
firm_breach = model_ci._rules_check(None, PID, IDX_BREACH)
ok(firm_breach["status"] == "fail",
   "a model that breaches an INHERITED FIRM rule fails model CI — which it could not do before, "
   f"because the firm library was never read; got {firm_breach['status']!r}")
ok(firm_breach.get("provenance", {}).get("inherited_count") == 1,
   "...and the stored report carries where the rules came from")

# ── the derived sweep: no evaluator may reach the library directly ───────────────────────────────
SRC = pathlib.Path(__file__).resolve().parent / "src" / "aec_api"
LIBRARY_REACH = ("rule_library.load(", "rule_library.STARTER_RULES", "STARTER_RULES")


def _strip_docstrings(tree: ast.AST) -> ast.AST:
    """Drop every docstring, so the sweep below rules on CODE and not on prose.

    **Its first draft read the raw source and the measurement is what caught it.** The second arm
    came back naming `model_ci._rules_check`, `routers/standards.rules_run` and
    `rule_library.load` — all three because a docstring or comment of mine QUOTES the defect it
    replaced (*"this read `rule_library.load(pid) or STARTER_RULES`"*). The main arm survived only
    by luck, because those same functions mention `applicable_rules` too.

    *A checker that reads prose can be tripped by an explanation and defeated by a comment* — which
    is the failure this repository has paid for more than any other. `ast.unparse` discards comments
    by construction and this discards docstrings, so the only thing left to match is what runs.
    """
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            body = getattr(node, "body", None)
            if (body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                node.body = body[1:] or [ast.Pass()]
    return tree


def _functions(path: pathlib.Path):
    """(qualified name, executable source) for every function in a module, nested ones included."""
    tree = _strip_docstrings(ast.parse(path.read_text(encoding="utf-8")))
    out = []

    def walk(node, prefix):
        for child in ast.iter_child_nodes(node):
            if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                name = f"{prefix}{child.name}"
                out.append((name, ast.unparse(child)))
                walk(child, name + ".")
            else:
                walk(child, prefix)

    walk(tree, "")
    return out


def sweep(body_of) -> list[str]:
    """Every function that RUNS rules and also reaches the library directly.

    `body_of` yields (label, source) pairs, so the self-test below can feed it the pre-fix bodies
    instead of the tree — a sweep that can only ever be pointed at the fixed code is a sweep that
    can only report good news.
    """
    bad = []
    for label, src in body_of:
        if "rule_library.run(" not in src:
            continue
        hits = [m for m in LIBRARY_REACH if m in src]
        if hits and "applicable_rules" not in src:
            bad.append(f"{label} runs rules and reads the library directly ({', '.join(hits)})")
    return bad


def tree_bodies():
    for path in sorted(SRC.rglob("*.py")):
        if path.name == "firm_standards.py":
            continue                      # the one module allowed to reach the library
        for name, src in _functions(path):
            yield (f"{path.relative_to(SRC)}::{name}", src)


def modules_seeing_library() -> set[str]:
    """Modules that could NAME `rule_library`'s sample set at all.

    **The second arm below matched the bare identifier `STARTER_RULES` anywhere in the tree**, which
    is a rule about `rule_library`'s samples applied to a population it has no view of. It redded on
    the day `cost_rules.py` was born: a COST rule set — a selector bound to a cost code and a rate,
    a different vocabulary answering a different question — named its own starter set and this gate
    reported it as a third reference to the model-check samples. *A rule applied outside the
    population it was reasoned about does not degrade gracefully; it produces confident findings
    about code it cannot see.*

    The narrowing is airtight in the safe direction and deliberately coarse: a module that never
    mentions `rule_library` cannot be naming ITS samples, however the import is spelled — as a
    module (`from . import rule_library`), as a name (`from .rule_library import STARTER_RULES`) or
    inside a function, which is this codebase's house style. A module that does mention it stays in
    the population on the bare identifier alone, so moving the reference behind an import hides
    nothing.
    """
    out = set()
    for path in sorted(SRC.rglob("*.py")):
        if path.name == "firm_standards.py":
            continue
        try:
            tree = _strip_docstrings(ast.parse(path.read_text(encoding="utf-8")))
        except SyntaxError:
            out.add(str(path.relative_to(SRC)))        # unparseable: fail CLOSED, stay in scope
            continue
        # CODE ONLY. A raw text match put `cost_rules.py` in scope on its own DOCSTRING, which
        # names `rule_library` four times to explain why it is the deliberate NON-candidate — so the
        # prose arguing the two are different vocabularies was read as evidence that they are the
        # same one. `ast.unparse` emits no comments and `_strip_docstrings` drops the rest, which is
        # the identical correction the first arm already carries ten lines of self-test for. *A gate
        # that reads prose as code will be defeated by the sentence explaining it.*
        if "rule_library" in ast.unparse(tree):
            out.add(str(path.relative_to(SRC)))
    return out


def sample_referencing(body_of, sees: set[str]) -> list[str]:
    """Functions naming the model-check sample set, scoped to modules that can see it.

    A separate function so it can be mutated directly. Asserting that the ARM reports something is
    not asserting that it reports the right thing — the mistake `test_unique_read_guard`'s own first
    draft made one layer up.
    """
    return sorted({label for label, src in body_of
                   if "STARTER_RULES" in src and label.split("::")[0] in sees})


bodies = list(tree_bodies())
ok(len(bodies) > 500, f"the walk found functions to rule on ({len(bodies)})")
ok(sum(1 for _, s in bodies if "rule_library.run(" in s) >= 2,
   "...including the ones that RUN rules — a population of zero would report a clean tree")
problems = sweep(bodies)
ok(not problems, "no evaluator reaches the rule library directly" + (
    "" if not problems else " — " + " | ".join(problems)))

# ── the self-test: the sweep must re-find both pre-fix evaluators ────────────────────────────────
PRE_FIX = [
    ("model_ci._rules_check (as shipped before this change)", '''
def _rules_check(db, pid, idx):
    rules = rule_library.load(pid) or rule_library.STARTER_RULES
    r = rule_library.run(idx, rules)
    return r
'''),
    ("routers/standards.rules_run (as shipped before this change)", '''
def rules_run(pid, db, _):
    stored = rule_library.load(pid) or rule_library.STARTER_RULES
    out = rule_library.run(_idx_for(pid), stored)
    return out
'''),
]
refound = sweep(PRE_FIX)
ok(len(refound) == 2,
   f"the sweep re-finds BOTH pre-fix evaluators before it may report anything ({len(refound)})")

# ...and must not flag the pack evaluator, which runs a regulator's own requirements and never
# touches the library. A rule that flagged it would need an exemption, and an exemption list is
# where the next instance hides.
ok(not sweep([("jurisdiction_packs.check_packs", '''
def check_packs(idx, packs):
    for p in packs:
        res = rule_library.run(idx, p.get("requirements") or [])
    return res
''')]),
   "a non-library evaluation (a jurisdiction pack's own requirements) is not flagged — no "
   "exemption needed")

# ...and the stripping that makes the above rule on code is itself mutation-proved, in both
# directions: a function whose only mention is in prose must be clean, and the same text as CODE
# must be caught. Fed through the real parser, not a string, so it tests what the sweep does.
def _probe(src: str) -> list[tuple[str, str]]:
    tree = _strip_docstrings(ast.parse(src))
    return [(f.name, ast.unparse(f)) for f in tree.body
            if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef))]


ok(not sweep(_probe('''
def documented(pid, idx):
    """This used to read `rule_library.load(pid) or rule_library.STARTER_RULES`."""
    # ...and STARTER_RULES is named here too, in a comment.
    return rule_library.run(idx, helper(pid))
''')),
   "a function whose only mention of the library is in its DOCSTRING or a comment is not flagged")

ok(len(sweep(_probe('''
def actual(pid, idx):
    return rule_library.run(idx, rule_library.load(pid) or rule_library.STARTER_RULES)
'''))) == 1,
   "...and the same text as executable code IS flagged — the stripping narrows prose, not the rule")


# ── the second arm: who may reference the sample set at all ──────────────────────────────
#
# Covers the sweep's stated blind spot from the other end: a function that loads the library through
# a helper would read clean above. Two functions may name the samples, each for a reason, and a
# third reds.
_SEES_LIB = modules_seeing_library()
ok("routers/standards.py" in _SEES_LIB,
   "the module holding the one permitted reference is not in the scoped population, so this arm "
   f"would pass over an empty set — {sorted(_SEES_LIB)[:5]}")
ok("cost_rules.py" not in _SEES_LIB,
   "the COST rule store reads as able to see the model-check samples, which it cannot — the "
   "scoping is matching something other than a reference to `rule_library`")
referencing = sample_referencing(bodies, _SEES_LIB)
ok(referencing == ["routers/standards.py::rules_get"],
   "outside `firm_standards`, the sample set is referenced only by the LISTING that flags it as "
   f"`seeded` — got {referencing}")

# The narrowing must not open a hole: a module that CAN see the library is still caught on the bare
# identifier, and one that cannot is still ignored. Both arms, because asserting only the first
# would pass a scoping rule that excluded everything.
_SCOPE_PROBE = [("rule_library.py::third", "return STARTER_RULES"),
                ("cost_rules.py::effective", "return STARTER_RULES")]
ok(sample_referencing(_SCOPE_PROBE, {"rule_library.py"}) == ["rule_library.py::third"],
   "the scoped arm either lost a reference from a module that CAN see the samples, or kept one "
   "from a module that cannot — it must do exactly one of those and it must be the second")
ok("STARTER_RULES" in (SRC / "firm_standards.py").read_text(encoding="utf-8"),
   "...and by `applicable_rules`, which labels every sample row `starter`")

print()
if FAILED:
    print(f"FAILED: {len(FAILED)}")
    for f in FAILED:
        print("  - " + f)
    sys.exit(1)
print("FIRM-RULES-OPTIONAL: the firm's standards are evaluated, and a pass over samples is not a pass.")
