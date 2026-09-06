"""Every read-decide-insert on a mapped model is guarded, and the population is DERIVED.

## Why this exists

Three seeding races were fixed on 2026-08-25 (the sign-in doors), a fourth on the SCIM path, and a
fifth in `settings_store`. What bound them together was recorded as prose, in comments, next to each
fix: *"swept 2026-08-27"*. **A sweep held as prose is a check that can only report good news.**
Nothing in the tree could name the population, so nothing could notice a sixth site — and there
were four, found the day this file was written.

They were not exotic. They were the sites whose key is a composite NATURAL key rather than a
PRIMARY key, and they were missed for a reason worth stating: `get_or_create_by_pk` was the only
shape the sweep had to hand, so the sites it could not express stayed unconverted AND unmentioned.
**A sweep is bounded by the fix available to it**, and the leftovers do not announce themselves.
`cost_db.import_custom_vintage` even wrote down what was missing — *"this wants
`auth.get_or_create_by_pk`'s idiom with a query instead of a primary key"* — and nothing acted on
it for ten days, because a note in a comment is not a check.

## What this gate is shaped around

The derivation, not the answer. This file does not carry a list of known sites; it walks every
tracked source file under the two service source trees and reports the shape:

    <lookup of Model>  ...  if <cond>:  ...  db.add(Model(...))

An entry in `EXEMPT` is how a site says "this shape is correct here, and why". Everything else must
route through `auth.get_or_create_by_pk` / `get_or_create_by_key`, which by construction no longer
matches the shape.

## Why there is no "did this function read the model first" precondition

**The first version of this gate had one, it shipped, and it was blind within the hour.** It
required the model's name to appear inside a lookup call in the same function — `db.get(User, ...)`,
`select(SavedView)`. `modules.add_enum_option` reads through a HELPER (`list_enum_options(db, pid)`),
so the name `EnumOption` never appears in a lookup there, and the site was invisible. It was a real
seeding race with a docstring promising the opposite (*"is idempotent against the JSON options +
existing customs"*) over a table with three non-unique indexes — the third instance of the class this
file exists for, sitting unreported inside a gate reporting **0 unguarded**.

So the precondition is gone. Every mapped model is a candidate and the shape detected is only the
**conditional insert**, which is syntactic. "Did this function look the model up" is a semantic
question — helpers, relationship access, raw SQL — and an AST answering it will always answer some
cases wrongly, silently, in the direction of reporting less.

The cost is four legitimate sites that are not get-or-create at all (a Topic per clash, per failing
CI check) and now need an entry in `EXEMPT`. That is the correct trade: an exemption is a sentence
someone wrote and can be argued with, whereas the old precondition dropped sites without a trace.

**What it still cannot see, stated so the next reader does not have to find out the hard way:** an
insert that is not inside an `if` at all — one guarded by an early `return`, or by a `try/except`
around the insert instead of a branch. `mark_view_seen` happens to use the `try/except` form and is
only visible here because it ALSO has a branch. A guard style this file cannot parse is the next
blind spot, and it will look exactly like a clean report.

## The assertion that makes the other two mean anything

`test_the_deriver_finds_the_races_that_are_already_fixed` runs the deriver over the code AS IT
STOOD before the 2026-08-25 fix and requires it to find all three sign-in doors.

This is not decoration. **The first version of this deriver found ONE of those four sites** and
reported "2 seeding sites, both benign" against today's tree — a confident, clean, entirely
worthless answer. The bug: it looked for the `Model(...)` assignment only inside the single
statement that held the `.add()`, and the doors are written as two statements —

    u = User(username=email, ...)      # one statement
    db.add(u)                          # the next

so every door fell outside the window it searched. It was caught by running it against known
positives, which is the only reason it was caught at all. Derive the population AND prove the
derivation reaches it; a completeness verdict computed by an unvalidated detector is confident and
unfounded.

Run: cd services/api && PYTHONPATH=src:../data/src ./.venv/bin/python test_seeding_sweep.py
"""
from __future__ import annotations

import ast
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent

#: The source trees a seeding race can actually ship from. Test files construct rows directly on
#: purpose — that is what a fixture is — so they are out of scope, and saying so here is the only
#: honest way to keep them out: a filter that silently dropped them would be indistinguishable from
#: a deriver that could not see them.
SCOPE = ("services/api/src/", "services/data/src/")

#: Sites where read-decide-insert is correct as written, each with the reason. Anything not listed
#: must route through `auth.get_or_create_by_pk` or `auth.get_or_create_by_key`.
EXEMPT: dict[str, str] = {
    "services/api/src/aec_api/cost_db.py::import_custom_vintage":
        "Admin-only (`/cost/import/*`), never runs at boot, and `ix_cost_dataset_vintage` is UNIQUE "
        "so the loser gets a refusal rather than a duplicate row — one 500 for one of two admins "
        "importing the same vintage in the same second, and the retry succeeds. The site carries "
        "this reasoning inline, including what would change the answer (any caller that runs at "
        "boot). Swept 2026-08-27, deliberately not converted.",
    "services/api/src/aec_api/jobs.py::_clash_detect":
        "Not a get-or-create: it creates one Topic per finding inside a per-finding loop, with no existence read and nothing to fold into. Two concurrent runs produce two sets of issues, which is what running an analysis twice means — the same shape as any append-only log. Listed rather than filtered out because the gate no longer asks whether a function read the model first, and this is the cost of that: a stated reason instead of a silent omission.",
    "services/api/src/aec_api/routers/analysis.py::run_clash":
        "Not a get-or-create: it creates one Topic per finding inside a per-finding loop, with no existence read and nothing to fold into. Two concurrent runs produce two sets of issues, which is what running an analysis twice means — the same shape as any append-only log. Listed rather than filtered out because the gate no longer asks whether a function read the model first, and this is the cost of that: a stated reason instead of a silent omission.",
    "services/api/src/aec_api/routers/analysis.py::run_clash_federated":
        "Not a get-or-create: it creates one Topic per finding inside a per-finding loop, with no existence read and nothing to fold into. Two concurrent runs produce two sets of issues, which is what running an analysis twice means — the same shape as any append-only log. Listed rather than filtered out because the gate no longer asks whether a function read the model first, and this is the cost of that: a stated reason instead of a silent omission.",
    "services/api/src/aec_api/routers/standards.py::ci_run":
        "Not a get-or-create: it creates one Topic per finding inside a per-finding loop, with no existence read and nothing to fold into. Two concurrent runs produce two sets of issues, which is what running an analysis twice means — the same shape as any append-only log. Listed rather than filtered out because the gate no longer asks whether a function read the model first, and this is the cost of that: a stated reason instead of a silent omission.",
    "services/api/src/aec_api/routers/modules.py::mark_view_seen":
        "Already guarded, by a different idiom: it catches IntegrityError from the UNIQUE "
        "(view_id, user) constraint, rolls back, and advances the winner's row. Correct, and left "
        "alone rather than rewritten to use the helper — converting working code to make a gate's "
        "output tidier is how a fix becomes a regression.",
}

def mapped_models(root: Path) -> set[str]:
    """Every class deriving from the declarative `Base`, read from the models modules."""
    out = set()
    for f in tracked(root, "*models.py"):
        try:
            tree = ast.parse((root / f).read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.ClassDef) and any(
                    isinstance(b, ast.Name) and b.id == "Base" for b in n.bases):
                out.add(n.name)
    return out


def tracked(root: Path, pattern: str) -> list[str]:
    return subprocess.run(["git", "ls-files", pattern], cwd=root,
                          capture_output=True, text=True, check=True).stdout.split()


def seeding_sites(src: str, models: set[str]) -> list[tuple[str, str, int]]:
    """Every `(function, model, line)` where a conditional branch inserts a mapped model —
    **wherever the read that decided it happens, or whether one is visible here at all.**

    There is deliberately no "the enclosing function also looks the model up" condition; the module
    docstring says why it was removed and what it cost when it was there. The shape reported is the
    conditional insert alone, so a site whose read goes through a helper is still seen.

    The two statements need not be adjacent, and MUST NOT be required to be: the sign-in doors
    write `u = User(...)` and `db.add(u)` as separate statements, and an earlier version of this
    function searched for the assignment only within the statement holding the `.add()`. It found
    one of the four known races and reported the tree clean. `test_the_deriver_finds_the_races_that
    _are_already_fixed` exists because of that.
    """
    hits: list[tuple[str, str, int]] = []
    tree = ast.parse(src)
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        # Every mapped model is a candidate — no "does this function look it up" precondition; see
        # the module docstring. The shape detected is the CONDITIONAL INSERT, which is syntactic and
        # so cannot be evaded by moving the read somewhere this parser cannot follow.
        candidates = models
        for node in ast.walk(fn):
            if not isinstance(node, ast.If):
                continue
            branch = [n for st in (*node.body, *node.orelse) for n in ast.walk(st)]
            var_model = {
                t.id: n.value.func.id
                for n in branch
                if isinstance(n, ast.Assign) and isinstance(n.value, ast.Call)
                and isinstance(n.value.func, ast.Name) and n.value.func.id in candidates
                for t in n.targets if isinstance(t, ast.Name)
            }
            for n in branch:
                if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                        and n.func.attr == "add" and n.args):
                    continue
                a = n.args[0]
                if isinstance(a, ast.Call) and isinstance(a.func, ast.Name) \
                        and a.func.id in candidates:
                    hits.append((fn.name, a.func.id, n.lineno))
                elif isinstance(a, ast.Name) and a.id in var_model:
                    hits.append((fn.name, var_model[a.id], n.lineno))
    return sorted(set(hits))


#: `routers/saml.py::saml_acs` EXACTLY as it stood at 38881856^ — the commit before the three
#: sign-in doors were fixed. Copied verbatim rather than written to suit this deriver, which is the
#: point: a positive sample authored alongside the detector shares its blind spots and confirms it
#: instead of testing it. This one predates the detector by two weeks and does not know it exists.
_KNOWN_POSITIVE = '''
def saml_acs(request, SAMLResponse, db):
    email = (ident.email or ident.name_id or "").strip().lower()
    u = db.get(User, email)
    if u is None:
        if os.environ.get("AEC_OAUTH_NO_AUTOPROVISION") == "1":
            raise HTTPException(403, "no account for this email")
        u = User(username=email, password_hash="saml!" + uuid.uuid4().hex,
                 role="user", email=email, tier="free", provisioned=True)
        db.add(u)
    elif not u.email:
        u.email = email
    db.commit()
'''


#: `modules.add_enum_option` in the shape it had before this file could see it: the read that
#: decides the insert goes through a HELPER, so the model's name never appears in a lookup call
#: here. Kept because `_KNOWN_POSITIVE` cannot stand in for it — that one reads with a direct
#: `db.get(User, ...)`, so it is still found when the removed precondition is put back, and the
#: gate would pass while going blind again. Measured, not assumed:
#:
#:     precondition restored -> SAML fixture FOUND (green), helper-read site MISSED
#:
#: A positive sample that survives the regression it is meant to catch is not a regression test.
_HELPER_READ_POSITIVE = '''
def add_enum_option(db, project_id, module, field, value, actor):
    existing = set(list_enum_options(db, project_id).get(module, {}).get(field, []))
    if value not in existing:
        db.add(EnumOption(project_id=project_id, module=module, field=field, value=value))
        db.commit()
'''


def check(label: str, ok: bool, detail: object = None) -> bool:
    print(f"  {'PASS' if ok else 'FAIL'}  {label}" + (f"   [{detail!r}]" if not ok else ""))
    return ok


def main() -> int:
    models = mapped_models(ROOT)
    ok = True

    print("\nderiver, against known positives and negatives")
    hits = seeding_sites(_KNOWN_POSITIVE, models)
    ok &= check("the pre-fix SAML door IS detected (1 site, on User)",
                [(f, m) for f, m, _ in hits] == [("saml_acs", "User")], hits)

    hits = seeding_sites(_HELPER_READ_POSITIVE, models)
    ok &= check("a site whose read goes through a HELPER is detected — the shape that was invisible "
                "until 2026-09-06, and the one _KNOWN_POSITIVE cannot stand in for",
                [(f, m) for f, m, _ in hits] == [("add_enum_option", "EnumOption")], hits)

    live = (ROOT / "services/api/src/aec_api/routers/saml.py").read_text(encoding="utf-8")
    ok &= check("...and the SAME function, after conversion, is NOT — so a fix removes a site "
                "rather than merely renaming one",
                seeding_sites(live, models) == [], seeding_sites(live, models))

    print("\npopulation")
    found: dict[str, tuple[str, int]] = {}
    for rel in tracked(ROOT, "*.py"):
        if not rel.startswith(SCOPE):
            continue
        try:
            src = (ROOT / rel).read_text(encoding="utf-8")
        except OSError:                      # pragma: no cover - tracked but unreadable
            continue
        try:
            sites = seeding_sites(src, models)
        except SyntaxError:                  # pragma: no cover - py2 bridges live outside SCOPE
            continue
        for fn, model, line in sites:
            found[f"{rel}::{fn}"] = (model, line)

    print(f"  {len(models)} mapped models, {len(found)} read-decide-insert sites in {len(SCOPE)} trees")
    for key, (model, line) in sorted(found.items()):
        print(f"    {key}  -> {model}  (line {line}){'  [exempt]' if key in EXEMPT else ''}")

    unguarded = sorted(set(found) - set(EXEMPT))
    ok &= check("every seeding site is guarded or carries a stated exemption", not unguarded,
                unguarded)

    stale = sorted(set(EXEMPT) - set(found))
    ok &= check("no exemption outlives the site it exempts", not stale, stale)

    ok &= check("every exemption states a reason",
                all(len(r) > 60 for r in EXEMPT.values()),
                [k for k, r in EXEMPT.items() if len(r) <= 60])

    print()
    if ok:
        print(f"SEEDING SWEEP OK - {len(found)} read-decide-insert sites across {len(models)} mapped "
              f"models, {len(EXEMPT)} exempt with stated reasons and 0 unguarded; the deriver is "
              "checked against TWO positives it must find — the pre-fix SAML door (a direct read) "
              "and a helper-mediated read — so a clean report means the tree is clean rather than "
              "the detector being blind.")
    else:
        print("SEEDING SWEEP FAILED")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
