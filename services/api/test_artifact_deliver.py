"""R24-REPORTS-BY-MOMENT — "shared, not just downloaded": mail a finished job's artifact.

The entry's remainder reads "scheduled and shared, not just downloaded", and the two halves have
DIFFERENT blockers. Its own wording says this "still wants a delivery surface and SMTP" — both of
which already ship: `mailer.py` sends real mail and `POST .../notifications/digest` is a working
assemble-then-send surface. What was actually missing was smaller and more specific: the mailer had
no way to carry a FILE. That is what this covers.

The SCHEDULED half is not here — it is in `test_routines_run.py`, and this line used to explain its
absence with "this tree has no scheduler of any kind", which was false when written. `routines.py`
and `routines_run.py` are a scheduler; what is genuinely still a deployment decision is only what
INVOKES the sweep on a cadence (in-process versus external cron hitting the endpoint).

Run: PYTHONPATH=src ./.venv/bin/python test_artifact_deliver.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_artifact_deliver.db"
# setdefault, not assignment: run_tests.py assigns STORAGE_DIR=./_storage_{test} and sweeps exactly
# that path afterwards. Overwriting it sent this test's 15 MiB blob to a directory the runner does
# not own, which is what the suite footer means by "dir(s) this runner does not own".
os.environ.setdefault("STORAGE_DIR", "./_storage_test_artifact_deliver")
os.environ.pop("AEC_RBAC", None)
os.environ.pop("AEC_SMTP_HOST", None)          # unconfigured: sends must report "disabled", not fail
for _f in ("./test_artifact_deliver.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import mailer, storage  # noqa: E402
from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import AuditLog, Job  # noqa: E402

# --- the pure half first: build_message must actually carry the bytes ---------------------------
# `build_message` is documented as pure and testable, so the attachment shape is checked without
# any SMTP at all. The ORDER matters and is the reason this is asserted rather than eyeballed:
# add_alternative has to run before add_attachment, or the html body lands inside the mixed part
# and mail clients render the attachment where the message should be.
msg = mailer.build_message("a@example.com", "Subj", "plain body", "<p>html body</p>",
                           [("pack.pdf", b"%PDF-1.4 fake", "application/pdf")])
atts = list(msg.iter_attachments())
assert len(atts) == 1, [p.get_content_type() for p in msg.walk()]
assert atts[0].get_filename() == "pack.pdf", atts[0].get_filename()
assert atts[0].get_content_type() == "application/pdf", atts[0].get_content_type()
assert atts[0].get_payload(decode=True) == b"%PDF-1.4 fake"
body = msg.get_body(preferencelist=("html",))
assert body is not None and "html body" in body.get_content(), "the html body must survive attaching"

# a message with no attachments must be byte-identical in shape to before — the parameter is
# additive, and an existing digest send must not silently become multipart/mixed.
plain = mailer.build_message("a@example.com", "S", "t")
assert not list(plain.iter_attachments()), "no attachments must mean no mixed part"

with TestClient(app) as c:
    pid = c.post("/projects", json={"name": "Deliver P"}).json()["id"]

    # --- a finished artifact job, built the way the job runner leaves one ----------------------
    key = f"{pid}/jobs/deadbeef-owner-monthly.pdf"
    storage.put(key, b"%PDF-1.4 owner monthly package")
    with SessionLocal() as s:
        s.add(Job(id="job-done", project_id=pid, kind="report_package", state="done",
                  params={}, result={"artifact_key": key, "media_type": "application/pdf",
                                     "filename": "owner-monthly.pdf",
                                     "bytes": 30, "reports": ["r1"]}))
        s.add(Job(id="job-running", project_id=pid, kind="report_package", state="running",
                  params={}))
        s.add(Job(id="job-noart", project_id=pid, kind="report_package", state="done",
                  params={}, result={}))
        s.commit()

    # --- the delivery itself: unconfigured SMTP reports "disabled", it does not 500 -------------
    # This is the shape the digest route already returns, on purpose: an operator who has not set
    # AEC_SMTP_HOST gets a truthful per-recipient status rather than an error that reads like a bug.
    r = c.post(f"/projects/{pid}/jobs/job-done/deliver",
               json={"to": ["owner@example.com", "lender@example.com"], "note": "Draw 7 pack."})
    assert r.status_code == 200, (r.status_code, r.text)
    out = r.json()
    assert out["smtp_configured"] is False, out
    assert out["filename"] == "owner-monthly.pdf", out
    assert out["bytes"] == len(b"%PDF-1.4 owner monthly package"), out
    assert sorted(out["results"]["disabled"]) == ["lender@example.com", "owner@example.com"], out

    # --- it is audited: who sent what to how many people ---------------------------------------
    # A file leaving the system is exactly the event an audit log exists for.
    with SessionLocal() as s:
        ev = [a for a in s.query(AuditLog).all() if a.action == "job.artifact.deliver"]
    assert len(ev) == 1, [(a.action) for a in ev]
    assert ev[0].detail["recipients"] == 2, ev[0].detail
    assert ev[0].detail["filename"] == "owner-monthly.pdf", ev[0].detail
    assert ev[0].detail["bytes"] == len(b"%PDF-1.4 owner monthly package"), ev[0].detail

    # --- refusals: same answers as the download route, plus delivery's own two -----------------
    # Mirroring job_artifact matters — a caller should not learn two different answers to
    # "is this artifact ready".
    assert c.post(f"/projects/{pid}/jobs/nope/deliver",
                  json={"to": ["a@example.com"]}).status_code == 404
    assert c.post(f"/projects/{pid}/jobs/job-running/deliver",
                  json={"to": ["a@example.com"]}).status_code == 409
    assert c.post(f"/projects/{pid}/jobs/job-noart/deliver",
                  json={"to": ["a@example.com"]}).status_code == 404

    # an empty recipient list is a refusal, not a silent success — otherwise a UI bug that drops
    # the address field reports "sent" and the pack goes nowhere.
    for empty in ([], ["", "   "]):
        r = c.post(f"/projects/{pid}/jobs/job-done/deliver", json={"to": empty})
        assert r.status_code == 422, (empty, r.status_code, r.text)

    # oversize is refused up front rather than as a per-recipient "error" from a server that
    # would have bounced it anyway.
    big = f"{pid}/jobs/big.pdf"
    storage.put(big, b"x" * (15 * 1024 * 1024 + 1))
    with SessionLocal() as s:
        s.add(Job(id="job-big", project_id=pid, kind="report_package", state="done", params={},
                  result={"artifact_key": big, "media_type": "application/pdf",
                          "filename": "big.pdf"}))
        s.commit()
    r = c.post(f"/projects/{pid}/jobs/job-big/deliver", json={"to": ["a@example.com"]})
    assert r.status_code == 413, (r.status_code, r.text)

    # --- a malformed recipient is that recipient's error, not everyone's -----------------------
    # `EmailMessage` rejects a header value containing CR/LF with ValueError. `send_email` is
    # documented to NEVER raise; built outside its try block it did, which aborted the delivery loop
    # after earlier recipients had already been served and before the audit row was written — so the
    # audit disagreed with what actually happened. The bad address must degrade to "error" alone.
    assert mailer.send_email("bad@example.com\r\nBcc: injected@example.com", "S", "b") == "error"
    r = c.post(f"/projects/{pid}/jobs/job-done/deliver",
               json={"to": ["good@example.com", "bad@example.com\r\nBcc: x@example.com"]})
    assert r.status_code == 200, (r.status_code, r.text)
    res = r.json()["results"]
    assert res.get("disabled") == ["good@example.com"], res
    assert res.get("error") == ["bad@example.com\r\nBcc: x@example.com"], res

    # --- recipients are de-duplicated, case-insensitively --------------------------------------
    # Every retained address is a synchronous SMTP conversation, so a duplicate is not merely untidy.
    r = c.post(f"/projects/{pid}/jobs/job-done/deliver",
               json={"to": ["a@example.com", "A@Example.com", " a@example.com "]})
    assert r.status_code == 200, (r.status_code, r.text)
    assert r.json()["results"]["disabled"] == ["a@example.com"], r.json()["results"]

    # --- the recipient cap REFUSES, it does not silently trim ----------------------------------
    # Trimming would be the same silent-success failure the empty-list 422 exists to prevent.
    many = [f"u{i}@example.com" for i in range(26)]
    r = c.post(f"/projects/{pid}/jobs/job-done/deliver", json={"to": many})
    assert r.status_code == 422, (r.status_code, r.text)
    assert "25" in r.text, r.text

    # --- oversize is refused from the STORED SIZE, without materialising the object -------------
    # storage.get() pulls the whole artifact into memory; checking len() afterwards spends exactly
    # the memory being refused. Patching get() to explode proves the refusal happens before it.
    _boom = storage.get
    storage.get = lambda k: (_ for _ in ()).throw(AssertionError(f"materialised {k}"))
    try:
        r = c.post(f"/projects/{pid}/jobs/job-big/deliver", json={"to": ["a@example.com"]})
        assert r.status_code == 413, (r.status_code, r.text)
    finally:
        storage.get = _boom

    # a job in ANOTHER project is not reachable through this project's path.
    pid2 = c.post("/projects", json={"name": "Other"}).json()["id"]
    assert c.post(f"/projects/{pid2}/jobs/job-done/deliver",
                  json={"to": ["a@example.com"]}).status_code == 404

# --- STARTTLS must present a VERIFYING context ---------------------------------------------------
# `starttls()` with no argument uses `ssl._create_stdlib_context()`, which on this interpreter
# reports verify_mode=CERT_NONE and check_hostname=False — the artifact and the SMTP password go up
# with no certificate check. Asserted through a fake SMTP rather than by reading the source, so the
# test measures what is passed at the call, not what the file appears to say.
import ssl  # noqa: E402


class _FakeSMTP:
    captured: list = []

    def __init__(self, host, port, timeout=None):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def starttls(self, context=None):
        _FakeSMTP.captured.append(context)

    def login(self, u, p):
        pass

    def send_message(self, m):
        pass


_real_smtp, _real_get = mailer.smtplib.SMTP, mailer.settings_store.get
mailer.smtplib.SMTP = _FakeSMTP
mailer.settings_store.get = lambda k, d=None: {"AEC_SMTP_HOST": "smtp.example.com",
                                               "AEC_SMTP_PORT": "587",
                                               "AEC_SMTP_TLS": "1"}.get(k, d)
try:
    assert mailer.send_email("a@example.com", "S", "b") == "sent"
finally:
    mailer.smtplib.SMTP, mailer.settings_store.get = _real_smtp, _real_get

assert len(_FakeSMTP.captured) == 1, _FakeSMTP.captured
_ctx = _FakeSMTP.captured[0]
assert _ctx is not None, "starttls() was called with no context — that context does NOT verify"
assert _ctx.verify_mode == ssl.CERT_REQUIRED, _ctx.verify_mode
assert _ctx.check_hostname is True, _ctx.check_hostname

# --- a mistyped port is a status, not an escaped exception ---------------------------------------
# The first fix moved build_message inside the boundary and left `int(AEC_SMTP_PORT)` outside it —
# the same defect class, one line above the guard. Settings are stored as arbitrary strings
# (settings_store.set_value(db, k, str(v)), no numeric validation), so a typo in the Settings form
# raised ValueError straight through a function documented never to raise, aborting the delivery
# loop before its audit row exactly as the CR/LF recipient did.
_real_get = mailer.settings_store.get
mailer.settings_store.get = lambda k, d=None: {"AEC_SMTP_HOST": "h",
                                               "AEC_SMTP_PORT": "not-a-number"}.get(k, d)
try:
    assert mailer.send_email("a@example.com", "S", "b") == "error"
finally:
    mailer.settings_store.get = _real_get

# --- an attacker-influenced recipient cannot forge log lines (CWE-117) --------------------------
# `%s` writes a literal CR/LF into the stream, so a recipient can append whatever it likes as a
# separate, plausible-looking log record. `%r` escapes it.
import io as _io  # noqa: E402
import logging as _logging  # noqa: E402

_buf = _io.StringIO()
_h = _logging.StreamHandler(_buf)
_ml = _logging.getLogger("aec.mail")
_saved, _prop = _ml.handlers[:], _ml.propagate
_ml.handlers[:] = [_h]
_ml.propagate = False
try:
    mailer.send_email("v@x.test\r\nFAKE: forged log line", "S", "b")
finally:
    _ml.handlers[:], _ml.propagate = _saved, _prop
_out = _buf.getvalue()
assert "FAKE: forged log line" in _out, _out          # the value is still reported...
assert "\nFAKE: forged log line" not in _out, repr(_out)   # ...but never as its own line

# --- cleartext SMTP auth is allowed but never silent -------------------------------------------
# AEC_SMTP_TLS=0 is a documented deployment choice (a local or trusted-network relay), so this is a
# warning rather than a refusal — but sending a credential unprotected without telling anyone is
# what would be indefensible.
_FakeSMTP.captured.clear()
_buf2 = _io.StringIO()
_h2 = _logging.StreamHandler(_buf2)
_saved, _prop = _ml.handlers[:], _ml.propagate
_ml.handlers[:] = [_h2]
_ml.propagate = False
_real_smtp, _real_get = mailer.smtplib.SMTP, mailer.settings_store.get
mailer.smtplib.SMTP = _FakeSMTP
mailer.settings_store.get = lambda k, d=None: {"AEC_SMTP_HOST": "h", "AEC_SMTP_PORT": "587",
                                               "AEC_SMTP_TLS": "0", "AEC_SMTP_USER": "u",
                                               "AEC_SMTP_PASSWORD": "hunter2-secret"}.get(k, d)
try:
    assert mailer.send_email("a@example.com", "S", "b") == "sent"   # still allowed
finally:
    mailer.smtplib.SMTP, mailer.settings_store.get = _real_smtp, _real_get
    _ml.handlers[:], _ml.propagate = _saved, _prop
assert "cleartext" in _buf2.getvalue(), _buf2.getvalue()
assert "hunter2-secret" not in _buf2.getvalue(), "the password must never be logged"
assert not _FakeSMTP.captured, "starttls must not run when TLS is off"

print("test_artifact_deliver OK")
