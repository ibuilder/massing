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
from datetime import timezone

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


def _assigned(n: ast.AST):
    """`(targets, value)` for an assignment node, or `None` -- and `x: T = v` IS an assignment.

    Every derivation below walks assignments to follow a value, and each of them walked `ast.Assign`
    alone. Review caught what that costs on PR #552: an annotated `rec: dict = get_record(...)`
    breaks the Core taint chain, so the update behind it reads as PLAIN; an annotated
    `prior: dict = p.dev_property` drops the ORM site out of the population *entirely*, taking its
    ledger entry with it. **The blind spot is one `mypy --strict` pass wide** -- adding annotations is
    the most ordinary edit in the language, it changes no behaviour, and it would have silently
    emptied both derivations while every count still printed.

    `ast.AugAssign` is deliberately NOT folded in here: `x += y` is a read-modify-write by
    construction, and the ORM detector treats it as one without consulting the right-hand side at
    all. Returning it from this helper would route it through the "does the value mention the object"
    test and lose that.
    """
    if isinstance(n, ast.Assign):
        return n.targets, n.value
    if isinstance(n, ast.AnnAssign) and n.value is not None:
        return [n.target], n.value
    return None


def _table_names(fn: ast.AST) -> set[str]:
    """Names in this function bound to a register table: `t = TABLES[key]`, plus `_cas_row_edit`'s
    `t` parameter, which IS a register table by contract (every call site passes `TABLES[key]`)."""
    names = set()
    if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
        if fn.name == "_cas_row_edit":
            names.add("t")
    for n in ast.walk(fn):
        pair = _assigned(n)
        if pair is None:
            continue
        targets, value = pair
        if isinstance(value, ast.Subscript) and isinstance(value.value, ast.Name) \
           and value.value.id == "TABLES":
            names.update(t.id for t in targets if isinstance(t, ast.Name))
    return names


def _tainted(fn: ast.AST) -> set[str]:
    """Names carrying a value read from the row, to a fixed point.

    Seeds are `get_record(...)` results and `_cas_row_edit`'s `rec` parameter (the row handed to a
    recompute callback). Propagation is through assignment -- annotated or not, see `_assigned` --
    which is what makes the PRE-FIX `set_element_guids` visible: `rec` -> `cur` -> `result` ->
    `.values(element_guids=result)`.
    """
    taint = set()
    if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) and fn.name in ("recompute", "supersede"):
        taint.update(a.arg for a in fn.args.args)
    for _ in range(8):                                   # fixed point; the chains here are short
        before = set(taint)
        for n in ast.walk(fn):
            pair = _assigned(n)
            if pair is None:
                continue
            targets, value = pair
            txt = ast.unparse(value)
            seeded = "get_record(" in txt or any(
                isinstance(x, ast.Name) and x.id in taint for x in ast.walk(value))
            if seeded:
                for t in targets:
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
            # The CONCURRENCY TOKEN is not payload. `set_assignee` writes
            # `modified_at=_next_stamp(rec.get("modified_at"))` -- it reads the row, but only to
            # advance the stamp other writers swap on; `assignee` is the caller's whole intent and
            # there is no update to lose. Counting the token as derived made the tightened rule
            # report a correct writer as the defect it exists to find. *A rule made stricter in one
            # place has to be re-checked everywhere it already passed.*
            payload = [kw for kw in values.keywords if kw.arg != "modified_at"]
            written = {kw.arg for kw in values.keywords if kw.arg}

            def _is_tainted(node, taint=taint):
                return any(x.id in taint for x in ast.walk(node) if isinstance(x, ast.Name))

            # WHICH columns carry a value read from the row, not merely whether any do. A splat
            # (`**vals`) hides the mapping from column to expression, so a tainted splat makes the
            # set UNKNOWN -- represented as None, which disables the guard exemption below rather
            # than silently widening it.
            splat_tainted = any(kw.arg is None and _is_tainted(kw.value) for kw in payload)
            tainted_cols = None if splat_tainted else {kw.arg for kw in payload
                                                       if kw.arg and _is_tainted(kw.value)}
            derived = splat_tainted or bool(tainted_cols)

            # TWO shapes count as swapping, and collapsing them is what made the earlier drafts wrong
            # in three different directions:
            #
            #   (a) a non-identity column compared against something READ from this row --
            #       `t.c.modified_at == stamp`, `t.c.workflow_state == rec[...]`. This protects the
            #       whole statement: the row cannot have moved at all since the read.
            #   (b) a CONSTANT predicate on a column this statement WRITES -- `promote_comment`'s
            #       `.where(topic_id.is_(None)).values(topic_id=...)`, the conditional-write idiom.
            #       This protects only THAT COLUMN, so it counts only when the guarded columns cover
            #       every column carrying a read-derived value.
            #
            # (b) used to be "the statement writes this column anywhere", which review caught as a
            # fail-open on PR #552: `.where(status == "open").values(status=..., element_guids=<from
            # the read>)` passed, though a concurrent `element_guids` change does not move `status`
            # and the stale write still lands. *Fixing an over-broad rule by narrowing one clause can
            # leave the same hole one column to the left* -- the first tightening removed
            # `deleted_at IS NULL` and left this.
            #
            # `WHERE deleted_at IS NULL` is neither -- a constant compared against a column the
            # statement does not write is a FILTER.
            def _col_of(node, owners=owners):
                """The column name a comparison side refers to: `t.c.col` or `Model.col`."""
                for a in ast.walk(node):
                    if not isinstance(a, ast.Attribute) or a.attr == "c":
                        continue                 # `t.c` itself is the accessor, not a column
                    base = a.value
                    if (isinstance(base, ast.Attribute) and base.attr == "c") or \
                       (isinstance(base, ast.Name) and base.id in owners):
                        return a.attr
                return None

            swap_cols, guard_cols = set(), set()
            for w in wheres:
                for cmp_ in [x for x in ast.walk(w) if isinstance(x, ast.Compare)]:
                    sides = [cmp_.left] + list(cmp_.comparators)
                    col = next((c for c in (_col_of(x) for x in sides) if c), None)
                    if col is None or col in _ID_COLS:
                        continue
                    (swap_cols if any(_is_tainted(side) for side in sides) else guard_cols).add(col)
                # `.is_(None)` is a Call, not a Compare, so it needs its own pass -- and it is the
                # spelling BOTH shipped conditional writes use.
                for call in [x for x in ast.walk(w) if isinstance(x, ast.Call)]:
                    if not (isinstance(call.func, ast.Attribute)
                            and call.func.attr in ("is_", "isnot", "is_not")):
                        continue
                    col = _col_of(call.func.value)
                    if col and col not in _ID_COLS:
                        guard_cols.add(col)
            swapped = bool(swap_cols) or (tainted_cols is not None and bool(tainted_cols)
                                          and tainted_cols <= (guard_cols & written))
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

#: The same pre-fix writer with two locals ANNOTATED -- a change that alters no behaviour whatever.
#: Before review caught this on PR #552 the taint chain broke at the first annotation and the
#: statement classified PLAIN: the analyser reported the defect fixed because somebody ran a type
#: sweep. There is no such writer in the tree today, which is the point -- this shape had to be
#: CONSTRUCTED to be tested, and an analyser only ever fed the repository never sees it.
_PRE_FIX_ANNOTATED = (_PRE_FIX
                      .replace("    rec = get_record(", "    rec: dict = get_record(")
                      .replace("    cur = set(", "    cur: set = set("))
check("SELF-TEST: an ANNOTATED assignment carries taint -- `rec: dict = get_record(...)` is a read",
      [v for *_, v in classify(_PRE_FIX_ANNOTATED, "<annotated>")] == ["BLIND_RMW"],
      f"got {classify(_PRE_FIX_ANNOTATED, '<annotated>')}")

_GUARDED = (_PRE_FIX
            .replace("    cur = set(", "    stamp = rec.get(\"modified_at\")\n    cur = set(")
            .replace("t.c.project_id == project_id)",
                     "t.c.project_id == project_id, t.c.modified_at == stamp)"))
check("SELF-TEST: adding the swap predicate -- and nothing else -- moves the verdict to CAS",
      [v for *_, v in classify(_GUARDED, "<guarded>")] == ["CAS"],
      f"got {classify(_GUARDED, '<guarded>')}")

# The hole CodeRabbit found on PR #552: a non-identity column compared against a CONSTANT is not a
# swap, and the first draft of `classify` called it one. This fixture must stay BLIND_RMW.
_FAKE_GUARD = _PRE_FIX.replace("t.c.project_id == project_id)",
                               "t.c.project_id == project_id, t.c.deleted_at.is_(None))")
check("SELF-TEST: a non-identity column compared to a CONSTANT is NOT a swap (`deleted_at IS NULL`)",
      [v for *_, v in classify(_FAKE_GUARD, "<fake>")] == ["BLIND_RMW"],
      f"got {classify(_FAKE_GUARD, '<fake>')}")

# The conditional-write idiom, as `promote_comment` ships it: a constant predicate on the column
# being WRITTEN. Tightening the rule for `deleted_at IS NULL` flagged this correct writer until the
# rule learned the difference.
_COND_WRITE = '''
def promote(db, cid):
    rec = get_record(db, "k", "p", cid)
    claim = rec["id"]
    db.execute(update(RecordComment).where(RecordComment.id == cid, RecordComment.topic_id.is_(None))
               .values(topic_id=claim))
'''
check("SELF-TEST: a CONSTANT predicate on the column being WRITTEN is a guard, not a filter",
      [v for *_, v in classify(_COND_WRITE, "<cond>")] == ["CAS"],
      f"got {classify(_COND_WRITE, '<cond>')}")

# The hole review found in the FIRST tightening: a constant guard on one written column, beside a
# DIFFERENT column carrying the read-derived value. `status` not moving says nothing about whether
# `element_guids` did, so this is still a blind write.
_GUARD_WRONG_COL = '''
def half_guarded(db, key, project_id, rid, incoming):
    t = TABLES[key]
    rec = get_record(db, key, project_id, rid)
    merged = sorted(set(rec.get("element_guids") or []) | incoming)
    db.execute(update(t).where(t.c.id == rid, t.c.status == "open")
               .values(status="open", element_guids=merged))
'''
check("SELF-TEST: a guard on ONE written column does not protect a DIFFERENT column's derived value",
      [v for *_, v in classify(_GUARD_WRONG_COL, "<half>")] == ["BLIND_RMW"],
      f"got {classify(_GUARD_WRONG_COL, '<half>')}")

# ...and the same statement IS protected once the guard covers the column that carries the value.
_GUARD_RIGHT_COL = _GUARD_WRONG_COL.replace('t.c.status == "open")', 't.c.status == "open", '
                                            't.c.element_guids == rec.get("element_guids"))')
check("SELF-TEST: ...and covering that column with the guard makes it CAS, so this is not always-no",
      [v for *_, v in classify(_GUARD_RIGHT_COL, "<full>")] == ["CAS"],
      f"got {classify(_GUARD_RIGHT_COL, '<full>')}")

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


def _row_aliases(fn: ast.AST) -> set[str]:
    """Names bound to THE REGISTER ROW -- `rec = get_record(...)`, and `other = rec`.

    Deliberately NOT `_tainted`. That is *data dependence*, which is the right question for "did this
    value come from the row" and the wrong one for "is this the row". Review made the distinction on
    PR #552: under data dependence `metadata.get("modified_at")` and `stamp + timedelta(days=1)` both
    qualify as the prior token, and **neither is the value the CAS predicate will be compared
    against** -- so a writer feeding either one would swap on a token no row ever held, match nothing
    or match wrongly, and be certified correct on the way past.

    Propagation is through a BARE NAME only (`x = rec`), never through an expression mentioning one.
    An alias is an identity claim; data dependence is a provenance claim, and this file has now been
    wrong in both directions by conflating the two.
    """
    names: set[str] = set()
    if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)) \
       and fn.name in ("recompute", "supersede"):
        names.update(a.arg for a in fn.args.args)        # the row handed to a CAS callback
    for _ in range(4):                                   # fixed point; these chains are one hop
        before = set(names)
        for n in ast.walk(fn):
            pair = _assigned(n)
            if pair is None:
                continue
            targets, value = pair
            direct = (isinstance(value, ast.Call) and isinstance(value.func, ast.Name)
                      and value.func.id == "get_record") \
                or (isinstance(value, ast.Name) and value.id in names)
            if direct:
                names.update(t.id for t in targets if isinstance(t, ast.Name))
        if names == before:
            break
    return names


def _is_prior_stamp_read(node: ast.AST, rows: set[str]) -> bool:
    """Is this node ITSELF `<row>.get("modified_at")` / `<row>["modified_at"]`?

    Not an `ast.walk` containment test, which is what the previous draft did in both directions:
    `rec.get("modified_at") + timedelta(days=1)` CONTAINS the read and is not it, and
    `metadata.get("modified_at")` is the right SHAPE off the wrong object.
    """
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
       and node.func.attr in ("get", "pop") and node.args \
       and isinstance(node.args[0], ast.Constant) and node.args[0].value == "modified_at" \
       and isinstance(node.func.value, ast.Name) and node.func.value.id in rows:
        return True
    return isinstance(node, ast.Subscript) and isinstance(node.slice, ast.Constant) \
        and node.slice.value == "modified_at" \
        and isinstance(node.value, ast.Name) and node.value.id in rows


def _is_next_stamp_call(node: ast.AST) -> bool:
    """Is this node a CALL of `_next_stamp` -- as opposed to a mention of the name?"""
    return isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
        and node.func.id == "_next_stamp"


def _prior_stamp_names(fn: ast.AST, rows: set[str]) -> set[str]:
    """Names holding the row's PRE-IMAGE `modified_at`, which is the only legitimate argument.

    Seeded by a read of that key off a ROW ALIAS and carried only through bare-name assignment,
    because `_cas_row_edit` is written in two statements: `stamp = rec.get("modified_at")` ...
    later ... `vals["modified_at"] = _next_stamp(stamp)`. A derived value (`stamp + delta`, a
    `.replace(...)`, a format) is NOT the token and does not propagate -- the previous draft carried
    taint through any expression mentioning an accepted name, which admitted every one of those.
    """
    names: set[str] = set()
    for _ in range(4):                                   # fixed point; these chains are one hop
        before = set(names)
        for n in ast.walk(fn):
            pair = _assigned(n)
            if pair is None:
                continue
            targets, value = pair
            if _is_prior_stamp_read(value, rows) \
               or (isinstance(value, ast.Name) and value.id in names):
                names.update(t.id for t in targets if isinstance(t, ast.Name))
        if names == before:
            break
    return names


def _stamp_arg_ok(value: ast.AST, rows: set[str], priors: set[str]) -> bool:
    """Is this expression a `_next_stamp(<the register row's prior modified_at>)` CALL?

    Two drafts, two directions, one sentence apart.

    The first asked whether the NAME `_next_stamp` occurred anywhere in the expression, so
    `_next_stamp(None)` passed -- and `None` makes the helper skip its `now <= prev` comparison and
    return a bare `_now()`, the unguarded clock it exists to replace. *Naming the guard is not
    calling it.*

    The second accepted any `"modified_at"` read off any object, and carried names through any
    expression mentioning one -- so `_next_stamp(metadata.get("modified_at"))` and
    `_next_stamp(stamp + delta)` passed. *And calling it is not feeding it the token the CAS
    predicate will be compared against.* Both now resolve through `_row_aliases`.
    """
    if not _is_next_stamp_call(value):
        return False
    if len(value.args) != 1 or value.keywords:
        return False                                     # fails closed on anything unfamiliar
    arg = value.args[0]
    if _is_prior_stamp_read(arg, rows):
        return True
    return isinstance(arg, ast.Name) and arg.id in priors


def _stamp_ok(values: ast.Call, rows: set[str], priors: set[str]):
    """Does THIS `.values(...)` set `modified_at` from `_next_stamp(<prior token>)`?"""
    for kw in values.keywords:
        if kw.arg == "modified_at":
            return _stamp_arg_ok(kw.value, rows, priors)
    # A splat: the mapping is in a dict built elsewhere, so `_splat_ok` resolves THAT dict.
    return None


def _dict_stamp_map(nodes, rows: set[str], priors: set[str]) -> dict[str, list[bool]]:
    """dict name -> the `modified_at` verdicts assigned INTO that particular dict.

    Keyed by name, which is the whole point. The previous draft pooled every stamp assignment in the
    function into one flat list, so a correctly-stamped `vals` authorised a second
    `.values(**other)` whose dict had no stamp at all.
    """
    out: dict[str, list[bool]] = {}
    for n in nodes:
        pair = _assigned(n)
        if pair is None:
            continue
        targets, value = pair
        for t in targets:
            if isinstance(t, ast.Name) and isinstance(value, ast.Dict):
                out.setdefault(t.id, []).extend(
                    _stamp_arg_ok(v, rows, priors)
                    for k, v in zip(value.keys, value.values)
                    if isinstance(k, ast.Constant) and k.value == "modified_at")
            elif isinstance(t, ast.Subscript) and isinstance(t.slice, ast.Constant) \
                    and t.slice.value == "modified_at" and isinstance(t.value, ast.Name):
                out.setdefault(t.value.id, []).append(_stamp_arg_ok(value, rows, priors))
    return out


def _splat_ok(values: ast.Call, stamp_map: dict[str, list[bool]],
              rows: set[str], priors: set[str]) -> bool:
    """Does the dict THIS `.values(**x)` splats carry a valid stamp -- that dict, not some dict?

    Review's second finding on `c0257bd7`, and it is round two's sentence one level down. That round
    fixed "yes, somewhere" for UPDATES: each update is validated against its own `.values(...)`. The
    fix then reintroduced it for the DICTS those updates splat, by pooling every `modified_at`
    assignment in the function into one list -- so a writer with two splatted updates passed on the
    strength of the first one's dict. *The same defect can be fixed at one level and recreated at the
    next by the fix itself, and it reads as the same code both times.*

    Anything unresolvable -- no splat, several, or a splat of something that is not a name or a dict
    literal -- fails closed.
    """
    splats = [kw.value for kw in values.keywords if kw.arg is None]
    if len(splats) != 1:
        return False
    node = splats[0]
    if isinstance(node, ast.Dict):                       # `.values(**{...})`, checked in place
        marks = [_stamp_arg_ok(v, rows, priors) for k, v in zip(node.keys, node.values)
                 if isinstance(k, ast.Constant) and k.value == "modified_at"]
    elif isinstance(node, ast.Name):
        marks = stamp_map.get(node.id, [])
    else:
        return False
    return bool(marks) and all(marks)


def stamps_through_helper(fn: ast.AST) -> bool:
    """Does EVERY register update in this writer stamp `modified_at` from `_next_stamp(...)`?

    Two drafts of this were wrong, both in the direction of passing.

    The first asked whether the STRING "modified_at" appeared anywhere in `ast.unparse(fn)`, which
    review pointed out a DOCSTRING satisfies -- and every function here has a long one, several
    discussing that column at length. The check could not have failed.

    The second read the assignment but returned on the FIRST valid stamp anywhere in the function, so
    a writer with two updates passed while the second one omitted the stamp or used a bare `_now()`.
    *A check that answers "yes, somewhere" is not answering the question a sweep asks, which is
    always "every one".* Each update is now validated against its own `.values(...)`, and a function
    with no update at all is not a writer and cannot pass vacuously.

    The third was wrong in the same direction one layer down: it accepted any expression CONTAINING
    the name `_next_stamp`, so `_next_stamp(None)` -- which returns the bare clock -- satisfied it.
    See `_stamp_arg_ok`, which every shape now routes through.
    """
    body = list(fn.body)
    if body and isinstance(body[0], ast.Expr) and isinstance(body[0].value, ast.Constant) \
       and isinstance(body[0].value.value, str):
        body = body[1:]                          # drop the docstring, which is prose, not behaviour
    nodes = [x for b in body for x in ast.walk(b)]

    # Every way a SPLATTED values dict can receive the stamp. There are three shapes across three
    # writers and each draft of this detector has known one fewer than exist: a dict literal
    # (`transition`), a subscript assignment into a dict built earlier (`_cas_row_edit`), and the
    # plain keyword handled in `_stamp_ok`. Listing them is unavoidable; being CAUGHT missing one is
    # what the per-update rewrite bought, since the previous draft passed on any single good stamp
    # and would have said nothing. The verdicts are now keyed BY DICT NAME -- see `_splat_ok`.
    rows = _row_aliases(fn)
    priors = _prior_stamp_names(fn, rows)
    stamp_map = _dict_stamp_map(nodes, rows, priors)

    updates = 0
    for n in nodes:
        if not (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)):
            continue
        parts = _chain_parts(n)
        if not parts or parts[2] is None:
            continue
        updates += 1
        verdict = _stamp_ok(parts[2], rows, priors)
        if verdict is False:
            return False                         # this update names the column and not the helper
        if verdict is None:                      # splatted -- THIS dict must supply it
            if not _splat_ok(parts[2], stamp_map, rows, priors):
                return False
    return updates > 0


#: A writer whose ONLY mention of the column is prose. The pre-fix check passed this.
_PROSE_ONLY = ast.parse(
    'def writer(db, t, rid):\n'
    '    """This one advances modified_at, honestly it does."""\n'
    '    db.execute(update(t).where(t.c.id == rid).values(assignee=None))\n').body[0]
check("SELF-TEST: a DOCSTRING mentioning the column does not count as advancing it",
      not stamps_through_helper(_PROSE_ONLY), "prose satisfied the stamp check")

#: A writer that stamps with a bare `_now()` -- the collision `_next_stamp` exists to close.
_BARE_NOW = ast.parse(
    'def writer(db, t, rid):\n'
    '    db.execute(update(t).where(t.c.id == rid)'
    '.values(assignee=None, modified_at=_now()))\n').body[0]
check("SELF-TEST: a bare `_now()` does not count either -- that is the collision this closes",
      not stamps_through_helper(_BARE_NOW), "`_now()` satisfied the stamp check")

#: And the shipped writers must PASS it, or the two negatives above prove only that it says no.
_REAL = ast.parse(
    'def writer(db, t, rid, key, project_id):\n'
    '    rec = get_record(db, key, project_id, rid)\n'
    '    db.execute(update(t).where(t.c.id == rid)'
    '.values(assignee=None, modified_at=_next_stamp(rec.get("modified_at"))))\n').body[0]
check("SELF-TEST: and a writer that DOES stamp through the helper passes, so it is not always-no",
      stamps_through_helper(_REAL), "the real shape failed the stamp check")

_DICT_SHAPE = ast.parse(
    'def writer(db, t, rid, key, project_id):\n'
    '    rec = get_record(db, key, project_id, rid)\n'
    '    vals = {"workflow_state": "x", "modified_at": _next_stamp(rec.get("modified_at"))}\n'
    '    db.execute(update(t).where(t.c.id == rid).values(**vals))\n').body[0]
check("SELF-TEST: the DICT-LITERAL shape counts -- the one the strengthened check first missed",
      stamps_through_helper(_DICT_SHAPE), "the splatted-dict shape failed the stamp check")

#: `_next_stamp(None)`, in all three shapes. The argument is not a near-miss: `None` skips the
#: `now <= prev` comparison inside the helper, so it returns a bare `_now()` -- the very clock the
#: helper replaces. Every one of these passed the name-presence draft review caught on PR #552.
_STAMP_NONE_KW = ast.parse(
    'def writer(db, t, rid, key, project_id):\n'
    '    rec = get_record(db, key, project_id, rid)\n'
    '    db.execute(update(t).where(t.c.id == rid)'
    '.values(assignee=None, modified_at=_next_stamp(None)))\n').body[0]
_STAMP_NONE_DICT = ast.parse(
    'def writer(db, t, rid, key, project_id):\n'
    '    rec = get_record(db, key, project_id, rid)\n'
    '    vals = {"workflow_state": "x", "modified_at": _next_stamp(None)}\n'
    '    db.execute(update(t).where(t.c.id == rid).values(**vals))\n').body[0]
_STAMP_NONE_SUB = ast.parse(
    'def writer(db, t, rid, key, project_id):\n'
    '    rec = get_record(db, key, project_id, rid)\n'
    '    vals = {"workflow_state": "x"}\n'
    '    vals["modified_at"] = _next_stamp(None)\n'
    '    db.execute(update(t).where(t.c.id == rid).values(**vals))\n').body[0]
for _shape, _fx in (("keyword", _STAMP_NONE_KW), ("dict literal", _STAMP_NONE_DICT),
                    ("subscript assign", _STAMP_NONE_SUB)):
    check(f"SELF-TEST: `_next_stamp(None)` is REFUSED in the {_shape} shape -- naming the guard is "
          "not calling it, and calling it is not feeding it the token it must beat",
          not stamps_through_helper(_fx), f"`_next_stamp(None)` passed as a {_shape}")

#: A name that holds `_now()` rather than the row's token is refused for the same reason.
_STAMP_WRONG_NAME = ast.parse(
    'def writer(db, t, rid, key, project_id):\n'
    '    rec = get_record(db, key, project_id, rid)\n'
    '    stamp = _now()\n'
    '    vals = {"workflow_state": "x"}\n'
    '    vals["modified_at"] = _next_stamp(stamp)\n'
    '    db.execute(update(t).where(t.c.id == rid).values(**vals))\n').body[0]
check("SELF-TEST: a local NOT read from the row is refused as the argument, however it is spelled",
      not stamps_through_helper(_STAMP_WRONG_NAME), "`_next_stamp(_now())` passed through a local")

#: The right SHAPE off the wrong OBJECT. `metadata` is not the register row, so its `modified_at`
#: is not the token the CAS predicate compares against -- the writer would swap on a value no row
#: ever held. The `c0257bd7` draft accepted this because it asked about the KEY and not the object.
_STAMP_WRONG_OBJECT = ast.parse(
    'def writer(db, t, rid, key, project_id, metadata):\n'
    '    rec = get_record(db, key, project_id, rid)\n'
    '    db.execute(update(t).where(t.c.id == rid)'
    '.values(assignee=None, modified_at=_next_stamp(metadata.get("modified_at"))))\n').body[0]
check("SELF-TEST: `modified_at` read off an object that is NOT the register row is refused",
      not stamps_through_helper(_STAMP_WRONG_OBJECT), "a stamp from an unrelated object passed")

#: The right object, TRANSFORMED. A value derived from the token is not the token: the predicate
#: `t.c.modified_at == <read>` is compared against what was READ, so anything arithmetic happened to
#: cannot be it. The `c0257bd7` draft carried names through any expression that mentioned one.
_STAMP_DERIVED = ast.parse(
    'def writer(db, t, rid, key, project_id):\n'
    '    rec = get_record(db, key, project_id, rid)\n'
    '    stamp = rec.get("modified_at")\n'
    '    shifted = stamp + timedelta(days=1)\n'
    '    db.execute(update(t).where(t.c.id == rid)'
    '.values(assignee=None, modified_at=_next_stamp(shifted)))\n').body[0]
check("SELF-TEST: a TRANSFORMED prior token is refused -- data dependence is not identity",
      not stamps_through_helper(_STAMP_DERIVED), "a derived value passed as the prior token")

#: TWO splatted updates, only the FIRST dict stamped. Round two fixed exactly this for updates and
#: its own fix recreated it for the dicts they splat, by pooling every stamp in the function.
_TWO_SPLATS = ast.parse(
    'def writer(db, t, rid, key, project_id):\n'
    '    rec = get_record(db, key, project_id, rid)\n'
    '    vals = {"workflow_state": "x", "modified_at": _next_stamp(rec.get("modified_at"))}\n'
    '    other = {"title": "y"}\n'
    '    db.execute(update(t).where(t.c.id == rid).values(**vals))\n'
    '    db.execute(update(t).where(t.c.id == rid).values(**other))\n').body[0]
check("SELF-TEST: a SECOND splatted update whose OWN dict has no stamp fails, though the first "
      "dict's stamp is valid -- \"yes, somewhere\" one level below where round two fixed it",
      not stamps_through_helper(_TWO_SPLATS), "one dict's stamp authorised another dict's update")

#: ...and both dicts stamped passes, so the per-dict rule is not always-no.
_TWO_SPLATS_OK = ast.parse(
    'def writer(db, t, rid, key, project_id):\n'
    '    rec = get_record(db, key, project_id, rid)\n'
    '    vals = {"workflow_state": "x", "modified_at": _next_stamp(rec.get("modified_at"))}\n'
    '    other = {"title": "y", "modified_at": _next_stamp(rec.get("modified_at"))}\n'
    '    db.execute(update(t).where(t.c.id == rid).values(**vals))\n'
    '    db.execute(update(t).where(t.c.id == rid).values(**other))\n').body[0]
check("SELF-TEST: ...and two separately-stamped dicts still pass",
      stamps_through_helper(_TWO_SPLATS_OK), "two correctly stamped dicts were rejected")

#: ...and `_cas_row_edit`'s real two-statement shape passes, annotated or not, so the rule above is
#: not simply always-no. The annotated arm is the `_assigned` fix under its own load.
_STAMP_VIA_LOCAL = ast.parse(
    'def writer(db, t, rid, key, project_id):\n'
    '    rec = get_record(db, key, project_id, rid)\n'
    '    stamp = rec.get("modified_at")\n'
    '    vals = {"workflow_state": "x"}\n'
    '    vals["modified_at"] = _next_stamp(stamp)\n'
    '    db.execute(update(t).where(t.c.id == rid).values(**vals))\n').body[0]
check("SELF-TEST: the token read into a LOCAL first passes -- `_cas_row_edit`'s shipped shape",
      stamps_through_helper(_STAMP_VIA_LOCAL), "the two-statement shape was rejected")
_STAMP_VIA_ANN = ast.parse(
    'def writer(db, t, rid, key, project_id):\n'
    '    rec = get_record(db, key, project_id, rid)\n'
    '    stamp: object = rec.get("modified_at")\n'
    '    vals: dict = {"workflow_state": "x"}\n'
    '    vals["modified_at"] = _next_stamp(stamp)\n'
    '    db.execute(update(t).where(t.c.id == rid).values(**vals))\n').body[0]
check("SELF-TEST: ...and still passes when that local is ANNOTATED, which `transition` already is",
      stamps_through_helper(_STAMP_VIA_ANN), "annotating the local lost the prior token")

#: TWO updates, only the first stamped. The previous draft returned True on the first good stamp and
#: never looked at the second -- review caught it on PR #552.
_TWO_UPDATES = ast.parse(
    'def writer(db, t, rid, key, project_id):\n'
    '    rec = get_record(db, key, project_id, rid)\n'
    '    db.execute(update(t).where(t.c.id == rid)'
    '.values(assignee=None, modified_at=_next_stamp(rec.get("modified_at"))))\n'
    '    db.execute(update(t).where(t.c.id == rid).values(title="x"))\n').body[0]
check("SELF-TEST: a SECOND update without a stamp fails, even when the first one has a good stamp",
      not stamps_through_helper(_TWO_UPDATES), "one good stamp covered an unstamped sibling")

#: ...and both stamped passes, so the two-update rule is not simply always-no.
_TWO_OK = ast.parse(
    'def writer(db, t, rid, key, project_id):\n'
    '    rec = get_record(db, key, project_id, rid)\n'
    '    db.execute(update(t).where(t.c.id == rid)'
    '.values(assignee=None, modified_at=_next_stamp(rec.get("modified_at"))))\n'
    '    db.execute(update(t).where(t.c.id == rid)'
    '.values(title="x", modified_at=_next_stamp(rec.get("modified_at"))))\n').body[0]
check("SELF-TEST: ...and two correctly-stamped updates still pass",
      stamps_through_helper(_TWO_OK), "two good stamps were rejected")

#: A function with NO register update is not a writer and must not pass vacuously.
_NO_UPDATE = ast.parse('def reader(db, t, rid):\n    return db.execute(select(t))\n').body[0]
check("SELF-TEST: a function with no update at all does not pass the stamp check vacuously",
      not stamps_through_helper(_NO_UPDATE), "a non-writer satisfied the stamp check")

_no_stamp = []
for path, name in WRITERS:
    tree = ast.parse((HERE / path).read_text(encoding="utf-8"))
    fn = next(f for f in ast.walk(tree)
              if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and f.name == name)
    if not stamps_through_helper(fn):
        _no_stamp.append((path, name))
check("EVERY register-row writer advances `modified_at` THROUGH `_next_stamp` -- the column has no "
      "`onupdate=`, so the token's coverage is a property of the call sites, not of the schema, and "
      "one writer stamping with a bare `_now()` reopens the collision for all of them",
      not _no_stamp, f"{len(WRITERS)} writers; without a monotonic stamp: {_no_stamp}")


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


# ---------------------------------------------------------------- 4b. the COLLISION branch runs
# `_next_stamp` returns `prev + 1us` only when `_now()` fails to advance, which no ordinary test
# reaches -- so it is the one branch of this concurrency control that could ship broken and stay
# quiet. Worse, it is the branch that returns a TZ-AWARE datetime while SQLite hands `modified_at`
# back NAIVE: if the two render differently, the next `WHERE modified_at == <what we just read>`
# matches nothing and every subsequent edit 409s. Exercised here against the real table by freezing
# the clock, because *a branch that only runs under contention is a branch only production runs.*
RID_C = fresh(["GUID-A"])
s = SessionLocal()
_frozen = modules.get_record(s, KEY, PID, RID_C)["modified_at"]
s.close()
_aware = _frozen.replace(tzinfo=timezone.utc) if _frozen.tzinfo is None else _frozen

_real_now = modules._now
modules._now = lambda: _aware                     # the clock does not advance, for ANY writer
try:
    check("`_next_stamp` advances even when the clock does not -- the branch's whole purpose",
          modules._next_stamp(_frozen) > _aware,
          f"{modules._next_stamp(_frozen)!r} vs prev {_aware!r}")

    # THE INTERLEAVING THIS BRANCH EXISTS FOR, run with the clock frozen so B's write cannot move the
    # token by luck. A holds a snapshot taken before B wrote. With the branch, B's stamp is `S+1us`,
    # A's predicate on `S` matches nothing, A re-reads and re-applies -- GUID-B survives. Without it,
    # B leaves the stamp at `S`, A's stale predicate MATCHES, and A's write (derived from the
    # pre-image) erases GUID-B while reporting success.
    #
    # The first draft of this asserted only that a frozen-clock edit LANDS and that the next edit
    # matches -- both of which stay true with the branch deleted, because SQLite serialises the
    # writes and each session sees its own. *Two checks that pass under the mutation are two checks
    # that were measuring the round-trip, not the guard* -- so they are replaced by this one, which
    # was verified to fail when the branch is removed.
    s = SessionLocal()
    SNAP_F = modules.get_record(s, KEY, PID, RID_C)
    s.close()

    sb = SessionLocal()
    modules.set_element_guids(sb, KEY, PID, RID_C, ["GUID-B"], "bob", "add")
    sb.close()

    _r, _f = stale_once(SNAP_F)
    modules.get_record = _f
    try:
        sa = SessionLocal()
        modules.set_element_guids(sa, KEY, PID, RID_C, ["GUID-C"], "carol", "add")
        sa.close()
    finally:
        modules.get_record = _r
finally:
    modules._now = _real_now

s = SessionLocal()
_frozen_final = sorted(modules.get_record(s, KEY, PID, RID_C).get("element_guids") or [])
s.close()
check("with the clock FROZEN, a concurrent tag still survives -- the token advanced although the "
      "clock did not, which is the only thing keeping the predicate from being reusable",
      _frozen_final == ["GUID-A", "GUID-B", "GUID-C"], f"element_guids={_frozen_final}")


# ================================================================ 6. the ORM population
#: Every ORM read-modify-write site, with a STATUS and the reading that settled it.
#:
#: The status is a structured field, not a word inside the prose. Review caught the reason on PR
#: #552: the count of open gaps was computed by looking for the substring "OPEN" in the
#: justification, and one entry had been written with a capital O and lower-case rest -- so the gate
#: reported 13 open sites when there were 14, and the threat model inherited the wrong number.
#: *A count derived by grepping prose is prose*, and this file exists to stop exactly that.
#:
#: STATUSES: "EXEMPT" (read and reasoned not to be a lost update) · "OPEN" (a real gap, named) ·
#: "LOCKED" (protected by a control other than the CAS -- today only `pid_lock`). Asserted below, so
#: a typo cannot quietly drop a site out of every count.
STATUSES = {"EXEMPT", "OPEN", "LOCKED"}

ORM_LEDGER = {
    ("src/aec_api/coordination_fresh.py", "recheck", "labels"): ("EXEMPT",
        "`labels |= {one constant}`. `recheck` is the ONLY writer of an EXISTING topic's labels -- "
        "every other site sets them at creation -- so the only caller that can lose a race is "
        "another `recheck` adding the SAME label. Established by grepping the column, not inferred "
        "from the shape of the statement."),
    ("src/aec_api/routers/bim.py", "_with_kind", "has_source_ifc"): ("EXEMPT",
        "`p.has_source_ifc = bool(p.source_ifc and Path(...).exists())` -- a response field computed "
        "onto a detached object for serialisation. Never written back to the row."),
    ("src/aec_api/routers/bim.py", "_with_kind", "model_kind"): ("EXEMPT",
        "the other half of the same line's intent -- the function's own comment says it sets `the "
        "(non-column) fields ProjectOut reads`. Neither is a column, so neither can lose an update."),
    ("src/aec_api/routers/cloud.py", "_link_account", "refresh_token"): ("EXEMPT",
        "`new or old` keep-the-old-value fallback on an OAuth refresh token. The write is the "
        "caller's COMPLETE intent, not an accumulation, so a lost race overwrites with a whole value "
        "rather than dropping somebody else's contribution -- last-writer-wins is the behaviour the "
        "provider's token rotation actually wants."),
    ("src/aec_api/routers/cloud.py", "_link_account", "local_admin_at_link"): ("EXEMPT",
        "`local_admin_at_link` records whether the account was ALREADY an admin before the link, so "
        "role sync demotes only an elevation it granted. Its fallback keeps the earlier answer, and "
        "the earlier answer is the true one -- a later link cannot make the account less "
        "pre-existing. Losing the race preserves the safer value."),
    ("src/aec_api/routers/cloud.py", "_fresh_access_token", "access_token"): ("EXEMPT",
        "same fallback, same rotation."),
    ("src/aec_api/routers/cloud.py", "_fresh_access_token", "refresh_token"): ("EXEMPT", "same."),
    ("src/aec_api/routers/cloud.py", "_fresh_access_token", "expires_at"): ("EXEMPT",
        "written in the same statement group as the token it describes, from the same response. A "
        "lost race replaces the triple wholesale rather than splitting it -- the failure worth "
        "naming here would be a token from one refresh with an expiry from another, and the three "
        "writes share one commit."),
    ("src/aec_api/routers/cloud.py", "cloud_refresh_profile", "display_name"): ("EXEMPT",
        "same -- display name falls back to the stored value when the provider omits it."),
    ("src/aec_api/routers/cloud.py", "cloud_refresh_profile", "avatar_url"): ("EXEMPT", "same."),
    ("src/aec_api/routers/cloud.py", "cloud_refresh_profile", "cloud_roles"): ("EXEMPT",
        "NOT a fallback -- `link.cloud_roles = roles` is a whole value from the provider's fresh "
        "`userinfo`, which is the point of the route. Two concurrent refreshes both write what the "
        "provider currently says, so the loser loses nothing it read. Called out rather than folded "
        "into the sentence above because this one is authorisation-bearing and deserves its own "
        "reading."),
    ("src/aec_api/routers/cloud.py", "cloud_refresh_profile", "cloud_tier"): ("EXEMPT",
        "same -- entitlement tier, whole value from the same `userinfo` response."),
    ("src/aec_api/routers/connections.py", "update_connection", "name"): ("EXEMPT",
        "`body.name or c.name` is a PATCH keeping an unsent field. **This sentence used to cover the "
        "whole function**, and the function also merges `config` -- see CROSS_FIELD, where that "
        "attribute now sits as OPEN."),
    ("src/aec_api/routers/scim.py", "scim_create_user", "external_id"): ("EXEMPT",
        "same -- the re-provision branch keeps `external_id` when the IdP omits it."),
    ("src/aec_api/routers/scim.py", "_apply_patch_op", "email"): ("EXEMPT",
        "same -- SCIM PATCH keeps an unparsable email."),
    ("src/aec_api/routers/verification.py", "set_status", "ifc_class"): ("EXEMPT",
        "same -- element metadata falls back to what was already recorded when the model no longer "
        "carries it."),
    ("src/aec_api/routers/verification.py", "set_status", "storey"): ("EXEMPT",
        "same, from the same property-index lookup one line below."),
    ("src/aec_api/routers/proforma.py", "update_scenario", "result"): ("EXEMPT",
        "`s.result = solve(s.assumptions)` reads `assumptions` ASSIGNED TWO LINES ABOVE from the "
        "request body, not from the row -- there is no stale read to lose -- and it writes a "
        "different column from the one it reads."),
    ("src/aec_api/jobs.py", "_run_one", "result"): ("EXEMPT",
        "job lifecycle -- `state`/`result`/`error` are written from the run's own outcome. The CLAIM "
        "is the contested step and it is already a conditional UPDATE, gated by "
        "`test_race_conditions.py`."),
    ("src/aec_api/routers/auth.py", "mfa_verify", "mfa_recovery"): ("EXEMPT",
        "`mfa_recovery = remaining` consumes one code. A concurrent second verify could consume the "
        "same code twice -- but both requests must already hold a VALID code, so the race grants no "
        "access the caller did not have; it wastes one code. Named rather than silently exempt "
        "because 'a code can be used twice' deserves to be someone's deliberate call."),
    ("src/aec_api/routers/drawings.py", "rekey_storey_markups", "sheet_id"): ("EXEMPT",
        "a one-shot backfill that rewrites `sheet_id` keys; not a concurrent path."),
}

#: The project's `source_ifc` pointer: read the current IFC, derive a NEW version from it, write the
#: pointer back. Guarded -- by `pid_lock.mutating`, a per-project advisory lock, not by a CAS -- at
#: SIX of its twelve call sites. The checks below assert the split in both directions, and demand the
#: lock span the whole read-modify-write rather than only the assignment.
#:
#: `upload_source_ifc` and `import_rvt` are deliberately absent: they write uploaded bytes to a fixed
#: path, derived from nothing they read, so last-writer-wins is an upload's specified behaviour. They
#: are also not in the ORM population at all, which is how the stale-entry check found them when a
#: first draft listed them anyway -- *an exemption for a site that was never in scope is a claim
#: about nothing, and it reads exactly like one that matters.*
IFC_PIPELINE = {
    ("src/aec_api/routers/authoring.py", "edit", "source_ifc"): ("LOCKED", "whole RMW inside `pid_lock.mutating`"),
    ("src/aec_api/routers/authoring.py", "edit_graph", "source_ifc"): ("LOCKED", "same"),
    ("src/aec_api/routers/authoring.py", "edit_batch", "source_ifc"): ("LOCKED", "same"),
    ("src/aec_api/routers/authoring.py", "macros_run", "source_ifc"): ("LOCKED", "same"),
    ("src/aec_api/routers/authoring.py", "option_activate", "source_ifc"): ("LOCKED", "same"),
    ("src/aec_api/mcp_tools.py", "_run_recipe", "source_ifc"): ("LOCKED", "same"),
    ("src/aec_api/routers/authoring.py", "bake_layers", "source_ifc"): ("OPEN",
        "derives a new IFC from the current one, unlocked (gap G-11 / RMW-LOCKGAP)"),
    ("src/aec_api/routers/authoring.py", "import_families", "source_ifc"): ("OPEN", "same"),
    ("src/aec_api/routers/authoring.py", "import_family_pack", "source_ifc"): ("OPEN", "same"),
    ("src/aec_api/routers/authoring.py", "place_family", "source_ifc"): ("OPEN", "same"),
    ("src/aec_api/routers/authoring.py", "content_import", "source_ifc"): ("OPEN", "same"),
    ("src/aec_api/routers/authoring.py", "_restore_version", "source_ifc"): ("OPEN",
        "reads the pointer to validate containment, then writes it -- same class"),
}

#: Sites that read one column and write another, or write a value the caller supplied whole -- plus
#: the ones that are genuinely open and have no concurrency token available.
CROSS_FIELD = {
    # `bim.promote_markup` was here and is CLOSED (MARKUP-PROMOTE) -- it is not merely re-statused,
    # because the conditional UPDATE removes the `m.topic_id = t.id` assignment and the site leaves
    # the derived population altogether. **This gate reported the entry stale before the ledger was
    # touched**, which is the direction it exists for: closing a gap must force the record to move,
    # or the tree ends up describing a defect nobody can still find.
    ("src/aec_api/drawingset.py", "revise_sheet", "data"): ("OPEN",
        "`m.data = d2`, derived from `m.data`; no token on that table."),
    ("src/aec_api/routers/connections.py", "put_mappings", "config"): ("OPEN",
        "`c.config = cfg` merged from `c.config`; no token on that table -- `connections` carries "
        "only `created_at`."),
    ("src/aec_api/routers/connections.py", "update_connection", "config"): ("OPEN",
        "**The find that prompted keying this ledger by attribute.** `merged = dict(c.config or {})` "
        "-> merge the body's keys, KEEPING a stored secret where the form sent it blank -> "
        "`c.config = merged`. That is an accumulation, not a whole-value write, and it was EXEMPT "
        "until 2026-09-14 on the strength of a sentence about `body.name or c.name` -- a different "
        "line of the same function. *An exemption that reasons about part of its subject and reports "
        "on all of it* is this file's own subject, one level up.\n"
        "It is the SECOND writer of the blob `put_mappings` writes, so the two are a pair: one admin "
        "saving connection settings while another saves field mappings loses a write, and whichever "
        "fix `connections` eventually gets has to cover both. *A lock one side does not take "
        "protects nothing* -- the lesson `dev_property` paid for."),
    ("src/aec_api/routers/proforma.py", "put_property", "dev_property"): ("LOCKED",
        "`dev_property` -- the site this pull request's own fix created, then HID from this analyser "
        "by hoisting the read into a local, then hid AGAIN behind an annotation. `projects` carries "
        "no `modified_at` to swap on, so it takes `pid_lock.mutating(pid)` instead, as does its "
        "partner `realestate.save_appraisal`. Verified lexically below, not asserted here."),
    ("src/aec_api/routers/proforma.py", "sync_gmp_to_hard", "dev_budget"): ("OPEN",
        "`dev_budget` merge -- same class, same missing token."),
    ("src/aec_api/routers/proforma.py", "sync_model_to_hard", "dev_budget"): ("OPEN", "`dev_budget` merge -- same."),
}

#: JSON collections on tables with NO `modified_at`, so the register row's token does not exist for
#: them, and JSON equality is not a swap that behaves the same on SQLite and Postgres -- the identical
#: trap `FOR UPDATE` is. Closing these means a migration (roadmap: RMW-TOKEN, gap G-10).
BAND_2 = {
    ("src/aec_api/routers/proforma.py", "share_scenario", "shared_with"): ("OPEN",
        "`shared_with` -- two concurrent grants, one silently dropped. The response echoes the "
        "caller's own target either way, so neither caller can tell it did not take."),
    ("src/aec_api/routers/realestate.py", "save_appraisal", "dev_property"): ("LOCKED",
        "`dev_property` merge -- the OTHER writer of the same blob, locked with `put_property` "
        "because half a lock is none. The non-concurrent half of this blob's problem WAS fixed here: "
        "`proforma.put_property` used to replace it wholesale and delete the appraisal on every "
        "ordinary save -- *a write that reads nothing cannot lose an update, it just deletes one.*"),
}


def orm_rmw_sites() -> list[tuple[str, str, str]]:
    """`obj.attr = <expr derived from obj>` -- INCLUDING through a local.

    The first draft asked only whether the right-hand side mentioned `obj` DIRECTLY, and the fix this
    very pull request made to `proforma.save_property` hoisted the read into a local
    (`prior = p.dev_property or {}` ... `p.dev_property = {**body, ...prior...}`) -- so the analyser
    stopped seeing a site that the same commit had just created. **The fix moved out of its own
    gate's view**, which is worse than the gate never having covered it: the count stayed the same
    and nothing said anything.

    So taint propagates one hop through locals, the same way the Core classifier already does it.
    Written down because the shape is general: *hoisting a read into a variable is the cheapest way
    to make a pattern-matching check stop matching, and it is what a tidy-up commit looks like.*

    Review then found the sequel on PR #552, and it is the same sentence with a cheaper edit:
    ANNOTATING that hoisted local (`prior: dict = p.dev_property`) made the site vanish again,
    because both loops walked `ast.Assign` alone. See `_assigned`.
    """
    out = []
    for p in sorted(SRC.rglob("*.py")):
        out += _orm_sites_in(ast.parse(p.read_text(encoding="utf-8")), str(p.relative_to(HERE)))
    return sorted(set(out))


def _orm_sites_in(tree: ast.AST, path: str) -> list[tuple[str, str, str]]:
    """The per-file half of `orm_rmw_sites`, split out so a FIXTURE can be run through it.

    It was inlined in the loop above, which meant the only way to exercise the analyser was to find a
    real file exhibiting the shape -- and the shape review found missing (`prior: dict = ...`) does
    not occur in this tree, so no amount of reading the source would have produced a failing case.
    *An analyser that can only be fed the repository cannot be given the input it gets wrong.*

    It reports the ATTRIBUTE as well as the function, and that is not cosmetic. The ledgers were
    keyed by `(path, function)` until 2026-09-14, so one status and one sentence covered every
    read-modify-write in a function -- and **six functions write more than one**. The reason names
    whichever the author was looking at; the rest are exempted by a sentence about a different line.
    That is this file's own subject one level up: *an exemption that reasons about part of its
    subject and reports on all of it.* It had already hidden a live gap -- see
    `connections.update_connection`.
    """
    out = []
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        # local -> the object names its value was read from
        via: dict[str, set[str]] = {}
        for _ in range(4):                           # fixed point; these chains are one or two hops
            for n in ast.walk(fn):
                pair = _assigned(n)
                if pair is None:
                    continue
                targets, value = pair
                srcs = {x.value.id for x in ast.walk(value)
                        if isinstance(x, ast.Attribute) and isinstance(x.value, ast.Name)}
                for nm in ast.walk(value):
                    if isinstance(nm, ast.Name) and nm.id in via:
                        srcs |= via[nm.id]
                if not srcs:
                    continue
                for t in targets:
                    for nm in ast.walk(t):
                        if isinstance(nm, ast.Name):
                            via.setdefault(nm.id, set()).update(srcs)
        for n in ast.walk(fn):
            pair = _assigned(n)
            if pair is not None:
                targets, value = pair
            elif isinstance(n, ast.AugAssign):
                targets, value = [n.target], n.value
            else:
                continue
            for tgt in targets:
                if not (isinstance(tgt, ast.Attribute) and isinstance(tgt.value, ast.Name)):
                    continue
                obj = tgt.value.id
                if obj in ("self", "cls", "os", "sys"):
                    continue
                used = {x.value.id for x in ast.walk(value)
                        if isinstance(x, ast.Attribute) and isinstance(x.value, ast.Name)}
                for nm in ast.walk(value):
                    if isinstance(nm, ast.Name) and nm.id in via:
                        used |= via[nm.id]
                if isinstance(n, ast.AugAssign) or obj in used:
                    out.append((path, fn.name, tgt.attr))
    return sorted(set(out))


#: `proforma.put_property`'s shape, in three spellings. The direct read and the hoisted local were
#: already covered; the ANNOTATED local is the one review found missing on PR #552, and it dropped
#: the site out of the population entirely -- taking its ledger entry with it, so `_stale` would then
#: have reported the ENTRY as the problem and pointed the next reader at the wrong file.
_ORM_DIRECT = ('def put_property(db, p, body):\n'
               '    p.dev_property = {**body, "appraisal": (p.dev_property or {}).get("appraisal")}\n')
_ORM_HOISTED = ('def put_property(db, p, body):\n'
                '    prior = p.dev_property or {}\n'
                '    p.dev_property = {**body, "appraisal": prior.get("appraisal")}\n')
_ORM_ANNOTATED = ('def put_property(db, p, body):\n'
                  '    prior: dict = p.dev_property or {}\n'
                  '    p.dev_property = {**body, "appraisal": prior.get("appraisal")}\n')
for _spelling, _src in (("read inline", _ORM_DIRECT), ("hoisted into a local", _ORM_HOISTED),
                        ("hoisted and ANNOTATED", _ORM_ANNOTATED)):
    check(f"SELF-TEST: the ORM analyser sees the read-modify-write with the read {_spelling}",
          _orm_sites_in(ast.parse(_src), "<fx>") == [("<fx>", "put_property", "dev_property")],
          f"got {_orm_sites_in(ast.parse(_src), '<fx>')}")

#: ONE function, TWO read-modify-written attributes. The analyser must report both, because the
#: ledger key is `(path, function, attribute)` and a function that reported only its first attribute
#: would file one race and leave the other unexamined -- which is precisely what the
#: `(path, function)` key did until 2026-09-14, and it hid `connections.update_connection`'s `config`
#: merge behind a sentence about `name`.
_ORM_TWO_ATTRS = ('def save(db, c, body):\n'
                  '    c.name = body.get("name") or c.name\n'
                  '    merged = dict(c.config or {})\n'
                  '    merged.update(body.get("config") or {})\n'
                  '    c.config = merged\n')
check("SELF-TEST: one function writing TWO attributes yields TWO entries, not one",
      _orm_sites_in(ast.parse(_ORM_TWO_ATTRS), "<fx>") == [("<fx>", "save", "config"),
                                                           ("<fx>", "save", "name")],
      f'got {_orm_sites_in(ast.parse(_ORM_TWO_ATTRS), "<fx>")}')

#: ...and a wholesale overwrite is NOT one, so the three positives above are not always-yes. This is
#: `put_property` as it shipped BEFORE this pull request -- which is a different defect, not a race.
check("SELF-TEST: a write that reads nothing back is not a read-modify-write",
      _orm_sites_in(ast.parse('def put_property(db, p, body):\n    p.dev_property = body\n'),
                    "<fx>") == [],
      "a wholesale overwrite was counted as a read-modify-write")

ORM = orm_rmw_sites()
check("the ORM derivation REACHES a known site, asserted before its count is believed",
      ("src/aec_api/coordination_fresh.py", "recheck", "labels") in ORM, f"found {len(ORM)}")
_KNOWN = {**ORM_LEDGER, **BAND_2, **IFC_PIPELINE, **CROSS_FIELD}
_bad_status = sorted((k, v[0]) for k, v in _KNOWN.items() if v[0] not in STATUSES)
check("every ledger entry carries a STATUS from the declared set, so the open count is structural "
      "rather than a substring search over prose -- which is how it read 13 when it was 14",
      not _bad_status, f"{len(_KNOWN)} entries; bad status: {_bad_status}")
_unfiled = [s for s in ORM if s not in _KNOWN]
check("every ORM read-modify-write is either reasoned exempt or named as an open gap",
      not _unfiled, f"unfiled={_unfiled}")
_stale = [k for k in _KNOWN if k not in ORM]
check("no ledger entry outlives the site it describes", not _stale, f"stale={_stale}")

# The key gained its third column on 2026-09-14, and this is the check that says the third column
# EARNS its place rather than decorating the file. A `(path, function)` key can carry exactly one
# status, so a function whose attributes disagree could not be expressed at all -- one of them had to
# ride on the other's reasoning, and `connections.update_connection` did: `name` EXEMPT as a PATCH
# default, `config` a genuine accumulating merge, one sentence covering both.
#
# *Asserting the re-key is possible is not asserting it was necessary.* This demands a live instance.
_by_fn: dict[tuple[str, str], set[str]] = {}
for (_p, _f, _a), (_st, _) in _KNOWN.items():
    _by_fn.setdefault((_p, _f), set()).add(_st)
_disagree = sorted(k for k, v in _by_fn.items() if len(v) > 1)
check("at least one function's attributes carry DIFFERENT statuses -- the thing the old "
      "(path, function) key could not express, so the extra column is load-bearing and not cosmetic",
      _disagree,
      "NO function's attributes disagree. Two very different things cause this and the fix differs: "
      "(a) somebody collapsed the attribute key back to one value per function, in which case the "
      "checks above will be red too -- fix those first; or (b) the last genuinely-disagreeing site "
      "was legitimately CLOSED, today `connections.update_connection` (`name` EXEMPT, `config` "
      "OPEN), in which case nothing is wrong and this check has outlived its subject: delete it and "
      "say so in the commit. *A check whose failure message can misdiagnose is worse than one that "
      "stays silent, because somebody acts on it.*")
# ---------------------------------------------------------------- the IFC pipeline's OTHER control
def under_pid_lock(path: str, name: str, col: str = "source_ifc") -> bool:
    """Is the WHOLE `<col>` read-modify-write inside `with pid_lock.mutating(...)`?

    The first draft asked only about the ASSIGNMENT, and review caught that on PR #552: a route can
    read `p.source_ifc`, spend a minute deriving a new IFC version from it, and only then enter the
    lock to assign -- passing a check that looks at the write alone while two callers derive from the
    same old version and the second assignment erases the first. *A lock proves nothing about the
    statement it contains; it proves something about the interval it spans, and this was measuring
    the wrong one.*

    So every `.<col>` mention -- read or write -- must be inside the lock. That is stricter than
    strictly necessary (a read for logging would count), and deliberately so: this function decides
    whether to CERTIFY a route as protected, and the safe direction for a certifier is to refuse
    something it cannot prove.

    `col` is a parameter because the second column arrived: the `dev_property` blob has two writers in
    two routers, and locking only the one review named would have left the pair exactly as racy as
    before -- *a lock one side does not take protects nothing.*
    """
    tree = ast.parse((HERE / path).read_text(encoding="utf-8"))
    fn = next((f for f in ast.walk(tree)
               if isinstance(f, (ast.FunctionDef, ast.AsyncFunctionDef)) and f.name == name), None)
    return fn is not None and lock_spans_rmw(fn, col)


def lock_spans_rmw(fn: ast.AST, col: str = "source_ifc") -> bool:
    """The node-level half of `under_pid_lock`, split out so the fixtures below can exercise it."""
    outside = []

    class V(ast.NodeVisitor):
        def __init__(self):
            self.depth = 0

        def visit_With(self, node):
            held = any("pid_lock.mutating" in ast.unparse(i.context_expr) for i in node.items)
            self.depth += 1 if held else 0
            self.generic_visit(node)
            self.depth -= 1 if held else 0

        visit_AsyncWith = visit_With

        def visit_Attribute(self, node):
            if node.attr == col and not self.depth:
                outside.append(node.lineno)
            self.generic_visit(node)

    V().visit(fn)
    return not outside


#: The shape review named: read and derive OUTSIDE, assign INSIDE. The first draft passed this.
_LATE_LOCK = ast.parse(
    'def route(db, pid, p, ed):\n'
    '    out = ed.apply_recipe(p.source_ifc, "add_family", {}, "/tmp/new.ifc")\n'
    '    with pid_lock.mutating(pid):\n'
    '        p.source_ifc = out\n'
    '        db.commit()\n').body[0]
check("SELF-TEST: deriving from `source_ifc` BEFORE the lock and assigning inside is NOT protected",
      not lock_spans_rmw(_LATE_LOCK), "a read outside the lock was certified as locked")

#: The shape the six shipped routes actually use: the whole thing inside.
_FULL_LOCK = ast.parse(
    'def route(db, pid, ed):\n'
    '    with pid_lock.mutating(pid):\n'
    '        p = _project(db, pid)\n'
    '        out = ed.apply_recipe(p.source_ifc, "add_family", {}, "/tmp/new.ifc")\n'
    '        p.source_ifc = out\n'
    '        db.commit()\n').body[0]
check("SELF-TEST: ...and the fully-enclosed shape IS, so the checker is not always-no",
      lock_spans_rmw(_FULL_LOCK), "a fully locked route was reported unprotected")

#: No lock at all -- the six open sites.
_NO_LOCK = ast.parse(
    'def route(db, pid, p, ed):\n'
    '    out = ed.apply_recipe(p.source_ifc, "add_family", {}, "/tmp/new.ifc")\n'
    '    p.source_ifc = out\n').body[0]
check("SELF-TEST: and an unlocked route is unprotected",
      not lock_spans_rmw(_NO_LOCK), "an unlocked route was certified")

_claimed_locked = sorted(k for k, (st, _) in IFC_PIPELINE.items() if st == "LOCKED")
_lying = [k for k in _claimed_locked if not under_pid_lock(*k)]
check("every site this ledger calls locked IS lexically under `pid_lock.mutating`",
      not _lying, f"{len(_claimed_locked)} claimed locked; not actually: {_lying}")

#: The second locked column. Derived from the ledgers rather than listed, so adding a third writer
#: of this blob and forgetting to lock it reds the build instead of joining a list nobody re-reads.
#: The filter was `"dev_property" in <the reason prose>` until the ledger gained an attribute key --
#: *a derivation over prose, in the file whose own lesson is that a count derived by grepping prose
#: IS prose.* It reads `k[2] == "dev_property"` now, and `under_pid_lock(*k)` takes the column
#: straight from the key rather than being told it a second time.
DEV_PROPERTY = sorted(k for k, (st, _) in {**CROSS_FIELD, **BAND_2}.items()
                      if st == "LOCKED" and k[2] == "dev_property")
check("the `dev_property` pair is BOTH writers, derived from the ledgers -- locking one of two is "
      "locking neither, and this is the shape that makes the omission visible",
      DEV_PROPERTY == [("src/aec_api/routers/proforma.py", "put_property", "dev_property"),
                       ("src/aec_api/routers/realestate.py", "save_appraisal", "dev_property")],
      f"got {DEV_PROPERTY}")
_dp_lying = [k for k in DEV_PROPERTY if not under_pid_lock(*k)]
check("...and every `dev_property` read AND write in both is lexically under `pid_lock.mutating`",
      not _dp_lying, f"claimed locked but is not: {_dp_lying}")

_claimed_open = sorted(k for k, (st, _) in IFC_PIPELINE.items() if st == "OPEN")
# NOT `_secretly_fixed`, which is what this was called for about twenty minutes. CodeQL's
# `py/clear-text-logging-sensitive-data` classifies a source by its IDENTIFIER NAME, so a local
# containing "secret" flowing into the `print` in `check()` is a HIGH alert -- on a gate whose values
# are file paths and function names. A pure false positive, fixed by naming the variable better
# rather than by suppressing the query: *a suppression is a claim that has to be re-read and
# re-believed by everyone who meets it, and this one would have been protecting a synonym.*
_quietly_closed = [k for k in _claimed_open if under_pid_lock(*k)]
check("and every site it calls OPEN really is unlocked -- so closing one must update this ledger "
      "rather than leave a gap recorded that no longer exists",
      not _quietly_closed, f"{len(_claimed_open)} open; closed without updating this list: "
                           f"{_quietly_closed}")

check("the share-token view counter is no longer an ORM read-modify-write",
      ("src/aec_api/client_portal.py", "model_fragment") not in ORM
      and ("src/aec_api/client_portal.py", "digest") not in ORM,
      "the increment moved into SQL")

_open = [k for k, (st, _) in _KNOWN.items() if st == "OPEN"]
print()
print(f"test_rmw_sweep {'FAILED' if FAILED else 'OK'}"
      f"  ({len(SITES)} register-row update sites, {len(WRITERS)} writers stamping monotonically, "
      f"{len(ORM)} ORM sites: {len(_KNOWN) - len(_open)} reasoned exempt or locked, "
      f"{len(_open)} named open)")
if FAILED:
    for f_ in FAILED:
        print(f"  - {f_}")
    sys.exit(1)
