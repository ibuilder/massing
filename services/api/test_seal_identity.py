"""A professional seal must attest to a PERSON, not to a session.

A PE/RA seal is not an authorisation, it is a personal legal attestation that a named licensed human
was in responsible charge of the work. Responsible charge cannot be delegated to software, and a
licensee whose seal reaches work they did not supervise is the specific thing a state board
disciplines. Three separate holes had to close before `/pdf/seal` could claim that, and each earlier
fix looked complete:

  1. anonymous     -> `Depends(current_user)` identified without authorising; an unauthenticated
                      caller got back a PDF bearing a rendered PE seal with a name and licence number
                      of their choosing. Fixed with require_identified.
  2. impersonation -> `profile` was free text, so ANY authenticated user could seal under a
                      colleague's licence number. Fixed by deriving the seal from a verified licence
                      row that belongs to the caller.
  3. automation    -> binding to the account still is not binding to a person: any process holding a
                      bearer token can replay it, so an agent driving this API with a user's token
                      would emit sealed documents and the audit row would record a human act that
                      never happened. Fixed with a step-up assertion a stored credential cannot
                      satisfy.

Hole 3 is why this file exists. It is invisible to every test that authenticates the normal way,
because a valid token is exactly what the attack has.

Single-operator mode is deliberately NOT covered here — see test_stamps, which runs RBAC-off and must
keep passing unchanged. There are no accounts, no passwords and no login in the desktop build, so a
step-up would be theatre in front of an app that is unauthenticated by design.

Run: PYTHONPATH="src;../data/src" ./.venv/Scripts/python.exe test_seal_identity.py
"""
import io
import json
import os
import sys
from datetime import date, timedelta

os.environ["DATABASE_URL"] = "sqlite:///./test_seal_identity.db"
os.environ["STORAGE_DIR"] = "./test_storage_seal_identity"
os.environ["AEC_RBAC"] = "1"                    # the only configuration the bugs exist in
os.environ.pop("AEC_TRUST_XUSER", None)
os.environ.pop("AEC_ADMIN_EMAILS", None)        # the bootstrap account is the platform admin here
os.environ.pop("AEC_SEAL_ALLOW_PROFILE", None)  # default posture: free-text identities refused
os.environ["AEC_AUTH_SECRET"] = "test-secret-that-is-long-enough-to-be-accepted"
os.environ["AEC_API_KEY"] = "test-api-key-for-the-machine-identity"
for _f in ("./test_seal_identity.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402
from pypdf import PdfReader, PdfWriter  # noqa: E402

import aec_api.rbac as rbac  # noqa: E402
from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import AuditLog  # noqa: E402

FAILED: list[str] = []
_TOTAL = 0


def check(label, ok, detail=""):
    global _TOTAL
    _TOTAL += 1
    print(f"{'PASS' if ok else 'FAIL'}  {label}{(' — ' + str(detail)) if detail and not ok else ''}")
    if not ok:
        FAILED.append(label)


def blank_pdf() -> bytes:
    w = PdfWriter()
    w.add_blank_page(width=612, height=792)
    b = io.BytesIO()
    w.write(b)
    return b.getvalue()


def seal_text(pdf: bytes) -> str:
    return "\n".join((p.extract_text() or "") for p in PdfReader(io.BytesIO(pdf)).pages)


PDF = blank_pdf()
PW = "Correct-Horse-9!"
FUTURE = (date.today() + timedelta(days=365)).isoformat()
PAST = (date.today() - timedelta(days=1)).isoformat()


def login(c, who):
    return (c.post("/auth/login", json={"username": who, "password": PW}).json() or {}).get("token")


def seal(c, tok, **data):
    return c.post("/pdf/seal", files={"file": ("d.pdf", PDF, "application/pdf")},
                  data={"template_id": "seal-pe", "sign": "false", "page": "1", **data},
                  headers={"Authorization": f"Bearer {tok}"})


# The CONTROL. Assert the FLAGS, not a 403 somewhere: with RBAC off every identity is authenticated by
# construction and each assertion below would pass for the wrong reason.
check("CONTROL: RBAC is actually ON", rbac.RBAC_ON is True, rbac.RBAC_ON)
check("CONTROL: not LOCAL_MODE (which drops the step-up requirement by design)",
      rbac.LOCAL_MODE is False, rbac.LOCAL_MODE)

with TestClient(app) as c:
    # boss = first account in an empty DB, so legitimately the bootstrap platform admin.
    c.post("/auth/register", json={"username": "boss@seal.test", "password": PW})
    boss = login(c, "boss@seal.test")
    # bob = an ORDINARY account. Testing any of this with the bootstrap admin proves nothing.
    c.post("/auth/register", json={"username": "bob@seal.test", "password": PW, "role": "user"},
           headers={"Authorization": f"Bearer {boss}"})
    bob = login(c, "bob@seal.test")
    check("both accounts obtained tokens", bool(boss and bob), f"boss={bool(boss)} bob={bool(bob)}")
    BOB = {"Authorization": f"Bearer {bob}"}
    BOSS = {"Authorization": f"Bearer {boss}"}

    # --- provisioning: a licence is an assertion about a state board's credential ------------------
    lic_body = {"user": "bob@seal.test", "name_on_seal": "Bob R. Builder, P.E.",
                "license_no": "PE-77341", "state": "NY", "discipline": "PE", "expiration": FUTURE}
    r = c.post("/admin/licenses", json=lic_body, headers=BOB)
    check("an ordinary user cannot record their OWN licence (self-attestation is worth nothing)",
          r.status_code == 403, r.status_code)

    r = c.post("/admin/licenses", json=lic_body, headers=BOSS)
    check("a platform admin can record a licence", r.status_code == 201, r.text[:120])
    bob_lic = (r.json() or {}).get("id")
    check("the row records WHO verified it", (r.json() or {}).get("verified_by") == "boss@seal.test",
          r.json())

    r = c.post("/admin/licenses", json={**lic_body, "user": "nobody@seal.test"}, headers=BOSS)
    check("a licence for a nonexistent user is refused", r.status_code == 404, r.status_code)
    r = c.post("/admin/licenses", json={"user": "bob@seal.test", "name_on_seal": "X"}, headers=BOSS)
    check("a licence missing licence_no/state is refused", r.status_code == 422, r.status_code)

    # boss holds a licence too — needed to prove bob cannot borrow it.
    boss_lic = (c.post("/admin/licenses", json={
        "user": "boss@seal.test", "name_on_seal": "Ada Boss, P.E.", "license_no": "PE-00001",
        "state": "NY", "expiration": FUTURE}, headers=BOSS).json() or {}).get("id")

    mine = c.get("/licenses/mine", headers=BOB).json()["licenses"]
    check("/licenses/mine returns only the caller's own licences",
          [m["id"] for m in mine] == [bob_lic], mine)

    # --- the step-up: an assertion about a person, not a session -----------------------------------
    check("sealing with a valid bearer token but NO step-up is refused — this is the automation hole",
          seal(c, bob, license_id=bob_lic).status_code == 403,
          seal(c, bob, license_id=bob_lic).status_code)

    r = c.post("/auth/step-up", json={"password": "wrong-password", "act": "pdf.seal"}, headers=BOB)
    check("step-up with the wrong password is refused", r.status_code == 403, r.status_code)
    r = c.post("/auth/step-up", json={"password": PW, "act": "not-a-real-act"}, headers=BOB)
    check("step-up for an unknown action is refused (no minting assertions for arbitrary acts)",
          r.status_code == 400, r.status_code)
    r = c.post("/auth/step-up", json={"password": PW, "act": "pdf.seal"},
               headers={"Authorization": f"Bearer {os.environ['AEC_API_KEY']}"})
    check("the api-key identity cannot step up — a machine credential has no person behind it",
          r.status_code == 403, r.status_code)

    su = (c.post("/auth/step-up", json={"password": PW, "act": "pdf.seal"},
                 headers=BOB).json() or {}).get("token")
    check("a correct password yields a step-up assertion", bool(su), "no token — probe is inert")

    # A step-up must not be promotable into a session, even though it is signed with the same key.
    #
    # This MUST use a fresh client. `/auth/login` sets an httponly `aec_token` cookie and TestClient
    # keeps a cookie jar, so on `c` the bad Authorization header is ignored and `current_user` falls
    # through to the cookie — the request succeeds as the logged-in user and the assertion passes for
    # entirely the wrong reason. The first draft of this check did exactly that and reported the
    # step-up as promotable when it is not.
    with TestClient(app) as clean:
        r = clean.get("/licenses/mine", headers={"Authorization": f"Bearer {su}"})
        check("a step-up assertion is NOT usable as a bearer token", r.status_code == 403,
              r.status_code)

    # --- sealing, and where the identity comes from ------------------------------------------------
    r = seal(c, bob, license_id=bob_lic, step_up=su)
    check("bob seals with his own verified licence + step-up", r.status_code == 200, r.text[:140])
    txt = seal_text(r.content) if r.status_code == 200 else ""
    check("the seal carries the LICENCE's name, not anything the caller typed",
          "Bob R. Builder" in txt and "PE-77341" in txt, txt[:160])

    r = seal(c, bob, license_id=boss_lic, step_up=su)
    check("bob cannot seal with ANOTHER user's licence id", r.status_code == 403, r.status_code)

    r = seal(c, bob, step_up=su, profile=json.dumps(
        {"name": "Someone Else, PE", "license_no": "PE-99999", "state": "NY"}))
    check("the legacy free-text profile is refused by default", r.status_code == 403, r.status_code)

    r = seal(c, bob, step_up=su)
    check("sealing with no licence at all is refused", r.status_code == 422, r.status_code)

    # An expired licence must refuse: a document sealed under a lapsed licence is precisely what a
    # board disciplines, so this is a 409 rather than something the caller can shrug off.
    exp_lic = (c.post("/admin/licenses", json={
        "user": "bob@seal.test", "name_on_seal": "Bob R. Builder, P.E.", "license_no": "PE-OLD",
        "state": "TX", "expiration": PAST}, headers=BOSS).json() or {}).get("id")
    r = seal(c, bob, license_id=exp_lic, step_up=su)
    check("an EXPIRED licence refuses to seal", r.status_code == 409, f"{r.status_code} {r.text[:90]}")

    # --- the fp binding: a password change kills outstanding assertions ---------------------------
    su2 = (c.post("/auth/step-up", json={"password": PW, "act": "pdf.seal"},
                  headers=BOB).json() or {}).get("token")
    c.post("/auth/password", json={"current": PW, "new": "Different-Horse-42!"}, headers=BOB)
    r = seal(c, bob, license_id=bob_lic, step_up=su2)
    check("a step-up assertion dies when the password changes (fp binding), not merely on expiry",
          r.status_code in (401, 403), r.status_code)

    # --- the audit row has to distinguish a verified seal from a free-text one ---------------------
    db = SessionLocal()
    rows = [a.detail for a in db.query(AuditLog).filter(AuditLog.action == "pdf.seal").all()]
    db.close()
    check("exactly one seal succeeded, so exactly one audit row exists", len(rows) == 1, len(rows))
    if rows:
        d = rows[0]
        check("the row records it was derived from a verified licence", d.get("via") == "license", d)
        check("the row names the licence ROW, not just a typed number",
              d.get("license_id") == bob_lic, d)
        check("the row records that a step-up was required", d.get("step_up") is True, d)

print()
if FAILED:
    print(f"seal_identity: {len(FAILED)} FAILED — {FAILED}")
    sys.exit(1)
print(f"seal_identity: all {_TOTAL} checks passed — a seal now requires a verified licence belonging "
      "to the caller AND a fresh step-up a stored token cannot satisfy; free-text identities, other "
      "people's licences, expired licences, the api-key, and a token-only caller are all refused, and "
      "the audit row says which licence row it came from.")
