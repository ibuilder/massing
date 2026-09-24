"""RMW-LOCKBOUND — a writer that WAITS for the project lock must give up, and must not write anyway.

`pid_lock.mutating` serialises sidecar read-modify-write per project. Until now the wait was
**unbounded**: `pg_advisory_lock` blocks until the holder releases, with no ceiling. Every one of the
30 call sites is a plain `def`, so FastAPI runs them in the threadpool -- which means a stuck holder
does NOT wedge the event loop, it pins threadpool workers. Starlette's default pool is 40, so 40
requests queued on one project starve every route in the app. *Naming the mechanism matters: "it
blocks the server" and "it exhausts the threadpool" send a reader to different fixes, and this entry
had the first written down.*

## Why this is a separate file from `test_pid_lock_pgxproc.py`

That file asks whether the lock EXCLUDES. This one asks whether a writer excluded by it eventually
STOPS. Those are opposite failure directions -- a lock that excluded nobody passes this file's
positive control, and a lock that excluded everybody for ever passes that file's exclusion check.

## The three premises, each measured rather than recalled (PostgreSQL 16, 2026-09-23)

1. `lock_timeout` bounds `pg_advisory_lock` -> SQLSTATE `55P03`. It is not documented as applying to
   advisory locks in so many words, so it was probed.
2. A lock timeout and an UNREACHABLE SERVER raise the same SQLAlchemy class, `OperationalError`. Only
   the sqlstate separates them (a dead server carries `sqlstate = None`). This is the whole reason
   `_SQLSTATE_LOCK_TIMEOUT` exists -- see mutation M2.
3. A plain `SET lock_timeout` is CONNECTION-scoped and survives return to the pool: measured at
   1500ms still in force on the next checkout of the same backend. `SET LOCAL` reverts at commit,
   and the advisory lock survives that commit because it is session-scoped. Both halves had to hold.

## What each mutation catches

* **M1** remove the `SET LOCAL` -> B waits for the whole hold. The bound is gone and nothing else
  notices, because an unbounded wait looks exactly like a slow one.
* **M2** delete the sqlstate branch so a lock timeout falls into `except Exception` ->
  `acquired = False` and B **proceeds having taken no cross-process lock**. This is the dangerous
  one: it converts a bounded wait into a silent correctness bug, strictly worse than the unbounded
  wait it replaced. M1 alone does not catch it and neither does any check in the sibling file.
"""
from __future__ import annotations

import ast
import io
import os
import subprocess
import sys
import tempfile
import time
import tokenize
from pathlib import Path

FAILED: list[str] = []


def check(label: str, ok: bool, why: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + label + ("" if ok else "   -- " + why))
    if not ok:
        FAILED.append(label)


sys.path.insert(0, "src")
sys.path.insert(0, os.path.join("..", "data", "src"))
from aec_api import pid_lock  # noqa: E402

# --- 1. STATIC: the bound exists and is applied in the only form that does not leak ----------------
#: Static because the behavioural arm below needs a server, and most invocations of this suite have
#: none. These two lines are then the ONLY thing standing between the tree and a silently unbounded
#: wait -- the same argument the sibling file makes for its blocking-form pin.
_RAW = Path("src/aec_api/pid_lock.py").read_text(encoding="utf-8")


def _code_only(src: str) -> str:
    """`src` with COMMENTS and docstrings removed, so these checks read the program, not its prose.

    Not cosmetic. The first draft of the `SET LOCAL` check below was
    `"SET LOCAL lock_timeout" in src and "SET lock_timeout" not in src` against the raw file -- and
    it FAILED on correct code, because the comment that explains why a plain `SET` is wrong contains
    the words `SET lock_timeout`. **A check that greps a source file is reading whatever a future
    author writes ABOUT the code alongside the code**, and prose is exactly where the forbidden form
    gets named. It can fail on a correct tree (as it did) or pass on a broken one, once somebody
    quotes the right string in a comment.
    """
    out, prev_tok = [], tokenize.INDENT
    for tok in tokenize.generate_tokens(io.StringIO(src).readline):
        if tok.type == tokenize.COMMENT:
            continue
        #: A STRING that is the whole statement is a docstring (or a stray expression); either way it
        #: is not code these checks should match on.
        if tok.type == tokenize.STRING and prev_tok in (tokenize.INDENT, tokenize.NEWLINE,
                                                        tokenize.NL, tokenize.DEDENT):
            prev_tok = tok.type
            continue
        out.append(tok.string)
        if tok.type not in (tokenize.NL, tokenize.NEWLINE, tokenize.INDENT, tokenize.DEDENT):
            prev_tok = tok.type
    return " ".join(out)


_SRC = _code_only(_RAW)

#: SELF-TEST, run before any verdict: the stripper must actually remove a comment naming the
#: forbidden form, and must NOT remove a real statement using it. Without both directions this is a
#: function that could return the input unchanged and every check below would still pass.
_probe = 'x = 1  # SET lock_timeout = bad\ndb.execute("SET LOCAL lock_timeout = 5")\n'
_stripped = _code_only(_probe)
check("the source stripper removes a comment that NAMES the forbidden form",
      "bad" not in _stripped, f"comment survived stripping: {_stripped!r}")
check("  ...while keeping a real statement that USES it",
      "SET LOCAL lock_timeout" in _stripped, f"code was stripped too: {_stripped!r}")

check("the acquisition sets a lock timeout at all",
      "lock_timeout" in _SRC, "no lock_timeout in pid_lock.py -- the wait is unbounded again")
check("  ...as SET LOCAL, not SET -- a plain SET is connection-scoped and rides the pool back out",
      "SET LOCAL lock_timeout" in _SRC and "SET lock_timeout" not in _SRC,
      "a connection-scoped SET imposes this timeout on unrelated queries that later draw the "
      "same pooled connection (measured: 1500ms still in force on the next checkout)")
check("  ...and the budget is INTERPOLATED, since `SET` rejects a bind parameter outright",
      "SET LOCAL lock_timeout = {" in _RAW,
      "a parameterised SET is a syntax error, which raises, degrades to in-process, and lets the "
      "write proceed unserialised -- the failure this change exists to prevent")
check("  ...and a lock timeout is told apart from an unreachable server by SQLSTATE",
      "55P03" in _SRC,
      "both raise OperationalError; without the sqlstate a timeout degrades to in-process and the "
      "write proceeds unserialised")
check("the budget is configurable, following the AEC_*_TIMEOUT_S convention",
      "AEC_PID_LOCK_TIMEOUT_S" in _SRC and isinstance(pid_lock.LOCK_TIMEOUT_S, int),
      "no env override, so a deployment cannot tune the wait")
check("refusal is a TimeoutError subclass, this tree's spelling for a budget overrun",
      issubclass(pid_lock.LockTimeout, TimeoutError),
      "callers that catch TimeoutError for sandbox/convert overruns would miss this one")

#: --- the four review findings, each pinned so it cannot come back ------------------------------
#: **The nested transaction is the one that mattered.** A session-level advisory lock lives on a
#: CONNECTION; committing a `with db.begin():` block returns this Session's connection to the pool,
#: so the unlock afterwards runs on whatever connection it next draws. Measured under contention:
#: the backend changed and `pg_advisory_unlock` returned FALSE, stranding the real lock. A static pin
#: because the behavioural arm cannot see it -- the lock still EXCLUDES; it is the release that
#: breaks, one caller later.
def _acquires_on(src: str) -> str:
    """What does `_advisory` take the advisory lock on -- a `Connection` or a `Session`?

    **This is the whole invariant, and it took two review rounds to state correctly.** A session-level
    advisory lock lives on a CONNECTION, so the lock's lifetime is that connection's lifetime. Two
    constraints pull in opposite directions and a `Session` cannot satisfy both:

      * end its transaction and the connection goes back to the pool -- measured: the backend changed
        between acquisition and unlock and `pg_advisory_unlock` returned FALSE, stranding the lock;
      * leave the transaction open across the yield and a deployment with
        `idle_in_transaction_session_timeout` kills the session mid-critical-section -- measured: with
        that timeout at 1 s and a 3 s section, a rival writer took the lock. A lost update.

    A checked-out `Connection` with a COMMITTED acquisition transaction satisfies both. So the thing
    to pin is the TYPE the lock is taken on, not the presence of a `begin()` block -- the first draft
    of this check forbade `with db.begin():` outright, which is now the correct code.

    Asked by AST. *The draft before that compared substrings against the comment-stripped source,
    where `_code_only` joins tokens with spaces -- so `"with db.begin()"` could never match however
    broken the code was. String LITERALS survive tokenising; CODE STRUCTURE does not.*
    """
    for node in ast.walk(ast.parse(src)):
        if not isinstance(node, ast.FunctionDef) or node.name != "_advisory":
            continue
        for inner in ast.walk(node):
            if not isinstance(inner, ast.Call):
                continue
            func = inner.func
            if isinstance(func, ast.Attribute) and func.attr == "connect" \
                    and isinstance(func.value, ast.Name) and func.value.id == "engine":
                return "connection"
            if isinstance(func, ast.Name) and func.id == "SessionLocal":
                return "session"
    return "unknown"


check("the advisory lock is taken on a checked-out Connection, not a Session",
      _acquires_on(_RAW) == "connection",
      f"_advisory acquires on a {_acquires_on(_RAW)}: a Session releases its connection when its "
      f"transaction ends (unlock then hits a different backend and returns False) and strands the "
      f"lock; keeping that transaction open instead exposes it to "
      f"idle_in_transaction_session_timeout, which kills the lock mid-critical-section")
#: SELF-TESTS, both directions: the detector must tell the two apart, or it is the substring check.
check("  ...and that detector reports `session` for the Session shape",
      _acquires_on("def _advisory(pid):\n    db = SessionLocal()\n") == "session",
      "the detector cannot see a Session acquisition")
check("  ...and `connection` for the Connection shape",
      _acquires_on("def _advisory(pid):\n    db = engine.connect()\n") == "connection",
      "the detector cannot see a Connection acquisition")

check("the budget is REFUSED when non-positive rather than defaulted",
      "must be positive" in _RAW,
      "lock_timeout = 0 is PostgreSQL's 'no timeout' (measured), so AEC_PID_LOCK_TIMEOUT_S=0 would "
      "silently restore the unbounded wait this setting exists to remove")
for _bad in ("0", "-5", "30s", "abc"):
    _raised = None
    os.environ["AEC_PID_LOCK_TIMEOUT_S"] = _bad
    try:
        pid_lock._lock_timeout_s()
    except BaseException as _e:                      # noqa: BLE001
        _raised = _e
    check(f"  ...and {_bad!r} is refused by name", isinstance(_raised, ValueError),
          f"raised {type(_raised).__name__ if _raised else 'nothing'}")
os.environ.pop("AEC_PID_LOCK_TIMEOUT_S", None)
check("  ...while ABSENT still means the default, so existing deployments are untouched",
      pid_lock._lock_timeout_s() == 30, "the unset default changed")

#: A 503 the caller can retry, not the generic 500 -- which would also file every contention event
#: in the error-log feed and Sentry as a server fault.
import aec_api.main as _main  # noqa: E402

check("LockTimeout is mapped to a response, not left to the generic 500 handler",
      pid_lock.LockTimeout in _main.app.exception_handlers,
      "`.env.example` promises a 503; without a handler this is a 500 and an error-log entry")

_MAIN = Path("src/aec_api/main.py").read_text(encoding="utf-8")
check("  ...and that response is 503 with Retry-After",
      "status_code=503" in _MAIN and "Retry-After" in _MAIN,
      "a retryable condition needs a status clients retry")

#: The documented scope must NOT claim more than the code bounds -- the in-process RLock is still
#: unbounded, and an operator reading only `.env.example` would not know.
_ENV = Path("../../.env.example").read_text(encoding="utf-8")
check("`.env.example` names the waits this budget does NOT bound",
      "in-process" in _ENV.lower() and "AEC_PID_LOCK_TIMEOUT_S" in _ENV,
      "the entry reads as bounding all waiting; two threads in ONE worker queue on the RLock "
      "first and never reach PostgreSQL")

# --- 2. BEHAVIOURAL: two real processes, one server -----------------------------------------------
_URL = os.environ.get("AEC_TEST_PG_URL") or (
    f"postgresql+psycopg://{os.environ.get('PGUSER', 'postgres')}@"
    f"{os.environ['PGHOST']}:{os.environ.get('PGPORT', '5432')}/"
    f"{os.environ.get('PGDATABASE', 'postgres')}"
    if os.environ.get("AEC_PG_REQUIRED") and os.environ.get("PGHOST") else None)

_CHILD = r"""
import os, sys, time
sys.path.insert(0, "src")
sys.path.insert(0, os.path.join("..", "data", "src"))
from aec_api import pid_lock

role, pid, logpath, hold = sys.argv[1:5]

def log(ev):
    with open(logpath, "a") as fh:
        fh.write("%s %s %.6f\n" % (role, ev, time.time()))

log("BACKEND=" + pid_lock.cross_process_status()["backend"])
t0 = time.monotonic()
try:
    with pid_lock.mutating(pid):
        log("IN")
        time.sleep(float(hold))
        log("OUT")
except pid_lock.LockTimeout as e:
    log("REFUSED=%.3f" % (time.monotonic() - t0))
except BaseException as e:
    log("OTHER=%s:%s" % (type(e).__name__, str(e)[:60].replace("\n", " ")))
"""

_arms: list[str] = []
if _URL:
    _dir = tempfile.mkdtemp(prefix="pidbound_")
    _log = os.path.join(_dir, "events.log")
    _script = os.path.join(_dir, "child.py")
    Path(_script).write_text(_CHILD, encoding="utf-8")

    _env = dict(os.environ, DATABASE_URL=_URL, AEC_PID_LOCK_TIMEOUT_S="2", PYTHONUTF8="1")
    _PROJ = f"bound-{os.getpid()}"

    #: A holds far longer than B's 2 s budget, so "B stopped" cannot be B simply outliving A.
    _a = subprocess.Popen([sys.executable, _script, "A", _PROJ, _log, "12"], env=_env)
    _t = time.time() + 30
    while time.time() < _t and "A IN" not in (Path(_log).read_text() if Path(_log).exists() else ""):
        time.sleep(0.05)

    _b0 = time.monotonic()
    _b = subprocess.run([sys.executable, _script, "B", _PROJ, _log, "0"], env=_env, timeout=60)
    _b_wall = time.monotonic() - _b0
    _a.wait(timeout=60)
    _ev = Path(_log).read_text(encoding="utf-8")
    _arms.append("two-process")

    #: `.split()` first: every line ends with the child's wall-clock stamp, so splitting on "="
    #: alone keeps it and the comparison below can never match. Cost one round.
    _backends = [ln.split()[1].split("=", 1)[1] for ln in _ev.splitlines() if "BACKEND=" in ln]
    check("both processes actually got the cross-process backend",
          len(_backends) == 2 and all(b == pid_lock.BACKEND_ADVISORY for b in _backends),
          f"backends were {_backends} -- an in-process-only run cannot measure any of this")

    _refused = [ln for ln in _ev.splitlines() if ln.startswith("B REFUSED=")]
    check("B is REFUSED rather than waiting out A's hold",
          bool(_refused),
          "B did not raise LockTimeout; events were: "
          + "; ".join(ln for ln in _ev.splitlines() if ln.startswith("B ")))
    if _refused:
        _waited = float(_refused[0].split()[1].split("=", 1)[1])
        check("  ...at roughly its 2 s budget, not at A's 12 s hold",
              1.0 < _waited < 6.0, f"B waited {_waited:.2f}s on a 2s budget against a 12s hold")
    check("  ...and B never entered the critical section",
          "B IN" not in _ev,
          "B ACQUIRED THE LOCK WHILE A HELD IT -- a refused wait that writes anyway is worse than "
          "an unbounded one (this is mutation M2's signature)")
    check("  ...and B's process still finished promptly",
          _b.returncode == 0 and _b_wall < 20, f"rc={_b.returncode}, wall={_b_wall:.1f}s")

    #: POSITIVE CONTROL. Without it, a lock that refused EVERY caller -- including uncontended ones --
    #: would pass every check above, and that is a total outage wearing the costume of a fix.
    _log2 = os.path.join(_dir, "solo.log")
    subprocess.run([sys.executable, _script, "C", f"{_PROJ}-solo", _log2, "0"],
                   env=_env, timeout=60)
    _ev2 = Path(_log2).read_text(encoding="utf-8")
    check("an UNCONTENDED writer still takes the lock normally",
          "C IN" in _ev2 and "C OUT" in _ev2 and "REFUSED" not in _ev2,
          f"uncontended writer did not complete: {_ev2.strip()!r}")

    #: THE LOCK MUST SURVIVE AN IDLE-IN-TRANSACTION TIMEOUT. A deployment (or a managed PostgreSQL
    #: role) that sets `idle_in_transaction_session_timeout` terminates a session sitting idle in a
    #: transaction -- and a session-level advisory lock dies with its session, MID critical section.
    #: A rival then enters: a lost update, which is the failure this lock exists to prevent.
    #: Reproduced against the pre-fix shape at 1 s / 3 s before this check was written; it is here so
    #: the shape cannot drift back. Static checks cannot see this -- the code looks identical either
    #: way, and only the transaction's STATE across the yield differs.
    from sqlalchemy import create_engine as _create_engine  # noqa: E402
    from sqlalchemy import text as _text  # noqa: E402
    from sqlalchemy.orm import sessionmaker as _sessionmaker  # noqa: E402

    import aec_api.pid_lock as _pl  # noqa: E402

    #: Set on the ROLE, not on a connection of ours and not on a named database.
    #:
    #: * not a plain `SET`: the GUC is per-session and `pid_lock` opens its OWN connection, so a
    #:   `SET` here lands on the wrong session entirely. *The first draft did exactly that and the
    #:   Session-shape mutation sailed through it -- the check passed whatever the code did.*
    #: * not `ALTER DATABASE <name>`: the second draft hardcoded `postgres`, which is neither the
    #:   database CI uses (`mig_runtime`) nor one its role owns -- CI failed with "must be owner of
    #:   database postgres". *A fixture that names an environment it was not written in is a fixture
    #:   that only works where it was written.*
    #:
    #: `ALTER ROLE CURRENT_USER` needs no ownership, interpolates no identifier, and applies to the
    #: role's NEW connections -- which is what `dispose()` below forces. It is also a fair model of
    #: the real hazard: a managed PostgreSQL imposing this per role or per database.
    #:
    #: THE ENGINE IS BUILT FROM `_URL`, NOT TAKEN FROM `aec_api.db`. The third draft read
    #: `aec_api.db.engine` -- the engine THIS process imported at startup -- and only the CHILD
    #: processes above are given `DATABASE_URL=_URL`. Locally the parent happened to carry a
    #: Postgres DSN too, so it passed; in CI the parent is SQLite and `ALTER ROLE` died with
    #: `near "ROLE": syntax error`. *Every arm above ran against the server and this one ran
    #: against a different database entirely -- inside the same `if _URL:` block that had just
    #: proved a server exists.* So the engine is constructed here and `aec_api.db` is re-pointed at
    #: it for the duration, because `_advisory` re-reads that attribute on every call.
    _pl_db = __import__("aec_api.db", fromlist=["engine"])
    _pl_eng = _create_engine(_URL, pool_pre_ping=True)
    check("the idle-timeout arm is wired to the SERVER, not to this process's default engine",
          _pl_eng.dialect.name == "postgresql",
          f"built {_pl_eng.dialect.name!r} from _URL -- this arm would measure a database that has "
          f"no advisory locks and no idle_in_transaction_session_timeout")
    _pl_saved = (_pl_db.engine, _pl_db.SessionLocal)
    _pl_db.engine = _pl_eng
    _pl_db.SessionLocal = _sessionmaker(bind=_pl_eng)
    with _pl_eng.connect() as _cfg:
        _cfg.execute(_text("ALTER ROLE CURRENT_USER SET idle_in_transaction_session_timeout = 1000"))
        _cfg.commit()
    _pl_eng.dispose()                          # force fresh connections that inherit the new setting
    _survived = None
    try:
        with _pl.mutating(f"{_PROJ}-idle"):
            time.sleep(3)                      # longer than the 1 s idle timeout above
            _rival = _pl_eng.connect()
            _survived = not _rival.execute(
                _text("SELECT pg_try_advisory_lock(:k)"),
                {"k": _pl.advisory_key(f"{_PROJ}-idle")}).scalar()
            if not _survived:
                _rival.execute(_text("SELECT pg_advisory_unlock(:k)"),
                               {"k": _pl.advisory_key(f"{_PROJ}-idle")})
                _rival.commit()
            _rival.close()
    except BaseException as _e:                # noqa: BLE001
        _survived = f"raised {type(_e).__name__}: {_e!s:.80}"
    with _pl_eng.connect() as _cfg:
        _cfg.execute(_text("ALTER ROLE CURRENT_USER RESET idle_in_transaction_session_timeout"))
        _cfg.commit()
    _pl_eng.dispose()
    _pl_db.engine, _pl_db.SessionLocal = _pl_saved      # leave the module as this file found it
    check("the lock survives a critical section longer than idle_in_transaction_session_timeout",
          _survived is True,
          f"a rival took the lock mid-section ({_survived}) -- the acquiring session was killed for "
          f"sitting idle in a transaction, and the advisory lock died with it: a LOST UPDATE")

check(f"at least one behavioural arm ran -- ran: {', '.join(_arms) or 'NONE (static only)'}",
      bool(_arms) or not os.environ.get("AEC_PG_REQUIRED"),
      "AEC_PG_REQUIRED is set but no two-process arm ran, so the bound was never exercised")

# --- 3. THE ARM THAT MATTERS RUNS SOMEWHERE -------------------------------------------------------
#: **Measured, not assumed: mutation M2 SURVIVES a static-only run.** Folding the lock timeout into
#: the degrade branch leaves `_SQLSTATE_LOCK_TIMEOUT` in the source, so every check in section 1
#: still passes while a contended write proceeds unserialised. Section 2 is the only thing that sees
#: it, and section 2 needs a server -- which the API test gate's job does not have.
#:
#: So this asserts the CI step that does have one is still there. Without it, deleting eleven lines
#: of YAML would silently retire the only check standing between this tree and that mutation, and
#: nothing would go red. *A gate whose real arm runs in one place is one deletion from being
#: decoration, and the deletion is in a different file from the gate.*
#:
#: The parse is deliberately small. `test_pid_lock_pgxproc.py` carries the fuller version -- it also
#: rejects a step made inert by `continue-on-error` or an `if:` -- and is not imported because that
#: module runs its checks at import time. *Duplication with a pointer beats an import with side
#: effects; the sibling is named so the next reader can see which is authoritative.*
_WF = Path("../../.github/workflows/db-migrations.yml")
_ME = "test_pid_lock_bound.py"
try:
    import yaml
    _doc = yaml.safe_load(_WF.read_text(encoding="utf-8"))
    _steps = [st for job in (_doc.get("jobs") or {}).values()
              for st in (job.get("steps") or [])
              if _ME in str(st.get("run", ""))]
except Exception as _e:                              # noqa: BLE001
    _steps, _err = [], _e
    print(f"      (workflow parse failed: {type(_e).__name__}: {_e})")

check("a CI step runs this file against a real server",
      bool(_steps),
      f"no step in {_WF.name} invokes {_ME}; the two-process arm then runs NOWHERE and the "
      f"degrade-branch mutation is ungated")
check("  ...with AEC_PG_REQUIRED, without which that step takes this file's static branch",
      bool(_steps) and any(str((st.get("env") or {}).get("AEC_PG_REQUIRED", "")) for st in _steps),
      "the step exists but does not opt in to a server, so it asserts only that it exists -- "
      "which is circular")

print()
print("test_pid_lock_bound " + ("FAILED - " + str(len(FAILED)) if FAILED else "OK"))
for f in FAILED:
    print("  - " + f)
sys.exit(1 if FAILED else 0)
