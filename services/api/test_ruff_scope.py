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
    not carry its own copy of the ruff arguments: it PARSES `.github/workflows/ci.yml`, extracts the
    `ruff check` line, and measures THAT. Narrow the CI command and this test goes red; edit this
    test's idea of the command and it no longer matches CI, which it also checks. The two have to
    agree because only one of them exists.

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

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
CI = os.path.join(ROOT, ".github", "workflows", "ci.yml")

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
with open(CI, encoding="utf-8") as fh:
    ci_text = fh.read()

# `run: cd services/api && python -m ruff check <paths>` — captured from the workflow, not retyped.
m = re.search(r"^\s*run:\s*cd\s+(\S+)\s*&&\s*python -m ruff check\s+(.+)$", ci_text, re.M)
check("ci.yml still has a `cd <dir> && ruff check` step this gate can read", m is not None,
      "" if m else "no `run: cd ... && python -m ruff check ...` line found — if the step was "
                   "restructured, update the pattern here rather than deleting the gate")
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
