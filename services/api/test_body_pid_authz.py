"""SEC-BODY-PID — a project id in the request BODY must be authorised like one in the path.

`POST /test-fit/optimize` read another project's `purchase_price` and hard $/sf with **no gate of
any kind**, from a `pid` supplied in the request body. Four independent mechanisms exist and not one
of them could see it:

1. `rbac.require_role(...)` is a dependency whose inner signature is `dep(pid: str, ...)`, so
   FastAPI resolves that `pid` from the **path or query**. A body field is unreachable to it. The
   route could not have used it even if someone had tried.
2. `test_route_authz` walks `/projects/{pid}` routes only. **No `{pid}` in the path ⇒ outside its
   remit** — the same shape already recorded as "require_role on a GLOBAL route".
3. `main._PROTECTED_PREFIXES` is a hand-maintained list of top-level prefixes and does not contain
   `/test-fit`. (It also only applies with `AEC_RBAC=1`, so it is a second layer, never the fix.)
4. `test_global_authz` had the route in its **frozen BASELINE**, grouped under the comment
   "stateless compute — no stored state". It was the only one of the five routes under that label
   that takes a `Session`: `/test-fit/compare`, `/structure/recommend`, `/generate/massing/preview`
   and `/massing/optioneer` are genuine calculators; this one reads the database.

**That fourth point is the one worth keeping.** The exemption list did not fail to notice the route
— it had *examined* it and filed it as safe by association with its neighbours, on the strength of
the file it lives in and the shape of its signature. `test_global_authz`'s own docstring says
"triaging all 43 is real work and this test does not pretend to have done it", which was honest, and
this is what that honesty cost. **A frozen baseline preserves the reasoning of the day it was
written, including the parts that were wrong.**

The predicate that isolates it is not "has no authz" (34 routes, mostly fine) but **"has no authz
AND takes a DB session"** — a route that cannot read stored data cannot leak it.

WHAT THIS ASSERTS. With RBAC on, a caller with no role on the target project must be refused before
the project is read. Not "the values are not echoed" — they are not, but the caller controls
`plate_w`, `plate_d`, `floors` and the rest of `econ`, so the returned ranking is **invertible**:
vary the inputs, observe the yield, solve for the seed. Refusing the read is the only honest fix.

The no-`pid` case must keep working. Without `pid` the route is a pure calculator over
caller-supplied numbers and is legitimately open, like its four siblings — a fix that closed it
would have broken the feature to fix the leak.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_body_pid_authz.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_body_pid_authz.db"
os.environ["STORAGE_DIR"] = "./test_storage_body_pid_authz"
os.environ["AEC_RBAC"] = "1"            # the gate is a no-op with RBAC off, as require_role is
os.environ["AEC_TRUST_XUSER"] = "1"     # lets the suite act as a named user via X-User
for _f in ("./test_body_pid_authz.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api.db import Base, SessionLocal, engine  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import Project, ProjectMember  # noqa: E402

Base.metadata.create_all(bind=engine)
client = TestClient(app)

LAND = 7_350_000.0     # distinctive values so a leak is unambiguous in the output
HARD_PSF = 412.5

failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail and not ok else ''}")
    if not ok:
        failures.append(name)


db = SessionLocal()
db.add(Project(id="secret-deal", name="Confidential Deal",
               dev_property={"purchase_price": LAND},
               dev_budget={"lines": [{"category": "hard", "unit_cost": HARD_PSF,
                                      "quantity": 1000, "description": "shell $/sf"}]}))
db.add(ProjectMember(project_id="secret-deal", user="owner", role="admin"))
db.commit()
db.close()

BODY = {"plate_w": 120.0, "plate_d": 70.0, "floors": 6, "targets": {}, "econ": {}}


def optimize(user: str | None, pid: str | None):
    body = dict(BODY)
    if pid:
        body["pid"] = pid
    headers = {"X-User": user} if user else {}
    return client.post("/test-fit/optimize", json=body, headers=headers)


# 1) THE DEFECT. A caller with no role on the project must not reach it. This is the assertion that
#    fails on the unfixed code: it returned 200 and seeded the econ from someone else's deal.
r = optimize("stranger", "secret-deal")
check("a caller with no role on the project is refused", r.status_code == 403,
      f"got {r.status_code} — an unauthorised caller reached another project's financials")

# 2) An ANONYMOUS caller likewise. `current_user` returns the literal "anonymous" with RBAC on and no
#    credential, which identifies without authorising — the mistake this repo has shipped twice.
r = optimize(None, "secret-deal")
check("an anonymous caller is refused", r.status_code == 403, f"got {r.status_code}")

# 3) The owner still works — a gate that refuses everyone is not a fix.
r = optimize("owner", "secret-deal")
check("a member with the role still succeeds", r.status_code == 200, f"got {r.status_code}")

# 4) The no-pid calculator stays open. Closing it would break the feature to fix the leak.
r = optimize(None, None)
check("no pid: the pure calculator is still reachable", r.status_code == 200, f"got {r.status_code}")

# 5) A refused response must not carry the values in ANY form. Asserting the status alone would pass
#    for a 403 that had already computed and attached the ranking.
r = optimize("stranger", "secret-deal")
blob = r.text
check("the refusal leaks neither value", str(LAND) not in blob and str(HARD_PSF) not in blob,
      "a seeded value appears in the refused response body")

# 6) The route must be gone from test_global_authz's frozen baseline — FIXED, not re-frozen. Without
#    this, a future edit could drop the gate and the baseline would silently declare it acceptable
#    again. Same reason the /pdf/* and /templates entries were deleted rather than kept.
src = open(os.path.join(os.path.dirname(__file__), "test_global_authz.py"), encoding="utf-8").read()
baseline = src[src.index("BASELINE = {"):src.index("}", src.index("BASELINE = {"))]
check("the route is not re-frozen in the global-authz baseline",
      '"/test-fit/optimize"' not in baseline,
      "it is still listed as known-unguarded, which would re-accept the defect")

print(f"\ntest_body_pid_authz {'OK' if not failures else 'FAILED: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
