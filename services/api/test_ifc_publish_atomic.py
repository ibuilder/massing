"""A reader must never observe the published `source.ifc` mid-write.

## The defect this pins

PR #557's first pass locked the `source_ifc` POINTER and left the BYTES outside the lock. Every
producer — upload, RVT import, blank create, massing generate — wrote the published path directly:

  * `import_rvt` called `ifc_path.write_bytes(ifc)` on `.../source.ifc`;
  * the generators wrote `str(ifc_path)` for the same fixed name;
  * `upload_source_ifc` went through `storage.stream_to_path`, which DOES write `<dest>.part` and
    rename — but the part name is derived from the DESTINATION, so two concurrent uploads to one
    project share `source.ifc.part` and interleave into it before either renames.

`bake_layers` takes the project lock and then opens `p.source_ifc`. With the bytes produced outside
that lock, it could open a file being rewritten underneath it. *A lock proves something about the
interval it spans, and the interval has to contain the bytes as well as the pointer* — the same
correction PR #552 forced on `under_pid_lock`, one layer down.

## Why this test and `test_lock_boundary` are both needed

`test_lock_boundary` is an AST analyser: it can see that every `p.source_ifc = ...` sits inside
`pid_lock.mutating`, and it says nothing whatever about which path the bytes were written to. The
whole defect above passes it. Only behaviour can see the difference between publishing a file and
publishing it atomically.

Run: cd services/api && PYTHONPATH="src:../data/src" .venv/bin/python test_ifc_publish_atomic.py
"""
from __future__ import annotations

import os
import sys
import threading
import time

os.environ["DATABASE_URL"] = "sqlite:///./_ifcatomic_test.db"
os.environ.setdefault("STORAGE_DIR", "./_storage_ifcatomic")
os.environ.setdefault("AEC_TRUST_XUSER", "1")

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import pathlib  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402

from aec_api.db import Base, SessionLocal, engine  # noqa: E402
from aec_api.models import Project  # noqa: E402
from aec_api.routers.authoring_shared import publish_source_ifc, staged_ifc  # noqa: E402

Base.metadata.create_all(engine)

FAILED: list[str] = []


def check(label: str, ok, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}   {detail if not ok else ''}")
    if not ok:
        FAILED.append(label)


PID = "ifc-atomic-test"
#: A FRESH directory per run, not a fixed `./_ifc_atomic`. This file deliberately KEEPS one
#: `.rollback-*` backup and asserts there is exactly one, and that no other rollback scratch is left
#: behind. In a fixed directory those two assertions are armed by any run that dies between creating
#: the kept backup and the cleanup at the end -- a crash, a timeout, a cancelled CI job -- and then
#: EVERY later run fails, for a reason that has nothing to do with the code under test, until
#: somebody deletes the file by hand. `run_tests.py` reports `_ifc_*` as residue it does not own, so
#: the runner never clears it either. *A test that asserts "nothing was left behind" must not share
#: a directory with its own previous failures.*
WORK = pathlib.Path(tempfile.mkdtemp(prefix="ifc_atomic_")).resolve()
FINAL = WORK / "source.ifc"

OLD = b"ISO-10303-21;\n/* OLD COMPLETE MODEL */\nEND-ISO-10303-21;\n"
NEW_HEAD = b"ISO-10303-21;\n/* NEW MODEL "
NEW_TAIL = b"*/\nEND-ISO-10303-21;\n"
NEW = NEW_HEAD + b"x" * 4096 + NEW_TAIL


def reset() -> Project:
    db = SessionLocal()
    db.query(Project).filter(Project.id == PID).delete()
    p = Project(id=PID, name="atomic", source_ifc=str(FINAL))
    db.add(p)
    db.commit()
    db.refresh(p)
    FINAL.write_bytes(OLD)
    for junk in WORK.glob(".staged-*"):
        junk.unlink(missing_ok=True)
    return p


def _slow_write(path: pathlib.Path, data: bytes) -> None:
    """Write `data` in chunks with a pause, so a concurrent reader has a window to catch a
    partial file. A producer that wrote atomically would give the reader nothing to catch."""
    with open(path, "wb") as fh:
        for i in range(0, len(data), 512):
            fh.write(data[i:i + 512])
            fh.flush()
            time.sleep(0.002)


def observe(stop: threading.Event) -> list[bytes]:
    """Everything a reader sees at the PUBLISHED path while a producer runs."""
    seen: list[bytes] = []
    while not stop.is_set():
        try:
            seen.append(FINAL.read_bytes())
        except OSError:
            seen.append(b"<missing>")
        time.sleep(0.001)
    return seen


def run_producer(write_to_published: bool) -> list[bytes]:
    """Produce a new model while a reader watches the published path. Returns what it saw."""
    p = reset()
    db = SessionLocal()
    p = db.get(Project, PID)
    stop = threading.Event()
    seen: list[bytes] = []

    def watch():
        seen.extend(observe(stop))

    watcher = threading.Thread(target=watch, name="reader")
    watcher.start()
    try:
        if write_to_published:
            # MUTATION: the pre-fix shape -- bytes straight onto the published path.
            _slow_write(FINAL, NEW)
            with_lock = SessionLocal()
            row = with_lock.get(Project, PID)
            row.source_ifc = str(FINAL)
            with_lock.commit()
            with_lock.close()
        else:
            with staged_ifc(FINAL) as staged:
                _slow_write(staged, NEW)
                publish_source_ifc(db, p, PID, staged, FINAL)
    finally:
        time.sleep(0.01)
        stop.set()
        watcher.join(timeout=10)
        db.close()
    return seen


def partials(seen: list[bytes]) -> list[int]:
    """Sizes the reader saw that were neither the complete OLD file nor the complete NEW one."""
    return [len(b) for b in seen if b not in (OLD, NEW)]


# --- the fix ------------------------------------------------------------------------------------
seen_fixed = run_producer(write_to_published=False)
check("the reader polled the published path often enough for the result to mean something",
      len(seen_fixed) > 5, f"only {len(seen_fixed)} observations")
check("staged publication: the reader NEVER sees a partial file -- every observation is either the "
      "complete old model or the complete new one",
      not partials(seen_fixed), f"partial sizes observed: {partials(seen_fixed)[:8]}")
check("...and the new model really was published (the run is not vacuously clean because nothing "
      "was written)", NEW in seen_fixed or FINAL.read_bytes() == NEW,
      f"final is {len(FINAL.read_bytes())} bytes")
check("...and the staged file is gone -- promotion renames it away rather than leaving residue",
      not list(WORK.glob(".staged-*")), f"left behind: {[q.name for q in WORK.glob('.staged-*')]}")
# --- the published path must never be ABSENT, which is not the same property as "never partial" --
#: Round 4's rollback moved the previous file aside with `os.replace`, leaving a window where
#: `source.ifc` did not exist. `bake_layers` calls `project_with_source` BEFORE taking the lock, and
#: that helper raises 409 "project has no accessible source IFC" on a missing file -- so a concurrent
#: read could be REFUSED during a publication that then succeeded. *A fix for one property can cost
#: an unrelated one that nothing was asserting.*
#:
#: **Tested at the primitive, with a real window, and not through `publish_source_ifc`.** The first
#: version of this asserted `b"<missing>" not in seen_fixed` during a normal publish -- and reverting
#: the fix left it PASSING, because two back-to-back renames are microseconds and the reader polls
#: every millisecond. *A check that cannot observe the interval it describes reports on nothing*, so
#: the window is made wide here deliberately: with a rename the reader must catch the gap, with a
#: hard link there is no gap to catch at any width.
def _backup_window(take_backup) -> bool:
    """Was the published path ever absent while `take_backup` held the old file aside?"""
    reset()
    stop, missed = threading.Event(), []

    def watch():
        while not stop.is_set():
            missed.append(not FINAL.exists())
            time.sleep(0.001)

    w = threading.Thread(target=watch, daemon=True)
    w.start()
    try:
        bk = FINAL.with_name(".probe-backup")
        with staged_ifc(FINAL) as st:
            st.write_bytes(NEW)
            take_backup(FINAL, bk)
            time.sleep(0.05)            # a WIDE window -- narrow is what made the first draft vacuous
            os.replace(st, FINAL)
        bk.unlink(missing_ok=True)
    finally:
        time.sleep(0.01)
        stop.set()
        w.join(timeout=5)
    return any(missed)

check("MUTATION: taking the backup with a RENAME does leave the published path missing -- so the "
      "check below measures the primitive and not the width of the window",
      _backup_window(os.replace),
      "a rename left no observable gap; widen the sleep or this proves nothing")
check("taking it with a HARD LINK never does -- the published path is continuously present, so a "
      "reader that checks it before taking the lock cannot be refused mid-publication",
      not _backup_window(os.link), "os.link still left the published path missing")
# ...and the helper must actually USE the link, which is a question about behaviour rather than
# about source text. This asserted `"os.link(final, backup)" in <the module's source>`, which is the
# same defect `test_pin_pgnull` was built to record: *asking the right question and then asserting
# something adjacent to the answer.* It passed on a spelling and would pass on dead code, while a
# faithful rewrite (`os.link(src=final, dst=backup)`, or the call moved into a helper) reds it for
# no reason. Wrap `authoring_shared.os.link` instead and run a REAL publication through it.
import aec_api.routers.authoring_shared as _ash  # noqa: E402

_linked: list[tuple[str, str]] = []
_real_link = _ash.os.link


def _spy_link(src, dst):
    _linked.append((str(src), str(dst)))
    return _real_link(src, dst)


_p = reset()
_db = SessionLocal()
_p = _db.get(Project, PID)
_ash.os.link = _spy_link
try:
    with staged_ifc(FINAL) as _st:
        _st.write_bytes(NEW)
        publish_source_ifc(_db, _p, PID, _st, FINAL)
finally:
    _ash.os.link = _real_link
    _db.close()

check("...and `publish_source_ifc` really CALLS os.link on a live publication -- behaviour, not a "
      "source-text match, which would pass on a spelling and on dead code alike",
      any(s_ == str(FINAL) and "/.rollback-" in d_.replace("\\", "/") for s_, d_ in _linked),
      f"os.link was not called with (final, .rollback-*): {_linked}")
check("  and the published file survived that publication intact",
      FINAL.exists() and FINAL.read_bytes() == NEW,
      f"final={'missing' if not FINAL.exists() else len(FINAL.read_bytes())} bytes")

# --- MUTATION: write straight to the published path, as every producer did before this PR --------
seen_raw = run_producer(write_to_published=True)
check("MUTATION: writing the PUBLISHED path directly DOES expose partial files to a reader -- so "
      "this test measures the staging and not the timing",
      partials(seen_raw), "no partial observed; the writer was too fast for the reader to catch "
                          "and this check proves nothing -- widen the file or slow the write")

# --- the staging name must be unique, which is the half `.part` got wrong ------------------------
with staged_ifc(FINAL) as a, staged_ifc(FINAL) as b:
    check("two concurrent stagings of one destination get DIFFERENT paths -- `stream_to_path`'s "
          "`<dest>.part` is a function of the destination, so it is shared and interleavable",
          a != b, f"{a.name} == {b.name}")

# --- the context manager removes a staged file its producer never promoted ----------------------
with staged_ifc(FINAL) as abandoned:
    abandoned.write_bytes(b"never promoted")
    _abandoned = abandoned
check("a staged file whose producer failed before promoting is removed, not leaked -- this tree "
      "has already run a disk out on orphaned scratch once",
      not _abandoned.exists(), f"{_abandoned} survived")

# --- a FAILED publication must leave the previous model intact --------------------------------
#: A rename is cheap to undo -- one more rename, nothing copied -- but it does not undo itself, and
#: `put_stream` and `commit` cannot be undone at all. Before the rollback guard,
#: a storage failure after the rename left the published path holding the new bytes with nothing else
#: published -- readers opening a model the system had not accepted. *Atomic at each step is not
#: atomic across the sequence.*
import aec_api.storage as _storage  # noqa: E402

reset()
_db = SessionLocal()
_p = _db.get(Project, PID)
_real_put = _storage.put_stream


def _boom(*_a, **_kw):
    raise RuntimeError("object storage unavailable")


_storage.put_stream = _boom
try:
    with staged_ifc(FINAL) as _st:
        _st.write_bytes(NEW)
        try:
            publish_source_ifc(_db, _p, PID, _st, FINAL)
            _raised = False
        except RuntimeError:
            _raised = True
finally:
    _storage.put_stream = _real_put
    _db.close()

check("a publication that fails midway RAISES rather than reporting success",
      _raised, "publish_source_ifc swallowed the storage failure")
check("...and the previously published model is restored byte-for-byte -- a reader never ends up "
      "holding a model the system did not finish publishing",
      FINAL.read_bytes() == OLD, f"final is {len(FINAL.read_bytes())} bytes, expected the old {len(OLD)}")
check("...and no rollback scratch is left behind",
      not list(WORK.glob(".rollback-*")), f"left: {[q.name for q in WORK.glob('.rollback-*')]}")

# --- and when the RESTORE ITSELF fails, the backup must SURVIVE -------------------------------
#: The `finally` used to unlink the backup unconditionally. With `os.link`, `backup` and `final`
#: begin as one inode, and after `os.replace(staged, final)` the backup holds the LAST reference to
#: the previous model -- so deleting it on the path where the restore failed destroys the user's
#: model outright and leaves the refused bytes published. *Cleanup in a `finally` runs on the branch
#: where cleanup is exactly the wrong thing to do.* A surviving `.rollback-*` is evidence that a
#: publication failed AND could not be undone; it is not litter.
reset()
_db3 = SessionLocal()
_p3 = _db3.get(Project, PID)
_real_replace = os.replace


def _replace_failing_restore(src, dst):
    """Promotion works; putting the backup BACK does not -- the branch that still needs the file."""
    if str(src).find(".rollback-") >= 0:
        raise OSError("restore failed")
    return _real_replace(src, dst)


_storage.put_stream = _boom
os.replace = _replace_failing_restore
try:
    with staged_ifc(FINAL) as _st4:
        _st4.write_bytes(NEW)
        try:
            publish_source_ifc(_db3, _p3, PID, _st4, FINAL)
        except (RuntimeError, OSError):
            pass
finally:
    os.replace = _real_replace
    _storage.put_stream = _real_put
    _db3.close()

_kept = list(WORK.glob(".rollback-*"))
check("when the restore itself fails the backup is KEPT -- it is the only copy of the previous "
      "model left, and an unconditional cleanup would destroy it",
      len(_kept) == 1, f"rollback files: {[q.name for q in _kept]}")
check("...and it still holds the previous model byte-for-byte, so the model is recoverable",
      bool(_kept) and _kept[0].read_bytes() == OLD,
      f"{_kept[0].read_bytes()[:24] if _kept else b''!r}")
for _q in _kept:
    _q.unlink(missing_ok=True)

# --- and the SAME failure with NO previous file to restore ---------------------------------------
#: The arm above always had something to roll back, because `reset()` writes OLD to FINAL every time.
#: *A rollback test that always has a previous file never exercises the branch where there is none* --
#: and that branch was empty: `backup` is None for a FIRST publication (blank create, first upload,
#: first generate), so the `except` did nothing while `os.replace(staged, final)` had already put the
#: refused bytes at the published path. The orphan is the smaller half. The larger one is that the
#: NEXT publication sees `final.exists()` and adopts those bytes as its backup, so a later failure
#: RESTORES a model the system refused -- which is why this asserts the follow-on too.
reset()
FINAL.unlink(missing_ok=True)                 # a project with no model yet: the no-backup path
_db2 = SessionLocal()
_p2 = _db2.get(Project, PID)
_storage.put_stream = _boom
try:
    with staged_ifc(FINAL) as _st2:
        _st2.write_bytes(NEW)
        try:
            publish_source_ifc(_db2, _p2, PID, _st2, FINAL)
            _raised2 = False
        except RuntimeError:
            _raised2 = True
finally:
    _storage.put_stream = _real_put

check("a FIRST publication that fails also raises", _raised2, "the no-backup path swallowed it")
check("...and leaves NO file at the published path -- with no previous model, rolling back means "
      "leaving nothing, not leaving bytes the system refused to publish",
      not FINAL.exists(),
      f"{FINAL.name} survived holding {len(FINAL.read_bytes()) if FINAL.exists() else 0} refused bytes")

# The follow-on: a later SUCCESSFUL publish must not be able to adopt refused bytes as its backup.
with staged_ifc(FINAL) as _st3:
    _st3.write_bytes(OLD)
    publish_source_ifc(_db2, _p2, PID, _st3, FINAL)
check("...so the next publication publishes its own bytes, with no refused model left to inherit",
      FINAL.read_bytes() == OLD, f"published {len(FINAL.read_bytes())} bytes, expected {len(OLD)}")
_db2.close()

print()
print(f"test_ifc_publish_atomic {'FAILED' if FAILED else 'OK'}"
      + ("" if FAILED else f" - {len(seen_fixed)} reader observations, 0 partial"))
for f in FAILED:
    print(f"  - {f}")
#: Removed only on a PASS: a failed run's staged files, backups and published bytes are the evidence
#: somebody will want, and the directory is under the system temp root either way.
if not FAILED:
    shutil.rmtree(WORK, ignore_errors=True)
sys.exit(1 if FAILED else 0)
