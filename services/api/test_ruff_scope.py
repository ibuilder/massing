"""
Ruff's CI invocation must cover every tracked Python file, minus a declared vendor list.

WHY THIS EXISTS
    Until 2026-09-03 `ci.yml` ran `cd services/api && ruff check src/ ../data/src/`. That is two
    source trees. The repository has 1,338 tracked `.py` files; those two trees hold 612. The other
    726 were NEVER LINTED — and the list is not an odd corner:

        672  services/api/*.py           the entire backend test suite
         27  services/api/migrations/    every alembic revision
          7  scripts/                    repo tooling
          4  integrations/pyrevit/lib/   the Revit bridge
          3  apps/editor-bridge/         the Blender bridge
          3  services/data/*.py          the data-service suites
        ...  plugins/, .claude/hooks/

    Nothing announced this. `ruff check src/ ../data/src/` exits 0 and prints "All checks passed!",
    and a passing lint step reads as "this repository is linted". It is the vacuous-gate failure in
    its purest form: the check was real, the SCOPE was the fiction.

    Widening it found 230 findings, five of them `assert False` in tests that guard security
    behaviour (path-traversal rejection among them) — latent rather than live, since nothing here
    runs `python -O`, but a rule ruff exists to catch and had never been asked about.

THE FAILURE THIS GATE IS SHAPED AROUND
    A scope gate that measures a command NOBODY RUNS is the same bug one level up. So this test does
    not carry its own copy of the ruff arguments: it reads every workflow under `.github/workflows/`,
    finds the step that runs `ruff check`, and measures THAT. Narrow the CI command and this test
    goes red. The two have to agree because only one of them exists.

    THE FIRST VERSION OF THIS WAS BYPASSABLE, and CodeRabbit found it on the PR that introduced it.
    It used `re.search` over `ci.yml` — which takes the FIRST match. Adding an earlier, harmless
    line (`ruff check ../.. --show-files`) and narrowing the real one below it would have left this
    gate measuring the decoy and passing, with the enforcing lint reduced to two directories again.
    A gate that reads the workflow instead of restating it is the right shape; reading only the
    first thing that matches is not reading the workflow.

    So the extraction is now: EVERY workflow file, EVERY `run:` step, and there must be EXACTLY ONE
    `ruff check` in the whole set. Two is ambiguous — this test cannot know which one enforces — and
    ambiguity resolved by picking one is how the bypass worked. A step that cannot fail the build is
    rejected outright: `--exit-zero`, `--show-files` and `--statistics` all report without enforcing,
    and `|| true` or `continue-on-error` neutralise any command at all.

    *A gate derived from a config is only as good as its derivation. "Parses the workflow" sounded
    like a guarantee and was a substring search.*

THE VENDOR CARVE-OUT IS A LIST, NOT A PATTERN
    Five trees are vendored verbatim from upstream and excluded in `ruff.toml` — judging someone
    else's code by our flags is how a verbatim copy becomes a fork. Those trees are named here
    EXPLICITLY, and each one must still match at least one tracked file: an exclusion that stops
    matching is a stale exclusion, and a stale exclusion is how a directory quietly leaves the lint
    scope without anyone deciding that it should.

WHAT THIS DOES NOT CHECK
    That the RULE SET is right. `ruff.toml` selects F/E9/B/I/UP/C4 and that is a judgement call, not
    a fact. This gate is about which FILES the judgement is applied to.

    One caveat worth knowing, because widening the scope hit it: `target-version` is a single global
    setting, and `integrations/pyrevit/**` must still parse on IronPython 2.7. Running `--fix` there
    stripped `# -*- coding: utf-8 -*-` from four files (UP009), three of which hold non-ASCII source
    — a SyntaxError at import on Python 2, in code no CI here executes. `ruff.toml` now ignores `UP`
    for that tree. Scope and rule set are different questions, and widening one can break the other.
"""
import os
import re
import subprocess
import sys

import yaml

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
WORKFLOWS = os.path.join(ROOT, ".github", "workflows")

#: Flags and shell suffixes that make a `ruff check` REPORT rather than ENFORCE. A step carrying any
#: of these cannot fail the build, so it cannot be the lint gate — and treating it as one is exactly
#: the bypass this list exists to close. Listed explicitly; never inferred.
NON_ENFORCING = ("--exit-zero", "--show-files", "--statistics", "--show-settings", "|| true")

#: Vendored verbatim from upstream; excluded in `ruff.toml` for the reason recorded there. Named as
#: exact repository-relative directory prefixes — never as a glob or a heuristic, because an inferred
#: exemption is how a gate stops gating.
VENDORED = (
    "services/api/src/massingplan/",
    "services/api/src/massingcapture/",
    "services/data/src/massingifc_scene/",
    "services/data/src/massingifc_ifc/",
    "services/data/src/massingviser_geometry/",
)

# ---------------------------------------------------------------- the command CI actually runs
def _steps(doc):
    """Every step mapping in a parsed workflow, with the job that owns it."""
    for job_name, job in (doc.get("jobs") or {}).items():
        if not isinstance(job, dict):
            continue
        for step in job.get("steps") or []:
            if isinstance(step, dict):
                yield job_name, job, step


#: (workflow, job, step, run-text) for every step whose shell command mentions `ruff check`. ALL
#: workflows, ALL steps — not the first regex hit in one file.
invocations = []
_wf_files = sorted(
    f for f in os.listdir(WORKFLOWS) if f.endswith((".yml", ".yaml"))
) if os.path.isdir(WORKFLOWS) else []
check("there are workflow files to scan", bool(_wf_files), f"{len(_wf_files)} under .github/workflows")

for wf in _wf_files:
    with open(os.path.join(WORKFLOWS, wf), encoding="utf-8") as fh:
        try:
            doc = yaml.safe_load(fh)
        except yaml.YAMLError as exc:                       # a workflow we cannot parse is a FAILURE:
            check(f"{wf} parses as YAML", False, str(exc)[:200])   # skipping it is how one hides a
            continue                                        # second ruff invocation from this gate.
    if not isinstance(doc, dict):
        continue
    for job_name, job, step in _steps(doc):
        run = step.get("run")
        if isinstance(run, str) and "ruff check" in run:
            invocations.append((wf, job_name, job, step, run))

# EXACTLY one. Two invocations means this gate has to guess which one enforces, and a gate that
# guesses is a gate that can be pointed at a decoy — which is precisely the bypass CodeRabbit found
# in the first version of this file.
check(
    "exactly one `ruff check` invocation exists across all workflows",
    len(invocations) == 1,
    "; ".join(f"{w}:{j}" for w, j, _job, _s, _r in invocations) or "none found",
)
if len(invocations) != 1:
    print(
        "\n  If a second ruff invocation is genuinely wanted, this gate must be taught WHICH one is\n"
        "  the enforcing lint — by step name, not by position. Do not relax the count and let it\n"
        "  pick the first."
    )
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)

wf, job_name, job, step, run = invocations[0]

# A step that cannot fail the build is not a gate, whatever it prints.
_neutered = [tok for tok in NON_ENFORCING if tok in run]
if job.get("continue-on-error") is True:
    _neutered.append("continue-on-error (job)")
if step.get("continue-on-error") is True:
    _neutered.append("continue-on-error (step)")
check("the ruff step can actually fail the build", not _neutered,
      f"{wf}: {', '.join(_neutered)}" if _neutered else run.strip())

m = re.search(r"cd\s+(\S+)\s*&&\s*python -m ruff check\s+(.+?)\s*$", run.strip(), re.S)
check(f"the ruff step in {wf} has the `cd <dir> && ruff check <paths>` shape this gate reads",
      m is not None,
      "" if m else f"got: {run.strip()[:160]} — if the step was restructured, teach this pattern "
                   "the new shape rather than deleting the gate")
if not m:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)

cwd = os.path.join(ROOT, m.group(1))
args = m.group(2).split()
check("the ruff step runs from the directory holding ruff.toml",
      os.path.isfile(os.path.join(cwd, "ruff.toml")),
      f"cd {m.group(1)} — ruff resolves the config AND its extend-exclude paths from here")

# ---------------------------------------------------------------- what that command would check
shown = subprocess.run(
    [sys.executable, "-m", "ruff", "check", *args, "--show-files"],
    cwd=cwd, capture_output=True, text=True, timeout=300,
)
check("ruff --show-files enumerated the command's file set", shown.returncode == 0,
      shown.stderr.strip()[:300])
checked = {os.path.relpath(p.strip(), ROOT).replace("\\", "/") for p in shown.stdout.splitlines() if p.strip()}

tracked_out = subprocess.run(
    ["git", "ls-files", "*.py"], cwd=ROOT, capture_output=True, text=True, timeout=120,
)
tracked = {p.strip().replace("\\", "/") for p in tracked_out.stdout.splitlines() if p.strip()}
check("git ls-files returned a Python tree", tracked_out.returncode == 0 and len(tracked) > 500,
      f"{len(tracked)} tracked .py")

# ---------------------------------------------------------------- the coverage claim itself
unchecked = sorted(tracked - checked)
unexplained = [p for p in unchecked if not p.startswith(VENDORED)]
check(
    "every tracked .py is linted, or is in a vendored tree named above",
    not unexplained,
    f"{len(checked)} checked · {len(unchecked)} vendored-excluded"
    if not unexplained else
    f"{len(unexplained)} file(s) linted by NOTHING: " + ", ".join(unexplained[:8])
    + (" ..." if len(unexplained) > 8 else ""),
)

# A vendor prefix that matches nothing is stale — the tree was renamed, moved or deleted, and the
# carve-out now silently forgives whatever moves under that name next.
_stale = [v for v in VENDORED if not any(p.startswith(v) for p in tracked)]
check("every declared vendored prefix still matches tracked files", not _stale, ", ".join(_stale))

# And the carve-out must stay a carve-out. If the excluded set ever outgrows the linted one, the
# "vendored" label has stopped describing what it names.
check("the vendored carve-out is a minority of the tree", len(unchecked) < len(checked) // 4,
      f"{len(unchecked)} excluded vs {len(checked)} checked")

if unexplained:
    print(
        "\n  A tracked Python file is outside ruff's reach. Do NOT fix this by adding it to\n"
        "  VENDORED — that list is for code copied verbatim from upstream, and using it as an\n"
        "  exemption list turns this gate into a record of what we gave up on. Widen the ruff\n"
        "  command in ci.yml instead, and fix what it then reports."
    )

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_ruff_scope OK")
