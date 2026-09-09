"""LIMIT-FILTER — a capped window whose predicate runs in Python answers "you have nothing".

`agent_packs.run_log` applied `limit` before the project filter, so a quiet project behind a busy
one reported **zero runs while runs existed** (fixed 2026-09-09). This file exists because that was
an instance of a class, not a bug: the population is DERIVED here, and two more live defects came
out of it.

**Why the shape is dangerous.** A cap is a promise about SIZE. A predicate applied after it turns
that into a promise about MEMBERSHIP the code cannot keep: the rows that satisfy the predicate may
all sit outside the window, and what comes back is not a short answer but an EMPTY one. Empty reads
as "there are none", which is a different claim and the one a person acts on. Nothing errors, no
count looks wrong, and the failure is invisible until someone independently knows the row exists.

**The two found here, both measured before being fixed:**

  * `fin_ingest.import_history` — filtered `action == module.import` across every project, capped at
    100, then dropped the other projects' rows in Python. One import on project A behind 150 newer
    on project B: **A's import lineage came back empty.** That answer is what somebody reads when
    they are tracing where a number came from.
  * `modules.notifications` — scoped the project in SQL but then took the newest 200 rows for the
    whole project and asked, in Python, which concerned *this* user. A user's assigned RFI buried
    under 250 newer activities by other people: **the bell feed went 1 → 0.**

**`my_work` sits ten lines below `notifications` with the correct shape already written down** —
*"Filters in SQL … bounded on both axes"* — over the same registry and the same two conditions. The
fix was adjacent to the defect the entire time, which is the argument for sweeping a class instead
of fixing whatever instance gets reported.

**What the analyser does, and what it deliberately does not.** It reports every function that calls
`.limit()` and then filters rows in Python — a `continue` in a loop, or a comprehension with an
`if`. It CANNOT tell a defect from a legitimate one, and it does not try: several of the sites below
are correct, because their scope is already in SQL and the Python test is classification (is this
row a pin at all?) or a best-effort skip (the blob is missing). So it FAILS CLOSED — every site must
carry a reviewed verdict here, and a site the analyser finds that nobody has classified reds the
build. That is the same design as `test_unique_read_guard.py`, for the same reason: a predicate that
decides what to LOOK at hides everything it excludes from its own output.

Run: PYTHONPATH=src:../data/src ./.venv/bin/python test_limit_filter.py
"""
from __future__ import annotations

import ast
import os
import pathlib
import sys
import textwrap

os.environ["DATABASE_URL"] = "sqlite:///./test_limit_filter.db"
os.environ["STORAGE_DIR"] = "./test_storage_limit_filter"
os.environ["AEC_RBAC"] = "1"
os.environ["AEC_TRUST_XUSER"] = "1"
for _f in ("./test_limit_filter.db",):
    if os.path.exists(_f):
        os.remove(_f)

FAILED: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    if not ok:
        FAILED.append(f"{label}{(' — ' + detail) if detail else ''}")


# --------------------------------------------------------------------------------------------
# The analyser. Kept as a plain function over source text so the self-tests below can mutate it
# directly rather than through the filesystem.
# --------------------------------------------------------------------------------------------
def sites(source: str) -> list[tuple[str, int]]:
    """Every function in `source` that calls `.limit(...)` and then filters ROWS in Python.

    "Then" is by line number: a Python filter appearing BEFORE the cap is not this shape — it
    narrows what gets capped, which is the correct order. Only a filter after the cap can delete
    rows the cap already chose.
    """
    out: list[tuple[str, int]] = []
    tree = ast.parse(source)
    for node in ast.walk(tree):
        if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        caps = [n.lineno for n in ast.walk(node)
                if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                and n.func.attr == "limit"]
        if not caps:
            continue
        first_cap = min(caps)
        filters = [n.lineno for n in ast.walk(node) if isinstance(n, ast.Continue)]
        filters += [n.lineno for n in ast.walk(node)
                    if isinstance(n, (ast.ListComp, ast.SetComp, ast.GeneratorExp, ast.DictComp))
                    and any(g.ifs for g in n.generators)]
        if any(ln > first_cap for ln in filters):
            out.append((node.name, node.lineno))
    return out


# --------------------------------------------------------------------------------------------
# Self-test the analyser BOTH WAYS before believing anything it says about the tree.
# A probe that reports the authoring shapes proves it can see; a probe that stays silent on the
# near-misses proves it is not simply reporting everything with a `.limit()` in it.
# --------------------------------------------------------------------------------------------
_MUST_REPORT = {
    # The pre-fix `import_history`, verbatim in shape: cap the world, then drop the other projects.
    "pre-fix import_history": '''
        def import_history(db, pid, limit=100):
            q = db.query(AuditLog).filter(AuditLog.action == IMPORT).order_by(x).limit(limit)
            out = []
            for row in q.all():
                d = row.detail or {}
                if d.get("project_id") != pid:
                    continue
                out.append(d)
            return out
    ''',
    # The pre-fix `notifications`: project in SQL, but the per-USER predicate after the cap.
    "pre-fix notifications": '''
        def notifications(db, project_id, user, party, limit=30):
            recent = db.query(A).filter(A.project_id == project_id).order_by(x).limit(200).all()
            out = []
            for a in recent:
                if a.actor == user:
                    continue
                out.append(a)
            return out
    ''',
    # The comprehension spelling of the same thing — a different syntax, the same defect.
    "post-cap comprehension": '''
        def feed(db, pid, limit=50):
            rows = db.query(A).order_by(x).limit(limit).all()
            return [r for r in rows if r.project_id == pid]
    ''',
}

_MUST_STAY_SILENT = {
    # A cap with no Python row filter at all.
    "capped, no filter": '''
        def recent(db, pid, limit=50):
            rows = db.query(A).filter(A.project_id == pid).order_by(x).limit(limit).all()
            return [{"id": r.id} for r in rows]
    ''',
    # A Python filter with no cap — unbounded, but not this class.
    "filtered, no cap": '''
        def everything(db, pid):
            out = []
            for r in db.query(A).all():
                if r.project_id != pid:
                    continue
                out.append(r)
            return out
    ''',
    # The correct ORDER: narrow in Python first, then cap what survived. Not this defect.
    "filter before cap": '''
        def narrowed(db, pid, limit=50):
            keep = [k for k in KEYS if k.startswith(pid)]
            rows = db.query(A).filter(A.key.in_(keep)).order_by(x).limit(limit).all()
            return rows
    ''',
}

for name, src in _MUST_REPORT.items():
    check(f"analyser sees the authoring shape: {name}", bool(sites(textwrap.dedent(src))),
          "reported nothing — an analyser that cannot find a known defect can only report good news")
for name, src in _MUST_STAY_SILENT.items():
    check(f"analyser stays silent on the near-miss: {name}", not sites(textwrap.dedent(src)),
          "reported it — a analyser that reports everything gives its reviewer nothing to review")

# And prove the ORDER test is load-bearing rather than incidental: an analyser that ignored line
# order would report "filter before cap", which is the correct shape.
_order_blind = sites(textwrap.dedent(_MUST_STAY_SILENT["filter before cap"]))
check("the before/after ordering is what separates the two", not _order_blind,
      "the cap/filter ORDER is what makes this a defect, and the analyser must use it")

# --------------------------------------------------------------------------------------------
# The reviewed population. Derived by the analyser; each site classified by hand, because the
# analyser cannot tell a row filter from a classification and must not pretend to.
# --------------------------------------------------------------------------------------------
SQL_SCOPED = "correct — the scope is already in SQL; the Python test classifies, it does not scope"
DERIVED_TALLY = ("correct — the comprehension counts the window it was given; it does not decide "
                 "which rows the window holds")

VERDICTS: dict[tuple[str, str], str] = {
    # THE ANALYSER CANNOT TELL THESE TWO APART, AND IT SHOULD NOT TRY. `run_log` matches on
    # `failures = [x for x in runs if x.get("ok") is False]` — a tally computed over rows that have
    # already been returned, for `failure_count`. It removes nothing from the answer. Teaching the
    # analyser to skip it would mean teaching it which comprehensions "produce the result", and a
    # predicate that decides what to LOOK at hides everything it excludes from its own output —
    # this repository has been caught by exactly that four times. Over-reporting costs a line in
    # this table; under-reporting costs a defect nobody can see. The regression guard for
    # `run_log`'s actual defect is behavioural and lives in `test_agent_packs.py`, where it was
    # mutation-checked against the pre-fix code.
    ("agent_packs.py", "run_log"): DERIVED_TALLY,
    ("pins.py", "resolve_pins"): SQL_SCOPED,          # `continue` = "not a pin", not "not mine"
    ("report.py", "_project_photos"): SQL_SCOPED,     # `continue` = the blob is missing
    ("routers/standards.py", "load_timings"): SQL_SCOPED,   # project + window both in SQL
}

# The three that WERE this defect. Fixing one removes it from the analyser's population entirely —
# the Python filter is gone, so there is nothing left to match. That is why they are asserted
# ABSENT rather than carrying a verdict: a "fixed" entry in the table above could never match, and
# a row that can never match is a row that proves nothing while looking like coverage.
#
# Naming them here turns the disappearance into a regression guard. Reintroduce the shape in any of
# these and the analyser reports it, no verdict covers it, and the build goes red on the exact
# function that carried the defect the first time.
# `run_log` is deliberately NOT here: it still matches the analyser, for the unrelated reason
# explained beside its verdict above, so "absent" is not a claim that can be made about it.
FIXED_MUST_NOT_RETURN = {
    ("fin_ingest.py", "import_history"),  # the project filter ran after limit(100)   — 2026-09-09
    ("modules.py", "notifications"),      # the per-USER predicate ran after limit(200) — 2026-09-09
    # `timeline` carried the verdict SQL_SCOPED here — "topic_id in SQL; the ifs dispatch on
    # action" — and that verdict was WRONG, not merely superseded. The `if a.action == ...` chain
    # is a dispatch AND a filter: `bcf.comment.create`, `markup.promote` and `record.comment.promote`
    # are real actions written against a topic_id that every branch declines, so a busy topic could
    # spend its whole `_TIMELINE_CAP` window on rows yielding no events and answer EMPTY. Reading a
    # Python `if` as "dispatch, therefore harmless" is the way this analyser gets talked out of a
    # real site; what settles it is which rows the cap can be spent on, not what the branch is for.
    # The action set now filters in SQL, ahead of the LIMIT, so the shape is gone.  — 2026-09-09
    ("topic_lifecycle.py", "timeline"),
}

ROOT = pathlib.Path(__file__).resolve().parent / "src" / "aec_api"
found: set[tuple[str, str]] = set()
for path in sorted(ROOT.rglob("*.py")):
    rel = path.relative_to(ROOT).as_posix()
    try:
        for fn, _ln in sites(path.read_text(encoding="utf-8")):
            found.add((rel, fn))
    except SyntaxError as exc:                       # a file we cannot parse is not a pass
        FAILED.append(f"could not parse {rel}: {exc}")

unclassified = sorted(found - set(VERDICTS))
check("every site the analyser finds carries a reviewed verdict", not unclassified,
      f"unclassified: {unclassified} — classify each in VERDICTS (this gate FAILS CLOSED on "
      f"purpose: a new capped-then-filtered read is a wrong answer waiting for scale)")

stale = sorted(set(VERDICTS) - found)
check("no verdict outlives the site it describes", not stale,
      f"listed but no longer found: {stale} — remove them, or the count reads as coverage it "
      f"no longer has")

returned = sorted(found & FIXED_MUST_NOT_RETURN)
check("a site that was fixed has not grown the shape back", not returned,
      f"{returned} filter rows in Python after a cap again — this is the defect that reported "
      f"zero runs, an empty import lineage and an empty bell feed")

# The population must be non-empty, or every assertion above passes vacuously. This repository has
# been caught by exactly that: `test_pair_filter`'s precondition swept an empty registry and
# printed a clean result.
# 4, not 5: `topic_lifecycle.timeline` left the population when its action filter moved into SQL
# (see FIXED_MUST_NOT_RETURN). The floor exists to catch an analyser that finds NOTHING, so it
# tracks the population; it is not a claim that the tree should hold a particular number of these.
check("the analyser actually reached the tree", len(found) >= 4,
      f"only {len(found)} sites found under {ROOT} — a sweep whose population is empty passes for "
      f"the same reason a correct one does")

# --------------------------------------------------------------------------------------------
# Behaviour. The structural gate above cannot tell whether the fixed sites actually answer now.
# --------------------------------------------------------------------------------------------
from datetime import datetime, timedelta, timezone  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import fin_ingest  # noqa: E402
from aec_api.db import Base, SessionLocal, engine  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import AuditLog, RecordActivity  # noqa: E402

Base.metadata.create_all(bind=engine)
NOW = datetime.now(timezone.utc)


def _hdr(user: str) -> dict[str, str]:
    return {"X-User": user}


with TestClient(app) as client:
    pid = client.post("/projects", headers=_hdr("gc"), json={"name": "Busy Tower"}).json()["id"]
    mine = client.post(f"/projects/{pid}/modules/rfi", headers=_hdr("gc"), json={
        "assignee": "ann", "data": {"subject": "Slab edge detail", "question": "OK to core?"}},
    ).json()["id"]
    theirs = client.post(f"/projects/{pid}/modules/rfi", headers=_hdr("gc"), json={
        "assignee": "zoe", "data": {"subject": "Not ann's", "question": "?"}}).json()["id"]

    from aec_api.modules import notifications  # noqa: E402

    with SessionLocal() as db:
        db.query(RecordActivity).delete()
        db.add(RecordActivity(project_id=pid, module="rfi", record_id=mine, actor="gc",
                              action="create", ts=NOW - timedelta(days=3)))
        db.commit()
        before = notifications(db, pid, "ann", None)
        check("baseline: ann's assigned work is in her feed at all", len(before) == 1,
              f"got {before!r} — a burial test whose baseline is already empty proves nothing, "
              f"which is how the first draft of this measurement lied")

        # Bury it under activity by other people on a record ann has nothing to do with.
        for i in range(250):
            db.add(RecordActivity(project_id=pid, module="rfi", record_id=theirs, actor="bob",
                                  action="update", ts=NOW - timedelta(minutes=250 - i)))
        # An activity with NO actor: `a.actor == user` is False for None, so the old code KEPT it.
        db.add(RecordActivity(project_id=pid, module="rfi", record_id=mine, actor=None,
                              action="update", ts=NOW - timedelta(days=2)))
        # An activity whose record is gone: the old `if not rec: continue` dropped it.
        db.add(RecordActivity(project_id=pid, module="rfi", record_id="deleted-999", actor="bob",
                              action="update", ts=NOW))
        db.commit()

        after = notifications(db, pid, "ann", None)
        refs = {x["ref"] for x in after}
        check("THE DEFECT: assigned work survives 250 newer activities by other people",
              len(after) >= 1 and refs == {"RFI-001"},
              f"got {after!r} — this is the bell feed going empty while ann holds an open RFI")
        check("a NULL-actor activity is still delivered",
              any(x["actor"] is None for x in after),
              f"got {after!r} — `actor != user` in SQL is NULL-rejecting, and dropping these "
              f"silently is exactly what a naive translation of the Python does")
        # NOTE the reason, because it is not the obvious one: this holds because the relevance
        # predicate reads the RECORD's columns, which are NULL for a deleted record, so the OR is
        # NULL and the row fails the WHERE clause under either join. Mutating the join to `isouter`
        # SURVIVES this assertion — deliberately recorded rather than papered over, because the
        # engine's first docstring credited the INNER join with a job the predicate was doing.
        check("an activity whose record was deleted is not delivered",
              all(x["ref"] for x in after),
              f"got {after!r} — the old code already dropped these via `if not rec: continue`")
        check("ann is not notified about zoe's record", "RFI-002" not in refs, repr(after))

    # --- import lineage, at the size that exposes it -----------------------------------------
    with SessionLocal() as db:
        db.query(AuditLog).filter(AuditLog.action == fin_ingest.IMPORT_ACTION).delete()
        db.add(AuditLog(action=fin_ingest.IMPORT_ACTION, actor="ann",
                        ts=NOW - timedelta(hours=5),
                        detail={"project_id": "quiet", "module": "direct_cost",
                                "filename": "budget.csv", "imported": 42, "error_count": 0}))
        for i in range(150):
            db.add(AuditLog(action=fin_ingest.IMPORT_ACTION, actor="bob",
                            ts=NOW - timedelta(minutes=150 - i),
                            detail={"project_id": "busy", "module": "direct_cost",
                                    "filename": f"b{i}.csv", "imported": 1, "error_count": 0}))
        # No project_id at all: the old Python `!=` excluded it, and NULL ->> excludes it too.
        db.add(AuditLog(action=fin_ingest.IMPORT_ACTION, actor="sys", ts=NOW,
                        detail={"module": "direct_cost"}))
        db.commit()

        quiet = fin_ingest.import_history(db, "quiet")
        busy = fin_ingest.import_history(db, "busy")
        check("THE DEFECT: a quiet project's lineage survives 150 newer imports elsewhere",
              quiet["import_count"] == 1 and quiet["imports"][0]["filename"] == "budget.csv",
              f"got {quiet!r} — an empty lineage reads as 'nothing was imported here'")
        check("a capped window says it is capped",
              busy["import_count"] == 100 and busy["import_total"] == 150
              and busy["truncated"] is True,
              f"got counts={busy.get('import_count')}/{busy.get('import_total')} "
              f"truncated={busy.get('truncated')} — 100 of 150 presented as the whole is the "
              f"same defect one layer down")
        check("a batch carrying no project_id belongs to no project",
              all(r["filename"] for r in quiet["imports"] + busy["imports"]), "")

if FAILED:
    print("FAIL test_limit_filter")
    for f in FAILED:
        print("  -", f)
    sys.exit(1)
print(f"test_limit_filter OK  ({len(found)} capped-then-filtered sites derived and classified, "
      f"{len(FIXED_MUST_NOT_RETURN)} former defects asserted gone; "
      f"analyser self-tested in both directions)")
