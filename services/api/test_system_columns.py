"""SYSTEM-COLUMN-PHANTOM — a name on the system-column allowlist that is not a column.

`modules_query.SYSTEM_COLUMNS` names the row columns a caller may filter and sort a register by.
`_resolve_field` returns `{"_system": True}` for anything in it, and both `_field_expr` and
`_display_expr` then index `t.c[name]` on the strength of that flag alone. So a name the allowlist
admits but the TABLE does not have is a `KeyError` raised inside a request handler — **a 500 on
caller-supplied input**, which is the one thing `_resolve_field` exists to prevent: its own docstring
says "Never trust a caller-supplied field name", and the trust it was actually extending was in the
literal three lines above it.

Two of the six names were phantoms. Measured over HTTP against a live register before the fix:

    ?sort=not_a_field     -> 400      (the intended answer)
    ?sort=workflow_state  -> 200
    ?sort=updated_at      -> 500      <- the register column is `modified_at`
    ?sort=ball_in_court   -> 500      <- derived from workflow_state, never stored

`updated_at` is the THIRD instance of that exact typo: `quality.py` and `rfi.register` both read it
off a module row and silently got `None` for `avg_days_to_close` (fixed 2026-08). Those two failed
quietly and this one is reachable from a URL — *the same wrong name is not the same severity in two
places, and the loud one was found last.*

**The stored form is worse than the transient one.** `validate_view_config` resolves `sort`,
`group_by`, `agg_field`, `columns` and `filters` through this same `_resolve_field`, with no table in
scope at all. Measured against the pre-fix code: saving a view with `{"sort": "updated_at"}` returned
**201**, and listing the project's views returned **200** — the 500 arrives only when the view is
APPLIED, because that is where the sort becomes a query. So the stored form is not a louder version
of the same failure, it is a quieter one: it is accepted, it lists, and it fails at the moment
somebody clicks it. A 500 you can reproduce by re-typing a URL is an incident; one somebody saved
into a shared view is a support ticket whose cause is two screens away from the symptom.

So the fix is not "delete the two names". Deleting them fixes today's list and leaves the next one
reachable. `_system_field` validates the allowlist against the register table at resolve time, which
turns any future phantom back into the 400 an unknown field is supposed to get, and this gate asserts
the list statically so it never gets that far.

**A third derivation bounds the fix.** `_system_field` is one function, so it only closes the class
while every site that indexes a register table by a caller-supplied name goes through it. Those sites
are DERIVED — `t.c[<non-literal>]`, which is 3 today (`_field_expr`, `_eq_or_pair`, `_display_expr`)
— and each must sit under a `_system` test. The ORM shape of the same defect, `getattr(Model, name)`
with a caller-supplied name, was searched for and is absent: a clean negative, recorded because "we
checked and found none" and "we did not check" look identical afterwards.

**Both halves are checked independently, and that is deliberate.** The static half would pass if the
runtime guard were deleted; the runtime half would pass if the list were wrong. So the block below
puts the two phantoms BACK on the allowlist and requires the guard to refuse them anyway — proving
the guard, not the list — and then deletes the guard and requires the `KeyError` to return, proving
those assertions were testing something. Neither half is asserted while the other is doing the work.

Run: cd services/api && PYTHONPATH=src:../data/src ./.venv/bin/python test_system_columns.py
"""
import ast
import os
import pathlib

os.environ["DATABASE_URL"] = "sqlite:///./test_syscol.db"
os.environ["STORAGE_DIR"] = "./test_syscol_storage"

for f in ("./test_syscol.db",):
    if os.path.exists(f):
        os.remove(f)

from fastapi import HTTPException  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aec_api import modules_query as mq  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.modules_registry import REGISTRY, TABLES  # noqa: E402

FAILED: list[str] = []


def check(label, cond, detail=""):
    (print(f"PASS  {label}   {detail}") if cond
     else (FAILED.append(label), print(f"FAIL  {label}   {detail}")))


# ---- the derivation, as a function, so a mutation can be aimed at IT ------------------------------
def phantoms(allowlist) -> list[str]:
    """Every name in `allowlist` that is not a column on some register table, as `key.name`.

    Derived from `TABLES` — the same objects the queries run against — rather than from a list of
    column names written down here. A gate that carries its own copy of the schema is checking one
    piece of prose against another.
    """
    out = []
    for key, t in sorted(TABLES.items()):
        cols = {c.name for c in t.columns}
        out += [f"{key}.{n}" for n in sorted(allowlist) if n not in cols]
    return out


with TestClient(app) as c:
    # ---- population first: every sweep below is vacuous on an empty registry ----------------------
    check("the module registry is loaded before anything is derived from it", len(REGISTRY) > 130,
          f"{len(REGISTRY)} modules")
    check("every registered module has a table", set(REGISTRY) == set(TABLES),
          f"REGISTRY {len(REGISTRY)}, TABLES {len(TABLES)}; symmetric difference "
          f"{sorted(set(REGISTRY) ^ set(TABLES)) or 'none'}")
    check("SYSTEM_COLUMNS is non-trivial", len(mq.SYSTEM_COLUMNS) >= 5,
          f"{sorted(mq.SYSTEM_COLUMNS)}")

    # ---- STATIC HALF: the allowlist names real columns --------------------------------------------
    found = phantoms(mq.SYSTEM_COLUMNS)
    check("no name on SYSTEM_COLUMNS is a phantom column", not found,
          f"checked {len(mq.SYSTEM_COLUMNS)} names x {len(TABLES)} tables"
          if not found else f"{len(found)} phantom(s), e.g. {found[:4]}")

    # The derivation must FIND the two names that shipped, or it is only reporting good news.
    for ghost in ("updated_at", "ball_in_court"):
        check(f"the derivation finds the shipped phantom {ghost!r}",
              bool(phantoms(set(mq.SYSTEM_COLUMNS) | {ghost})),
              "a checker that cannot reproduce the defect it was written for is answering, "
              "not checking")

    # ---- the POPULATION of sites that trust the `_system` flag -----------------------------------
    #
    # The fix is in one function, so it only holds if every place that indexes a register table by a
    # caller-supplied name goes through it. Derived rather than listed: `t.c[<expr>]` with a
    # non-literal subscript, each of which must sit under a `_system` test. A fourth such site added
    # without that guard reds this, which is the point — the fix is one function only as long as the
    # population is three.
    #
    # `unguarded_sites` is a function of SOURCE TEXT so it can be run against a synthetic defect
    # before it is trusted on the real file. A derivation that has never been shown to find anything
    # reports a clean tree for the same reason a correct one does.
    def unguarded_sites(src: str) -> tuple[list[int], list[int]]:
        """`(all dynamic t.c[...] lines, the ones NOT under a `_system` test)`."""
        tree = ast.parse(src)
        parents: dict[int, ast.AST] = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[id(child)] = node

        def guarded(node: ast.AST) -> bool:
            """Is this site under a CONTROL-FLOW CONDITION that tests `_system`?

            Only `If.test` and `IfExp.test`, and that narrowness is the whole correctness of this
            function. The first draft asked `"_system" in ast.unparse(<any enclosing stmt>)` — and
            `ast.unparse` of a compound statement includes its entire BODY, so an unrelated
            `_system` anywhere in the enclosing `for` marked everything inside it guarded.
            `_apply_filters` has exactly that shape, so making its `t.c[name]` unconditional was
            invisible: measured, the old predicate reported the mutated tree clean.

            *A checker that asks "does this text appear nearby" is asking about proximity and
            answering about control flow.* Found by review, and it is the fourth time in this line
            of work that the checker carried the defect it was written to catch.
            """
            cur: ast.AST | None = node
            while cur is not None:
                if isinstance(cur, ast.If) and "_system" in ast.unparse(cur.test):
                    return True
                if isinstance(cur, ast.IfExp) and "_system" in ast.unparse(cur.test):
                    return True
                if isinstance(cur, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    return False
                cur = parents.get(id(cur))
            return False

        sites = [n for n in ast.walk(tree)
                 if isinstance(n, ast.Subscript)
                 and isinstance(n.value, ast.Attribute) and n.value.attr == "c"
                 and isinstance(n.value.value, ast.Name) and n.value.value.id == "t"
                 and not isinstance(n.slice, ast.Constant)]
        return [n.lineno for n in sites], [n.lineno for n in sites if not guarded(n)]

    _BAD = "def f(t, name):\n    return t.c[name]\n"
    _GOOD = "def f(t, name, f_):\n    if f_.get('_system'):\n        return t.c[name]\n    return None\n"
    _TERNARY = "def f(t, name, f_, j):\n    return t.c[name] if f_.get('_system') else j\n"
    _LITERAL = "def f(t):\n    return t.c['data']\n"
    # PROXIMITY IS NOT CONTROL FLOW. An unrelated `_system` in the enclosing loop must NOT clear an
    # unconditional lookup — this is the exact shape `_apply_filters` has, and the shape the first
    # draft of `guarded` was blind to.
    _NEARBY = ("def f(t, name, rows):\n"
               "    for r in rows:\n"
               "        if r.get('_system'):\n"
               "            pass\n"
               "        x = t.c[name]\n"
               "    return x\n")
    check("the site derivation FINDS an unguarded t.c[name]", unguarded_sites(_BAD) == ([2], [2]),
          f"got {unguarded_sites(_BAD)}")
    check("...and clears a guarded one", unguarded_sites(_GOOD)[1] == [],
          f"got {unguarded_sites(_GOOD)}")
    check("...and clears the ternary form", unguarded_sites(_TERNARY)[1] == [],
          f"got {unguarded_sites(_TERNARY)}")
    check("...and ignores a literal column name", unguarded_sites(_LITERAL) == ([], []),
          "t.c['data'] is not a caller-supplied name and must not be counted")
    check("...and is NOT fooled by an unrelated `_system` in the enclosing loop",
          unguarded_sites(_NEARBY) == ([5], [5]),
          f"got {unguarded_sites(_NEARBY)} — proximity is not control flow; the first draft of this "
          f"predicate read the whole enclosing statement and cleared this")

    _SRC = pathlib.Path("src/aec_api/modules_query.py").read_text(encoding="utf-8")

    # And the same question asked of the REAL file, not a synthetic: make `_eq_or_pair`'s lookup
    # unconditional and require the derivation to flag it. The synthetic case above proves the rule;
    # this proves the rule reaches the site that motivated it.
    _MUT = _SRC.replace(
        'text_expr = t.c[name] if f.get("_system") else _json_text(db, t.c.data, name)',
        "text_expr = t.c[name]")
    check("the mutation the self-test needs still applies to modules_query.py", _MUT != _SRC,
          "the `_eq_or_pair` line was reworded — re-derive this mutation rather than deleting it")
    check("...and removing `_eq_or_pair`'s own guard is CAUGHT", bool(unguarded_sites(_MUT)[1]),
          f"unguarded in the mutated tree: {sorted(unguarded_sites(_MUT)[1]) or 'NONE — blind'}")

    _all, _bad = unguarded_sites(_SRC)
    check("every dynamic `t.c[...]` is under a `_system` test", not _bad,
          f"{len(_all)} site(s) at lines {sorted(_all)}; unguarded: {sorted(_bad) or 'none'}")
    check("the population is the three known sites, not fewer", len(_all) == 3,
          f"{len(_all)} — if this grew, read the new one; if it shrank, the derivation broke")

    # ---- RUNTIME HALF: the guard, with the allowlist deliberately WRONG ---------------------------
    #
    # This is the half that survives the next phantom. It is asserted with `updated_at` put BACK on
    # the allowlist, because a runtime guard that is only ever asked about correct input is untested.
    mod = REGISTRY["rfi"]
    t = TABLES["rfi"]
    real = mq.SYSTEM_COLUMNS
    try:
        mq.SYSTEM_COLUMNS = set(real) | {"updated_at", "ball_in_court"}

        for ghost in ("updated_at", "ball_in_court"):
            check(f"_system_field refuses {ghost!r} even while the allowlist admits it",
                  mq._system_field(mod, ghost) is None)
            try:
                mq._resolve_field(mod, ghost)
                check(f"_resolve_field raises 400 for {ghost!r}", False, "returned a field instead")
            except HTTPException as e:
                check(f"_resolve_field raises 400 for {ghost!r}", e.status_code == 400,
                      f"status {e.status_code}")
            # `_field_expr` is the site that actually raised. db is unused on both paths reached here.
            try:
                mq._field_expr(None, t, mod, ghost)
                check(f"_field_expr raises 400 for {ghost!r}", False, "built an expression instead")
            except HTTPException as e:
                check(f"_field_expr raises 400 for {ghost!r}", e.status_code == 400)
            except KeyError:
                check(f"_field_expr raises 400 for {ghost!r}", False,
                      "KeyError -> this is the 500 the fix exists to remove")

        # MUTATION: put the pre-fix `_system_field` back and require the KeyError to return. Without
        # this the two checks above would pass on a build where the guard had been deleted and only
        # the LIST was right — which is the state the code shipped in.
        real_sysf = mq._system_field
        try:
            mq._system_field = lambda m, n: ({"name": n, "type": "text", "_system": True}
                                             if n in mq.SYSTEM_COLUMNS else None)
            hit = False
            try:
                mq._field_expr(None, t, mod, "updated_at")
            except KeyError:
                hit = True
            except HTTPException:
                pass
            check("removing the table check reinstates the KeyError", hit,
                  "the guard is load-bearing" if hit else
                  "the checks above pass without the guard, so they are not testing it")
        finally:
            mq._system_field = real_sysf
    finally:
        mq.SYSTEM_COLUMNS = real

# ---- END TO END: the symptom, over real HTTP -----------------------------------------------------
with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "System Columns"}).json()["id"]
    r = c.post(f"/projects/{pid}/modules/rfi",
               json={"data": {"subject": "Column phantom", "question": "Which column?",
                              "discipline": "Structural"}})
    check("a record exists to sort", r.status_code in (200, 201), f"{r.status_code} {r.text[:200]}")

    def status(params):
        return c.get(f"/projects/{pid}/modules/rfi", params=params).status_code

    check("?sort=workflow_state is 200", status({"sort": "workflow_state"}) == 200)
    check("?sort=created_at is 200", status({"sort": "created_at"}) == 200)
    check("?sort=modified_at is 200 — the column the phantom meant",
          status({"sort": "modified_at"}) == 200,
          "`updated_at` was the intended capability all along; it named the wrong column")
    check("?sort=not_a_field is 400", status({"sort": "not_a_field"}) == 400)
    for ghost in ("updated_at", "ball_in_court"):
        check(f"?sort={ghost} is 400, not 500", status({"sort": ghost}) == 400,
              f"got {status({'sort': ghost})}")
        check(f"?f.{ghost}.eq= is 400, not 500",
              c.get(f"/projects/{pid}/modules/rfi",
                    params={f"f.{ghost}.eq": "x"}).status_code == 400)
        check(f"?group_by={ghost} is 400, not 500",
              c.get(f"/projects/{pid}/modules/rfi/aggregate",
                    params={"group_by": ghost}).status_code == 400)
        # The STORED form. A view saved with a phantom sort 500s on every read of it afterwards,
        # and nothing in the saved-view path has a table in scope to notice.
        vst = c.post(f"/projects/{pid}/modules/rfi/views",
                     json={"name": f"v-{ghost}", "config": {"sort": ghost}}).status_code
        check(f"a saved view sorting by {ghost} is refused at WRITE time", vst in (400, 422),
              f"{vst} — before the fix this was ACCEPTED and 500'd on every read of the view")
    # A 200 is not an ordering, and an ordering that merely honours `sort_dir` is not an ordering by
    # THIS column. `modified_at` is the capability the phantom name was reaching for, so the check
    # has to separate it from `created_at`: the FIRST record is touched last, which makes the two
    # orders disagree. Without that, a fallback that quietly ordered by creation would pass.
    second = c.post(f"/projects/{pid}/modules/rfi",
                    json={"data": {"subject": "Second", "question": "later"}})
    check("a second record exists to order against", second.status_code in (200, 201),
          f"{second.status_code} {second.text[:160]}")
    first_id = r.json()["id"]
    touched = c.patch(f"/projects/{pid}/modules/rfi/{first_id}",
                      json={"data": {"subject": "Column phantom", "question": "touched last"}})
    check("the FIRST record is touched last, so the two orders must disagree",
          touched.status_code == 200, f"{touched.status_code} {touched.text[:160]}")

    def refs(col, direction="asc"):
        rows = c.get(f"/projects/{pid}/modules/rfi",
                     params={"sort": col, "sort_dir": direction}).json()
        rows = rows.get("items", rows) if isinstance(rows, dict) else rows
        return [x["ref"] for x in rows]

    m_asc, m_desc, c_asc = refs("modified_at"), refs("modified_at", "desc"), refs("created_at")
    check("?sort=modified_at reverses with sort_dir", len(m_asc) == 2 and m_asc == m_desc[::-1],
          f"asc={m_asc} desc={m_desc}")
    check("...and orders by modified_at, not by creation", m_asc != c_asc,
          f"modified_at asc={m_asc}, created_at asc={c_asc} — identical would mean the sort is "
          f"falling through to the default order and the 200 proves nothing")

    check("a saved view sorting by modified_at is accepted",
          c.post(f"/projects/{pid}/modules/rfi/views",
                 json={"name": "v-modified", "config": {"sort": "modified_at"}}
                 ).status_code in (200, 201))

print(("FAILED: " + "; ".join(FAILED)) if FAILED else "test_system_columns OK")
raise SystemExit(1 if FAILED else 0)
