"""AUDIT-COMMIT — an audit row nobody commits is an audit row nobody has.

`get_db` yields a session and only ever ``close()``s it. Nothing in the request path commits on the
way out, so a route that calls ``audit.record`` after its engine has already committed leaves the
audit row pending in a session that is about to be discarded. The request returns 200. The trail is
empty. Nothing anywhere goes red — which is why this is a gate and not a comment.

Found by touching the transaction boundary in `responsibility`, not by looking for it: BOTH of that
router's write routes had it, and one of them is the edit that can orphan an entire matrix.

**Derive the population, do not list it.** Every function anywhere under `src/aec_api` that calls
``audit.record`` is a candidate; a function is SAFE only if a ``.commit()`` follows that call in the
same function body. Anything else is UNKNOWN, and **UNKNOWN reds the build** unless it is named in
`EXEMPT` with a reason — because the two blind spots this repo has already paid for were both a
predicate deciding what to LOOK at, and everything such a predicate excludes is invisible to its own
output. A delegated commit is real (`bim.delete_project` has one) but it is not something this
analyser can see, so it is an exemption with evidence rather than a rule.

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


def audit_sites(tree: ast.AST, label: str) -> list[tuple[str, int, bool]]:
    """(name, line, commit_follows) for every function calling ``audit.record``.

    Separate from the verdict on purpose. An earlier gate in this repo asserted that its analyser
    still *reported* a site, so a mutation that misclassified every site passed — reporting a site
    and classifying it are different questions, and asserting one is not asserting the other."""
    out = []
    for fn in [n for n in ast.walk(tree)
               if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))]:
        body = list(ast.walk(fn))
        rec = [n.lineno for n in body
               if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
               and n.func.attr == "record" and isinstance(n.func.value, ast.Name)
               and n.func.value.id == "audit"]
        if not rec:
            continue
        commits = [n.lineno for n in body
                   if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                   and n.func.attr == "commit"]
        out.append((f"{label}::{fn.name}", min(rec), any(c > min(rec) for c in commits)))
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
