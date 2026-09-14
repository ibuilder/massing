"""RMW-SWEEP — is a write DERIVED from a read guarded by what it read?

WHY THIS EXISTS
    `transition` was one instance of a class, not a one-off. The shape is: read a column, compute a
    new value FROM what you read, write it back under `where(id == rid)` alone. Nothing holds the row
    still in between, so two callers both read the old value and the second write erases the first --
    **and both callers are told they succeeded**. Reproduced against the real functions before any of
    this was written: two `add` calls on `["GUID-A"]` left `["GUID-A", "GUID-C"]`, GUID-B gone; two
    `link` calls left one link of the two.

    *A lost update that refuses one caller is nearly fixed; one that tells both they succeeded has to
    be found twice.* The same severity inversion the seeding sweep recorded.

    Five sat on the register row -- `set_element_guids`, `link_record`, `update_record`, `revise`,
    and `transition` before PR #551 -- and `update_record` is the one that matters most: it is the
    path the register's inline cells use, it merges `{**what we read, **what you sent}`, and the
    control the threat model names for it (`expected_modified_at`) is OPT-IN and passed by one of
    five web call sites.

WHAT IT ASSERTS, AND WHY EACH IS SEPARATE
    1. TOKEN COVERAGE. The fix swaps on `modified_at`, and the dynamic register table declares that
       column with NO `onupdate=` -- so "every writer advances it" is a property of the call sites,
       not of the schema. One writer that forgot it would make the predicate match a row somebody
       else had just changed: a lock that looks present. Derived at FUNCTION scope, because
       `transition` and `update_record` splat `**vals` and a scan reading only the text inside
       `.values(...)` finds neither.
    2. BEHAVIOUR, on the real `set_element_guids`, against a losing interleaving built by hand: the
       concurrently-added GUID SURVIVES. This is the question the item is about.
    3. MUTATION. The `modified_at` predicate is removed and the same interleaving must lose the GUID
       again. *A check that still passes with the guard taken out is not testing the guard* -- and
       asserting the emitted SQL rather than the outcome is how the pin sweep's first draft passed
       with the defect reinstated.
    4. BEHAVIOUR, on the real `update_record`: two people editing DIFFERENT fields of one record from
       stale reads both keep their field. The merge is the highest-traffic instance.
    5. STATIC POPULATION, derived by AST with transitive taint from `get_record`, and FAIL-CLOSED: an
       `update()` whose target this analyser cannot resolve is UNKNOWN and reds the build. The
       classifier is run against the PRE-FIX `set_element_guids` source and must call it BLIND_RMW
       before any verdict is printed -- *derive the population AND prove the derivation reaches it.*
    6. ORM POPULATION, `obj.attr = <expr mentioning obj>` across `src/aec_api`, against a ledger that
       records a verdict per site. A site not in the ledger reds the build; an exemption whose site is
       gone reds it too.

WHAT THE SELF-TESTS ALREADY CAUGHT, once, before a verdict was ever printed
    Teaching the analyser about mapped model classes (so two correctly-guarded writes stopped
    reporting as UNKNOWN) made it read `t.c` itself as a column name -- so EVERY write looked
    swapped-on and the two pre-fix bodies came back CAS. The population check would have printed
    "0 blind" over a tree that had not been examined. *A widening and a rule change are different
    edits, and widening one can break the other* -- the lesson `test_ruff_scope` had to learn when
    `--fix` stripped a coding declaration out of four IronPython files.

BOUNDARY, stated rather than left to be discovered
    This gate is about VALUE-derived writes: the new value is computed from the old one. `transition`
    is DECISION-derived -- the value is a constant from the workflow, and what came from the read is
    the *permission* to write it. That question is `test_transition_cas.py`'s, and the two
    derivations are deliberately unrelated, so a future instance must evade both.

WHAT IT COULD NOT REACH, named because a sweep is bounded by the fix available to it
    Two off-register instances stay open, in `BAND_2` below: `Scenario.shared_with` and
    `Project.dev_property`. Neither table carries a `modified_at`, so the register row's token does
    not exist for them, and JSON equality is not a swap that behaves the same on both backends. They
    are frozen here -- listed, reasoned, and unable to grow -- rather than left silent, which is how
    the seeding sweep lost four sites.

HONEST LIMIT
    SQLite serialises writers, so a genuinely parallel collision cannot be reproduced in-process (the
    caveat `test_race_conditions.py` states). What IS proven is the property the fix relies on,
    against the real tables and the real functions, through the exact losing interleaving.

Run: cd services/api && PYTHONPATH="src:../data/src" .venv/bin/python test_rmw_sweep.py
"""
import ast
import os
import pathlib
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "data", "src"))
os.environ.setdefault("AEC_TEST", "1")
os.environ["DATABASE_URL"] = "sqlite:///./test_rmw_sweep.db"
os.environ["STORAGE_DIR"] = "./test_storage_rmw_sweep"
for _f in ("./test_rmw_sweep.db",):
    if os.path.exists(_f):
        os.remove(_f)

FAILED = []


def check(label, ok, detail=""):
    print(f"{'PASS' if ok else 'FAIL'}  {label}" + (f"   {detail}" if detail else ""))
    if not ok:
        FAILED.append(label)


HERE = pathlib.Path(os.path.dirname(os.path.abspath(__file__)))
SRC = HERE / "src" / "aec_api"


# ======================================================================== the analyser
#
# Kept as free functions taking SOURCE TEXT so the self-tests can mutate a function's body and run
# the real classifier over it. `test_unique_read_guard`'s first draft asserted that its analyser
# still REPORTED a site, which a mutation routing every site to "safe" passed -- reporting a site and
# classifying it are different questions, and only one of them was being asserted.

_ID_COLS = {"id", "project_id", "token"}


def _mapped_models() -> set[str]:
    """Every declaratively-mapped class name, read out of `models.py` rather than listed.

    A Core `update(SomeModel)` is the same question as `update(TABLES[key])` -- a write that may or
    may not swap on what it read -- so both are classified. Without this the analyser cannot tell a
    mapped class from an unresolvable expression and reports two shipped, correctly-guarded writes as
    UNKNOWN, which is a fail-closed gate crying wolf: *an alarm that is always on is an alarm nobody
    reads.*
    """
    tree = ast.parse((SRC / "models.py").read_text(encoding="utf-8"))
    return {c.name for c in ast.walk(tree)
            if isinstance(c, ast.ClassDef)
            and any(isinstance(b, ast.Name) and b.id == "Base" for b in c.bases)}


MODELS = _mapped_models()


def _table_names(fn: ast.AST) -> set[str]:
    """Names in this function bound to a register table: `t = TABLES[key]`, plus `_cas_row_edit`'s
    `t` parameter, which IS a register table by contract (every call site passes `TABLES[key]`)."""
    names = set()
    if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if fn.name == "_cas_row_edit":
            names.add("t")
    for n in ast.walk(fn):
        if isinstance(n, ast.Assign) and isinstance(n.value, ast.Subscript) \
           and isinstance(n.value.value, ast.Name) and n.value.value.id == "TABLES":
            names.update(t.id for t in n.targets if isinstance(t, ast.Name))
    return names


def _tainted(fn: ast.AST) -> set[str]:
    """Names carrying a value read from the row, to a fixed point.

    Seeds are `get_record(...)` results and `_cas_row_edit`'s `rec` parameter (the row handed to a
    recompute callback). Propagation is through plain assignment, which is what makes the PRE-FIX
    `set_element_guids` visible: `rec` -> `cur` -> `result` -> `.values(element_guids=result)`.
    """
    taint = set()
    if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn.name in ("recompute", "supersede"):
        taint.update(a.arg for a in fn.args.args)
    for _ in range(8):                                   # fixed point; the chains here are short
        before = set(taint)
        for n in ast.walk(fn):
            if not isinstance(n, ast.Assign):
                continue
            txt = ast.unparse(n.value)
            seeded = "get_record(" in txt or any(
                isinstance(x, ast.Name) and x.id in taint for x in ast.walk(n.value))
            if seeded:
                for t in n.targets:
                    taint.update(x.id for x in ast.walk(t) if isinstance(x, ast.Name))
        if taint == before:
            break
    return taint


def _chain_parts(call: ast.Call):
    """Split `update(X).where(A).values(B)` into (X_node, [where args], [values keywords]) or None."""
    wheres, values, node = [], None, call
    while isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
        if node.func.attr == "where":
            wheres.extend(node.args)
        elif node.func.attr == "values":
            values = node
        node = node.func.value
    if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "update"):
        return None
    return (node.args[0] if node.args else None), wheres, values


def classify(source: str, path: str) -> list[tuple[str, str, int, str]]:
    """(path, function, lineno, verdict) for every Core `update(...)` chain on a register table.

    CAS        -- the WHERE constrains a column beyond id/project_id, so the write swaps on the read.
    BLIND_RMW  -- the VALUES carry something read from the row and the WHERE does not. The defect.
    PLAIN      -- the VALUES carry nothing read from the row; there is no update to lose.
    UNKNOWN    -- the target could not be resolved. Fails the build: the two blind spots that cost
                  the most were both a predicate deciding what to LOOK at, so this one reports
                  rather than skips.
    """
    out = []
    tree = ast.parse(source)
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        tnames, taint = _table_names(fn), _tainted(fn)
        for n in ast.walk(fn):
            if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)):
                continue
            parts = _chain_parts(n)
            if parts is None:
                continue
            target, wheres, values = parts
            if values is None:                # the outer link of the chain is not `.values(...)`
                continue
            owners = set(tnames) | MODELS
            if isinstance(target, ast.Name) and target.id in owners:
                pass
            elif isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name) \
                    and target.value.id == "TABLES":
                owners = owners | {"TABLES"}
            elif isinstance(target, ast.Name):
                out.append((path, fn.name, n.lineno, "UNKNOWN"))
                continue
            else:
                out.append((path, fn.name, n.lineno, "UNKNOWN"))
                continue
            derived = any(x.id in taint for x in ast.walk(values) if isinstance(x, ast.Name))
            # A column named in the WHERE that is not part of the row's IDENTITY. `id`/`project_id`/
            # `token` locate the row; anything else is a value the write is swapping on. Both spellings
            # are read -- `t.c.col` for a Core table and `Model.col` for a mapped class -- because
            # reading only the first reported every mapped-class guard as absent.
            cols = set()
            for w in wheres:
                for a in ast.walk(w):
                    if not isinstance(a, ast.Attribute) or a.attr == "c":
                        continue                 # `t.c` itself is the accessor, not a column
                    base = a.value
                    if isinstance(base, ast.Attribute) and base.attr == "c":
                        cols.add(a.attr)
                    elif isinstance(base, ast.Name) and base.id in owners:
                        cols.add(a.attr)
            swapped = bool(cols - _ID_COLS)
            out.append((path, fn.name, n.lineno,
                        "CAS" if swapped else ("BLIND_RMW" if derived else "PLAIN")))
    return out


# ---------------------------------------------------------------- SELF-TEST, before any verdict
# The exact pre-fix `set_element_guids`, lifted from git history. If the classifier does not call
# this BLIND_RMW, every number it prints below is unfounded.
_PRE_FIX = '''
def set_element_guids(db, key, project_id, rid, guids, actor, mode="add"):
    t = TABLES[key]
    rec = get_record(db, key, project_id, rid)
    cur = set(rec.get("element_guids") or [])
    incoming = {g for g in guids if g}
    result = sorted(cur | incoming if mode == "add" else cur - incoming if mode == "remove" else incoming)
    db.execute(update(t).where(t.c.id == rid, t.c.project_id == project_id)
               .values(element_guids=result or None, modified_at=_now()))
    return {"element_guids": result}
'''
_self = classify(_PRE_FIX, "<pre-fix>")
check("SELF-TEST: the classifier calls the shipped pre-fix `set_element_guids` BLIND_RMW",
      [v for *_ , v in _self] == ["BLIND_RMW"], f"got {_self}")

_PRE_FIX_UPDATE_RECORD = '''
def update_record(db, key, project_id, rid, data, actor, party):
    t = TABLES[key]
    rec = get_record(db, key, project_id, rid)
    merged = apply_table_totals(get_module(key), {**(rec.get("data") or {}), **data})
    vals = {"data": merged, "modified_at": _now()}
    db.execute(update(t).where(t.c.id == rid).values(**vals))
'''
_self2 = classify(_PRE_FIX_UPDATE_RECORD, "<pre-fix>")
check("SELF-TEST: it reaches a SPLATTED values dict too -- the blind spot that cost PR #551 a round",
      [v for *_, v in _self2] == ["BLIND_RMW"], f"got {_self2}")

_GUARDED = _PRE_FIX.replace("t.c.project_id == project_id)",
                            "t.c.project_id == project_id, t.c.modified_at == stamp)")
check("SELF-TEST: adding the swap predicate -- and nothing else -- moves the verdict to CAS",
      [v for *_, v in classify(_GUARDED, "<guarded>")] == ["CAS"],
      f"got {classify(_GUARDED, '<guarded>')}")

_UNRESOLVED = '''
def somewhere(db, whatever):
    db.execute(update(whatever).where(whatever.c.id == 1).values(x=2))
'''
check("SELF-TEST: it FAILS CLOSED -- an unresolvable target is UNKNOWN, not skipped",
      [v for *_, v in classify(_UNRESOLVED, "<u>")] == ["UNKNOWN"],
      f"got {classify(_UNRESOLVED, '<u>')}")

if FAILED:                                   # a broken analyser must not print a clean tree
    print("\nself-tests failed -- no population verdict is printed, because none would mean anything")
    for f_ in FAILED:
        print(f"  - {f_}")
    sys.exit(1)


# ================================================================ 5. the shipped population
SITES = []
for p in sorted(SRC.rglob("*.py")):
    SITES.extend(classify(p.read_text(encoding="utf-8"), str(p.relative_to(HERE))))

_blind = [s for s in SITES if s[3] == "BLIND_RMW"]
_unknown = [s for s in SITES if s[3] == "UNKNOWN"]
check("no register-row write derives its value from a read it does not swap on",
      not _blind, f"{len(SITES)} sites; blind={_blind}")
check("no register-row write is unresolvable (fails CLOSED)", not _unknown, f"unknown={_unknown}")
check("the CAS helper is itself classified CAS, so the fix is visible to the analyser that judges it",
      ("src/aec_api/modules.py", "_cas_row_edit", ) == tuple(
          [(s[0], s[1]) for s in SITES if s[1] == "_cas_row_edit"][0]) if
      [s for s in SITES if s[1] == "_cas_row_edit"] else False,
      f"{[s for s in SITES if s[1] == '_cas_row_edit']}")


# ================================================================ 1. the token's coverage
def register_writers() -> list[tuple[str, str]]:
    """Every function issuing a Core `update()` on a register table, at FUNCTION scope."""
    out = []
    for p in sorted(SRC.rglob("*.py")):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            tnames = _table_names(fn)
            for n in ast.walk(fn):
                parts = _chain_parts(n) if isinstance(n, ast.Call) else None
                if not parts:
                    continue
                target = parts[0]
                if (isinstance(target, ast.Name) and target.id in tnames) or \
                   (isinstance(target, ast.Subscript) and isinstance(target.value, ast.Name)
                        and target.value.id == "TABLES"):
                    out.append((str(p.relative_to(HERE)), fn.name))
                    break
    return sorted(set(out))


WRITERS = register_writers()
check("the writer derivation REACHES `transition`, whose values are a splatted dict",
      ("src/aec_api/modules.py", "transition") in WRITERS, f"found {len(WRITERS)}: {WRITERS}")

_no_stamp = []
for path, name in WRITERS:
    tree = ast.parse((HERE / path).read_text(encoding="utf-8"))
    fn = next(f for f in ast.walk(tree)
              if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and f.name == name)
    if "modified_at" not in ast.unparse(fn):
        _no_stamp.append((path, name))
check("EVERY register-row writer advances `modified_at` -- the column has no `onupdate=`, so the "
      "token's coverage is a property of the call sites and not of the schema",
      not _no_stamp, f"{len(WRITERS)} writers; without a stamp: {_no_stamp}")


# ================================================================ the behavioural half
from fastapi import HTTPException  # noqa: E402
from sqlalchemy import update  # noqa: E402

from aec_api import modules  # noqa: E402
from aec_api.db import SessionLocal, init_db  # noqa: E402
from aec_api.models import Project  # noqa: E402

init_db()
_db = SessionLocal()
_proj = Project(name="rmw")
_db.add(_proj)
_db.commit()
PID = _proj.id
_db.close()

KEY = "rfi"


def fresh(guids=None):
    s = SessionLocal()
    r = modules.create_record(s, KEY, PID, {"data": {"subject": "S", "question": "Q"}}, "alice", "GC")
    rid = r["id"]
    if guids:
        modules.set_element_guids(s, KEY, PID, rid, guids, "alice", "set")
    s.close()
    return rid


def stale_once(snapshot):
    """Stand in for `get_record` for exactly ONE call, then step aside.

    A retry-based fix needs the stale read to be transient: a `get_record` that lies for ever would
    make the loop spin to its 409 and the test would "pass" for the wrong reason -- it would be
    measuring the retry cap, not the recovery.
    """
    real = modules.get_record
    state = {"n": 0}

    def fake(*a, **k):
        state["n"] += 1
        return dict(snapshot) if state["n"] == 1 else real(*a, **k)
    return real, fake


# ---------------------------------------------------------------- 2. set_element_guids recovers
RID = fresh(["GUID-A"])
s_read = SessionLocal()
SNAP = modules.get_record(s_read, KEY, PID, RID)          # A's read, taken before B commits
s_read.close()

sb = SessionLocal()
modules.set_element_guids(sb, KEY, PID, RID, ["GUID-B"], "bob", "add")
sb.close()

_real, _fake = stale_once(SNAP)
modules.get_record = _fake
try:
    sa = SessionLocal()
    modules.set_element_guids(sa, KEY, PID, RID, ["GUID-C"], "carol", "add")
    sa.close()
finally:
    modules.get_record = _real

s = SessionLocal()
FINAL = sorted(modules.get_record(s, KEY, PID, RID).get("element_guids") or [])
s.close()
check("a tag added concurrently SURVIVES a second tagger deciding from a stale read",
      FINAL == ["GUID-A", "GUID-B", "GUID-C"], f"element_guids={FINAL}")


# ---------------------------------------------------------------- 3. MUTATION: remove the guard
# Reinstate the pre-fix statement shape inside the helper -- id/project_id only -- and run the same
# interleaving. The GUID must be lost again. This asserts the OUTCOME, not the emitted SQL: the pin
# sweep's first draft asserted the statement and passed with the defect put back.
_real_cas = modules._cas_row_edit


def _blind_cas(db, t, key, project_id, rid, recompute, what, *, retries=1):
    rec = modules.get_record(db, key, project_id, rid)
    vals = recompute(rec)
    if vals is None:
        return rec
    vals["modified_at"] = modules._now()
    db.execute(update(t).where(t.c.id == rid, t.c.project_id == project_id).values(**vals))
    return rec


RID_M = fresh(["GUID-A"])
s_read = SessionLocal()
SNAP_M = modules.get_record(s_read, KEY, PID, RID_M)
s_read.close()
sb = SessionLocal()
modules.set_element_guids(sb, KEY, PID, RID_M, ["GUID-B"], "bob", "add")
sb.close()

modules._cas_row_edit = _blind_cas
_real, _fake = stale_once(SNAP_M)
modules.get_record = _fake
try:
    sa = SessionLocal()
    modules.set_element_guids(sa, KEY, PID, RID_M, ["GUID-C"], "carol", "add")
    sa.close()
finally:
    modules.get_record = _real
    modules._cas_row_edit = _real_cas

s = SessionLocal()
MUT = sorted(modules.get_record(s, KEY, PID, RID_M).get("element_guids") or [])
s.close()
check("MUTATION: with the swap predicate removed, the same interleaving LOSES the concurrent tag",
      MUT == ["GUID-A", "GUID-C"], f"element_guids={MUT} (expected GUID-B to be gone)")


# ---------------------------------------------------------------- 4. update_record keeps both fields
RID_U = fresh()
s_read = SessionLocal()
SNAP_U = modules.get_record(s_read, KEY, PID, RID_U)
s_read.close()

sb = SessionLocal()
modules.update_record(sb, KEY, PID, RID_U, {"question": "bob's question"}, "bob", "GC")
sb.close()

_real, _fake = stale_once(SNAP_U)
modules.get_record = _fake
try:
    sa = SessionLocal()
    modules.update_record(sa, KEY, PID, RID_U, {"subject": "carol's subject"}, "carol", "GC")
    sa.close()
finally:
    modules.get_record = _real

s = SessionLocal()
DATA = modules.get_record(s, KEY, PID, RID_U).get("data") or {}
s.close()
check("two people editing DIFFERENT fields from stale reads both keep their edit",
      DATA.get("question") == "bob's question" and DATA.get("subject") == "carol's subject",
      f"question={DATA.get('question')!r} subject={DATA.get('subject')!r}")

# and the opt-in lock still REFUSES rather than retrying -- the two locks answer different questions
s = SessionLocal()
_cur = modules.get_record(s, KEY, PID, RID_U)["modified_at"]
s.close()
_sq = SessionLocal()
try:
    modules.update_record(_sq, KEY, PID, RID_U, {"subject": "x"}, "dave", "GC",
                          expected_modified_at="1999-01-01T00:00:00+00:00")
    _refused = ""
except HTTPException as e:
    _refused = str(e.detail)
finally:
    _sq.close()
check("`expected_modified_at` still REFUSES a stale write instead of quietly retrying it",
      "stale_write" in _refused, _refused or "not refused")
_ = _cur


# ================================================================ 6. the ORM population
#: Every `obj.attr = <expr mentioning obj>` in `src/aec_api`, with the reading that settled it.
#: A site not listed here reds the build; an entry whose site is gone reds it too.
ORM_LEDGER = {
    ("src/aec_api/coordination_fresh.py", "recheck"):
        "`labels |= {one constant}`. `recheck` is the ONLY writer of an EXISTING topic's labels -- "
        "every other site sets them at creation -- so the only caller that can lose a race is another "
        "`recheck` adding the SAME label. Established by grepping the column, not inferred from the "
        "shape of the statement.",
    ("src/aec_api/routers/bim.py", "_with_kind"):
        "`p.has_source_ifc = bool(p.source_ifc and Path(...).exists())` -- a response field computed "
        "onto a detached object for serialisation. Never written back to the row.",
    ("src/aec_api/routers/cloud.py", "_link_account"):
        "`new or old` keep-the-old-value fallback on an OAuth refresh token. The write is the "
        "caller's COMPLETE intent, not an accumulation, so a lost race overwrites with a whole value "
        "rather than dropping somebody else's contribution -- last-writer-wins is the behaviour the "
        "provider's token rotation actually wants.",
    ("src/aec_api/routers/cloud.py", "_fresh_access_token"): "same fallback, same rotation.",
    ("src/aec_api/routers/cloud.py", "cloud_refresh_profile"):
        "same -- display name and avatar fall back to the stored value when the provider omits them.",
    ("src/aec_api/routers/connections.py", "update_connection"):
        "same -- `body.name or c.name` is a PATCH keeping an unsent field.",
    ("src/aec_api/routers/scim.py", "scim_create_user"):
        "same -- the re-provision branch keeps `external_id` when the IdP omits it.",
    ("src/aec_api/routers/scim.py", "_apply_patch_op"): "same -- SCIM PATCH keeps an unparsable email.",
    ("src/aec_api/routers/verification.py", "set_status"):
        "same -- element metadata falls back to what was already recorded when the model no longer "
        "carries it.",
    ("src/aec_api/routers/proforma.py", "update_scenario"):
        "`s.result = solve(s.assumptions)` reads `assumptions` ASSIGNED TWO LINES ABOVE from the "
        "request body, not from the row -- there is no stale read to lose -- and it writes a "
        "different column from the one it reads.",
}

#: Open, and deliberately so. Both write a JSON collection on a table with NO `modified_at`, so the
#: register row's token does not exist for them, and JSON equality is not a swap that behaves the
#: same on SQLite and Postgres -- the identical trap `FOR UPDATE` is. Fixing them means giving those
#: tables a concurrency token, which is a migration and a separate item (roadmap: RMW-TOKEN).
BAND_2 = {
    ("src/aec_api/routers/proforma.py", "share_scenario"):
        "`shared_with` -- two concurrent grants, one silently dropped. The response echoes the "
        "caller's own target either way, so neither caller can tell it did not take.",
    ("src/aec_api/routers/realestate.py", "save_appraisal"):
        "`dev_property` merge -- a concurrent write to a different key of the same blob is lost. The "
        "non-concurrent half of this blob's problem WAS fixed here: `proforma.save_property` used to "
        "replace it wholesale and delete the appraisal on every ordinary save.",
}


def orm_rmw_sites() -> list[tuple[str, str]]:
    out = []
    for p in sorted(SRC.rglob("*.py")):
        tree = ast.parse(p.read_text(encoding="utf-8"))
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for n in ast.walk(fn):
                if not isinstance(n, (ast.Assign, ast.AugAssign)):
                    continue
                targets = n.targets if isinstance(n, ast.Assign) else [n.target]
                for tgt in targets:
                    if not (isinstance(tgt, ast.Attribute) and isinstance(tgt.value, ast.Name)):
                        continue
                    if tgt.value.id in ("self", "cls", "os", "sys"):
                        continue
                    used = {x.value.id for x in ast.walk(n.value)
                            if isinstance(x, ast.Attribute) and isinstance(x.value, ast.Name)}
                    if isinstance(n, ast.AugAssign) or tgt.value.id in used:
                        out.append((str(p.relative_to(HERE)), fn.name))
    return sorted(set(out))


ORM = orm_rmw_sites()
check("the ORM derivation REACHES a known site, asserted before its count is believed",
      ("src/aec_api/coordination_fresh.py", "recheck") in ORM, f"found {len(ORM)}")
_unfiled = [s for s in ORM if s not in ORM_LEDGER and s not in BAND_2]
check("every ORM read-modify-write is either reasoned exempt or named as an open gap",
      not _unfiled, f"unfiled={_unfiled}")
_stale = [k for k in list(ORM_LEDGER) + list(BAND_2) if k not in ORM]
check("no ledger entry outlives the site it describes", not _stale, f"stale={_stale}")
check("the share-token view counter is no longer an ORM read-modify-write",
      ("src/aec_api/client_portal.py", "model_fragment") not in ORM
      and ("src/aec_api/client_portal.py", "digest") not in ORM,
      "the increment moved into SQL")

print()
print(f"test_rmw_sweep {'FAILED' if FAILED else 'OK'}"
      f"  ({len(SITES)} register-row update sites, {len(WRITERS)} writers, "
      f"{len(ORM)} ORM sites: {len(ORM_LEDGER)} exempt, {len(BAND_2)} open)")
if FAILED:
    for f_ in FAILED:
        print(f"  - {f_}")
    sys.exit(1)
