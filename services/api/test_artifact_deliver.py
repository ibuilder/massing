"""R24-REPORTS-BY-MOMENT — "shared, not just downloaded": mail a finished job's artifact.

The entry's remainder reads "scheduled and shared, not just downloaded", and the two halves have
DIFFERENT blockers. Its own wording says this "still wants a delivery surface and SMTP" — both of
which already ship: `mailer.py` sends real mail and `POST .../notifications/digest` is a working
assemble-then-send surface. What was actually missing was smaller and more specific: the mailer had
no way to carry a FILE. That is what this covers.

The SCHEDULED half is deliberately not here: it needs a recurring-trigger record and a runner, and
this tree has no scheduler of any kind, so picking one is a deployment decision.

Run: PYTHONPATH=src ./.venv/bin/python test_artifact_deliver.py"""
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_artifact_deliver.db"
os.environ["STORAGE_DIR"] = "./test_storage_artifact_deliver"
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

    # a job in ANOTHER project is not reachable through this project's path.
    pid2 = c.post("/projects", json={"name": "Other"}).json()["id"]
    assert c.post(f"/projects/{pid2}/jobs/job-done/deliver",
                  json={"to": ["a@example.com"]}).status_code == 404

print("test_artifact_deliver OK")
