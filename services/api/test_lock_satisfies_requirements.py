"""The committed lock must satisfy the constraints `requirements.in` declares.

WHY THIS EXISTS
    `requirements.lock` is what CI installs (`pip install --require-hashes -r requirements.lock`,
    ci.yml) and what the production image installs (services/api/Dockerfile). `requirements.in` is
    only the *input* to pip-compile — nothing installs it, and therefore nothing was checking that
    the two agree.

    On 2026-08-01 they did not. Dependabot raised floors in `requirements.in`:

        fastapi>=0.140.7      (PR #132)      lock pinned  fastapi==0.139.0
        anthropic>=0.120.0    (PR #133)      lock pinned  anthropic==0.116.0

    Both PRs merged. Neither regenerated the lock. So the lock pinned versions **below its own
    stated minimum**, and every CI run and every container built from it installed the older
    packages — while `requirements.in` sat in the repo saying, truthfully but ineffectively, that
    they were too old. A floor nobody enforces is a comment.

WHY THE EXISTING WORKFLOW DID NOT CATCH IT
    `.github/workflows/lockfile.yml` DOES check this, properly, by recompiling in the prod image.
    But it triggers only on `workflow_dispatch` and on pushes touching `requirements.in`,
    `requirements.lock` or the workflow itself. A Dependabot PR touches `requirements.in`, so it
    ran and failed there — and the PR was merged anyway. Afterwards no ordinary push to main
    re-runs it, so main sat red on a workflow nobody was looking at. It surfaced only because it
    also fires on tag pushes, where three consecutive releases failed it.

    This test is the cheap, always-on half: it cannot recompile (no network, no prod interpreter)
    but it can compare what the lock PINS against what the input REQUIRES, in the normal suite,
    on every run. The workflow stays the authority on resolution; this stays the tripwire.

WHAT IS DELIBERATELY NOT ASSERTED
    That the lock is a *complete* or *minimal* resolution — that needs a real resolver. Only the
    direct constraints in `requirements.in` are checked, because those are the ones a human wrote
    on purpose and the ones Dependabot edits.

Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_lock_satisfies_requirements.py
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
IN_PATH = os.path.join(HERE, "requirements.in")
LOCK_PATH = os.path.join(HERE, "requirements.lock")

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


def _norm(name: str) -> str:
    """PEP 503 normalisation — `sentry-sdk`, `sentry_sdk` and `Sentry.SDK` are one project."""
    return re.sub(r"[-_.]+", "-", name).strip().lower()


def _version_key(v: str) -> tuple:
    """Compare release segments numerically. Pre/post/dev suffixes are dropped deliberately:
    a floor of `>=0.120.0` is about the release, and treating `0.120.0rc1` as satisfying it is a
    judgement this check does not need to make (no requirement here uses one)."""
    parts = re.split(r"[.]", re.split(r"[-+a-zA-Z]", v.strip(), maxsplit=1)[0])
    return tuple(int(p) for p in parts if p.isdigit())


for path in (IN_PATH, LOCK_PATH):
    if not os.path.exists(path):
        print(f"FAIL  missing {path}")
        sys.exit(1)

with open(IN_PATH, encoding="utf-8") as fh:
    in_lines = fh.read().splitlines()
with open(LOCK_PATH, encoding="utf-8") as fh:
    lock_text = fh.read()

# --- what the lock PINS -------------------------------------------------------------------------
# `name[extras]==version \` at the start of a line. Continuation lines (hashes, `# via`) never match.
#
# The `[extras]` group is NOT optional decoration to skip: pip-compile writes the extras into the
# lock too (`psycopg[binary]==3.3.4`, `uvicorn[standard]==0.51.0`, `sentry-sdk[fastapi]==2.66.1`).
# The first version of this pattern stopped at the bracket and reported all three as ABSENT FROM
# THE LOCK — three false alarms of the most alarming kind available, on packages that were pinned
# correctly all along. Parse both sides the same way or the comparison is between two different
# questions.
pinned = {_norm(m.group(1)): m.group(2)
          for m in re.finditer(r"(?m)^([A-Za-z0-9._-]+)(?:\[[^\]]*\])?==([^\s\\]+)", lock_text)}
check("the lock parses and pins a realistic number of packages", len(pinned) > 50,
      f"{len(pinned)} pinned")

# --- what requirements.in REQUIRES --------------------------------------------------------------
# Only direct `>=` floors, which is what Dependabot writes. Extras (`sentry-sdk[fastapi]`) and
# trailing comments are stripped. `-r`, `-c`, markers and unpinned names are skipped.
REQ = re.compile(r"^([A-Za-z0-9._-]+)\s*(?:\[[^\]]*\])?\s*>=\s*([0-9][^\s,;#]*)")
floors: list[tuple[str, str, int]] = []
for i, raw in enumerate(in_lines, 1):
    line = raw.strip()
    if not line or line.startswith(("#", "-")):
        continue
    m = REQ.match(line)
    if m:
        floors.append((_norm(m.group(1)), m.group(2), i))

check("requirements.in declares floors this test can check", len(floors) >= 5,
      f"{len(floors)} `>=` constraints found")

# --- every floor must be satisfied by the pin ---------------------------------------------------
violations = []
unpinned = []
for name, floor, lineno in floors:
    got = pinned.get(name)
    if got is None:
        # A required package absent from the lock would not install at all.
        unpinned.append(f"{name} (requirements.in:{lineno})")
        continue
    if _version_key(got) < _version_key(floor):
        violations.append(f"{name}: lock pins {got}, requirements.in:{lineno} requires >={floor}")

check("every package required by requirements.in is present in the lock",
      not unpinned, "; ".join(unpinned[:5]))

check("the lock satisfies every floor requirements.in declares",
      not violations,
      "\n        " + "\n        ".join(violations)
      + "\n        -> regenerate: run the 'Lockfile (pip-compile)' workflow, download the"
        " 'requirements-lock' artifact, and commit it." if violations else
      f"{len(floors)} floors checked against {len(pinned)} pins")

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print(f"test_lock_satisfies_requirements OK - {len(floors)} declared floors all satisfied by the "
      f"{len(pinned)} pins the container actually installs")
