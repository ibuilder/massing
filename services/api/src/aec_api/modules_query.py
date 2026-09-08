"""Module read + workflow-evaluation layer — the self-contained base under `modules.py`.

REL-3. `modules.py` is imported by ~114 files, which made it the riskiest thing in the codebase to
change and the hardest to reason about. It was carried on the backlog as needing *dependency
injection* to split. It does not: these functions call nothing else in `modules.py`, so the
dependency graph is already acyclic and the fix is a **layering cut**, not a seam.

What lives here: the pure workflow evaluators (which transitions are legal from a state, whose court
a record is in) and the read queries (list / count / state rollups / active records). Everything is a
plain function over a `Session` plus the registry — no writes, no audit, no notification side
effects, so it is safe to call from any read path.

`modules.py` re-exports every name below, so the ~114 importers are untouched.
"""
from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException
from sqlalchemy import Float, String, and_, case, cast, func, or_, select
from sqlalchemy.orm import Session

# CSV-SWEEP — the single spreadsheet-cell guard. It is defined in `aec_data` because that is the
# LOWER package (aec_api imports aec_data, never the reverse), so the API's CSV writers and
# aec_data's XLSX writer share ONE definition. Re-exported under the name the API already used.
from aec_data.cells import cell as csv_cell  # noqa: F401

from . import rbac
from .modules_registry import (
    REGISTRY,
    TABLES,
    reference_fields,
    reference_half,
    text_half,
)
from .modules_search import _is_postgres, _pg_document, _pg_tsquery
from .modules_search import search_filter as _search_filter


def _transition(mod: dict, frm: str, action: str) -> dict | None:
    for t in mod.get("workflow", {}).get("transitions", []):
        if t["from"] == frm and t["action"] == action:
            return t
    return None

def available_actions(mod: dict, state: str, party: str | None) -> list[dict]:
    out = []
    for t in mod.get("workflow", {}).get("transitions", []):
        if t["from"] == state and rbac.party_allowed(party, t.get("party", [])):
            out.append({"action": t["action"], "to": t["to"], "party": t.get("party", []),
                        "requires": t.get("requires") or []})
    return out

def court_party(mod: dict, state: str | None) -> str | None:
    """The party whose court a record in `state` is in — who owes the primary next move.

    Taken from the FIRST outgoing transition declared for the state: module authors list the primary
    forward action first (e.g. an RFI in `open` is answered by the Consultant before the GC's `void`
    escape hatch), so the first transition's party is the real ball-in-court. `/`-joins a move shared
    by several parties (Consultant/OwnersRep). Returns None for a terminal state — nobody's move —
    so `transition` leaves the last owner in place there."""
    if not state:
        return None
    for t in mod.get("workflow", {}).get("transitions", []):
        if t["from"] == state:
            parties = t.get("party") or []
            return "/".join(parties) if parties else None
    return None

def _json_text(db: Session, col, jkey: str):
    """Portable JSON scalar-as-text extraction (Postgres ->> / SQLite json_extract). `jkey` is a
    module-defined field name (safe to interpolate into the SQLite JSON path)."""
    if _is_postgres(db):
        return col.op("->>")(jkey)
    return func.json_extract(col, f"$.{jkey}")


def _fold(db: Session, expr):
    """Case-fold `expr` the same way on every backend.

    Postgres `lower()` folds the full Unicode range; SQLite's folds ASCII only, so `Ångström` and
    `ångström` compare unequal there — measured, not assumed. The two backends therefore returned
    DIFFERENT rows for the same filter, and since the API test gate runs SQLite while production runs
    Postgres, the tested behaviour was not the shipped behaviour. `db.py` registers `aec_lower` on
    every SQLite connection so both sides agree.

    It registers `str.lower` and NOT `str.casefold` on purpose — see that function's docstring. The
    first attempt used casefold, which folds ß to ss where Postgres `lower()` leaves it, and so
    swapped an Å divergence for a ß one. Parity with the production backend is the contract.
    """
    return func.aec_lower(expr) if not _is_postgres(db) else func.lower(expr)


# ---- MOD-FILTER: per-field filtering and sorting over the JSON `data` column ----------------------
#
# Until now a register could be narrowed by exactly two things: the full-text `q` and `workflow_state`.
# On a twenty-field register that means no filtering by discipline, vendor, cost code or date range,
# and sorting happened in the browser over whichever page had been fetched — so "sort by amount" on a
# 500-row register sorted 200 rows and silently called it the answer.
#
# Two rules make this safe, and they are the whole design:
#
# 1. **A field name is never taken from the caller.** `_resolve_field` looks the name up in the
#    module's declared fields and returns the *declared* definition, or raises. `_json_text`
#    interpolates `jkey` into a SQLite JSON path, so an unvalidated name would be an injection site —
#    its docstring already said the key must be module-defined, and this is what enforces it.
#
# 2. **A number is compared as a number.** JSON extraction yields text, and text comparison puts 9
#    above 10 and sorts $1,000 before $900. That is the failure mode this codebase keeps meeting: not
#    an error, a plausible wrong answer. Numeric and percent fields are cast to float before they are
#    compared or ordered; dates are left as text because ISO-8601 sorts correctly lexicographically,
#    which is the one case where the cheap thing is also the right thing.

#: Columns that live on the row rather than inside `data`, and may be filtered/sorted directly.
SYSTEM_COLUMNS = {"workflow_state", "created_at", "updated_at", "ref", "assignee", "ball_in_court"}

#: How many per-field filters one query may carry. Lives here rather than in the router because it
#: bounds `_apply_filters`, and `validate_view_config` must apply the SAME cap to a saved view — a
#: view that could store 50 filters would be refused only when someone replayed it as a URL.
MAX_FILTERS = 12

#: The operators a filter may use. `contains` is a case-insensitive substring; `in` takes a
#: comma-separated list; `empty`/`nonempty` ignore the value.
FILTER_OPS = {"eq", "ne", "gte", "lte", "contains", "in", "empty", "nonempty"}

_NUMERIC_FIELD_TYPES = {"number", "currency", "percent"}


def _resolve_field(mod: dict, name: str) -> dict:
    """The DECLARED definition of `name`, or HTTP 400. Never trust a caller-supplied field name."""
    if name in SYSTEM_COLUMNS:
        return {"name": name, "type": "text", "_system": True}
    for f in mod.get("fields", []):
        if f.get("name") == name:
            return f
    raise HTTPException(400, f"unknown filter/sort field {name!r} for this module")


def _field_expr(db: Session, t, mod: dict, name: str):
    """A comparable SQL expression for a declared field — cast to float when the field is numeric."""
    f = _resolve_field(mod, name)
    if f.get("_system"):
        return t.c[name], f
    expr = _json_text(db, t.c.data, name)
    if f.get("type") in _NUMERIC_FIELD_TYPES:
        # NULLIF('') so a blank string does not become 0.0 and sort among the real values — an empty
        # field and a zero are different facts.
        expr = cast(func.nullif(expr, ""), Float)
    return expr, f


def _apply_filters(db: Session, stmt, t, mod: dict, filters: list[tuple[str, str, str]],
                   project_id: str | None = None):
    """Add one WHERE clause per (field, op, value). Unknown field or op -> 400, never ignored:
    a filter that is silently dropped shows MORE rows than the user asked for and looks like data."""
    for name, op, value in filters:
        if op not in FILTER_OPS:
            raise HTTPException(400, f"unknown filter operator {op!r} (expected one of "
                                     f"{sorted(FILTER_OPS)})")
        expr, f = _field_expr(db, t, mod, name)
        numeric = f.get("type") in _NUMERIC_FIELD_TYPES and not f.get("_system")
        if op == "empty":
            stmt = stmt.where(or_(expr.is_(None), expr == ("" if not numeric else None)))
            continue
        if op == "nonempty":
            stmt = stmt.where(expr.isnot(None))
            if not numeric:
                stmt = stmt.where(expr != "")
            continue
        if op == "in":
            vals = [v.strip() for v in str(value).split(",") if v.strip()]
            if not vals:
                continue
            stmt = stmt.where(expr.in_([_coerce(v, numeric) for v in vals]))
            continue
        if op == "contains":
            # substring match is a TEXT operation; on a numeric field it would be nonsense, so the
            # cast is bypassed rather than silently comparing a float to a pattern
            text_expr = t.c[name] if f.get("_system") else _json_text(db, t.c.data, name)
            stmt = stmt.where(func.lower(cast(text_expr, String)).like(f"%{str(value).lower()}%"))
            continue
        v = _coerce(value, numeric)
        if op == "eq":
            stmt = stmt.where(_eq_or_pair(db, t, mod, name, f, expr, v, project_id))
            continue
        stmt = stmt.where({"ne": expr != v, "gte": expr >= v, "lte": expr <= v}[op])
    return stmt


def _eq_or_pair(db: Session, t, mod: dict, name: str, f: dict, expr, v,
                project_id: str | None = None):
    """`field == v`, widened to the pair's TEXT half when `name` is a reference with one beside it.

    PAIR-FILTER. "Everything open with this subcontractor" is the question the reference fields were
    added to make askable, and the additive pattern means a register in use across the change holds
    both eras: some rows point at the company record, some still carry the name somebody typed. A
    filter that matches only the linked rows returns a SHORT list, and a short filtered list is
    indistinguishable from "there are none" — the same failure this file's own sort note describes as
    *the wrong 200 rows*, and worse here because nothing on screen looks wrong.

    **Exact title, never a substring.** The widened clause matches a text twin equal to the linked
    record's title, case-insensitively. That is strictly more matches and every one of them is right.
    A `contains` match would also catch "Acme Electrical Inc" — and would catch "Acme Electrical
    Supply", a different firm, which on a register people ask money questions against is a filter
    that quietly over-reports. **A row whose typed name is a variant is still missed**; that is a
    known and deliberate limit, not an oversight, and the honest fix for it is linking the record.
    """
    if f.get("_system") or f.get("type") != "reference" or not f.get("module"):
        return expr == v
    twin = text_half(name, {x.get("name"): x for x in mod.get("fields", [])})
    if not twin:
        return expr == v
    target = TABLES.get(f["module"])
    if target is None:
        return expr == v
    # A scalar SUBQUERY, not a second round trip and not a join. `id` is the primary key, so it
    # yields at most one row by construction — which is also why this reads cleanly to
    # `test_unique_read_guard`: the first draft resolved the title with its own
    # `scalar_one_or_none()`, and that gate correctly reported it as an unresolvable
    # unique-demanding read, because `target` comes from `TABLES` at runtime and no analyser can see
    # which column it filtered on. The gate failing CLOSED on my own new code is it working; folding
    # the lookup into the clause is a better answer than arguing an exemption, and it costs one
    # query rather than two.
    # SCOPED TO THE PROJECT, not to the id alone. Every module table carries `project_id`, and the
    # filter VALUE is caller-supplied: resolving a title by id only lets a record id from another
    # project decide what a text twin in THIS project matches against (IDOR — found in review). The
    # id is a uuid4 so guessing one is not the threat; leaking a title across a tenant boundary is.
    title_q = select(_fold(db, target.c.title)).where(target.c.id == v)
    if project_id is not None:
        title_q = title_q.where(target.c.project_id == project_id)
    title = title_q.scalar_subquery()
    twin_expr = _fold(db, cast(_json_text(db, t.c.data, twin), String))
    # A NULL title (no such record, or an untitled one) makes the right side NULL, which is not
    # TRUE — so the clause degrades to `expr == v` rather than matching every row with a blank twin.
    return or_(expr == v, twin_expr == title)


def _coerce(value: str, numeric: bool):
    if not numeric:
        return value
    try:
        return float(value)
    except (TypeError, ValueError):
        raise HTTPException(400, f"{value!r} is not a number, but the field is numeric") from None


def _display_expr(db: Session, t, mod: dict, name: str, project_id: str | None, tag: str = "disp"):
    """`(expr, joins, numeric)` — the value a column RENDERS, not the value it stores.

    `joins` is a list of `(alias, onclause)` the caller must LEFT JOIN onto its statement. Returning
    them rather than mutating a statement handed in is what lets `aggregate` use this: there the
    expression is needed to BUILD the select, so there is no statement to mutate yet.

    REF-SORT / REF-LABEL. `_field_expr` compares a `reference` field as the uuid4 sitting in the JSON blob, which
    is the right expression for `eq` and a meaningless one for ORDER BY: measured before this
    existed, sorting `delivery` by `supplier_company` ascending returned Delta, Mid Atlantic, Acme,
    Zeta — the stored ids in lexical order, under an ascending arrow. 33 register columns are
    reference fields. The paired direction was worse: sorting the TEXT half put every linked row
    first as a NULL while COL-PAIR renders company names into those very cells, so the column read as
    visibly unsorted text under a sort indicator.

    So the key mirrors `pairedValue` + `refCell` in the web register — the order has to agree with the
    column the user is looking at. Per half, in order:

      * a reference that RESOLVES  -> the referenced record's title (what the link reads)
      * a reference that does not  -> the stored value verbatim. A legacy free-text value is TEXT,
                                      not a blank; it is the only handle anyone has for re-linking
                                      the record, and burying it under the empty rows is how it stops
                                      being noticed.
      * anything else              -> its own value

    and the column's own half wins whenever it has something to say, falling back to its pair twin
    when it does not. That is `pairedValue`'s rule, expressed in SQL.

    The join is LEFT and its project scope is in the **ON clause**. A predicate on the nullable side
    of an outer join in the WHERE clause turns it back into an inner join and deletes rows — see
    `aggregate`, where exactly that shipped. A sort orders rows; it must never choose them.
    """
    f = _resolve_field(mod, name)
    if f.get("_system"):
        return t.c[name], [], False
    by_name = {x.get("name"): x for x in mod.get("fields", [])}
    twin = (text_half(name, by_name) if f.get("type") == "reference"
            else reference_half(name, by_name))
    # A pair is always text+reference, so a numeric field is never half of one. Handling it here
    # keeps `_fold` (which is for names) away from a float, rather than sniffing the type afterwards.
    if f.get("type") in _NUMERIC_FIELD_TYPES:
        return cast(func.nullif(_json_text(db, t.c.data, name), ""), Float), [], True

    joins: list = []

    def half(fname: str):
        """The display expression for one half, joining its target when the half is a reference."""
        fd = by_name.get(fname) or {}
        raw = func.nullif(cast(_json_text(db, t.c.data, fname), String), "")
        target = TABLES.get(fd.get("module") or "") if fd.get("type") == "reference" else None
        if target is None:
            return raw
        a = target.alias(f"{tag}_{fname}")
        on = _json_text(db, t.c.data, fname) == a.c.id
        if project_id is not None:
            on = and_(on, a.c.project_id == project_id)
        joins.append((a, on))
        return func.coalesce(a.c.title, raw)

    expr = half(name)
    if twin:
        expr = func.coalesce(expr, half(twin))
    return expr, joins, False


def resolve_titles(db: Session, module_key: str, ids: set[str], project_id: str) -> dict[str, str]:
    """`{id: title}` for `ids` **within `project_id`**, or `{}` when the module is unknown.

    Scoped to the project for the reason PAIR-FILTER was: a record id is caller-supplied data, and a
    lookup by id alone lets a row created with another project's id pull that project's title across
    the boundary. Chunked because SQLite caps the number of bound parameters in one statement, and a
    CSV page is 1,000 rows — an unchunked `IN` over a full page is a query that works in tests and
    raises on a real export.
    """
    t = TABLES.get(module_key)
    if t is None or not ids:
        return {}
    out: dict[str, str] = {}
    todo = [i for i in ids if i]
    for i in range(0, len(todo), 500):
        chunk = todo[i:i + 500]
        rows = db.execute(select(t.c.id, t.c.title)
                          .where(t.c.project_id == project_id, t.c.id.in_(chunk)))
        out.update({r[0]: r[1] for r in rows if r[1]})
    return out


def is_pair_display(mod: dict, name: str) -> bool:
    """Does `name` render as something other than its stored value? REF-LABEL's population test.

    True for a reference field (it renders the referenced record's title) and for the text half of a
    pair (it renders the linked record when the text is empty). Everything else stores what it shows,
    so the display treatment is a no-op and is not applied — which keeps `group_by` on an ordinary
    select field byte-for-byte as it was.
    """
    by_name = {x.get("name"): x for x in mod.get("fields", [])}
    f = by_name.get(name)
    if not f:
        return False
    if f.get("type") == "reference" and f.get("module"):
        return True
    return reference_half(name, by_name) is not None


def _apply_sort(db: Session, stmt, t, mod: dict, sort: str | None, sort_dir: str | None,
                project_id: str | None = None):
    """Order by a declared field. Returns the statement unchanged when `sort` is absent, so the
    caller's default ordering still applies.

    **Blanks sort LAST in BOTH directions.** `register.ts` states that rule for the columns the
    server cannot order, and the server disagreed with it (SQLite puts NULL first ascending), so the
    same register ordered differently depending on which column was clicked.
    """
    if not sort:
        return stmt, False
    expr, joins, numeric = _display_expr(db, t, mod, sort, project_id, tag="sort")
    for a, on in joins:
        stmt = stmt.join(a, on, isouter=True)
    if not numeric:
        expr = _fold(db, expr)
    desc = str(sort_dir or "asc").lower() == "desc"
    blanks_last = case((expr.is_(None), 1), else_=0)
    return stmt.order_by(blanks_last, expr.desc() if desc else expr.asc()), True

def list_records(db: Session, key: str, project_id: str, state: str | None = None,
                 q: str | None = None, limit: int = 200, offset: int = 0,
                 filters: list[tuple[str, str, str]] | None = None,
                 sort: str | None = None, sort_dir: str | None = None) -> list[dict]:
    """One page of a module's register: state + full-text + per-field filters + sort, all in SQL.

    Everything narrowing or ordering the result happens BEFORE the limit, which is the whole point —
    filtering or sorting a page after fetching it answers a different question than the one asked and
    looks identical to the right answer.

    **Sorting on a reference field adds a LEFT JOIN** (see `_display_expr`), because the order has to be
    the referenced record's title rather than the uuid stored in the JSON blob. It is an outer join
    scoped in its ON clause, so it can neither drop a row nor multiply one — the target id is a
    primary key — but it is a second table in the plan, and a caller sizing a query should know it is
    there.
    """
    if key not in TABLES:
        raise HTTPException(404, f"unknown module {key!r}")
    t = TABLES[key]
    stmt = select(t).where(t.c.project_id == project_id)
    if state:
        stmt = stmt.where(t.c.workflow_state == state)
    if q:
        # filter in SQL (before LIMIT) so search scales + returns the right rows, not just matches
        # within the first page. Postgres full-text ranks by relevance; SQLite falls back to LIKE.
        stmt = stmt.where(_search_filter(db, t, q))
        if _is_postgres(db) and (tsq := _pg_tsquery(q)):
            stmt = stmt.order_by(func.ts_rank(_pg_document(t), func.to_tsquery("english", tsq)).desc())
    # MOD-FILTER — per-field narrowing, applied in SQL BEFORE the limit for the same reason `q` is:
    # filtering a page after fetching it answers a different question than the user asked, and looks
    # identical to the right answer.
    if filters:
        stmt = _apply_filters(db, stmt, t, REGISTRY.get(key) or {}, filters, project_id)
    stmt, _explicit_sort = _apply_sort(db, stmt, t, REGISTRY.get(key) or {}, sort, sort_dir,
                                      project_id)
    # `created_at` stays as the last ordering key even when an explicit sort is given, so a page is
    # STABLE across requests. Without a tiebreak, two rows with equal sort values can swap between
    # pages and a row is then either shown twice or never — the classic pagination hole.
    stmt = stmt.order_by(t.c.created_at).limit(limit).offset(offset)
    return [dict(r._mapping) for r in db.execute(stmt)]

#: R22-REPORT-BUILDER — the aggregate functions a grouped query may ask for.
#: `count` needs no field; the other three do, and only over a numeric one.
AGG_FNS = {"count", "sum", "avg", "min", "max"}

#: How many groups one aggregate may return. A `group_by` over a free-text field with thousands of
#: distinct values is a denial of service dressed as a report — and a SILENTLY truncated one is worse,
#: because a short list reads as the whole answer. Over this, the response says it was capped.
MAX_GROUPS = 200


#: R22-REPORT-BUILDER item 2 — the separator between a joined module and one of its fields in a
#: `group_by` / `agg_field`, e.g. `change_order.trade`. A dot rather than a new parameter so the two
#: names travel together: a field on the joined side is meaningless without the side it is on.
JOIN_SEP = "."


def _join_target(mod: dict, join: str) -> tuple[str, dict]:
    """`(target_key, target_module)` for a DECLARED reference field — or HTTP 400.

    R22-REPORT-BUILDER item 2. The join is never taken from the caller: `reference_fields` lists the
    edges the module *declares*, and the field name is interpolated into a JSON path by `_json_text`
    exactly as `_resolve_field`'s are. Accepting an arbitrary field here would reopen the injection
    site that `_resolve_field` exists to close, one level out — and accepting an arbitrary *module*
    would let a report join two tables that no schema says are related, which produces a number
    nobody can trace back to the data.
    """
    for f in reference_fields(mod):
        if f.get("name") == join:
            target = REGISTRY.get(f["module"])
            if target is None:
                raise HTTPException(400, f"{join!r} references unknown module {f['module']!r}")
            return f["module"], target
    declared = sorted(f["name"] for f in reference_fields(mod))
    raise HTTPException(400, f"{join!r} is not a declared reference field for this module"
                             + (f" (expected one of {declared})" if declared else ""))


def _side_field_expr(db: Session, base_t, base_mod: dict, join_key: str | None, join_t,
                     join_mod: dict | None, name: str):
    """A comparable expression for `field` or `joined_module.field`, resolved on the right side."""
    if join_key and name.startswith(join_key + JOIN_SEP):
        if join_mod is None:
            raise HTTPException(400, f"{name!r} names a joined module but no join was given")
        return _field_expr(db, join_t, join_mod, name[len(join_key) + 1:])
    return _field_expr(db, base_t, base_mod, name)


def aggregate(db: Session, key: str, project_id: str, group_by: str, agg: str = "count",
              agg_field: str | None = None, state: str | None = None,
              filters: list[tuple[str, str, str]] | None = None,
              join: str | None = None) -> dict:
    """Group a module's records by a DECLARED field and aggregate over them.

    This is what separates a saved *list* from a *report*: until now the only `group_by` in the module
    path was hardcoded to `workflow_state`, so "cost by discipline" or "RFIs per month" could not be
    expressed at all and the answer was a spreadsheet export.

    **Field names are validated by `_resolve_field`, the same one `_apply_filters` and `_apply_sort`
    use, and for the same reason** — `_json_text` interpolates the name into a JSON path, so an
    unvalidated name is an injection site, not a typo. A second validator here would be a second
    answer to "what is a field", which is how two sources of truth start disagreeing.

    **`sum`/`avg` are REFUSED on a non-numeric field rather than returning 0.** SQLite will happily
    sum text as zero and hand back a confident `0`, which reads as *this project has none* — the exact
    shape of wrong answer this module's header already warns about for text-compared numbers.
    """
    if key not in TABLES:
        raise HTTPException(404, f"unknown module {key!r}")
    if agg not in AGG_FNS:
        raise HTTPException(400, f"unknown aggregate {agg!r} (expected one of {sorted(AGG_FNS)})")
    t = TABLES[key]
    mod = REGISTRY.get(key) or {}

    # R22-REPORT-BUILDER item 2 — a report over ONE module is a saved list with totals. "RFIs against
    # change orders by trade" needs two, and until now `SavedView.module` was a single string so it
    # could not be expressed at all. The join runs along a DECLARED reference field: `data-><field>`
    # holds the target's id (the same shape `related_records` already reads), so the edge comes from
    # the schema rather than from the request.
    join_key: str | None = None
    join_t = None
    join_mod: dict | None = None
    if join:
        join_key, join_mod = _join_target(mod, join)
        join_t = TABLES[join_key].alias(f"j_{join_key}")

    def side(name: str):
        return _side_field_expr(db, t, mod, join_key, join_t, join_mod, name)

    # REF-LABEL — group by WHAT THE COLUMN RENDERS when it renders something other than it stores.
    #
    # Grouping a reference field by its stored value produced categories labelled with uuid4s ("cost
    # by supplier" as a chart of opaque ids), and split ONE firm in two: the rows that linked the
    # company record grouped under its id, the rows that typed the name grouped under NULL. Merging
    # them uses the rule PAIR-FILTER already applies — a typed name EXACTLY equal to the record's
    # title, case-insensitively, never a substring — so the report and the filter agree about what
    # "this firm" means.
    #
    # Grouping is on the FOLDED expression so case variants merge, while the label is `min()` of the
    # unfolded one, so the group reads "Acme Electrical" rather than "acme electrical". Fields that
    # store what they show are untouched: `is_pair_display` is false for them and this whole branch
    # is skipped, so grouping a select field cannot start folding "Open" into "open".
    # A join must not switch the display treatment off. The first version guarded on
    # `join_key is None`, so "cost by supplier, joined to change orders" fell back to uuid keys while
    # the same report without the join read firm names — the fix applied exactly where nobody had
    # added a join yet. Resolve which SIDE the field is on instead, and give each side its own alias
    # prefix so a report grouping a joined field cannot collide with one grouping a base field.
    gjoins: list = []
    glabel = None
    gside_t, gside_mod, gname, gtag = t, mod, group_by, "grp"
    if join_key and group_by.startswith(join_key + JOIN_SEP):
        gside_t, gside_mod, gname, gtag = join_t, (join_mod or {}), group_by[len(join_key) + 1:], "grpj"
    if gside_t is not None and is_pair_display(gside_mod, gname):
        gdisp, gjoins, _gnum = _display_expr(db, gside_t, gside_mod, gname, project_id, tag=gtag)
        gexpr, glabel = _fold(db, gdisp), func.min(gdisp)
    else:
        gexpr, _gf = side(group_by)
    value_expr = None
    if agg != "count":
        if not agg_field:
            raise HTTPException(400, f"{agg} needs a field to aggregate (agg_field)")
        aexpr, af = side(agg_field)
        if agg in ("sum", "avg") and (af.get("_system") or af.get("type") not in _NUMERIC_FIELD_TYPES):
            raise HTTPException(400, f"{agg} needs a numeric field; {agg_field!r} is declared "
                                     f"{af.get('type') or 'text'!r}")
        value_expr = {"sum": func.sum, "avg": func.avg,
                      "min": func.min, "max": func.max}[agg](aexpr)

    cols = [(glabel if glabel is not None else gexpr).label("key"), func.count().label("count")]
    if value_expr is not None:
        cols.append(value_expr.label("value"))
    stmt = select(*cols).where(t.c.project_id == project_id)
    if join_t is not None:
        # LEFT join: a base record with no related record still counts, under a NULL group. An inner
        # join would silently drop it, and "RFIs by change-order trade" that omits every RFI without
        # a change order answers a narrower question than the one asked — while looking complete.
        #
        # AGG-OUTER — the project scope belongs in the **ON clause**, and used to sit in a trailing
        # `.where(or_(join_t.project_id == project_id, join_t.id.is_(None)))`. A base row joined to a
        # record in ANOTHER project satisfies neither arm of that `or_`, so it was DELETED from the
        # result: **a predicate on the nullable side of an outer join is an inner join**, which is
        # precisely what the paragraph above says this must not be. Measured: three deliveries in the
        # register, the joined report counted two, with no error and no `truncated` flag — and a
        # short answer is indistinguishable from the right one. Nothing validates a reference VALUE
        # on write (`module_schema` checks the manifest's shape, not that an id exists or is local),
        # so a cross-project id is reachable rather than theoretical. Scoped here, it simply fails to
        # match: the reference resolves to NULL and the row keeps its place under the NULL group.
        stmt = stmt.select_from(t).join(
            join_t,
            and_(_json_text(db, t.c.data, join) == join_t.c.id,
                 join_t.c.project_id == project_id),
            isouter=True,
        )
    for a, on in gjoins:
        stmt = stmt.join(a, on, isouter=True)
    if state:
        stmt = stmt.where(t.c.workflow_state == state)
    if filters:
        stmt = _apply_filters(db, stmt, t, mod, filters, project_id)
    # One past the cap, so "there were more" is observed rather than inferred from a full page.
    stmt = stmt.group_by(gexpr).order_by(func.count().desc()).limit(MAX_GROUPS + 1)

    rows = [dict(r._mapping) for r in db.execute(stmt)]
    truncated = len(rows) > MAX_GROUPS
    if truncated:
        rows = rows[:MAX_GROUPS]
    return {"module": key, "group_by": group_by, "agg": agg, "agg_field": agg_field,
            "join": join, "join_module": join_key,
            "groups": rows, "group_count": len(rows),
            "truncated": truncated, "max_groups": MAX_GROUPS}


def count_records(db: Session, key: str, project_id: str, state: str | None = None,
                  q: str | None = None, since: datetime | None = None,
                  filters: list[tuple[str, str, str]] | None = None,
                  exclude_states: list[str] | None = None) -> int:
    """Count matches for a module filter (state / search / created-since) — for saved-view alerts.

    Takes `filters` for the same reason `list_records` does: a count that ignores a filter the list
    applied reports a total the page cannot account for, and a total is exactly the number a user
    trusts without checking.

    `exclude_states` drops those workflow states (NULL states are kept, matching a Python `not in`
    check), exactly as `sum_field` does. It was added when the sentence above came true literally:
    `/dev-budget/draw-forecast` returns `actual_billed` from `billed_to_date`, which excludes
    refused owner invoices, beside an `invoice_count` from this function, which did not — one
    payload disagreeing with itself about how many invoices the money came from. The amount and the
    count must exclude on the same rule or the page cannot be reconciled."""
    if key not in TABLES:
        return 0
    t = TABLES[key]
    stmt = select(func.count()).select_from(t).where(t.c.project_id == project_id)
    if state:
        stmt = stmt.where(t.c.workflow_state == state)
    if q:
        stmt = stmt.where(_search_filter(db, t, q))
    if since is not None:
        stmt = stmt.where(t.c.created_at > since)
    if filters:
        stmt = _apply_filters(db, stmt, t, REGISTRY.get(key) or {}, filters, project_id)
    if exclude_states:
        stmt = stmt.where(or_(t.c.workflow_state.is_(None),
                              t.c.workflow_state.notin_(exclude_states)))
    return int(db.execute(stmt).scalar() or 0)

def state_counts(db: Session, key: str, project_id: str) -> dict[str, int]:
    """{workflow_state: count} for a module via a single GROUP BY on the indexed `workflow_state`
    column — no JSON `data` is loaded or parsed. For dashboards / rollups that only need status
    tallies. Empty dict for an unknown module; a NULL state is keyed by ""."""
    if key not in TABLES:
        return {}
    t = TABLES[key]
    stmt = (select(t.c.workflow_state, func.count()).where(t.c.project_id == project_id)
            .group_by(t.c.workflow_state))
    return {(state or ""): int(n) for state, n in db.execute(stmt).all()}

def state_counts_all(db: Session, project_id: str) -> dict[str, dict[str, int]]:
    """DASH-UNION (PERF-4): every module's {workflow_state: count} in ONE round-trip — a UNION ALL of
    the per-module GROUP BYs. The dashboard previously issued one query per registered module (~124);
    at scale the round-trips, not the row work, dominated. Only non-empty modules appear in the
    result, so callers keep their `if not total: continue` shape."""
    from sqlalchemy import literal, union_all
    parts = [
        select(literal(key).label("mod"), t.c.workflow_state, func.count().label("n"))
        .where(t.c.project_id == project_id).group_by(t.c.workflow_state)
        for key, t in TABLES.items()
    ]
    if not parts:
        return {}
    out: dict[str, dict[str, int]] = {}
    for mod_key, state, n in db.execute(union_all(*parts)).all():
        out.setdefault(mod_key, {})[state or ""] = int(n)
    return out

def active_records(db: Session, key: str, project_id: str, exclude_states: set[str],
                   with_data: bool = True, states: set[str] | None = None,
                   limit: int | None = None) -> list[dict]:
    """Lean records NOT in `exclude_states` (e.g. closed/done): the columns a dashboard needs —
    id, ref, title, workflow_state, assignee (+ the `data` blob when `with_data`, for due dates).
    Skips parsing JSON for the typically-large tail of completed records.

    `with_data=False` omits the JSON entirely (the big cost at scale) for callers that only need the
    lean columns. `states` restricts to a specific state set (indexed) instead of the whole active
    tail; `limit` caps the rows returned — together they let a dashboard pull just the actionable
    slice of a mega-project module instead of every open row."""
    t = TABLES[key]
    cols = [t.c.id, t.c.ref, t.c.title, t.c.workflow_state, t.c.assignee]
    if with_data:
        cols.append(t.c.data)
    stmt = select(*cols).where(t.c.project_id == project_id)
    if states is not None:
        stmt = stmt.where(t.c.workflow_state.in_(states))
    else:
        stmt = stmt.where(t.c.workflow_state.notin_(exclude_states))
    if limit is not None:
        stmt = stmt.limit(limit)
    return [dict(r._mapping) for r in db.execute(stmt)]


# ---- R22-REPORT-BUILDER item 3: a saved view's `config` is a SCHEMA, not a blob -------------------
#
# `SavedView.config` was `Mapped[dict] = mapped_column(JSON, default=dict)` and the write route took
# `config: dict = Body(...)` and stored it verbatim. "filter/sort/column config" was true only in the
# docstring: a saved view was whatever a client happened to POST, so a schema change broke views
# silently with no migration path and nothing could tell a typo from a feature.
#
# **The validator does not invent a second answer to "what is a field".** It resolves every field
# name through `_resolve_field` and every operator through `FILTER_OPS` — the same two the list route
# uses — because `_json_text` interpolates a name into a JSON path, and a second validator here is
# how two sources of truth start disagreeing. That is the rule the `aggregate` docstring above
# already states; this is the third caller to follow it.
#
# **Unknown keys are REFUSED rather than ignored.** A view saved with `{"filtres": [...]}` that is
# accepted and then silently unused is the same class of wrong answer as a dropped filter: the user
# is shown more rows than they asked for and told nothing. Refusing is also what gives the schema a
# migration path — the set below is the contract, and changing it is a visible act.

#: Every key a saved view's `config` may carry. Anything else is a 422.
VIEW_CONFIG_KEYS = {"q", "state", "sort", "sort_dir", "filters", "columns", "group_by", "agg",
                    "agg_field", "join"}

#: R22-REPORT-BUILDER item 4 — who may READ a saved view. Ownership (project+module+user+name) is a
#: separate question and decides who may WRITE it; conflating the two is what made the builder a
#: personal filter. `project` is bounded by the project the view already belongs to.
VIEW_SCOPES = {"private", "project"}

#: How many columns a view may pin. Same reasoning as MAX_FILTERS: a bound that is stated.
MAX_VIEW_COLUMNS = 60


def validate_view_config(key: str, config: dict | None) -> dict:
    """The saved-view `config`, normalised — or HTTP 422 naming what was wrong.

    Returns filters as a list of `[name, op, value]` lists (JSON has no tuples), which is what
    `view_filters` reads back. Validation is by RESOLUTION, not by shape: a field name is accepted
    because the module declares it, not because it is a string.
    """
    if config is None:
        return {}
    if not isinstance(config, dict):
        raise HTTPException(422, "view config must be an object")
    mod = REGISTRY.get(key)
    if mod is None:
        raise HTTPException(404, f"unknown module {key!r}")

    if unknown := sorted(set(config) - VIEW_CONFIG_KEYS):
        raise HTTPException(422, f"unknown view config key(s): {', '.join(unknown)} "
                                 f"(expected one of {sorted(VIEW_CONFIG_KEYS)})")

    out: dict = {}
    for k in ("q", "state", "agg_field", "sort", "group_by", "join"):
        if (v := config.get(k)) is not None:
            if not isinstance(v, str):
                raise HTTPException(422, f"view config {k!r} must be a string")
            out[k] = v
    # `join` names a DECLARED reference field and is resolved first, because it decides which module
    # `group_by` / `agg_field` may name a field on. A view is validated exactly as the query it
    # replays would be — otherwise a view could be saved that the aggregate route then refuses.
    join_key: str | None = None
    join_mod: dict | None = None
    if "join" in out:
        join_key, join_mod = _join_target(mod, out["join"])

    # `sort`, `group_by` and `agg_field` name FIELDS. With a join in play they may name a field on
    # the joined side as `<module>.<field>`; `sort` may not, because ordering happens on the base.
    resolved: dict[str, dict] = {}
    for k in ("group_by", "agg_field"):
        if k in out:
            name = out[k]
            if join_key and name.startswith(join_key + JOIN_SEP):
                resolved[k] = _resolve_field(join_mod, name[len(join_key) + 1:])
            else:
                resolved[k] = _resolve_field(mod, name)
    if "sort" in out:
        _resolve_field(mod, out["sort"])

    if (sd := config.get("sort_dir")) is not None:
        if str(sd).lower() not in ("asc", "desc"):
            raise HTTPException(422, f"view config sort_dir must be 'asc' or 'desc', got {sd!r}")
        out["sort_dir"] = str(sd).lower()

    if (agg := config.get("agg")) is not None:
        if agg not in AGG_FNS:
            raise HTTPException(422, f"unknown aggregate {agg!r} (expected one of {sorted(AGG_FNS)})")
        # `aggregate` refuses two more things than "is this a known function", and a view that is
        # saved but unreplayable is the failure this whole validator exists to prevent — the
        # docstring above promises a view is validated exactly as the query it replays would be, and
        # until this block that promise was only kept for field NAMES. Both rules are re-asked of the
        # same resolved field definition `aggregate` uses, not re-derived from the name.
        if agg != "count":
            if "agg_field" not in out:
                raise HTTPException(422, f"{agg} needs a field to aggregate (agg_field)")
            af = resolved["agg_field"]
            if agg in ("sum", "avg") and (
                    af.get("_system") or af.get("type") not in _NUMERIC_FIELD_TYPES):
                raise HTTPException(422, f"{agg} needs a numeric field; {out['agg_field']!r} is "
                                         f"declared {af.get('type') or 'text'!r}")
        out["agg"] = agg

    if (cols := config.get("columns")) is not None:
        if not isinstance(cols, list):
            raise HTTPException(422, "view config columns must be a list")
        if len(cols) > MAX_VIEW_COLUMNS:
            raise HTTPException(422, f"too many columns (max {MAX_VIEW_COLUMNS})")
        for c in cols:
            if not isinstance(c, str):
                raise HTTPException(422, "view config columns must be field names")
            _resolve_field(mod, c)
        out["columns"] = list(cols)

    if (filters := config.get("filters")) is not None:
        if not isinstance(filters, list):
            raise HTTPException(422, "view config filters must be a list")
        if len(filters) > MAX_FILTERS:
            raise HTTPException(422, f"too many filters (max {MAX_FILTERS})")
        norm: list[list[str]] = []
        for f in filters:
            if not isinstance(f, (list, tuple)) or len(f) != 3:
                raise HTTPException(422, "each filter must be [field, op, value]")
            name, op, value = f
            if not isinstance(name, str) or not isinstance(op, str):
                raise HTTPException(422, "filter field and operator must be strings")
            if op not in FILTER_OPS:
                raise HTTPException(422, f"unknown filter operator {op!r} (expected one of "
                                         f"{sorted(FILTER_OPS)})")
            _resolve_field(mod, name)
            norm.append([name, op, "" if value is None else str(value)])
        out["filters"] = norm
    return out


def view_filters(config: dict | None) -> list[tuple[str, str, str]]:
    """The `(field, op, value)` filters a stored config carries, for `count_records` / `list_records`.

    **Raises `ValueError` when the stored `filters` cannot be read, and that is the whole point.**

    The first draft returned `[]` for anything it could not parse — tolerant by shape — and that made
    `view_alerts`' "uncountable" branch DEAD CODE: a row written before validation existed, holding
    `{"filters": "this was never validated"}`, produced no filters, so the feed counted the whole
    module and reported the wrong number confidently. The guard and the parser disagreed about what
    an unreadable config means, and the guard lost silently.

    Caught by `test_view_config.py` on its first run, which is the only reason it is not still there.
    Rows saved BEFORE this schema may hold anything; a caller that cannot read one must be able to
    tell that apart from a view that simply has no filters.
    """
    raw = (config or {}).get("filters")
    if raw is None:
        return []
    if not isinstance(raw, list):
        raise ValueError(f"stored filters are {type(raw).__name__}, expected a list")
    out: list[tuple[str, str, str]] = []
    for f in raw:
        if not isinstance(f, (list, tuple)) or len(f) != 3:
            raise ValueError(f"stored filter {f!r} is not [field, op, value]")
        out.append((str(f[0]), str(f[1]), str(f[2])))
    return out
