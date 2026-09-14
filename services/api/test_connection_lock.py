"""RMW-TOKEN (gap G-12): `Connection.config` had TWO writers and neither took a lock.

`update_connection` merges the body's keys into the blob (keeping a stored secret where the form
sent it blank); `put_mappings` rewrites the whole blob to replace its `mappings` key. Unlocked, an
admin saving credentials while another saves field mappings loses one of the two -- silently, since
each caller's 200 is true of its own merge.

What is asserted here is NOT that a lock is present but that **both edits survive**, which is the
thing the user actually cares about and the only claim a lock spanning too little would fail. A
test that grepped for `pid_lock` would pass on a lock around the assignment alone.

**This test and `test_rmw_sweep` catch DIFFERENT failures, and neither alone is enough** --
measured, not assumed. Deleting one route's lock reds the sweep AND this test. But making the two
routes lock on DIFFERENT KEYS -- `connection:<id>` against `mappings:<id>` -- reds only this one:
the sweep's `under_pid_lock` asks whether each mention sits inside *a* `pid_lock.mutating(...)`,
which both still do. *Static analysis can see that a lock is present; only behaviour can see that it
is the SAME lock.* That is "a lock one side does not take protects nothing" wearing the shape of a
lock, and it is why `_lock_key` is a shared helper rather than an f-string at each call site.

Run: cd services/api && PYTHONPATH="src:../data/src" .venv/bin/python test_connection_lock.py
"""
import os
import sys
import threading

os.environ["DATABASE_URL"] = "sqlite:///./_connlock_test.db"
os.environ.setdefault("STORAGE_DIR", "./_storage_connlock")
os.environ.setdefault("AEC_TRUST_XUSER", "1")

_DATA_SRC = os.path.join(os.path.dirname(__file__), "..", "data", "src")
if _DATA_SRC not in sys.path:
    sys.path.insert(0, _DATA_SRC)

import contextlib  # noqa: E402

from aec_api import pid_lock as _pl  # noqa: E402
from aec_api.db import Base, SessionLocal, engine  # noqa: E402
from aec_api.models import Connection, User  # noqa: E402
from aec_api.routers import connections as conn  # noqa: E402

Base.metadata.create_all(engine)

CID = "conn-lock-test"
ADMIN = User(username="admin-test", role="admin")

_db = SessionLocal()
_db.query(Connection).filter(Connection.id == CID).delete()
_db.add(Connection(id=CID, name="procore-1", type="procore",
                   config={"access_token": "SECRET-TOKEN", "mappings": {}}))
_db.commit()
_db.close()

FAILED: list[str] = []


def check(label: str, ok, detail: str = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}   {detail}")
    if not ok:
        FAILED.append(label)


def reset() -> None:
    """Put the blob back to its starting state between runs."""
    db = SessionLocal()
    db.get(Connection, CID).config = {"access_token": "SECRET-TOKEN", "mappings": {}}
    db.commit()
    db.close()


def run_both() -> dict:
    """One `update_connection` and one `put_mappings`, concurrently. Returns the final blob.

    Each worker is held INSIDE its critical section -- after its read of `config`, before its
    commit -- until the other arrives, so the interleaving is forced rather than hoped for. Under
    the real lock the second cannot arrive, so the first times out and proceeds; the locked run is
    slower by the timeout, never wrong. (The same shape `test_authoring_lock` needed after its own
    first draft proved timing-dependent: *synchronising the start of a race does not hold its
    window open.*)
    """
    mid = threading.Barrier(2)

    def hold():
        with contextlib.suppress(threading.BrokenBarrierError):
            mid.wait(timeout=2)

    def save_creds():
        db = SessionLocal()
        try:
            body = conn.ConnectionIn(name="procore-1", type="procore",
                                     config={"account_id": "ACCT-9"})
            _patched(db, hold)
            conn.update_connection(CID, body, db=db, admin=ADMIN)
        finally:
            db.close()

    def save_mappings():
        db = SessionLocal()
        try:
            _patched(db, hold)
            conn.put_mappings(CID, {"rfi": {"subject": "title"}}, db=db, admin=ADMIN)
        finally:
            db.close()

    ts = [threading.Thread(target=save_creds), threading.Thread(target=save_mappings)]
    for t in ts:
        t.start()
    for t in ts:
        t.join(timeout=30)

    db = SessionLocal()
    cfg = dict(db.get(Connection, CID).config or {})
    db.close()
    return cfg


def _patched(db, hold):
    """Make this session's `refresh` also pause, so the pause sits after the read of `config`."""
    original = db.refresh

    def refreshing(obj, *a, **kw):
        original(obj, *a, **kw)
        hold()
    db.refresh = refreshing


# --- the fix ---------------------------------------------------------------------------------
reset()
cfg = run_both()
check("a concurrent credential save and mapping save BOTH survive -- neither admin's edit is lost",
      cfg.get("account_id") == "ACCT-9" and cfg.get("mappings") == {"rfi": {"subject": "title"}},
      f"account_id={cfg.get('account_id')!r} mappings={cfg.get('mappings')!r}")
check("...and the stored secret the form did not re-send is still there",
      cfg.get("access_token") == "SECRET-TOKEN", f"access_token={cfg.get('access_token')!r}")

# --- MUTATION: the lock removed, one of the two edits is lost ----------------------------------
_real = _pl.mutating


@contextlib.contextmanager
def _no_lock(_key):
    """`pid_lock.mutating` with the serialisation taken out, signature intact."""
    yield


_pl.mutating = _no_lock
try:
    reset()
    cfg_m = run_both()
finally:
    _pl.mutating = _real

_lost = [k for k, want in (("account_id", "ACCT-9"),
                           ("mappings", {"rfi": {"subject": "title"}})) if cfg_m.get(k) != want]
check("MUTATION: with the lock neutered, the same interleaving LOSES one of the two edits -- so "
      "this test measures the lock and not the scheduler",
      _lost, f"lost: {_lost or 'nothing (the mutation did not bite)'}")

print()
print(f"test_connection_lock {'FAILED' if FAILED else 'OK'}")
for f in FAILED:
    print(f"  - {f}")
sys.exit(1 if FAILED else 0)
