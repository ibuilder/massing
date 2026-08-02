"""Two read-then-write races: the job queue's claim, and the ref counter's first-use seeding.

WHY THIS EXISTS
    The suite runs on SQLite, which serialises writers — so a race that needs two truly parallel
    writers cannot REPRODUCE here. What CAN be proven here, deterministically, is the property the
    fix relies on and the recovery path the old code lacked:

      * the claim is a COMPARE-AND-SWAP — after one worker claims a job, a second worker attempting
        the same claim matches zero rows and moves on, instead of committing `running` a second
        time and executing the handler concurrently;
      * counter seeding survives LOSING — when the "no counter row yet" branch collides with a row
        that appeared in between, the PK refusal stays inside a savepoint and the loser locks the
        winner's row, instead of surfacing the IntegrityError as a 500 on an ordinary create.

    Both defects share the shape this repo keeps finding: read state, decide, write — with nothing
    holding the world still in between. And both fixes share the shape of `rbac.consume_stepup`:
    let the DATABASE refuse the second writer, and keep the refusal local.

HONEST LIMITS
    Thread rounds below remove start-up skew with a barrier but cannot force a collision on this
    backend (same caveat as test_stepup_race). That is why each race ALSO has a deterministic test
    that constructs the exact losing interleaving by hand. The thread rounds still earn their keep:
    they assert the user-visible invariants (no crash, no duplicate ref, every job claimed exactly
    once) under whatever interleaving the backend does produce.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_race_conditions.py
"""
import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "data", "src"))
os.environ.setdefault("AEC_TEST", "1")
os.environ["DATABASE_URL"] = "sqlite:///./test_race_conditions.db"
os.environ["STORAGE_DIR"] = "./test_storage_race_conditions"
for _f in ("./test_race_conditions.db",):
    if os.path.exists(_f):
        os.remove(_f)

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


from sqlalchemy import select  # noqa: E402

from aec_api import jobs, modules  # noqa: E402
from aec_api.db import SessionLocal, init_db  # noqa: E402
from aec_api.models import Job, Project, RefCounter  # noqa: E402

init_db()

db = SessionLocal()
proj = Project(name="race")
db.add(proj)
db.commit()
PID = proj.id

# ---------------------------------------------------------------- job claim: the CAS, exactly
# The deterministic version of "two workers pick the same job". Worker A claims; worker B —
# whose SELECT (simulated by having observed the job while it was queued) chose the same row —
# runs _claim_next. Under the old read-then-write code B would commit `running` again and RETURN
# the job, i.e. two concurrent executions. Under the CAS, B's update matches 0 rows, B loops,
# finds the queue empty, and reports None.
jobs.register_kind("race_noop", lambda _db, _p: {"ok": True})
j1 = jobs.enqueue(db, "race_noop", PID, {}, actor="race@test")

db_a, db_b = SessionLocal(), SessionLocal()
# B observes the job while it is still queued (this is the stale read the race is made of).
seen_by_b = db_b.scalars(select(Job).where(Job.state == "queued")).all()
check("setup: worker B saw the queued job before A claimed", len(seen_by_b) == 1, str(len(seen_by_b)))

claimed_a = jobs._claim_next(db_a)
claimed_b = jobs._claim_next(db_b)
check("worker A claims the job", claimed_a is not None and claimed_a.id == j1.id)
check("worker B does NOT also claim it — the CAS refused the second writer",
      claimed_b is None, f"B got: {claimed_b.id if claimed_b else None}")
fresh = db.scalars(select(Job).where(Job.id == j1.id)).one()
db.refresh(fresh)
check("the job is running exactly once, not twice", fresh.state == "running", fresh.state)

# A loser must move ON, not give up: with a second queued job behind the contested one, the loser's
# loop should claim it. (This is the `while True` — a `return None` after one failed CAS would make
# a busy queue starve every worker that ever loses a race.)
j2 = jobs.enqueue(db, "race_noop", PID, {}, actor="race@test")
j3 = jobs.enqueue(db, "race_noop", PID, {}, actor="race@test")
db_c, db_d = SessionLocal(), SessionLocal()
got_c = jobs._claim_next(db_c)
got_d = jobs._claim_next(db_d)
ids = {g.id for g in (got_c, got_d) if g is not None}
check("two workers over two queued jobs claim ONE EACH — losers advance to the next job",
      ids == {j2.id, j3.id}, f"claimed: {ids}")

# Thread rounds: N jobs, 2 workers draining concurrently. Every job claimed exactly once.
N = 8
queued = [jobs.enqueue(db, "race_noop", PID, {}, actor="race@test").id for _ in range(N)]
claims: list[str] = []
claims_lock = threading.Lock()
barrier = threading.Barrier(2)


def drain():
    s = SessionLocal()
    try:
        barrier.wait(timeout=10)
        while True:
            got = jobs._claim_next(s)
            if got is None:
                break
            with claims_lock:
                claims.append(got.id)
    finally:
        s.close()


threads = [threading.Thread(target=drain) for _ in range(2)]
for t in threads:
    t.start()
for t in threads:
    t.join(timeout=30)
check("no drain thread hung", not any(t.is_alive() for t in threads))
check(f"{N} jobs drained by 2 concurrent workers, each claimed EXACTLY once",
      sorted(claims) == sorted(queued) and len(claims) == len(set(claims)),
      f"{len(claims)} claims, {len(set(claims))} distinct")

# ---------------------------------------------------------------- ref seeding: losing must not 500
# The exact losing interleaving, constructed by hand: this session's SELECT found no counter row
# (genuinely — none exists), and by the time it inserts, another writer has seeded. Simulated by
# inserting the winner's row through a SECOND session after the first session has already read
# None — the insert below then hits the real composite PK, raising the real IntegrityError, and
# the savepoint + re-lock path must recover and hand out the NEXT ref, not a 500.
db1, db2 = SessionLocal(), SessionLocal()
none_row = (db1.query(RefCounter)
              .filter(RefCounter.project_id == PID, RefCounter.module == "rfi")
              .with_for_update().first())
check("setup: session 1 read None (no counter row yet)", none_row is None)
# the other writer wins the seeding in between
db2.add(RefCounter(project_id=PID, module="rfi", n=7))
db2.commit()
# session 1 proceeds exactly as _next_ref's seeding branch does — via the function itself
try:
    ref = modules._next_ref(db1, "rfi", PID, {"ref_prefix": "RFI"})
    db1.commit()
    check("the losing seeder RECOVERS and allocates from the winner's counter",
          ref == "RFI-008", f"got {ref!r} (winner had n=7, loser must mint 8)")
except Exception as exc:  # noqa: BLE001 — the pre-fix behaviour was exactly this escape
    check("the losing seeder RECOVERS and allocates from the winner's counter",
          False, f"raised {type(exc).__name__}: {exc}")
finally:
    db1.close()
    db2.close()

# Thread rounds: first-ever creates for a fresh module, concurrently. Unique refs, zero raises.
db3 = SessionLocal()
proj2 = Project(name="race2")
db3.add(proj2)
db3.commit()
PID2 = proj2.id
db3.close()

refs: list[str] = []
errs: list[str] = []
refs_lock = threading.Lock()
barrier2 = threading.Barrier(4)


def create_first(i: int):
    s = SessionLocal()
    try:
        barrier2.wait(timeout=10)
        rec = modules.create_record(s, "rfi", PID2, {"data": {"subject": f"r{i}", "question": "?"}},
                                    actor="race@test", party=None)
        with refs_lock:
            refs.append(rec["ref"])
    except Exception as exc:  # noqa: BLE001 — a raise IS the pre-fix failure being measured
        with refs_lock:
            errs.append(f"{type(exc).__name__}: {exc}")
    finally:
        s.close()


threads = [threading.Thread(target=create_first, args=(i,)) for i in range(4)]
for t in threads:
    t.start()
for t in threads:
    t.join(timeout=30)
check("4 concurrent FIRST creates all succeed — no seeding 500", not errs, "; ".join(errs[:2]))
check("…and every ref is distinct", len(refs) == 4 and len(set(refs)) == 4, str(sorted(refs)))

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_race_conditions OK - job claim is CAS (one winner, losers advance), "
      "counter seeding survives losing (savepoint + re-lock, never a 500)")
