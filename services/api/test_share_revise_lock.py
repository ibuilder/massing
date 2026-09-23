"""RMW-SHARE (gap G-10) and RMW-REVISE: the last two open sites in the read-modify-write sweep.

`proforma.share_scenario` unions a grantee into `Scenario.shared_with`; `drawingset.revise_sheet`
appends a delta to a sheet's `revisions` list and tags every markup on that sheet `carried_from`.
Both read a value and write a value derived from it, and neither took anything to serialise on.

**What is asserted here is NOT that a lock is present but that BOTH edits survive** -- the claim a
user cares about, and the only one a lock spanning too little would fail. A test grepping for
`pid_lock` passes on a lock around the assignment alone; `test_rmw_sweep`'s `under_pid_lock` is that
grep, done properly, and it still cannot see whether two writers picked the SAME key.

**Both failures are invisible from either caller's own response, which is why they needed a test
rather than a bug report.** `share_scenario` answers with the list the winner built, and that list
contains the target THAT caller asked for -- so both requests return 201 with their own person
present and the loser's grantee simply cannot open the scenario. `revise_sheet` answers with its own
`delta_count`, incremented, for a delta the next read will not find.

**The sweep ledger keyed the revise site on `m.data`, and that is the less severe half** -- the
markup tag is idempotent (`"carried_from" not in d2`) and has no other read-modify-writer, while the
`revisions` list beside it loses an accepted revision outright. Both are covered below, and the
revisions half is the one with teeth. *A derivation keyed by attribute names the site it matched,
not the worst thing happening inside it.*

Run: cd services/api && PYTHONPATH="src:../data/src" .venv/bin/python test_share_revise_lock.py
"""
import os
import sys
import threading

os.environ["DATABASE_URL"] = "sqlite:///./_sharerev_test.db"
os.environ.setdefault("STORAGE_DIR", "./_storage_sharerev")
os.environ.setdefault("AEC_TRUST_XUSER", "1")

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import contextlib  # noqa: E402

from aec_api import drawingset  # noqa: E402
from aec_api import modules as me  # noqa: E402
from aec_api import pid_lock as _pl  # noqa: E402
from aec_api.db import Base, SessionLocal, engine  # noqa: E402
from aec_api.models import Scenario  # noqa: E402
from aec_api.routers import proforma as pf  # noqa: E402

me.load_registry()                       # register tables are defined lazily; `drawing` is one
Base.metadata.create_all(engine)

PID = "proj-sharerev"
SID = "scn-sharerev"

FAILED: list[str] = []


def check(label: str, ok, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}   {detail}")
    if not ok:
        FAILED.append(label)


def _guarded(name, fn, trouble):
    """`fn` with its exception recorded instead of printed to stderr and lost.

    A worker that raises leaves its edit absent, and at the stored value that is indistinguishable
    from the lost update this file hunts -- so the two are separated and reported apart."""
    def run():
        try:
            fn()
        except Exception as exc:              # noqa: BLE001 -- reported below, never swallowed
            trouble.append(f"{name} raised {type(exc).__name__}: {exc}")
    return run


def _run_pair(a, b) -> list[str]:
    """Run two workers concurrently and collect what went wrong. `Thread.join(timeout=...)`
    propagates neither the exception nor the fact that the thread is still running."""
    trouble: list[str] = []
    ts = [threading.Thread(target=_guarded(n, f, trouble), name=n) for n, f in (a, b)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=60)
    trouble += [f"{t.name} was still running after join(timeout=60)" for t in ts if t.is_alive()]
    return trouble


# --- RMW-SHARE: two grants at once -------------------------------------------------------------

def _reset_scenario() -> None:
    db = SessionLocal()
    db.query(Scenario).filter(Scenario.id == SID).delete()
    db.add(Scenario(id=SID, project_id=PID, name="base case", assumptions={}, shared_with=[]))
    db.commit()
    db.close()


def _share_both() -> tuple[list, list[str]]:
    """Two `share_scenario` calls, each held INSIDE its critical section -- after the read of
    `shared_with`, before the commit -- until the other arrives, so the interleaving is forced
    rather than hoped for. Under the real lock the second cannot arrive, so the first times out and
    proceeds: the locked run is slower by the timeout, never wrong."""
    mid = threading.Barrier(2)

    def hold():
        with contextlib.suppress(threading.BrokenBarrierError):
            mid.wait(timeout=2)

    def grant(who):
        def run():
            db = SessionLocal()
            try:
                original = db.refresh

                def refreshing(obj, *a, **kw):    # pause AFTER the re-read, inside the lock
                    original(obj, *a, **kw)
                    hold()
                db.refresh = refreshing
                pf.share_scenario(SID, who, db=db, actor="gc-admin")
            finally:
                db.close()
        return run

    trouble = _run_pair(("grant_lp_a", grant("lp-a")), ("grant_lp_b", grant("lp-b")))
    db = SessionLocal()
    shared = list(db.get(Scenario, SID).shared_with or [])
    db.close()
    return shared, trouble


_reset_scenario()
_shared, _t = _share_both()
check("both grant workers finished without raising -- a worker that dies leaves its grantee absent, "
      "which reads at the stored list exactly like the lost update this file hunts",
      not _t, "; ".join(_t))
check("two LPs granted access at the same moment are BOTH on the scenario -- neither grant is lost",
      {"lp-a", "lp-b"} <= set(_shared), f"shared_with={_shared}")


# --- RMW-REVISE: two revisions of one sheet at once ---------------------------------------------

def _reset_sheet() -> str:
    db = SessionLocal()
    t = me.TABLES["drawing"]
    db.execute(t.delete().where(t.c.project_id == PID))
    db.commit()
    rec = me.create_record(db, "drawing", PID,
                           {"data": {"title": "Level 1 Plan", "number": "A-101",
                                     "revision": "A"}},
                           "tester", "GC")
    db.close()
    return rec["id"]


def _revise_both(did: str) -> tuple[list, list[str]]:
    """Two `revise_sheet` calls on the SAME sheet. The hold sits after `get_record` -- the read the
    appended list is derived from -- which is where the lock has to already be held."""
    mid = threading.Barrier(2)
    original = me.get_record

    def held_get_record(*a, **kw):
        rec = original(*a, **kw)
        with contextlib.suppress(threading.BrokenBarrierError):
            mid.wait(timeout=2)
        return rec

    def revise(rev):
        def run():
            db = SessionLocal()
            try:
                drawingset.revise_sheet(db, PID, did, rev, description=f"delta {rev}")
            finally:
                db.close()
        return run

    me.get_record = held_get_record
    try:
        trouble = _run_pair(("revise_B", revise("B")), ("revise_C", revise("C")))
    finally:
        me.get_record = original

    db = SessionLocal()
    revs = [d.get("rev") for d in (me.get_record(db, "drawing", PID, did).get("data") or {}).get("revisions") or []]
    db.close()
    return revs, trouble


_did = _reset_sheet()
_revs, _t2 = _revise_both(_did)
check("both revision workers finished without raising", not _t2, "; ".join(_t2))
check("two revisions recorded on one sheet at once are BOTH in its revision block -- the half the "
      "sweep ledger did NOT name, and the one that loses an accepted revision",
      {"B", "C"} <= set(_revs), f"revisions={_revs}")


# --- MUTATION: neuter the lock and the same interleaving loses an edge ---------------------------
_real = _pl.mutating


@contextlib.contextmanager
def _no_lock(_key):
    """`pid_lock.mutating` with the serialisation taken out, signature intact."""
    yield


_pl.mutating = _no_lock
try:
    _reset_scenario()
    _shared_m, _tm = _share_both()
    _did_m = _reset_sheet()
    _revs_m, _tm2 = _revise_both(_did_m)
finally:
    _pl.mutating = _real

check("...and nothing raised in the MUTATION run either -- otherwise the losses below have a cause "
      "that has nothing to do with the lock and the mutation passes by accident",
      not (_tm + _tm2), "; ".join(_tm + _tm2))
check("MUTATION: with the lock neutered, one of the two GRANTS is lost -- so this measures the lock "
      "and not the scheduler",
      not ({"lp-a", "lp-b"} <= set(_shared_m)) and not _tm,
      f"shared_with={_shared_m}")
check("MUTATION: with the lock neutered, one of the two REVISIONS is lost",
      not ({"B", "C"} <= set(_revs_m)) and not _tm2, f"revisions={_revs_m}")

print()
print(f"test_share_revise_lock {'FAILED' if FAILED else 'OK'}"
      + ("" if FAILED else "  (two concurrent grants both survive; two concurrent sheet revisions "
                           "both survive; neutering the lock loses one of each)"))
for f in FAILED:
    print(f"  - {f}")
sys.exit(1 if FAILED else 0)
