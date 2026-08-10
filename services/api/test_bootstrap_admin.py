"""R43-ORG-OWNERSHIP — the bootstrap registration must not hand platform admin to a stranger.

`POST /auth/register` accepts no token when the user table is empty, because there is no admin yet
to authorise one. That is fine on its own. What was not fine is that it also set `role="admin"`, and
`role` is not a hint: `routers/auth._is_platform_admin` ends with `return u.role == "admin"`. So on
a fresh public deployment, the first stranger to reach /auth/register became platform admin —
unauthenticated, and with `AEC_ADMIN_EMAILS` already naming someone else.

The audit that found it started from the wrong premise and is worth recording as such. The roadmap
item said "registration granting ORG ownership", imported from a generic threat list; there is no
Org or Tenant model in this codebase at all. Reading the six `User(...)` construction sites instead
of the threat list is what turned up the real one — and five of the six were already correct, which
is exactly why the sixth had gone unnoticed.

The rule: when AEC_ADMIN_EMAILS is set the operator has declared who admins are, so bootstrap grants
"user". When it is unset (desktop, local, single-operator) bootstrap still grants "admin" and
nothing changes. Both halves are asserted below — testing only the refusal would pass on a function
that refuses everything and would have broken every local install silently.
"""
from __future__ import annotations

import os
import sys

os.environ.pop("AEC_ADMIN_EMAILS", None)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import models  # noqa: E402
from aec_api.db import SessionLocal, engine  # noqa: E402
from aec_api.main import app  # noqa: E402

FAILED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(("PASS  " if ok else "FAIL  ") + name + ("   " + detail if detail else ""))
    if not ok:
        FAILED.append(name)


def _empty_user_table() -> None:
    with SessionLocal() as db:
        db.query(models.User).delete()
        db.commit()


def _role_of(username: str) -> str | None:
    with SessionLocal() as db:
        u = db.get(models.User, username)
        return None if u is None else u.role


models.Base.metadata.create_all(bind=engine)
client = TestClient(app)
BODY = {"password": "Corr3ct-Horse-Battery!"}

# --- half 1: configured deployment — the first registrant is NOT platform admin ----------------
os.environ["AEC_ADMIN_EMAILS"] = "ops@example.com"
_empty_user_table()
r = client.post("/auth/register", json={"username": "stranger", **BODY})
check("a configured deployment still accepts the bootstrap registration", r.status_code == 201,
      "got " + str(r.status_code) + " " + r.text[:120])
check("the first registrant on a configured deployment is NOT admin",
      _role_of("stranger") == "user", "role=" + str(_role_of("stranger")))

# The claim under test is about PLATFORM ADMIN, not about a string in a column. Assert the thing
# that actually matters — that the account cannot reach an ops endpoint — because a role rename
# would keep the assertion above green while reopening the hole.
tok = client.post("/auth/login", json={"username": "stranger", **BODY}).json().get("token", "")
r = client.get("/auth/users", headers={"Authorization": "Bearer " + tok})
check("and cannot reach a platform-admin endpoint", r.status_code == 403,
      "GET /auth/users returned " + str(r.status_code))

# --- half 2: the twin — unconfigured deployment still bootstraps ---------------------------------
# Without this, half 1 passes on a change that broke every desktop and single-operator install.
os.environ.pop("AEC_ADMIN_EMAILS", None)
_empty_user_table()
r = client.post("/auth/register", json={"username": "operator", **BODY})
check("an UNconfigured deployment still bootstraps its first account", r.status_code == 201,
      "got " + str(r.status_code) + " " + r.text[:120])
check("and that account IS admin, as before", _role_of("operator") == "admin",
      "role=" + str(_role_of("operator")))

# --- half 3: the gate is still a gate — a second account still needs a token --------------------
r = client.post("/auth/register", json={"username": "second", **BODY})
check("a second registration without a token is still refused", r.status_code == 403,
      "got " + str(r.status_code))

_empty_user_table()

if FAILED:
    print("FAILED:", ", ".join(FAILED))
    sys.exit(1)
print("test_bootstrap_admin OK")
