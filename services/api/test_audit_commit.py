"""AUDIT-COMMIT — an audit row nobody commits is an audit row nobody has.

`audit.record` only calls ``db.add()``. `get_db` yields a session and only ever ``close()``s it, and
nothing in the request path commits on the way out — so a route that records an audit row without
reaching a commit afterwards leaves it pending in a session about to be discarded. The request
returns 200. The trail is empty. Nothing anywhere goes red, which is why this is a gate.

Found by touching the transaction boundary in `responsibility`, not by looking for it: BOTH of that
router's write routes had it, and one of them is the edit that can orphan an entire matrix.

**Derive the population, do not list it.** Every function under `src/aec_api` that calls
``audit.record`` is a candidate. Anything not proven safe is UNKNOWN, and **UNKNOWN reds the build**
unless it is named in `EXEMPT` with a reason — the blind spots this repo has already paid for were
all a predicate deciding what to LOOK at, and everything such a predicate excludes is invisible to
its own output.

**"Safe" is REACHABILITY, not line order, and that distinction is this gate's own bug report.** The
first version asked only whether some ``.commit()`` appeared at a later line in the same function.
It reported the tree clean, and `routers/analysis.py::run_clash_federated` was a live instance the
whole time: its `coordinate` branch records an audit row, and the only commit sat inside
``if create_topics and not coordinate`` — a branch that is mutually exclusive with the one holding
the record. Later in the file, never on the same path. Raised in review on the PR that added this
file, which is the second time in this repo an analyser has been confidently wrong about the very
defect it was written for.

So: a commit counts only when it is reached on EVERY path out of the block holding the record.
`_reaches_commit` climbs from the record's statement through its enclosing blocks, and at each level
`_unconditional_commit` looks only at what follows — descending through `with` (always runs once
entered) but never into `if`/`for`/`while`/`try` bodies, which are exactly the constructs that make
a commit conditional. Conservative by construction: a commit this cannot prove is not counted, and
the cost of that is an exemption with evidence rather than a silent pass. Over 106 call sites the
strictness costs ONE extra report, which was the real defect.

Run: PYTHONPATH=src ./.venv/bin/python test_audit_commit.py
"""
import ast
import os
import pathlib

SRC = pathlib.Path(__file__).parent / "src" / "aec_api"

# name -> why it is safe DESPITE having no visible commit. Each was read, and the first is asserted
# end-to-end below rather than taken on trust.
EXEMPT = {
    "routers/bim.py::delete_project":
        "delegates to bundle_io.delete_project(db, pid), which commits — asserted live below",
    "artifact_delivery.py::send":
        "a helper, not a route; both call sites (routers/jobs.py::deliver_artifact and "
        "jobs.py's scheduled-delivery path) commit after it returns",
}


def _is_commit(n: ast.AST) -> bool:
    return (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
            and n.func.attr == "commit")


def _unconditional_commit(stmts: list[ast.stmt]) -> bool:
    """Does this straight-line run of statements reach a commit on EVERY path?

    Descends only through what always executes once the block is entered. `if`/`for`/`while`/`try`
    bodies are deliberately NOT descended into: a commit inside one of those is exactly the
    conditional commit that made the first version of this gate report a clean tree."""
    for s in stmts:
        if isinstance(s, (ast.Expr, ast.Assign, ast.AugAssign, ast.Return)):
            if any(_is_commit(n) for n in ast.walk(s)):
                return True
        elif isinstance(s, (ast.With, ast.AsyncWith)) and _unconditional_commit(s.body):
            return True
    return False


def _reaches_commit(call: ast.AST, parent: dict, fn: ast.AST) -> bool:
    """Climb from the record's statement out through its enclosing blocks. At each level, does what
    FOLLOWS reach a commit unconditionally? A `finally` counts for a record in its own `try` body."""
    node = call
    while node in parent and not isinstance(node, ast.stmt):
        node = parent[node]
    cur = node
    while True:
        p = parent.get(cur)
        if p is None:
            return False
        for field in ("body", "orelse", "finalbody"):
            blk = getattr(p, field, None)
            if isinstance(blk, list) and cur in blk and \
                    _unconditional_commit(blk[blk.index(cur) + 1:]):
                return True
        if isinstance(p, ast.Try) and cur in (p.body or []) and \
                _unconditional_commit(p.finalbody or []):
            return True
        if p is fn:
            return False
        cur = p


def audit_sites(tree: ast.AST, label: str) -> list[tuple[str, int, bool]]:
    """(name, line, commit_reachable) for every ``audit.record`` call, one entry per CALL.

    Per call, not per function: `run_clash_federated` holds two, on mutually exclusive branches, and
    a per-function verdict cannot express "one of them is safe and the other is not".

    Separate from the verdict on purpose. An earlier gate in this repo asserted that its analyser
    still *reported* a site, so a mutation that misclassified every site passed — reporting a site
    and classifying it are different questions, and asserting one is not asserting the other."""
    out = []
    for fn in [n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        parent: dict = {}
        for p in ast.walk(fn):
            for c in ast.iter_child_nodes(p):
                parent[c] = p
        for call in [n for n in ast.walk(fn)
                     if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                     and n.func.attr == "record" and isinstance(n.func.value, ast.Name)
                     and n.func.value.id == "audit"]:
            out.append((f"{label}::{fn.name}", call.lineno, _reaches_commit(call, parent, fn)))
    return out


def verdict(sites: list[tuple[str, int, bool]]) -> list[str]:
    """The names that are neither committed nor exempt. Mutable on its own so a mutation can be
    aimed at the CLASSIFIER rather than at the finder."""
    return [f"{name}:{line}" for name, line, ok in sites if not ok and name not in EXEMPT]


def scan() -> list[tuple[str, int, bool]]:
    sites = []
    for f in sorted(SRC.rglob("*.py")):
        label = f.relative_to(SRC).as_posix()
        sites += audit_sites(ast.parse(f.read_text(encoding="utf-8")), label)
    return sites


# --- the gate ---------------------------------------------------------------------------------
sites = scan()
assert len(sites) >= 100, f"only {len(sites)} audit.record callers found — the walk stopped early"
bad = verdict(sites)
assert not bad, ("audit rows written into a session that is never committed:\n  "
                 + "\n  ".join(bad)
                 + "\n(add a db.commit() after audit.record, or an EXEMPT entry saying who commits)")

# --- prove the analyser reaches the shape it exists for --------------------------------------
# The pre-fix `put_config`: engine commits, THEN audit.record, then return. If a mutation of this
# gate cannot see that, the gate reports a clean tree for the exact defect it was written for.
PRE_FIX = """
def put_config(pid, roles, mode, db, actor):
    out = responsibility.set_config(db, pid, roles, mode, actor)
    audit.record(db, action="responsibility.config", actor=actor, method="PUT",
                 path=f"/projects/{pid}/responsibility/config", detail=out)
    return out
"""
probe = audit_sites(ast.parse(PRE_FIX), "probe.py")
assert [n for n, _, _ in probe] == ["probe.py::put_config"], probe
assert verdict(probe) == ["probe.py::put_config:4"], \
    f"the classifier calls the pre-fix shape SAFE — it would have missed the defect: {probe}"

# ...and that it does not call the fixed shape bad, which would make the gate unusable noise.
POST_FIX = PRE_FIX.replace("    return out", "    db.commit()\n    return out")
assert verdict(audit_sites(ast.parse(POST_FIX), "probe.py")) == [], "the fixed shape is still flagged"

# The shape the FIRST version of this gate could not see, reduced from `run_clash_federated`: two
# records on mutually exclusive branches, and a commit inside one of them. Every textual rule —
# min(rec), max(rec), "some commit at a later line" — calls this safe, because the commit really is
# further down the file. It is simply never on the other branch's path.
BRANCHED = """
def route(db, actor, coordinate, create_topics):
    if coordinate:
        audit.record(db, action="a.coordinate", actor=actor)
    if create_topics and not coordinate:
        audit.record(db, action="a.topics", actor=actor)
        db.commit()
    return {}
"""
branched = audit_sites(ast.parse(BRANCHED), "probe.py")
assert len(branched) == 2, f"one entry per CALL, not per function: {branched}"
assert verdict(branched) == ["probe.py::route:4"], \
    ("the classifier cannot see a commit that is on the OTHER branch — this is the exact shape "
     f"that hid a live defect through a full review: {branched}")
# ...and the same two records are BOTH safe once the commit moves to a common path.
BRANCHED_FIXED = BRANCHED.replace("        db.commit()\n    return {}", "    db.commit()\n    return {}")
assert verdict(audit_sites(ast.parse(BRANCHED_FIXED), "probe.py")) == [], \
    "a commit on a path both branches reach must clear both records"

# A commit inside a `for` is not reached when the loop body never runs; inside `with`, it is.
LOOPED = """
def route(db, actor, rows):
    audit.record(db, action="a", actor=actor)
    for r in rows:
        db.commit()
    return {}
"""
assert verdict(audit_sites(ast.parse(LOOPED), "probe.py")) == ["probe.py::route:3"], \
    "a commit inside a loop body is conditional — an empty sequence never reaches it"
WITHED = LOOPED.replace("    for r in rows:", "    with db.begin_nested():")
assert verdict(audit_sites(ast.parse(WITHED), "probe.py")) == [], \
    "a `with` body always runs once entered — refusing it would make the gate noise"

# --- the one exemption that can be checked live, is ------------------------------------------
os.environ["DATABASE_URL"] = "sqlite:///./test_audit_commit.db"
os.environ["STORAGE_DIR"] = "./test_storage_audit_commit"
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_audit_commit.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import AuditLog  # noqa: E402

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Doomed"}).json()["id"]
    r = c.delete(f"/projects/{pid}")
    assert r.status_code == 200, r.text[:200]
with SessionLocal() as db:
    actions = {a.action for a in db.query(AuditLog).all()}
assert "project.delete" in actions, \
    ("routers/bim.py::delete_project is EXEMPT because bundle_io commits for it — it no longer "
     f"does, so the exemption is now covering a real defect. Persisted: {sorted(actions)}")

print(f"AUDIT-COMMIT OK - {len(sites)} audit.record callers, {len(sites) - len(EXEMPT)} commit in "
      f"scope, {len(EXEMPT)} exempt with a named committer (one asserted live); the analyser is "
      "shown to flag the pre-fix put_config shape and to clear the fixed one")
