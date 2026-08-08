"""Approving a model version records WHO approved it, so the api-key cannot be the who.

WHAT MAKES THIS DIFFERENT FROM AN ORDINARY PERMISSION CHECK. `_REVIEW_ACTIONS` in `versions.py` is
`{submit: draft→in_review, approve: in_review→approved, reject: in_review→draft}` — there is **no
transition out of `approved`**. So `reviewed_by` is a permanent answer to "who approved the model
this drawing set was issued from", and the api-key is not a who: it is a shared machine credential
with no person behind it. `/auth/step-up` already refuses that identity for exactly this reason.

WHY NOT A FULL STEP-UP, WHICH IS WHAT THE ROADMAP ENTRY GESTURED AT. A seal is a per-document legal
attestation carrying personal liability, so it is worth a password per document. This is an internal
QA record. Demanding a re-authentication on every model approval would be a **contract change for
every human caller** in exchange for a much smaller claim, and a new gate that rejects legitimate
input is its own defect. What the step-up *thinking* yields here is narrower and cheaper: the record
must name a person, so refuse only the identity that cannot be one.

THE ASSERTIONS ARE PAIRED THROUGHOUT. A file that only checked the refusal would pass just as well
against a route that 403s for everything — and since the api-key resolves to `admin` on every
project, "the api-key is refused" is a surprising enough claim that its twin has to be visible: the
same call from a named editor must succeed, and `submit`/`reject` from the api-key must too.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_version_approve_identity.py
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_version_approve_identity.db"
os.environ["STORAGE_DIR"] = "./test_storage_version_approve_identity"
os.environ["AEC_RBAC"] = "1"            # without this require_role short-circuits and so does the gate
os.environ["AEC_TRUST_XUSER"] = "1"     # lets the suite act as a named user via X-User
os.environ["AEC_API_KEY"] = "test-api-key-for-approval-identity"
for _f in ("./test_version_approve_identity.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import rbac  # noqa: E402
from aec_api.db import Base, SessionLocal, engine  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import ModelVersion, Project, ProjectMember  # noqa: E402

Base.metadata.create_all(bind=engine)
client = TestClient(app)

failures: list[str] = []
KEY = {"Authorization": f"Bearer {os.environ['AEC_API_KEY']}"}
HUMAN = {"X-User": "dana"}


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"  {'ok  ' if ok else 'FAIL'}  {name}{('  — ' + detail) if detail and not ok else ''}")
    if not ok:
        failures.append(name)


def seed(pid: str, version: int, status: str = "draft") -> None:
    """A published snapshot, written directly — publishing needs a real IFC and this test is about
    the review transition, not about producing one."""
    db = SessionLocal()
    try:
        db.add(ModelVersion(project_id=pid, version=version, element_count=7,
                            note="seed", review_status=status))
        db.commit()
    finally:
        db.close()


db = SessionLocal()
try:
    db.add(Project(id="p-approve", name="Approval Identity"))
    db.add(ProjectMember(project_id="p-approve", user="dana", role="editor"))
    db.commit()
finally:
    db.close()

PID = "p-approve"
URL = f"/projects/{PID}/versions"


def review(v: int, action: str, headers: dict) -> "object":
    return client.post(f"{URL}/{v}/review", json={"action": action}, headers=headers)


# --- the api-key can still do everything that is not a permanent claim -------------------------
seed(PID, 1)
r = review(1, "submit", KEY)
check("the api-key may submit a draft for review", r.status_code == 200, f"{r.status_code} {r.text}")
r = review(1, "reject", KEY)
check("...and may reject one back to draft", r.status_code == 200, f"{r.status_code} {r.text}")

# --- but not the one that cannot be undone ------------------------------------------------------
# Submitted by the HUMAN on purpose. `versions.review` sets `reviewed_by = actor` on EVERY
# transition, not only on approve — so the field means "who last moved this", and it is only "who
# approved" once the terminal state is reached. Seeding it with a known non-api-key value is what
# makes the next assertion able to see a write that should not have happened: had the fixture
# submitted as the api-key, `reviewed_by` would already read "api-key" and a refusal that wrote
# would be indistinguishable from one that did not.
review(1, "submit", HUMAN)
r = review(1, "approve", KEY)
check("the api-key may NOT approve", r.status_code == 403, f"{r.status_code} {r.text}")
check("...and the refusal says why rather than just 'forbidden'",
      "no person behind it" in r.text, r.text)

# The refusal must be a refusal, not a 403 that already wrote. Checked against the STORED row and
# not the response, because a route that mutates and then raises returns the same 403 as one that
# refuses first.
db = SessionLocal()
try:
    row = db.query(ModelVersion).filter(ModelVersion.project_id == PID,
                                        ModelVersion.version == 1).first()
    check("...and the version is untouched — still in_review, still attributed to the submitter",
          row.review_status == "in_review" and row.reviewed_by == "dana",
          f"status={row.review_status!r} reviewed_by={row.reviewed_by!r}")
finally:
    db.close()

# --- THE TWIN. A named editor must be able to approve the very same version --------------------
r = review(1, "approve", HUMAN)
check("a named editor CAN approve the same version", r.status_code == 200, f"{r.status_code} {r.text}")
check("...and is recorded as the approver",
      r.status_code == 200 and r.json().get("reviewed_by") == "dana",
      r.text)

# --- LOCAL_MODE: a single-operator desktop build has one human and no identity provider ---------
# The route reads `rbac.LOCAL_MODE` at call time, so this exercises the real carve-out rather than a
# copy of its condition. Mirrors the seal route, which makes the same exemption for the same reason.
seed(PID, 2)
review(2, "submit", KEY)
_saved = rbac.LOCAL_MODE
rbac.LOCAL_MODE = True
try:
    r = review(2, "approve", KEY)
    check("in LOCAL_MODE the api-key IS the person, so approve is allowed",
          r.status_code == 200, f"{r.status_code} {r.text}")
finally:
    rbac.LOCAL_MODE = _saved

# ...and the carve-out is genuinely conditional: restore it and the next approval is refused again.
seed(PID, 3)
review(3, "submit", KEY)
r = review(3, "approve", KEY)
check("...and with LOCAL_MODE restored it is refused again", r.status_code == 403,
      f"{r.status_code} {r.text}")

# --- the gate must not swallow the ordinary failures the route already had ----------------------
seed(PID, 4)
r = review(4, "approve", HUMAN)     # still draft — approve requires in_review
check("an illegal transition is still 409, not 403", r.status_code == 409, f"{r.status_code} {r.text}")
r = review(999, "submit", HUMAN)
check("an unknown version is still 404", r.status_code == 404, f"{r.status_code} {r.text}")

print(f"\ntest_version_approve_identity "
      f"{'OK' if not failures else 'FAILED: ' + ', '.join(failures)}")
sys.exit(1 if failures else 0)
