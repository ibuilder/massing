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

**Which layer protects you.** The anchored regex alone already excludes the `aec.db` mentioned in
`test_stepup_race.py`'s comment — verified with comments left intact. Stripping comments is defence
in depth, not the mechanism, and it only removes WHOLE-LINE comments: a trailing `# ...` would
survive it. So if someone ever loosens the regex, the strip will not save them. Worth knowing
before editing either.

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
    # --- the assertion that would have caught the blocking defect in review -----------------------
    #
    # Everything above exercises `_sweep_leftovers`, which is safe BY CONSTRUCTION: a diff cannot name
    # a file that predates the run. `_sweep_owned` is the other half and has a DIFFERENT property — it
    # deletes BY NAME, so it is only ever as safe as the name. The guard covered the safer half and
    # called the job done, which is this repo's recurring defect wearing my own initials.
    #
    # What it missed: `_owned_dbs` matched the DSN anywhere in a test's source, including a COMMENT in
    # `test_stepup_race.py` warning that `sqlite:///./aec.db` is the developer's dev database. The
    # first green run of that test would have unlinked it — 5 MB, read out of the sentence warning
    # about it. Found by Subagent 3 in review, not by this file.
    #
    # So: over EVERY registered test, the owned set must be disjoint from what exists before a run.
    # One assertion, whole population, and it fails on a prose mention rather than on a name anyone
    # thought to list.
    # The same property against a DETERMINISTIC population first, because the live-files version
    # below is vacuous in a clean tree — it passed here reporting "0 live files", which proves
    # nothing at all. PROTECTED is nine fixed names, so this one cannot be satisfied by an empty
    # directory, and it is the check that actually holds in CI.
    named = []
    for t, home in [(x, rt.HERE) for x in rt.TESTS] + [(x, rt.DATA_DIR) for x in rt.DATA_TESTS]:
        for q in rt._owned_dbs(t, home):
            if q.name in PROTECTED:
                named.append(f"{t} -> {q.name}")
    check("no test's owned set NAMES a protected database", not named,
          "; ".join(sorted(named)[:5]) if named
          else f"{len(rt.TESTS) + len(rt.DATA_TESTS)} tests vs {len(PROTECTED)} protected names")

    # A live-files version of the same question USED to sit here — snapshot `*.db*` in `services/api`
    # and flag any test whose owned set intersects it. CI failed on it:
    #
    #     FAIL  no test CLAIMS a database that already exists
    #           test_jobs -> _test_jobs.db; test_worker_split -> _test_worker_split.db
    #
    # Neither is a defect. This suite runs INSIDE the pool it is inspecting, so `_test_jobs.db` exists
    # for the entirely correct reason that `test_jobs` is running at that moment. The check cannot be
    # made reliable in a directory where 543 tests execute concurrently — its answer depends on
    # scheduling.
    #
    # It is deleted rather than fixed, because the deterministic check above already covers the hazard
    # it was reaching for, and this one only ever added flakiness. Two things worth keeping:
    #
    #  - It was VACUOUS locally (a clean tree, "0 live files") and WRONG in CI. Both readings were
    #    useless and they failed in opposite directions, which is why a green local run said nothing.
    #  - The comment directly above already said the deterministic version "is the check that actually
    #    holds in CI" — the reasoning was written down and the racy check was shipped underneath it
    #    anyway. Knowing the rule is not the same as applying it.

    # --- the invariant that makes per-test sweeping concurrency-safe -----------------------------
    #
    # `_sweep_owned` deletes a test's databases the moment that test finishes, while 500+ others are
    # still running. That is safe ONLY because no two tests claim the same database name. Nothing
    # asserted it, and it is exactly the kind of property a copy-pasted new test breaks — which is
    # how tests arrive.
    #
    # The failure it would cause is this item's own signature, reintroduced by its own fix: the first
    # test to finish sweeps a database the second is still writing to, and the symptom is a failure
    # in an unrelated file that passes on re-run.
    #
    # Reads sources, not the filesystem, so it cannot pass vacuously against an empty directory.
    claims: dict[str, list[str]] = {}
    for t, home in [(x, rt.HERE) for x in rt.TESTS] + [(x, rt.DATA_DIR) for x in rt.DATA_TESTS]:
        for q in rt._owned_dbs(t, home):
            if q.name.endswith(".db"):
                claims.setdefault(q.name, []).append(t)
    shared = {n: ts for n, ts in claims.items() if len(ts) > 1}
    check("no database name is claimed by more than one test", not shared,
          "; ".join(f"{n} <- {', '.join(ts)}" for n, ts in sorted(shared.items())[:3]) if shared
          else f"{len(claims)} distinct names across {len(rt.TESTS) + len(rt.DATA_TESTS)} tests, none shared")

    # and the belt, asserted directly: even a bad name cannot delete a pre-existing file
    keeper = tmp / "aec.db"
    keeper.write_text("the developer's dev database")
    rt._sweep_owned("test_alpha", tmp, frozenset({keeper.resolve()}))
    check("a pre-run file survives _sweep_owned even when the population names it",
          keeper.exists(), "the `before` guard is what makes a bad name inert")

finally:
    shutil.rmtree(tmp, ignore_errors=True)


# =================================================================================================
# THE STORAGE HALF -- added after 93 directories and 1.42 GB survived seven runs and filled the disk
# mid-suite, producing `database or disk is full` scattered across 71 unrelated suites.
#
# The database half above is a snapshot diff, which is safe because a diff cannot name a file that
# existed beforehand. That design DOES NOT TRANSFER, and assuming it did is what left this gap open:
# `_run_one` clears `_storage_{t}` at test START, so last run's directory is already in the pre-run
# snapshot, the diff comes back empty, and nothing is ever swept. The storage half therefore sweeps
# by DERIVED NAME instead -- and the assertions below are about why that derivation must never be
# relaxed into a glob.
# =================================================================================================

# 1. Derived, and exactly one name per test.
check("_owned_dirs derives the runner's own STORAGE_DIR name",
      {d.name for d in rt._owned_dirs("test_alpha", rt.HERE)} == {"_storage_test_alpha"},
      str(sorted(d.name for d in rt._owned_dirs("test_alpha", rt.HERE))))

# 2. THE ONE THAT MATTERS. The tempting simplification is `glob("test_storage_*")` +
#    `glob("test_ifc_*")`. Those patterns match TRACKED SOURCE FILES in this very directory. This is
#    not hypothetical: running that glob during the incident returned three tracked .py files, and a
#    previous session did delete a tracked file exactly this way.
_glob_hits = sorted(q.name for pat in ("test_storage_*", "test_ifc_*") for q in rt.HERE.glob(pat))
_tracked_hits = [n for n in _glob_hits if n.endswith(".py")]
check("the naive glob DOES hit tracked source -- which is why the sweep derives instead",
      len(_tracked_hits) >= 3, ", ".join(_tracked_hits) or "no .py matched (assertion is now vacuous)")
check("...and nothing _owned_dirs proposes is a tracked path",
      not any((rt.HERE / d.name).is_file() for t in rt.TESTS for d in rt._owned_dirs(t, rt.HERE)),
      "every proposed name is a directory or absent")

# 3. Failed tests keep their storage; passed tests do not. Same rule as the database half: the
#    directory is the evidence for the failure.
_tmp2 = Path(tempfile.mkdtemp(prefix="sweepdirs_"))
try:
    _real_home, _real_data = rt.HERE, rt.DATA_DIR
    rt.HERE = rt.DATA_DIR = _tmp2
    (_tmp2 / "_storage_test_pass").mkdir()
    (_tmp2 / "_storage_test_fail").mkdir()
    removed, kept = rt._sweep_owned_dirs([("test_pass", True, 0.1), ("test_fail", False, 0.1)])
    check("a PASSED test's storage dir is swept", not (_tmp2 / "_storage_test_pass").exists(),
          f"removed={removed}")
    check("a FAILED test's storage dir is KEPT as evidence",
          (_tmp2 / "_storage_test_fail").exists(), f"kept={kept}")

    # 4. The reporter counts directories only -- a file can never be counted, so it can never be
    #    proposed for deletion by a future change that starts deleting what it reports.
    (_tmp2 / "test_storage_decoy.py").write_text("# a tracked-source lookalike")
    (_tmp2 / "test_storage_real").mkdir()
    n, _mb = rt._unowned_residue()
    check("_unowned_residue counts directories and ignores files that match the same pattern",
          n >= 1 and (_tmp2 / "test_storage_decoy.py").exists(),
          f"{n} dir(s) counted; the .py lookalike still exists")
finally:
    rt.HERE, rt.DATA_DIR = _real_home, _real_data
    shutil.rmtree(_tmp2, ignore_errors=True)

# 4b. THE SYMMETRY THAT WAS MISSING. `_run_one` swept the per-test DATABASE as each test finished
#     -- "removing each as it finishes keeps the peak at roughly one test's worth" -- and simply did
#     not do the same for the per-test STORAGE dir. That asymmetry is the whole bug: the storage was
#     cleared only at the START of the next run of the same test, so it accumulated across the run
#     and then across runs. Asserted structurally because `_run_one` spawns a subprocess and cannot
#     be driven in-process; what matters is that both sweeps sit under the SAME guard.
_src = (Path(__file__).resolve().parent / "run_tests.py").read_text(encoding="utf-8")
_body = _src[_src.index("def _run_one("):_src.index("def _owned_dbs(")]
_guard = 'if ok and os.environ.get("KEEP_TEST_DB") != "1":'
check("_run_one guards its per-test cleanup on pass + KEEP_TEST_DB", _guard in _body)
_after = _body[_body.index(_guard):] if _guard in _body else ""
check("...and sweeps the per-test DATABASE there", "_sweep_owned(t, cwd, before)" in _after)
check("...and the per-test STORAGE dir there too -- the half that was missing",
      '_storage_{t}' in _after and "rmtree" in _after,
      "both halves now sit under one guard, so a failed test keeps both")

# 5. The disk-full signatures match what SQLAlchemy and the OS actually emit.
_real_msg = ("sqlalchemy.exc.OperationalError: (sqlite3.OperationalError) "
             "database or disk is full")
check("the disk-full scan recognises the real SQLAlchemy message",
      any(s in _real_msg.lower() for s in rt._DISK_FULL), _real_msg[:60])
check("...and does not fire on an ordinary assertion failure",
      not any(s in "AssertionError: expected 3, got 4".lower() for s in rt._DISK_FULL))

print(("FAILED: " + "; ".join(FAILED)) if FAILED else "test_sweep_guard OK")
sys.exit(1 if FAILED else 0)
