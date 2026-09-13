"""PIN-SWEEP-PGNULL — the pin sweep, against a REAL PostgreSQL driver.

`test_pin_empty.py` already asserts this defect behaviourally, on every run, by registering a
sqlite3 converter so the driver decodes JSON columns the way psycopg does. That is the mechanism
faithfully — the dialect was never the cause, the DRIVER DECODING the column is — but it is a
reproduction, and the thing it reproduces is a claim about somebody else's driver. This file is
where that claim is checked against the driver itself.

What it seeds is the four representations a `json` pin column can actually hold in production:

    sqlnull    SQL NULL            absent; must stay absent
    jsonnull   the scalar `null`   non-NULL in SQL, decodes to Python None -- THE ROW AT ISSUE
    empty      `{}`                non-NULL, fails `pins.pin_fields`; the ground earlier sweeps held
    real       a placed anchor     must survive

`b3c9e42d18a5` converts `empty` and walks past `jsonnull`, reporting `changed=1` with an empty
`SKIPPED` -- a clean-looking run that left every legacy row exactly as it found it.
`d7f1a5c3e094` converts both.

**This file must not be able to pass by doing nothing.** A Postgres-only test that skips when there
is no Postgres is a test that reports success on every developer machine and can be silently
switched off in CI by deleting one workflow step. So when it cannot reach a server it does not
simply pass: it asserts that `.github/workflows/db-migrations.yml` still runs this file against the
service container, by reading the workflow. Deleting the step turns the local run red.

Run: `PYTHONPATH=src:../data/src python test_pin_pgnull.py`
  with a server: `PGHOST=... PGPORT=... PGUSER=... PGPASSWORD=... AEC_PG_REQUIRED=1 python test_pin_pgnull.py`
"""
from __future__ import annotations

import importlib.util
import os
import pathlib
import sys

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    if not ok:
        FAILED.append(f"{name} — {detail}")


def _load(path: str):
    p = pathlib.Path(path)
    spec = importlib.util.spec_from_file_location(p.stem, p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_OLD = "migrations/versions/2026_09_10_1700-b3c9e42d18a5_pin_anchor_register_sweep.py"
_NEW = "migrations/versions/2026_09_13_1210-d7f1a5c3e094_pin_sweep_sql_null_state.py"
check("the migration under test exists", pathlib.Path(_NEW).exists(), _NEW)
check("the migration it corrects exists", pathlib.Path(_OLD).exists(), _OLD)
if FAILED:
    print("FAIL test_pin_pgnull")
    for f in FAILED:
        print("  -", f)
    sys.exit(1)

#: The workflow that is supposed to run this file with a Postgres service container.
_WF = pathlib.Path("../../.github/workflows/db-migrations.yml")

#: Seed rows: (id, anchor value as JSON TEXT or None-for-SQL-NULL, must_end_up_sql_null)
_ROWS = (
    ("sqlnull",  None,                       True),
    ("jsonnull", "null",                     True),
    ("empty",    "{}",                       True),
    ("real",     '{"x": 1, "y": 2, "z": 3}', False),
)


def _url() -> str | None:
    """A libpq-style URL, or None when this run has not OPTED IN to writing to a database.

    **Ambient `PG*` is not consent.** This script does `CREATE TABLE` / `DROP TABLE`, and
    `run_tests.py` forwards the whole environment to every suite (`base = {**os.environ, ...}`) — so
    reading `PGHOST` on its own meant an ordinary suite run, on any machine with `PG*` exported for
    unrelated work, would create and drop probe tables in whatever database those variables happened
    to point at (`PGDATABASE` defaults to `postgres`). That is the hazard class
    `test_db_url_isolation.py` exists to prevent, arriving through a door it does not watch.

    So the opt-in is explicit and must be deliberate: either `AEC_TEST_PG_URL` names the target
    outright, or `AEC_PG_REQUIRED` says this run is the one that is supposed to reach a server — which
    is what `db-migrations.yml` sets, beside a `PGDATABASE` naming a throwaway database it created.
    """
    if os.environ.get("AEC_TEST_PG_URL"):
        return os.environ["AEC_TEST_PG_URL"]
    if not os.environ.get("AEC_PG_REQUIRED"):
        return None                      # ambient PG* alone is not permission to write
    if not os.environ.get("PGHOST"):
        return None                      # required but unaddressable — the caller below fails on it
    host = os.environ["PGHOST"]
    port = os.environ.get("PGPORT", "5432")
    user = os.environ.get("PGUSER", "postgres")
    pwd = os.environ.get("PGPASSWORD", "")
    db = os.environ.get("PGDATABASE", "postgres")
    auth = f"{user}:{pwd}@" if pwd else f"{user}@"
    # A socket directory rather than a hostname goes in the query string, as libpq expects.
    if host.startswith("/"):
        return f"postgresql+psycopg://{auth}/{db}?host={host}&port={port}"
    return f"postgresql+psycopg://{auth}{host}:{port}/{db}"


def _sweep_fixture(sa, engine, mod, table: str):
    """Create `table`, seed `_ROWS`, sweep `anchor`, return (changed, {id: is_sql_null}, SKIPPED)."""
    mod.SKIPPED.clear()
    with engine.begin() as conn:
        conn.execute(sa.text(f"DROP TABLE IF EXISTS {table}"))
        conn.execute(sa.text(f"CREATE TABLE {table} (id text PRIMARY KEY, anchor json)"))
        for rid, val, _ in _ROWS:
            conn.execute(sa.text(f"INSERT INTO {table} (id, anchor) VALUES (:i, CAST(:v AS json))"),
                         {"i": rid, "v": val})
    with engine.begin() as conn:
        changed = mod._sweep(conn, table, ("anchor",))
        state = {r[0]: bool(r[1]) for r in conn.execute(
            sa.text(f"SELECT id, anchor IS NULL FROM {table}"))}
    with engine.begin() as conn:
        conn.execute(sa.text(f"DROP TABLE IF EXISTS {table}"))
    skipped = sorted(mod.SKIPPED)
    mod.SKIPPED.clear()
    return changed, state, skipped


#: Does this run claim it will reach a server? Read ONCE, and consulted on every path below —
#: **the first version of this file only consulted it inside `if _u:`**, so with the variable set and
#: no `PGHOST` to build a URL from, `_url()` returned None, the no-server branch ran, and the script
#: exited 0. Clearing or renaming the job-level `PGHOST` would then have left a green CI step whose
#: only assertion was that the step itself existed — exactly the circularity the workflow comment
#: claims this design avoids. A flag that guards one branch of two guards nothing.
_REQUIRED = bool(os.environ.get("AEC_PG_REQUIRED"))

_u = _url()
_engine = None
if _u:
    try:
        import sqlalchemy as _sa
        _engine = _sa.create_engine(_u)
        with _engine.connect() as _c:
            _c.execute(_sa.text("SELECT 1"))
    except Exception as exc:                              # noqa: BLE001 — any driver/connect error
        # UNCONDITIONAL, and the `if _REQUIRED:` that used to stand here was the SAME defect the
        # comment above `_REQUIRED` describes, one flag along. `_url()` returns a URL only under an
        # explicit opt-in — `AEC_TEST_PG_URL`, or `AEC_PG_REQUIRED` plus a `PGHOST` to build one
        # from — so by the time this branch runs, somebody has already said "reach a server". Gating
        # the failure on the *second* of those two opt-ins meant a run that set only
        # `AEC_TEST_PG_URL`, at a dead port, exited 0 and printed **"no opt-in"** — asserting the
        # opposite of what had just happened. Measured before the fix, not reasoned about:
        # `AEC_TEST_PG_URL=postgresql+psycopg://postgres@127.0.0.1:1/nope` with `AEC_PG_REQUIRED`
        # unset gave `test_pin_pgnull OK (no opt-in; ...)` and exit 0.
        #
        # *A message that names the wrong cause is worse than a bare failure, because somebody acts
        # on it* — the reader would have gone looking for the missing opt-in they had just supplied.
        # Found by review on #548 and fixed after that PR merged; it sat in the review BODY rather
        # than an inline thread, which is how it survived two rounds that fixed everything inline.
        check("a PostgreSQL that this run explicitly asked for must be REACHABLE", False,
              f"{_u} — {type(exc).__name__}: {exc}")
        _engine = None
elif _REQUIRED:
    check("AEC_PG_REQUIRED is set, so a PostgreSQL must be ADDRESSABLE", False,
          "neither AEC_TEST_PG_URL nor PGHOST is set, so no server could even be attempted — this "
          "run was told it is the one that checks the sweep against a real driver, and it is not")

if _engine is not None:
    _new = _load(_NEW)
    _old = _load(_OLD)

    _ch, _st, _sk = _sweep_fixture(_sa, _engine, _new, "pgnull_probe_new")
    for _rid, _val, _want_null in _ROWS:
        check(f"d7f1a5c3e094: {_rid!r} ends SQL NULL={_want_null}", _st[_rid] is _want_null,
              f"got {_st[_rid]} — seeded as {_val!r}; state={_st!r}")
    check("d7f1a5c3e094: the count is what actually changed", _ch == 2,
          f"changed={_ch}, expected 2 — the `jsonnull` and `empty` rows. NOTE the unit: this fixture "
          f"seeds one column, so rows and column-values coincide here. They do not in general — see "
          f"the both-columns case in test_pin_empty.py, where this migration returns 2 for ONE row "
          f"and b3c9e42d18a5 returns 1")
    check("d7f1a5c3e094: neither empty form is misreported as uninterpretable", _sk == [],
          f"SKIPPED={_sk!r}")

    # The negative, and it is the migration in `main` rather than a contrivance. If this ever stops
    # failing, the check above is measuring nothing — or somebody edited a migration that has run.
    _cho, _sto, _sko = _sweep_fixture(_sa, _engine, _old, "pgnull_probe_old")
    check("b3c9e42d18a5 LEAVES the JSON scalar `null` behind — the defect, against the real driver",
          _sto["jsonnull"] is False,
          f"state={_sto!r} — if psycopg no longer decodes `null` to Python None, or the migration "
          f"was edited, then the assertion above proves nothing")
    check("b3c9e42d18a5: ...while sweeping the empty object, so its run looked clean",
          _sto["empty"] is True, f"state={_sto!r}")
    check("b3c9e42d18a5: ...and reported nothing at all about the row it walked past", _sko == [],
          f"SKIPPED={_sko!r} — the silence is why this survived review and a deploy")
    check("b3c9e42d18a5: ...and a real anchor did survive it", _sto["real"] is False,
          f"state={_sto!r}")
    _ran = "against PostgreSQL"
else:
    # NO SERVER. Do not pass quietly — prove the step that DOES run this is still in the workflow.
    check("db-migrations.yml exists to be checked", _WF.exists(), str(_WF))
    _text = _WF.read_text(encoding="utf-8") if _WF.exists() else ""
    check("CI still runs this file against the Postgres service container",
          "test_pin_pgnull.py" in _text,
          f"{_WF} no longer mentions test_pin_pgnull.py — with no server here and no step there, "
          f"this file would assert nothing anywhere, which is the only way it can be wrong")
    check("...and runs it with AEC_PG_REQUIRED, so a missing server there is a failure",
          "AEC_PG_REQUIRED" in _text,
          f"{_WF} does not set AEC_PG_REQUIRED — without it the CI run would take this same "
          f"no-server branch and assert only that the workflow mentions the file")
    _ran = "no opt-in; asserted the CI step that runs it for real still exists"

if FAILED:
    print("FAIL test_pin_pgnull")
    for f in FAILED:
        print("  -", f)
    sys.exit(1)
print(f"test_pin_pgnull OK  ({_ran})")
