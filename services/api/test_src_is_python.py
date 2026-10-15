"""Do the Python service source roots contain only Python?

**Written because I put a TypeScript file in one.** A `cd ../apps/web` failed inside a shell chain
whose next command was separated by `;` rather than `&&`, so the `cp` that followed restored a web
module into `services/api/src/` and it was committed. The litter was an exact duplicate of
`apps/web/src/fieldLogReadings.ts`, 86 lines, inside the FastAPI package.

NOTHING IN THE TREE NOTICED, and the reasons are each individually sound:

- `ruff` lints `.py`; a `.ts` file is not its subject.
- `test_ruff_scope.py` asserts the lint REACHES every tracked `.py`. That is the dual question and
  it cannot see a file that is not Python.
- `test_file_sizes.py` has a global ceiling on hand-written source; an 86-line file passes it.
- `test_declared_imports.py` reads Python `import` statements; there were none to read.

*Four checks over this directory, none of them asking what is IN it.* The population of every one
is "the Python files", so a non-Python file is outside all four by construction — the same shape as
a predicate that decides what to LOOK at, which this repo has paid for repeatedly.

WHY IT ASKS GIT RATHER THAN THE DISK. `__pycache__`, `.venv*/` and build residue live under these
roots in any working tree, and a disk walk would have to reimplement `.gitignore` to see past them —
which `test_scratch_ignored.py` records getting wrong twice, in both directions. What rots is what
is COMMITTED, so the committed set is the subject.

The allowlist is six exact paths, every one asserted to still exist: a provenance or marker file
whose reason has gone is an exemption nobody re-checked.
"""
import os
import subprocess

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

#: The Python services' source roots. `services/converter` is deliberately absent — it is a Node
#: service with zero tracked `.py`, so this rule would be a claim about the wrong language.
ROOTS = ["services/api/src", "services/data/src"]

#: Non-Python files these roots may hold, by exact path, with the reason each is here. Measured at
#: six on 2026-10-15. A seventh is a decision, not a drift: add it with its reason.
ALLOWED = {
    "services/api/src/massingcapture/VENDOR.md":
        "provenance for the vendored massingcapture copy, re-synced by overwrite",
    "services/api/src/massingplan/VENDOR.md":
        "provenance for the vendored massingplan copy",
    "services/api/src/massingplan/py.typed":
        "PEP 561 marker — its absence makes the package's annotations invisible to consumers",
    "services/data/src/VENDOR-massingifc-python.md":
        "provenance for the vendored massingifc python bindings",
    "services/data/src/massingviser_geometry/LICENSE":
        "the vendored geometry kernel's licence, which may not be removed",
    "services/data/src/massingviser_geometry/VENDOR.md":
        "provenance for that same vendored copy",
}


def tracked(paths: list[str]) -> list[str]:
    """Every file git tracks under `paths`, as repo-relative POSIX paths."""
    out = subprocess.run(["git", "ls-files", *paths], cwd=ROOT, capture_output=True, text=True)
    if out.returncode != 0:
        return []
    return [p for p in out.stdout.splitlines() if p.strip()]


def offenders(files: list[str], allowed: dict[str, str]) -> list[str]:
    """The verdict, SEPARATE from the walk so a mutation can be aimed at it directly.

    `test_unique_read_guard.py` records why: asserting that an analyser REPORTED a site is not
    asserting how it CLASSIFIED it, and its own first draft passed a mutation that routed every
    site to "safe". The walk and the ruling are two functions here for that reason.
    """
    return sorted(f for f in files if not f.endswith(".py") and f not in allowed)


def main() -> int:
    files = tracked(ROOTS)

    # VACUITY, both halves. An empty file list reports zero offenders and looks like a clean tree;
    # an allowlist that matched everything would do the same. Neither is a measurement.
    check("the walk found the Python service sources", len(files) > 400, f"{len(files)} tracked files")
    check("the roots are mostly Python", sum(1 for f in files if f.endswith(".py")) > 400)

    # THE RULING IS EXERCISED ON A SYNTHETIC OFFENDER before it may report a clean tree — the file
    # that prompted this gate, at the path it actually landed on.
    probe = "services/api/src/fieldLogReadings.ts"
    check("the ruling catches a non-Python file in the API package",
          offenders([*files, probe], ALLOWED) == [probe])
    # ...and does NOT catch an allowlisted one, which is the other half of the same question.
    check("an allowlisted file is not an offender",
          offenders(["services/api/src/massingplan/py.typed"], ALLOWED) == [])

    bad = offenders(files, ALLOWED)
    check("the Python service roots contain only Python, plus the named exemptions", not bad,
          "; ".join(bad) if bad else f"{len(ALLOWED)} exemptions")

    # An exemption whose file is gone is an exemption nobody re-checked.
    present = set(files)
    for path, why in sorted(ALLOWED.items()):
        check(f"exemption still exists: {path}", path in present, why)

    print(("FAIL  " + str(len(FAILED)) + " check(s) failed: " + "; ".join(FAILED))
          if FAILED else "SRC-IS-PYTHON OK - "
          f"{len(files)} tracked files under {', '.join(ROOTS)}, "
          f"{len(ALLOWED)} named non-Python exemptions, 0 strays")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
