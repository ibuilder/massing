"""R41-TEST-RESIDUE — the residue sweep must never propose a database it does not own.

`run_tests.py` removes the SQLite files a run creates, because leaving them behind reached 2.8 GB
across worktrees and manufactured `disk I/O error` plus timeouts that read as flaky tests in files
with nothing to do with it.

**Why this file exists rather than a comment saying the sweep is safe by construction.** It *is* safe
by construction — a snapshot diff can only remove files that appeared during the run, so a database
that existed beforehand is unreachable. But "it cannot by construction" is exactly the kind of claim
that stops being true after a refactor, silently, and the refactor that breaks it will look like a
simplification. Someone will read the diff and think `glob("test_*.db")` is tidier. The whole point of
this repo's gates is that a property nobody checks is a property that drifts, so the construction is
asserted rather than trusted.

**What is actually at stake.** `preview.db` is the database `.claude/launch.json` configures for the
dev API server. A sweep one character too greedy deletes a running dev server's state mid-session,
and the person it happens to will not connect it to a test-cleanup change. The other names here are
developer and probe databases that live in the same directory.

The list is a floor, not an inventory: the assertion is that the sweep proposes **nothing it did not
observe appear**, so an unlisted database is protected by the same property. Naming these makes the
regression legible when it happens.
"""
import shutil
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import run_tests as rt  # noqa: E402

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


#: Databases that live in `services/api` and are NOT test residue. `preview.db` is the dev API's,
#: from `.claude/launch.json`; the rest are developer/probe databases.
PROTECTED = ("aec.db", "aec_dev.db", "dev_modeling.db", "dev_resp.db", "dev_ui.db",
             "preview.db", "preview_smoke.db", "probe2.db", "probe_reserve.db")

# A temp directory, not `services/api`: this test runs concurrently with 500+ others in that very
# folder, so touching real filenames there would race the suite it is testing.
tmp = Path(tempfile.mkdtemp(prefix="_sweepguard_"))
dirs = (tmp,)

try:
    # every protected database exists BEFORE the run, which is the situation that matters
    for name in PROTECTED:
        (tmp / name).write_text("not test residue")
    before = rt._db_snapshot(dirs)
    check("the snapshot sees the pre-existing databases",
          len(before) == len(PROTECTED), f"{len(before)} of {len(PROTECTED)}")

    # ... then a run happens and creates its own
    for name in ("test_alpha.db", "auth_test.db", "_test_beta.db"):
        (tmp / name).write_text("run residue")

    removed, leftover = rt._sweep_leftovers(before, set(), dirs)
    check("the sweep removes what the run created", removed == 3 and leftover == 0,
          f"removed={removed} leftover={leftover}")

    survivors = {q.name for q in tmp.glob("*.db")}
    missing = [n for n in PROTECTED if n not in survivors]
    check("NO protected database was touched", not missing,
          "deleted: " + ", ".join(missing) if missing else f"all {len(PROTECTED)} intact")

    # the property stated positively: the sweep's candidate set is exactly "appeared during the run"
    (tmp / "arrived_later.db").write_text("created after the snapshot, by something else")
    before2 = rt._db_snapshot(dirs)
    (tmp / "test_gamma.db").write_text("run residue")
    rt._sweep_leftovers(before2, set(), dirs)
    check("a database created before the NEXT run is protected by that run's snapshot",
          (tmp / "arrived_later.db").exists(),
          "a file is protected from the moment it is observed, not by its name")

    # a failing test's database is evidence — the sweep must be able to spare it
    before3 = rt._db_snapshot(dirs)
    (tmp / "test_failed.db").write_text("evidence for a red suite")
    keep = {(tmp / "test_failed.db").resolve()}
    removed3, _ = rt._sweep_leftovers(before3, keep, dirs)
    check("a kept database survives even though the run created it",
          (tmp / "test_failed.db").exists() and removed3 == 0,
          "sweeping a failure's database destroys the thing needed to debug it")

    # and the guard that makes `keep` real: unresolved paths compare unequal and silently protect
    # nothing. This is the defect found while building the sweep, pinned so it cannot return.
    check("keep is compared as RESOLVED paths",
          rt._db_snapshot(dirs) == {q.resolve() for q in rt._db_snapshot(dirs)},
          "Path('./x.db') != Path('/abs/x.db') — an unresolved keep set protects nothing")
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print(("FAILED: " + "; ".join(FAILED)) if FAILED else "test_sweep_guard OK")
sys.exit(1 if FAILED else 0)
