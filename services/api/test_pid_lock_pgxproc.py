"""LOCK-XPROC — does the advisory lock exclude two PROCESSES? Nothing asked until now.

`test_pid_lock_xproc.py` is named for cross-process serialisation and asserts a great deal about it,
but its one exclusion check — *"two threads do NOT interleave inside the lock"* — is **two threads,
in one process, on SQLite**, which is the suite's default database. On SQLite `_advisory()` takes
nothing at all and yields `False`; the exclusion that check observes is entirely the in-process
`threading.RLock`. So the `pg_advisory_lock` call that the whole item exists for is exercised by no
test in this tree, and `R35-PIDLOCK-XPROC` could have shipped acquiring nothing.

What that file *does* prove across processes is that the two workers derive the same **key**. That is
necessary and it is not sufficient: agreeing on a lock id says nothing about whether taking it
excludes anybody. *A test named for a property can assert every neighbouring property and never the
one in its name.*

## What this file asserts, and why each half is needed

Two real OS processes, each entering `pid_lock.mutating(pid)` against one PostgreSQL database:

  * **positive** — same project: their held intervals must not overlap;
  * **mutation A** — different projects: they MUST overlap. Without this the positive check passes
    on a machine that merely ran them in sequence, and a lock that excluded *everything* would look
    identical to one that excludes correctly;
  * **mutation B** — same project, with `advisory_key` monkeypatched in the child to a per-process
    random value: they MUST overlap. This is note 1 of the `pid_lock` module docstring — the
    `hash()` defect — reinstated across real processes, which is the only place it is visible.

Mutation A alone would pass against a lock that is a no-op *and* against the real one, because a
no-op never overlaps when the harness serialises them itself. Mutation B is the one that fails if the
lock stops locking. Both are here because they fail on different things.

## It must not be able to pass by doing nothing

A Postgres-only test that skips when there is no Postgres reports success on every developer machine
and is switched off in CI by deleting one workflow step. So with no server it asserts that
`.github/workflows/db-migrations.yml` still runs this file with `AEC_PG_REQUIRED` — the same
construction `test_pin_pgnull.py` uses, and for the same reason.

Run: `PYTHONPATH=src:../data/src python test_pid_lock_pgxproc.py`
  with a server: `PGHOST=... PGUSER=... AEC_PG_REQUIRED=1 python test_pid_lock_pgxproc.py`
"""
from __future__ import annotations

import ast
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid

sys.path.insert(0, "src")

FAILED: list[str] = []


def check(label: str, ok: bool, detail: object = "") -> None:
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   -- {detail}" if not ok and detail else ""))
    if not ok:
        FAILED.append(label)


#: The workflow that is supposed to run this file against a service container.
_WF = pathlib.Path("../../.github/workflows/db-migrations.yml")

# --- the acquisition must be the BLOCKING form, and this is checkable without a server ------------
#: `_advisory` sets `acquired = True` immediately after the execute and never reads a result, because
#: `pg_advisory_lock` returns void and cannot fail without raising. `pg_try_advisory_lock` returns a
#: boolean and does NOT wait — so swapping one for the other (an obvious-looking "don't block the
#: request" change) leaves the code reporting a lock it does not hold. The dependence is real and
#: invisible at the call site, so it is pinned rather than left to a reviewer.
#:
#: **What this check is NOT.** The first draft of this comment said the behavioural checks "would
#: still pass whenever the two processes happened not to collide", implying these two lines are the
#: only thing standing between the tree and that swap. Measured instead of assumed: with the swap
#: applied the exclusion check below ALSO reds, and deterministically — the harness starts B only
#: once A is demonstrably inside, so a non-waiting B always overlaps. Where a server exists this is
#: therefore redundant with behaviour. Its value is the run with NO server — every ordinary local
#: invocation, where the exclusion arm cannot run at all and these two lines are the only thing that
#: sees the swap. *A check earns its place from where it is the ONLY one, not from the worst case it
#: can be described as catching.*
_SRC = pathlib.Path("src/aec_api/pid_lock.py").read_text(encoding="utf-8")
check("the acquisition is the BLOCKING pg_advisory_lock",
      "pg_advisory_lock(:k)" in _SRC, "acquisition SQL changed")
check("  and NOT a try_ variant, whose false return this code would never read",
      "pg_try_advisory_lock" not in _SRC,
      "pid_lock uses pg_try_advisory_lock but sets acquired=True without reading the result")


def _url() -> str | None:
    """A libpq-style URL, or None when this run has not OPTED IN to reaching a server.

    Ambient `PG*` is not consent — `run_tests.py` forwards the whole environment to every suite, so
    reading `PGHOST` alone would have an ordinary suite run take advisory locks in whatever database
    those variables happen to name. Same opt-in as `test_pin_pgnull.py`."""
    if os.environ.get("AEC_TEST_PG_URL"):
        return os.environ["AEC_TEST_PG_URL"]
    if not os.environ.get("AEC_PG_REQUIRED"):
        return None
    if not os.environ.get("PGHOST"):
        return None                      # required but unaddressable — failed on below, not skipped
    host = os.environ["PGHOST"]
    port = os.environ.get("PGPORT", "5432")
    user = os.environ.get("PGUSER", "postgres")
    dbn = os.environ.get("PGDATABASE", "postgres")
    #: NO PASSWORD IN THE URL. libpq reads `PGPASSWORD` from the environment, which the children
    #: already inherit, so embedding it here bought nothing and put the credential into a string that
    #: is passed to subprocesses, set as `DATABASE_URL`, and printed on failure.
    #:
    #: Two rounds were spent redacting that string at its sinks before this. Both redactions were
    #: correct and neither cleared the alert, because CodeQL traces the FLOW from the environment read
    #: to the printer and `str.replace` changes the value without removing the edge. *Sanitising a
    #: sink answers "is this output safe"; removing the source answers "is this value sensitive at
    #: all", and only the second makes the question stop existing.* The scrubbers below are kept as
    #: defence in depth. **Precisely: `_safe` redacts userinfo AND a `password=`/`PGPASSWORD=` query
    #: parameter; `_scrub` removes the value of `PGPASSWORD` from child output and derives nothing
    #: from `AEC_TEST_PG_URL`.** The earlier wording here said they "cover a caller-supplied URL",
    #: which was wider than the code — review caught the query-string gap, and the sentence was as
    #: wrong as the function. *A claim about a guard's coverage is a claim like any other.*
    auth = f"{user}@"
    if host.startswith("/"):
        return f"postgresql+psycopg://{auth}/{dbn}?host={host}&port={port}"
    return f"postgresql+psycopg://{auth}{host}:{port}/{dbn}"


def _safe(url: str) -> str:
    """`url` with any password removed, for anything that could reach a log.

    The connect-failure message below printed the DSN verbatim, so a wrong port or an unreachable
    service container would have written `PGPASSWORD` into the CI log in clear text -- flagged HIGH
    by CodeQL on the first push of this file. **A diagnostic is an output like any other**, and the
    string most worth printing when a connection fails is exactly the one carrying the credential.

    Splits on the LAST `@` before the host, not the first: a password may legitimately contain `@`,
    and `partition` would then keep part of it. Everything after the scheme and before that `@` is
    replaced wholesale rather than trying to preserve the username -- the username is not what makes
    the message useful, the host and port are.
    """
    #: The QUERY STRING too, not only the userinfo. libpq accepts the password as a parameter --
    #: `?password=...`, and psycopg passes `PGPASSWORD=` through the same way -- so a caller-supplied
    #: `AEC_TEST_PG_URL` can carry the secret somewhere the `@` split never looks. Raised in review
    #: against a claim in this file's own comment that these helpers "cover a caller-supplied URL";
    #: they did not, and the claim was wider than the code. *Stating a guard's coverage is a claim
    #: like any other and is checkable the same way.*
    url = re.sub(r"(?i)\b(password|pgpassword)=[^&\s]*", r"\1=***", url)
    scheme, sep, rest = url.partition("://")
    if not sep or "@" not in rest:
        return url
    return f"{scheme}://***@{rest.rsplit('@', 1)[1]}"


#: Consulted on EVERY path below, not only inside `if _u:` — the defect `test_pin_pgnull` records is
#: a flag that guards one branch of two and therefore guards nothing.
_REQUIRED = bool(os.environ.get("AEC_PG_REQUIRED") or os.environ.get("AEC_TEST_PG_URL"))

#: The child. Takes the lock, records when it was inside, and reports which backend it actually got —
#: so a run that silently fell back to in-process serialisation says so instead of failing as though
#: the lock were broken.
_CHILD = r"""
import os, sys, time
sys.path.insert(0, "src")
sys.path.insert(0, os.path.join("..", "data", "src"))
from aec_api import pid_lock

name, pid, logpath, hold, mode = sys.argv[1:6]

if mode == "randomkey":
    # note 1 of the pid_lock module docstring: a key that varies per process. Every worker takes a
    # DIFFERENT advisory lock, so none ever collide and the lock serialises nothing.
    import random
    _k = random.getrandbits(63)
    pid_lock.advisory_key = lambda _p, _k=_k: _k

def log(event):
    with open(logpath, "a") as fh:
        fh.write("%s %s %.6f\n" % (name, event, time.time()))

log("BACKEND=" + pid_lock.cross_process_status()["backend"])
with pid_lock.mutating(pid):
    log("IN")
    time.sleep(float(hold))
    log("OUT")
"""


def _probe_url() -> str | None:
    """`_url()` evaluated with `PGPASSWORD` set, so the assertion below cannot pass by the variable
    simply being absent -- the vacuous shape this file already made once today."""
    keep = {k: os.environ.get(k) for k in ("AEC_TEST_PG_URL", "AEC_PG_REQUIRED", "PGHOST", "PGPASSWORD")}
    try:
        os.environ.pop("AEC_TEST_PG_URL", None)
        os.environ["AEC_PG_REQUIRED"] = "1"
        os.environ["PGHOST"] = "probe-host"
        os.environ["PGPASSWORD"] = "sekret-not-in-url"
        return _url()
    finally:
        for k, v in keep.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v


def _scrub(text: str, pwd: str | None = None) -> str:
    """The Postgres password removed from captured CHILD output, at the capture boundary.

    The children are handed the DSN through `DATABASE_URL` in their environment, and their stdout and
    stderr are reported in a failure detail below. That is a second path from the credential to the
    log, distinct from the connect-failure message `_safe` covers, and CodeQL flagged it as one HIGH
    after the other was fixed. *Fixing the sink that was reported closes that sink* — the same shape
    this branch's own lock work keeps running into, arriving here in the security rules.

    Scrubbed where the text is CAPTURED rather than where it is printed, so a future `print(outs)`
    anywhere downstream cannot reintroduce it. A sanitiser applied at each sink is a list that has to
    stay complete; one applied at the boundary is a property of the value.
    """
    secret = os.environ.get("PGPASSWORD", "") if pwd is None else pwd
    return text.replace(secret, "***") if secret else text


def _run_pair(url: str, pid_a: str, pid_b: str, mode_b: str, hold: float = 1.5):
    """Start A, wait until it is demonstrably inside the lock, then start B. Returns the log lines.

    B is started only after A is INSIDE — otherwise a B that ran to completion before A ever acquired
    would prove nothing either way, and the positive check would be measuring process startup."""
    # OUTSIDE the repository, deliberately. A scratch file under `services/api` that a crashed run
    # left behind reads in `git status` exactly like uncommitted work -- the defect
    # `test_scratch_ignored.py` exists for. `tempfile` puts it where nothing here has to ignore it.
    log = pathlib.Path(tempfile.mkdtemp(prefix="pgxproc_")) / "events.log"
    log.write_text("", encoding="utf-8")
    env = {**os.environ, "DATABASE_URL": url, "PYTHONPATH": "src:../data/src"}

    def spawn(name, pid, hold_s, mode):
        return subprocess.Popen([sys.executable, "-c", _CHILD, name, pid, str(log), str(hold_s), mode],
                                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

    a = spawn("A", pid_a, hold, "plain")
    deadline = time.time() + 45
    while time.time() < deadline:
        if " IN " in log.read_text(encoding="utf-8"):
            break
        if a.poll() is not None:
            break
        time.sleep(0.02)
    b = spawn("B", pid_b, 0.05, mode_b)
    outs = {}
    for name, proc in (("A", a), ("B", b)):
        try:
            o, e = proc.communicate(timeout=90)
        except subprocess.TimeoutExpired:
            proc.kill()
            o, e = proc.communicate()
            e = (e or "") + " [KILLED after 90s]"
        #: Scrubbed HERE, not at the print: the value carries the property from the moment it exists.
        outs[name] = (proc.returncode, _scrub(o or ""), _scrub(e or ""))
    lines = [ln.split() for ln in log.read_text(encoding="utf-8").splitlines() if ln.strip()]
    shutil.rmtree(log.parent, ignore_errors=True)
    return lines, outs


def _intervals(lines):
    """{name: (in, out)} for every child that completed a full held interval."""
    marks: dict[str, dict[str, float]] = {}
    for parts in lines:
        if len(parts) == 3 and parts[1] in ("IN", "OUT"):
            marks.setdefault(parts[0], {})[parts[1]] = float(parts[2])
    return {n: (m["IN"], m["OUT"]) for n, m in marks.items() if "IN" in m and "OUT" in m}


def _overlap(iv) -> bool:
    """Were A and B inside their locks at the same instant?"""
    if set(iv) != {"A", "B"}:
        return False
    (ai, ao), (bi, bo) = iv["A"], iv["B"]
    return ai < bo and bi < ao


def _backends(lines) -> set[str]:
    return {p[1].split("=", 1)[1] for p in lines if len(p) == 3 and p[1].startswith("BACKEND=")}


#: THE REDACTION IS ASSERTED, not assumed. A helper that silently stopped redacting would restore the
#: exact CodeQL HIGH it was written for, and the only place it runs is a failure path that a green run
#: never takes -- so without these it would be exercised by nothing until the day it mattered.
#: *A guard that only runs when something has already gone wrong needs a test that runs always.*
#: The password is a PARAMETER here, not read from the environment -- the first draft of this check
#: was `... if os.environ.get("PGPASSWORD") == "sekret" else True`, which passes vacuously on every
#: ordinary run. That is the same shape as the `web_files()` sortedness assertion this branch's own
#: CHANGELOG records: *a check that passes because its population is empty has the same shape as one
#: that passes because the code is correct.* Caught before it was pushed, by the entry about it.
check("captured child output carries no password either -- the SECOND path from the credential to "
      "the log, flagged by CodeQL only after the first was fixed; scrubbed at CAPTURE so no later "
      "print can reintroduce it",
      _scrub("psycopg.OperationalError: ... password=sekret failed", pwd="sekret")
      == "psycopg.OperationalError: ... password=*** failed",
      _scrub("psycopg.OperationalError: ... password=sekret failed", pwd="sekret"))
check("  ...and an empty password scrubs nothing rather than replacing every empty string in the "
      "output, which `str.replace('', ...)` would do to every character boundary",
      _scrub("no credentials here", pwd="") == "no credentials here",
      _scrub("no credentials here", pwd=""))
#: AND THE CAPTURE BOUNDARY IS PINNED BY READING THIS FILE. The two checks above exercise `_scrub`
#: directly; NEITHER reds if somebody removes the call in `_run_pair`, because that function only runs
#: when a real server is reachable and the no-server run never reaches it. So the guard with the
#: widest blast radius was the one nothing asserted -- *a check that exercises the helper is not a
#: check that the helper is CALLED.* This reads the assignment itself and requires both captured
#: streams to pass through it.
_OUTS = next(
    (n for n in ast.walk(ast.parse(pathlib.Path(__file__).read_text(encoding="utf-8")))
     if isinstance(n, ast.Assign) and isinstance(n.value, ast.Tuple)
     and any(isinstance(tgt, ast.Subscript) and getattr(tgt.value, "id", "") == "outs"
             for tgt in n.targets)),
    None)
_SCRUBBED = [e for e in (_OUTS.value.elts[1:] if _OUTS else [])
             if isinstance(e, ast.Call) and getattr(e.func, "id", "") == "_scrub"]
check("child stdout AND stderr are both scrubbed where they are CAPTURED -- asserted from this "
      "file's own source, because `_run_pair` never runs on a machine with no PostgreSQL server and "
      "so no behavioural check here can reach it",
      _OUTS is not None and len(_SCRUBBED) == 2,
      f"found={'no outs[...] tuple assignment' if _OUTS is None else len(_SCRUBBED)} scrubbed of 2 "
      "-- a stream captured raw reaches the failure detail below unredacted")

#: The URL this file BUILDS never carries a credential in the first place, so there is nothing for the
#: scrubbers below to remove on the path that actually runs. Asserted directly, because the fix is an
#: absence and an absence is what nobody notices being undone.
check("the DSN built from PG* env vars embeds NO password -- libpq reads `PGPASSWORD` from the "
      "environment the children already inherit, so putting it in the URL bought nothing and put the "
      "credential into a string that is printed on failure",
      "sekret-not-in-url" not in (_probe_url() or ""),
      _probe_url())

check("the connect-failure message carries no password -- plain case",
      _safe("postgresql+psycopg://u:hunter2@db:5432/x") == "postgresql+psycopg://***@db:5432/x",
      _safe("postgresql+psycopg://u:hunter2@db:5432/x"))
check("  ...and a password containing `@` is removed WHOLE -- splitting on the first `@` would leave "
      "the tail of the secret in the log, which is not redaction",
      _safe("postgresql+psycopg://u:p@ss@db:5432/x") == "postgresql+psycopg://***@db:5432/x",
      _safe("postgresql+psycopg://u:p@ss@db:5432/x"))
check("  ...and a password carried as a QUERY PARAMETER is redacted too -- libpq accepts it there, "
      "so a caller-supplied `AEC_TEST_PG_URL` can put the secret where the `@` split never looks",
      _safe("postgresql+psycopg://u@db:5432/x?password=hunter2&sslmode=require")
      == "postgresql+psycopg://***@db:5432/x?password=***&sslmode=require",
      _safe("postgresql+psycopg://u@db:5432/x?password=hunter2&sslmode=require"))
check("  ...and the parameter redaction stops at the `&`, so the rest of the query survives and the "
      "message stays diagnosable",
      "sslmode=require" in _safe("postgresql://u@h/d?password=p&sslmode=require"),
      _safe("postgresql://u@h/d?password=p&sslmode=require"))
check("  ...and a URL with no credentials is passed through unchanged, so the message stays useful "
      "in the ordinary case",
      _safe("postgresql+psycopg://db:5432/x") == "postgresql+psycopg://db:5432/x",
      _safe("postgresql+psycopg://db:5432/x"))

_u = _url()
if _u:
    try:
        import sqlalchemy as _sa
        _eng = _sa.create_engine(_u)
        with _eng.connect() as _c:
            _c.execute(_sa.text("SELECT 1"))
        _eng.dispose()
    except Exception as exc:                              # noqa: BLE001 — any driver/connect error
        # UNCONDITIONAL: `_url()` returns a URL only under an explicit opt-in, so by here somebody has
        # already said "reach a server". Gating this on the flag again would let a run pointed at a
        # dead port exit 0 while printing "no opt-in" — asserting the opposite of what happened.
        check("the opted-in PostgreSQL server is reachable", False,
              f"{_safe(_u)} -- {type(exc).__name__}: {exc}")
        _u = None

if _u:
    PID = f"xproc-{uuid.uuid4().hex[:12]}"
    OTHER = f"xproc-{uuid.uuid4().hex[:12]}"

    # --- positive: same project, two processes, must NOT overlap --------------------------------
    lines, outs = _run_pair(_u, PID, PID, "plain")
    iv = _intervals(lines)
    check("both child PROCESSES entered and left the lock",
          set(iv) == {"A", "B"}, f"intervals={iv} procs={outs}")
    # Deliberately narrow, because the honest scope of this one is easy to overstate and a mutation
    # that removed the acquisition outright left it PASSING: `cross_process_status()` reports the
    # DIALECT, so it says the advisory path was available, never that a lock was taken. What proves
    # acquisition is the next check.
    check("  both children ran on an engine where the advisory path is available at all",
          _backends(lines) == {"postgres_advisory"}, f"backends={_backends(lines)}")
    check("two PROCESSES holding one project's lock do not overlap -- the advisory lock excludes "
          "across processes, which no existing test asked",
          set(iv) == {"A", "B"} and not _overlap(iv), f"intervals={iv}")

    # --- mutation A: different projects, must overlap ------------------------------------------
    # Without this the check above passes against a harness that merely ran them in sequence, and
    # against a lock so coarse it excludes unrelated projects.
    lines_a, outs_a = _run_pair(_u, PID, OTHER, "plain")
    iv_a = _intervals(lines_a)
    check("MUTATION A: two DIFFERENT projects DO overlap -- so the check above measures the lock "
          "rather than the order this harness starts things in, and the lock is per-project",
          _overlap(iv_a), f"intervals={iv_a} procs={outs_a}")

    # --- mutation B: the per-process key, across real processes --------------------------------
    lines_b, outs_b = _run_pair(_u, PID, PID, "randomkey")
    iv_b = _intervals(lines_b)
    check("MUTATION B: a per-process advisory key (the `hash()` defect, note 1) lets two processes "
          "into one project's lock at once -- so the positive check fails when the lock stops locking",
          _overlap(iv_b), f"intervals={iv_b} procs={outs_b}")
else:
    if _REQUIRED:
        check("AEC_PG_REQUIRED/AEC_TEST_PG_URL was set but no server could be addressed",
              False, "set PGHOST (and PGUSER/PGPASSWORD/PGDATABASE) or AEC_TEST_PG_URL")
    # NO SERVER. Do not pass quietly -- prove the step that DOES run this is still in the workflow.
    check("db-migrations.yml exists to be checked", _WF.exists(), str(_WF))
    _text = _WF.read_text(encoding="utf-8") if _WF.exists() else ""
    check("db-migrations.yml still runs this file against the service container",
          "test_pid_lock_pgxproc.py" in _text,
          f"{_WF} no longer mentions test_pid_lock_pgxproc.py -- with no server here and no step "
          f"there, the advisory lock is exercised by nothing anywhere")
    check("  and sets AEC_PG_REQUIRED, without which that step takes THIS branch",
          "AEC_PG_REQUIRED" in _text,
          f"{_WF} does not set AEC_PG_REQUIRED -- the CI run would assert only that the workflow "
          f"mentions the file, which is circular")
    print("\n  no PostgreSQL server: the cross-process assertions did not run here.")
    print("  They run in db-migrations.yml, which the checks above prove still invokes this file.")

print()
if FAILED:
    print(f"test_pid_lock_pgxproc FAILED - {len(FAILED)}")
    for f in FAILED:
        print("  -", f)
    sys.exit(1)
print("test_pid_lock_pgxproc OK")
