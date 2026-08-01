"""The test manifest is itself a hand-maintained list, so it gets a test.

`run_tests.py` holds `TESTS`, a hand-written registry of every suite. Nothing derived it from disk
and nothing checked it, which is the same shape as the G-8 RBAC prefix list that let four
authorisation holes through: a list a human must remember to update, with no check that they did.

The manifest can drift three ways, and the runner used to notice only the third:

  1. a name registered twice      -> the suite runs twice, burning wall time in a ~22 min gate
  2. a name with no file on disk  -> the runner's `.exists()` filter dropped it WITHOUT A WORD
  3. a file with no registration  -> a test nobody runs

This test asserts the live manifest is clean, and then — more importantly — feeds
`manifest_problems()` a synthetic violation of each rule to prove the detector can actually go red.
A gate asserted only against the passing case is indistinguishable from `return []`.

Pure list/set comparison: no DB, no TestClient, no env.
"""
import sys

import run_tests

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


# ---------------------------------------------------------------- the live manifest is sound
problems = run_tests.manifest_problems()
check("the live TESTS manifest has no problems", not problems, "; ".join(problems))

check("the manifest is not vacuously small", len(run_tests.TESTS) > 400,
      f"{len(run_tests.TESTS)} suites registered")

# ---------------------------------------------------- each rule fires on a synthetic violation
# Without these, every assertion above would still pass if manifest_problems() were `return []`.
DISK = {"test_a", "test_b"}

check("rule 1 fires on a duplicate registration",
      any("more than once" in p and "test_a" in p
          for p in run_tests.manifest_problems(["test_a", "test_a", "test_b"], DISK)),
      "duplicate must be reported AND named")

check("rule 2 fires on a registered entry with no file",
      any("no such file on disk" in p and "test_ghost" in p
          for p in run_tests.manifest_problems(["test_a", "test_b", "test_ghost"], DISK)),
      "the silently-dropped case — this is the one the old runner could not see")

check("rule 3 fires on an unregistered file on disk",
      any("not registered in TESTS" in p and "test_b" in p
          for p in run_tests.manifest_problems(["test_a"], DISK)),
      "unregistered file must be reported AND named")

check("a sound manifest reports nothing",
      run_tests.manifest_problems(["test_a", "test_b"], DISK) == [],
      "no false positives on a clean 1:1 map")

# All three at once: a real drifted manifest usually breaks more than one rule, and reporting only
# the first would send somebody round the loop three times on a 22-minute gate.
combined = run_tests.manifest_problems(["test_a", "test_a", "test_ghost"], DISK)
check("all three problems are reported together, not one at a time", len(combined) == 3,
      f"{len(combined)} problem(s): {' | '.join(combined)}")

print()
if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_manifest OK")
