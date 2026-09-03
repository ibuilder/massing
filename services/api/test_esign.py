"""PDF e-signatures — PAdES digital signing + status gating + the digital-sign endpoint.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_esign.py"""
import io
import os

os.environ["DATABASE_URL"] = "sqlite:///./test_esign.db"
os.environ["STORAGE_DIR"] = "./test_storage_esign"
os.environ.pop("AEC_RBAC", None)
os.environ.pop("ESIGN_PROVIDER", None)
for f in ("./test_esign.db",):
    if os.path.exists(f):
        os.remove(f)

import pypdf  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from aec_api import esign, esign_bridge  # noqa: E402
from aec_api.main import app  # noqa: E402


def _sig_fields(pdf: bytes):
    f = pypdf.PdfReader(io.BytesIO(pdf)).get_fields() or {}
    return [k for k, v in f.items() if getattr(v, "get", lambda *_: None)("/FT") == "/Sig"]


# --- unit: PAdES signing + status -------------------------------------------
from reportlab.lib.pagesizes import letter  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

_b = io.BytesIO(); _c = canvas.Canvas(_b, pagesize=letter); _c.drawString(72, 720, "Agreement"); _c.save()
plain = _b.getvalue()
signed = esign.digitally_sign(plain, reason="Executed", name="Pat GC")
assert signed[:4] == b"%PDF" and len(signed) > len(plain), "signed PDF should be valid + larger"
assert _sig_fields(signed) == ["AECSignature"], "expected an embedded PAdES signature field"
assert not _sig_fields(plain), "plain PDF has no signature"
fp = esign.signer_fingerprint()
assert len(fp) == 32 and fp == esign.signer_fingerprint(), "fingerprint stable"
assert esign.status()["available"] is True and esign.status()["kind"] == "self-signed"
assert esign_bridge.is_enabled() is False and esign_bridge.status()["enabled"] is False

# --- integration: endpoints --------------------------------------------------
with TestClient(app) as c:
    st = c.get("/esign/status").json()
    assert st["pades"]["available"] is True and st["bridge"]["enabled"] is False, st

    pid = c.post("/projects", json={"name": "Sign Tower"}).json()["id"]
    sc = c.post(f"/projects/{pid}/modules/subcontract",
                json={"data": {"vendor": "ACME Concrete", "trade": "Concrete", "value": 1_800_000}}).json()["id"]

    r = c.post(f"/projects/{pid}/contracts/subcontract/{sc}/digital-sign", json={})
    assert r.status_code == 200, r.text[:200]
    out = r.json()
    assert out["signed"] is True and len(out["fingerprint"]) == 32 and out["kind"] == "self-signed", out

    rec = c.get(f"/projects/{pid}/modules/subcontract/{sc}").json()
    atts = rec.get("attachments", [])
    assert any(a.get("filename", "").startswith("agreement-signed-") for a in atts), atts
    ds = (rec.get("data") or {}).get("digital_signatures") or []
    assert len(ds) == 1 and ds[0]["fingerprint"] == out["fingerprint"] and ds[0]["doc"] == "agreement", ds

    # --- 3rd-party bridge: gating (off) -------------------------------------
    r = c.post(f"/projects/{pid}/contracts/subcontract/{sc}/send-for-signature",
               json={"signers": [{"email": "owner@acme.test", "name": "Owner"}]})
    assert r.status_code == 409, ("bridge should be gated off", r.status_code, r.text[:200])

    # --- 3rd-party bridge: DocuSeal flow (transport monkeypatched) -----------
    os.environ["ESIGN_PROVIDER"] = "docuseal"
    os.environ["ESIGN_API_KEY"] = "test-token"
    os.environ["ESIGN_BASE_URL"] = "https://docuseal.local"
    _orig_post = esign_bridge.post_json
    calls = []

    def fake_post(url, headers, payload):
        calls.append(url)
        if url.endswith("/api/templates/pdf"):
            assert headers.get("X-Auth-Token") == "test-token", headers
            assert payload["documents"][0]["file"], "PDF must be base64-embedded"
            return {"id": 4242, "name": payload["name"]}
        if url.endswith("/api/submissions"):
            assert payload["template_id"] == 4242, payload
            return [{"submission_id": 99, "email": s["email"], "role": s["role"], "slug": "abc123"}
                    for s in payload["submitters"]]
        raise AssertionError(f"unexpected url {url}")

    esign_bridge.post_json = fake_post
    try:
        assert esign_bridge.is_enabled() is True and esign_bridge.status()["implemented"] is True
        r = c.post(f"/projects/{pid}/contracts/subcontract/{sc}/send-for-signature",
                   json={"signers": [{"email": "owner@acme.test", "name": "Owner", "party": "Owner"}]})
        assert r.status_code == 200, r.text[:300]
        out = r.json()
        assert out["provider"] == "DocuSeal (self-hosted)" and out["submission_id"] == 99, out
        assert out["signers"][0]["url"] == "https://docuseal.local/s/abc123", out
        assert calls == ["https://docuseal.local/api/templates/pdf", "https://docuseal.local/api/submissions"], calls
        rec = c.get(f"/projects/{pid}/modules/subcontract/{sc}").json()
        assert (rec.get("data") or {}).get("esign_submission", {}).get("submission_id") == 99, rec.get("data")
        w = c.post("/esign/webhook", json={"event_type": "form.completed",
                                           "data": {"submission_id": 99, "email": "owner@acme.test"}})
        assert w.status_code == 200 and w.json()["completed"] is True and w.json()["submission_id"] == 99, w.text
    finally:
        esign_bridge.post_json = _orig_post
        for k in ("ESIGN_PROVIDER", "ESIGN_API_KEY", "ESIGN_BASE_URL"):
            os.environ.pop(k, None)

# --- SEC: the provider webhook is an anonymous, internet-facing write into the AUDIT table --------
# It is anonymous by necessity (a provider holds no user credential) and carries no authority — it
# cannot mark a contract signed. The exposure was the audit row it writes per request, with
# caller-chosen strings of unbounded length: flooding it buries the real trail, which is what an
# audit log exists to prevent. So it now verifies an HMAC over the RAW body when a secret is set,
# throttles, caps the payload, and records WHICH posture produced each row.
import hashlib  # noqa: E402
import hmac  # noqa: E402
import json as _json  # noqa: E402

from aec_api.db import SessionLocal  # noqa: E402
from aec_api.models import AuditLog  # noqa: E402

_PAY = {"event_type": "form.completed",
        "data": {"submission_id": "S" * 5000, "email": "e" * 5000}}   # deliberately huge
_RAW = _json.dumps(_PAY).encode()
_JSON_HDR = {"content-type": "application/json"}

os.environ.pop("AEC_ESIGN_WEBHOOK_SECRET", None)
with TestClient(app) as c:
    # No secret configured: stays open on purpose. Silently dropping callbacks would break an operator
    # relying on this today; the bounding and throttling apply regardless.
    r = c.post("/esign/webhook", content=_RAW, headers=_JSON_HDR)
    assert r.status_code == 200, r.text
    # NB: AuditLog.id is a UUID string, so `order_by(id.desc())` sorts lexicographically and returns
    # an arbitrary row while reading exactly like "the newest one". Assert over the SET instead.
    _db = SessionLocal()
    _rows = _db.query(AuditLog).filter(AuditLog.action == "contract.esign_webhook").all()
    _db.close()
    # Select by this block's own marker payload. An earlier test in this file posts a legitimate
    # webhook, so "the only row" and "the newest row" are both wrong ways to find ours.
    _mine = [r.detail for r in _rows if str((r.detail or {}).get("submission_id", "")).startswith("SSS")]
    assert len(_mine) == 1, f"expected 1 marker row, got {len(_mine)} of {len(_rows)} webhook rows"
    _d = _mine[0]
    # The SHAPE was always fixed to four keys by parse_completion; the SIZE was not. 5000 -> 200.
    assert len(_d["submission_id"]) == 200, len(_d["submission_id"])
    assert len(_d["signer"]) == 200, len(_d["signer"])
    # An unverified row must never be readable as a verified one.
    assert _d["signature_verified"] is False, _d
    assert c.post("/esign/webhook", content=b'{"a":"' + b"x" * 200000 + b'"}',
                  headers=_JSON_HDR).status_code == 413
    assert c.post("/esign/webhook", content=b"not json", headers=_JSON_HDR).status_code == 400
    # A JSON array parses fine but is not a mapping — parse_completion would have raised on .get().
    assert c.post("/esign/webhook", content=b"[1,2]", headers=_JSON_HDR).status_code == 400

os.environ["AEC_ESIGN_WEBHOOK_SECRET"] = "provider-shared-secret"
try:
    with TestClient(app) as c:
        assert c.post("/esign/webhook", content=_RAW, headers=_JSON_HDR).status_code == 403
        assert c.post("/esign/webhook", content=_RAW,
                      headers={**_JSON_HDR, "X-Signature": "deadbeef"}).status_code == 403
        _good = hmac.new(b"provider-shared-secret", _RAW, hashlib.sha256).hexdigest()
        r = c.post("/esign/webhook", content=_RAW,
                   headers={**_JSON_HDR, "X-Signature": "sha256=" + _good})
        assert r.status_code == 200, r.text
        # The signature must cover the BODY, not merely exist: replaying a good signature against a
        # different payload is the whole attack a naive "is a signature present?" check permits.
        assert c.post("/esign/webhook", content=b'{"event_type":"x"}',
                      headers={**_JSON_HDR, "X-Signature": _good}).status_code == 403
        _db = SessionLocal()
        _flags = [r.detail.get("signature_verified") for r in
                  _db.query(AuditLog).filter(AuditLog.action == "contract.esign_webhook").all()
                  if str((r.detail or {}).get("submission_id", "")).startswith("SSS")]
        _db.close()
        # Exactly one signed call succeeded, so exactly one row may claim verification — and the
        # unverified row from the no-secret block must still be there saying so.
        assert _flags.count(True) == 1, _flags
        assert _flags.count(False) == 1, _flags
finally:
    os.environ.pop("AEC_ESIGN_WEBHOOK_SECRET", None)

print("ESIGN OK - PAdES signature embedded + detected; stable cert fingerprint; status gating "
      "(self-signed available, 3rd-party bridge off); digital-sign attaches signed PDF + records signer; "
      "DocuSeal bridge: gated off->409, send routes template+submission, stores submission, webhook parsed; "
      "webhook hardening: HMAC over the raw body when AEC_ESIGN_WEBHOOK_SECRET is set (a good signature "
      "replayed onto a different payload is refused), 413 oversized, 400 non-object, audit strings capped "
      "at 200 chars and each row stamped signature_verified")
