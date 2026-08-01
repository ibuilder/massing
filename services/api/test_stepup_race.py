"""A step-up assertion survives exactly one CONCURRENT spend, not merely one sequential replay.

WHY THIS EXISTS
    `rbac.consume_stepup` spends an assertion with a primary-key insert inside a SAVEPOINT, and its
    docstring makes a specific, strong claim:

        "two concurrent replays would both pass an `if already_spent` check and both proceed. Here
         the second insert violates the constraint and the database refuses it, so the race has no
         winner to give away."

    That claim shipped (#140, `dce2eeb4`) with a test that only replayed the token **sequentially** —
    spend, then spend again on the same thread. A sequential replay is satisfied by a plain
    read-then-write, which is precisely the implementation the docstring says would be wrong. So the
    test could not distinguish the design that was built from the design it was chosen over, and the
    interesting half of the claim was unverified while reading as covered.

    Reported by the session that wrote it, before anyone was bitten. That is the good version of this
    outcome, and the reason it is worth writing down: the author noticed their own test could not
    reach their own claim.

WHAT IS ASSERTED
    Two threads, two independent Sessions, released together by a barrier, both spending the SAME
    assertion. **Exactly one** must succeed. Not "at least one" — a race that lets both through is a
    replayable seal, and a race that lets neither through is a broken feature.

WHICH ASSERTION GUARDS WHICH HALF — established by mutation, not by reading
    Replacing the PK-insert-in-a-SAVEPOINT with the read-then-write the docstring calls wrong does
    **not** produce two winners. The PRIMARY KEY still refuses the second insert, so the winner count
    stays 1 and the headline assertion below stays green.

    What it does produce is `PendingRollbackError` in the loser: without the savepoint, the failed
    flush poisons the caller's whole transaction. So the claim decomposes, and the two halves are
    enforced by different things:

        "the race has no winner to give away"  <- the PRIMARY KEY
        the loser's refusal stays LOCAL        <- the SAVEPOINT

    Only the "no spender raised" assertion catches the savepoint's removal. That matters because a
    poisoned transaction discards whatever the caller had staged beside the spend — including the
    audit row — so the failure mode of dropping the savepoint is a security control that erases its
    own evidence, while still reporting the right number of winners.

    Both assertions are therefore load-bearing and neither substitutes for the other. Do not "simplify"
    this file down to the winner count.

HONEST LIMITS OF THIS TEST
    The suite runs on SQLite, which serialises writers. So this proves the OUTCOME (exactly one
    winner) under contention on the backend we test with; it does not prove two truly parallel
    INSERTs against Postgres, because SQLite will not give us two truly parallel INSERTs. The
    property is enforced by a PRIMARY KEY, which both backends honour, and the savepoint keeps the
    loser's rollback local — but the strongest available evidence here is "no interleaving this
    backend can produce yields two winners", and overstating that would repeat the exact defect this
    file exists to close.

    A `threading.Barrier` also cannot guarantee the two inserts collide; it only removes the
    thread-start skew that makes a collision unlikely. The test therefore runs several rounds, each
    with a fresh assertion, so a single lucky serialisation cannot pass it quietly.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_stepup_race.py
"""
import os
import sys
import threading

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "data", "src"))
os.environ.setdefault("AEC_TEST", "1")

# Own database, set BEFORE aec_api is imported (aec_api.db reads DATABASE_URL at import time).
# `run_tests.py` injects an isolated DSN per subprocess, so this file passed under the runner without
# it — but the documented way to run one test is to invoke it directly, and the fallback in
# `aec_api.db` is `sqlite:///./aec.db` **relative to the working directory**. Run from services/api,
# that is the developer's dev database: verified, a direct run creates a 4.5 MB aec.db and writes
# stepup_spent rows into it. It also puts this test's concurrent writers in contention with anything
# else holding that file. 334 of the 485 test files set this in-file for exactly this reason.
os.environ["DATABASE_URL"] = "sqlite:///./test_stepup_race.db"
os.environ["STORAGE_DIR"] = "./test_storage_stepup_race"
for _f in ("./test_stepup_race.db",):
    if os.path.exists(_f):
        os.remove(_f)

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


from aec_api import auth as _auth  # noqa: E402
from aec_api import rbac  # noqa: E402
from aec_api.db import SessionLocal, init_db  # noqa: E402

init_db()

ACT = "pdf.seal"
ACTOR = "race@seal.test"
PW_HASH = _auth.hash_password("correct horse battery staple")

#: Several rounds, because one round proves one interleaving. A barrier removes start-up skew; it
#: does not force a collision, and a test that passes only because the threads happened not to race
#: is the same class of false comfort as the sequential replay it replaces.
ROUNDS = 8


def spend_in_thread(token, results, index, barrier):
    """One spender, on its OWN Session — a shared Session would serialise in the client, not the DB."""
    db = SessionLocal()
    try:
        barrier.wait(timeout=10)
        results[index] = rbac.consume_stepup(db, token, ACT, PW_HASH, ACTOR)
        db.commit()
    except Exception as exc:  # noqa: BLE001 — a raise is a result too; record rather than crash
        results[index] = f"raised: {type(exc).__name__}: {exc}"
    finally:
        db.close()


winners = []
anomalies = []
for round_no in range(ROUNDS):
    token = _auth.create_stepup_token(ACTOR, ACT, PW_HASH)
    results = [None, None]
    barrier = threading.Barrier(2)
    threads = [threading.Thread(target=spend_in_thread, args=(token, results, i, barrier))
               for i in range(2)]
    for t in threads:
        t.start()
    for i, t in enumerate(threads):
        t.join(timeout=20)
        # `join(timeout=…)` returns whether or not the thread finished. Without this check a spender
        # still blocked at the deadline leaves results[i] as its initial None — neither an anomaly
        # (not a str) nor a winner (not True) — so it is counted as a legitimate loser and the round
        # still reports exactly 1 winner and passes, having proved nothing about contention. That is
        # the "a check that returns nothing is read as fine" shape this file documents, in its own
        # harness.
        if t.is_alive():
            results[i] = f"raised: thread {i} still running after join timeout (deadlock or lock wait)"

    raised = [r for r in results if isinstance(r, str)]
    if raised:
        anomalies.append(f"round {round_no}: {raised}")
    winners.append(sum(1 for r in results if r is True))

check("no spender raised — a refusal must be a False, never an exception",
      not anomalies, "; ".join(anomalies[:2]))

bad = [(i, w) for i, w in enumerate(winners) if w != 1]
check("exactly one concurrent spend wins, every round",
      not bad,
      f"rounds with the wrong winner count: {bad}" if bad
      else f"{ROUNDS} rounds, all exactly 1 winner")

# Both failure directions are real, and they fail differently, so name them separately rather than
# leaving a reader to infer which one a count of 0 or 2 meant.
check("no round let BOTH spenders through (a replayable assertion)",
      all(w <= 1 for w in winners), f"rounds with 2 winners: {[i for i, w in enumerate(winners) if w > 1]}")
check("no round let NEITHER through (a seal nobody can obtain)",
      all(w >= 1 for w in winners), f"rounds with 0 winners: {[i for i, w in enumerate(winners) if w < 1]}")

# ---------------------------------------------------------------- the loser's rollback stays local
# The savepoint's whole job is that the refused insert does not take the caller's transaction with
# it. If it did, a losing seal attempt would also discard the audit row staged beside it — the
# security control would erase its own evidence.
db = SessionLocal()
try:
    from aec_api.models import StepUpSpent as _S
    before = db.query(_S).filter(_S.sub == ACTOR).count()
    token = _auth.create_stepup_token(ACTOR, ACT, PW_HASH)
    first = rbac.consume_stepup(db, token, ACT, PW_HASH, ACTOR)
    second = rbac.consume_stepup(db, token, ACT, PW_HASH, ACTOR)
    check("the sequential replay still fails (the original claim, kept)",
          first is True and second is False, f"first={first} second={second}")
    # The session must still be usable after the refusal — not left in a rolled-back state. Assert
    # that by USING it: a real query that would raise on a poisoned session. (The first draft of this
    # line read `... is not None or True`, which cannot fail — the same vacuous-gate defect this whole
    # file exists to correct, written into the correction.)
    from aec_api.models import StepUpSpent
    # `>= 1` could not fail for the reason it claimed: the concurrent section above already wrote one
    # row per round for this same ACTOR, so the count was 8 before this block ran and a missing row
    # from the spend under test would still have passed. Assert the DELTA instead.
    #
    # And run the query inside try/except: a session poisoned by a missing SAVEPOINT raises
    # PendingRollbackError here, which was uncaught and surfaced as a traceback. A crash is a worse
    # signal than a named failure — it is easy to misread as a broken test rather than a broken
    # control, which is the wrong conclusion about the exact defect this asserts.
    try:
        after = db.query(StepUpSpent).filter(StepUpSpent.sub == ACTOR).count()
        usable, why = True, ""
    except Exception as exc:  # noqa: BLE001 — a poisoned session is the finding, not a crash
        after, usable, why = -1, False, f"{type(exc).__name__}: {exc}"
    check("the caller's session survives a refused spend (a poisoned one would raise here)",
          usable, why)
    check("the winning spend's row landed — asserted as a delta, not a non-zero count",
          usable and after == before + 1, f"before={before} after={after}")
    db.commit()
finally:
    db.close()

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_stepup_race OK")
