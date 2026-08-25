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

IT HAPPENED AGAIN ON 2026-08-07, THROUGH THE HALF THIS SCOPE PARAGRAPH LEFT OUT
    The paragraph below used to end "only the direct constraints in `requirements.in` are checked".
    That was a deliberate, reasonable scope — and it was **not the whole population**.
    `services/data/requirements.txt` declares floors too, and the API image runs that code: the
    Dockerfile copies `services/data/src` in and puts it on `PYTHONPATH`, and 59 files under
    `services/api/src` import `aec_data`. But pip installs only `services/api/requirements.lock`.

    So when Dependabot raised `trimesh>=4.12.2` to `>=5.0.0` there (#229), this test **passed** —
    `requirements.in` still said `trimesh>=4.0`, which the pinned 4.12.2 satisfies. The image kept
    shipping 4.12.2 while a manifest in the repo said 5.0.0 was required. Same failure as
    2026-08-01, one file to the left, four days later, past a gate written for exactly it.

    **A gate's population is part of its claim, and a second input file inherits none of the
    protection the first one has.** `SOURCES` below is now the population, and a missing entry fails
    loudly rather than shrinking the checked set in silence.

WHAT IS DELIBERATELY NOT ASSERTED
    That the lock is a *complete* or *minimal* resolution — that needs a real resolver. Only the
    direct constraints in the files listed in `SOURCES` are checked, because those are the ones a
    human wrote on purpose and the ones Dependabot edits.

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


#: Pre-release ranks, lowest first. A release with NO pre-release segment sorts ABOVE all of them,
#: which is why the sentinel is larger than every entry: 0.65b0 < 0.65rc1 < 0.65.
_PRE_RANK = {"dev": 0, "a": 1, "alpha": 1, "b": 2, "beta": 2, "rc": 3, "c": 3}
_NO_PRE = (9, 0)

_VER = re.compile(r"^(\d+(?:\.\d+)*)(?:[._-]?(dev|a|alpha|b|beta|rc|c)[._-]?(\d+)?)?", re.I)


def _version_key(v: str) -> tuple:
    """Order two versions, pre-releases included.

    The first version of this dropped every suffix and justified it in a comment: *"no requirement
    here uses one"*. That was **false when it was written** — `requirements.in` carries
    `opentelemetry-instrumentation-fastapi>=0.48b0` and `...-sqlalchemy>=0.65b0`, and with the
    suffix discarded both floors collapsed to `(0, 48)` and `(0, 65)`. A bump to `>=0.65b1` against
    a `0.65b0` pin would then have compared equal and passed — precisely the drift this file exists
    to catch, in the only four requirements that could exhibit it.

    Comparing a claim against the file it describes costs one grep. Asserting it in a comment costs
    nothing and proves nothing.
    """
    m = _VER.match(v.strip())
    if not m:
        return ((0,), _NO_PRE)
    release = tuple(int(p) for p in m.group(1).split("."))
    if not m.group(2):
        return (release, _NO_PRE)
    return (release, (_PRE_RANK.get(m.group(2).lower(), 0), int(m.group(3) or 0)))


for path in (IN_PATH, LOCK_PATH):
    if not os.path.exists(path):
        print(f"FAIL  missing {path}")
        sys.exit(1)

#: Every file whose floors the API lock must satisfy, tagged with the name used in failure messages.
#:
#: **`services/data/requirements.txt` is here because the API image RUNS that code.** The Dockerfile
#: copies `services/data/src` into the image and puts it on `PYTHONPATH`, and 59 files under
#: `services/api/src` import `aec_data` — but the only thing pip installs is
#: `services/api/requirements.lock`. So a floor raised in the data service's requirements is a
#: promise the container never keeps.
#:
#: That is not hypothetical. Dependabot raised `trimesh>=4.12.2` to `>=5.0.0` there on 2026-08-07
#: (#229) and this test **passed**, because its population was `requirements.in` alone and
#: `requirements.in` still said `trimesh>=4.0`, which the pinned 4.12.2 satisfies. The image kept
#: shipping 4.12.2 while the manifest said 5.0.0 was required — *truthfully and ineffectively*, which
#: is the sentence this file's own docstring already uses about the 2026-08-01 incident.
#:
#: **The gate was correct and its claim was narrower than it read.** The 2026-08-01 lesson was
#: "compare what the lock pins against what the input requires"; what went unstated was *which*
#: inputs. A second requirements file appeared later and inherited none of the protection.
SOURCES = [
    (IN_PATH, "requirements.in"),
    (os.path.join(HERE, "..", "data", "requirements.txt"), "services/data/requirements.txt"),
]

in_lines: list[tuple[str, str]] = []          # (line, source-label) so a failure names its file
for _path, _label in SOURCES:
    if not os.path.exists(_path):
        # Loud rather than skipped: a renamed or moved requirements file must not silently shrink
        # this test's population back to where it was when #229 slipped through. Verified by
        # mutation — pointing this at a missing file drops the floors from 48 to 35 and FAILS,
        # rather than passing on the smaller set.
        print(f"FAIL  requirements source missing: {_label} ({_path})")
        FAILED.append("requirements source missing")
        continue
    with open(_path, encoding="utf-8") as fh:
        in_lines += [(ln, _label) for ln in fh.read().splitlines()]
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
# Extras (`sentry-sdk[fastapi]`) and trailing comments are stripped. `-r`, `-c` and blanks skipped.
#
# EVERY requirement line must be accounted for — matched as a floor, or matched as a form this
# check deliberately cannot evaluate. A bare `len(floors) >= 5` could not tell "33 of 33 checked"
# from "5 of 33 checked, 28 silently dropped", so a requirement that changed operator (`>=` to
# `~=`) would leave the checked set without a word. The reconciliation below is the mutation check
# on the parser itself.
REQ = re.compile(r"^([A-Za-z0-9._-]+)\s*(?:\[[^\]]*\])?\s*(>=|==|~=|>)\s*([0-9][^\s,;#]*)")
NAME_ONLY = re.compile(r"^([A-Za-z0-9._-]+)\s*(?:\[[^\]]*\])?\s*(?:[;#].*)?$")

floors: list[tuple[str, str, str]] = []   # (name, floor, "<file>:<line>")
unversioned: list[str] = []
unparsed: list[str] = []
requirement_lines = 0
_line_no: dict[str, int] = {}                 # per-source numbering, so citations stay honest
for raw, _src in in_lines:
    _line_no[_src] = _line_no.get(_src, 0) + 1
    i = f"{_src}:{_line_no[_src]}"
    line = raw.split("#")[0].strip()
    if not line or line.startswith("-"):
        continue
    requirement_lines += 1
    m = REQ.match(line)
    if m:
        # `>=`, `==` and `~=` all state a minimum the lock must meet. `>` is treated as a floor too:
        # a pin equal to it would be a violation, but that stricter reading is not asserted here
        # because nothing in the file uses `>`, and inventing the rule now would be untested.
        floors.append((_norm(m.group(1)), m.group(3), i))
    elif NAME_ONLY.match(line):
        unversioned.append(f"{line} ({i})")     # legitimately unconstrained — nothing to check
    else:
        unparsed.append(f"{line} ({i})")

check("every requirement line is either checked or explicitly accounted for",
      not unparsed,
      "unparsed: " + "; ".join(unparsed[:5]) if unparsed else
      f"{requirement_lines} requirement lines = {len(floors)} with a version floor "
      f"+ {len(unversioned)} deliberately unconstrained")

check("the requirements sources declare floors this test can check", len(floors) >= 5,
      f"{len(floors)} version constraints found")

# --- every floor must be satisfied by the pin ---------------------------------------------------
violations = []
unpinned = []
for name, floor, lineno in floors:
    got = pinned.get(name)
    if got is None:
        # A required package absent from the lock would not install at all.
        unpinned.append(f"{name} ({lineno})")
        continue
    if _version_key(got) < _version_key(floor):
        violations.append(f"{name}: lock pins {got}, {lineno} requires >={floor}")

check("every package the requirements sources require is present in the lock",
      not unpinned, "; ".join(unpinned[:5]))

check("the lock satisfies every floor the requirements sources declare",
      not violations,
      "\n        " + "\n        ".join(violations)
      + "\n        -> regenerate: run the 'Lockfile (pip-compile)' workflow, download the"
        " 'requirements-lock' artifact, and commit it." if violations else
      f"{len(floors)} floors checked against {len(pinned)} pins")

# --- and the two sources must not disagree with EACH OTHER ---------------------------------------
# The check above is one-directional by construction: it asks whether the pin is at least the floor.
# A floor that is too LOW satisfies it for free — every pin is >= a floor of 0 — so a stale floor is
# invisible to it, and 5 of the 12 packages BOTH files declare had drifted apart by 2026-08-25:
#
#     defusedxml     requirements.in >=0.7.1     services/data >=0.7       (lock 0.7.1)
#     ifcopenshell   requirements.in >=0.8.0     services/data >=0.8.5     (lock 0.8.5)
#     manifold3d     requirements.in >=3.5.2     services/data >=2.0       (lock 3.5.2)
#     rdflib         requirements.in >=7.1       services/data >=7.6.0     (lock 7.6.0)
#     reportlab      requirements.in >=5.0.0     services/data >=4.0       (lock 5.0.0)
#
# **They disagree in BOTH directions**, which is what makes this drift rather than a decision:
# nobody deliberately requires ifcopenshell 0.8.0 in one file and 0.8.5 in the file next to it.
# Two of the five carry a stated security reason in the very file that then declares the weaker
# floor — `defusedxml` is commented "XXE / billion-laughs hardening" in one and "XXE-safe parser for
# untrusted P6 (PMXML) schedule uploads" in the other, and only one of those two lines actually
# delivers 0.7.1.
#
# Nothing shipped wrong: the lock pins at or above the higher floor in all five cases, and the lock
# is the only thing installed. That is exactly why it survived — **the runtime was right, so the
# declaration could be wrong indefinitely**. It becomes real the moment the lock is recompiled,
# because pip resolves against these files: with `defusedxml>=0.7` still written down, a fresh
# resolution is free to pick 0.7, and every check in this file stays green while the XXE floor the
# comment promises quietly disappears.
#
# It also explains six Dependabot pull requests that were closed rather than merged (#37, #38, #40,
# #89, #90, #92). Each raised a floor in `services/data/requirements.txt`; each was correct that the
# lock already carried the version; and closing them left the *declaration* behind. **"Already
# covered by the lock" is a true answer to the wrong question** — the floor is not a report of what
# is installed, it is the constraint the next resolution is bound by.
#
# The assertion is deliberately narrow: it does not require a floor to equal the pin (a floor
# legitimately sits below a resolved version), only that **two files declaring the same package
# declare the same thing**. That has one unambiguous right answer and needs no resolver.
by_pkg: dict[str, dict[str, list[str]]] = {}
for name, floor, lineno in floors:
    by_pkg.setdefault(name, {}).setdefault(floor, []).append(lineno)
multi = {n: v for n, v in by_pkg.items()
         if len({c.split(":")[0] for cs in v.values() for c in cs}) > 1}

# Anti-vacuity: if the two files ever stop sharing packages — a rename, a split, a source dropped
# from SOURCES — this check would pass over an empty set and report agreement it never tested.
check("the two requirements sources share packages to compare", len(multi) >= 8,
      f"{len(multi)} packages declared in more than one source")

disagree = sorted(n for n, v in multi.items() if len(v) > 1)
check("no package is declared with two different floors",
      not disagree,
      "\n        " + "\n        ".join(
          f"{n}: " + ", ".join(f"{c} says >={f}" for f, cs in sorted(by_pkg[n].items()) for c in cs)
          for n in disagree)
      + "\n        -> raise the lower one to match; the lock already pins at or above the higher."
      if disagree else f"all {len(multi)} shared packages agree")

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print(f"test_lock_satisfies_requirements OK - {len(floors)} declared floors all satisfied by the "
      f"{len(pinned)} pins the container actually installs, and the {len(multi)} packages both "
      "requirements sources declare agree with each other")
