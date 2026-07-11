"""SAML 2.0 SP — the security-critical path is response verification, so this drives real signed
assertions (self-signed cert via `cryptography`, signed with `signxml`) through the ACS and asserts:
  * a correctly-signed, in-window, right-audience assertion logs the user in (303 + session cookie,
    account auto-provisioned);
  * every attack is rejected with 403: tampered payload (digest break), unsigned assertion,
    assertion signed by a DIFFERENT key than the pinned IdP cert, expired Conditions, wrong audience.
Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_saml.py"""
import base64
import os
from datetime import datetime, timedelta, timezone

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from lxml import etree
from signxml import XMLSigner

SP = "massing-test-sp"
ACS = "https://app.example.com/api/auth/saml/acs"
NS = {"saml": "urn:oasis:names:tc:SAML:2.0:assertion"}


def _make_cert():
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "test-idp")])
    now = datetime(2020, 1, 1, tzinfo=timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now).not_valid_after(datetime(2035, 1, 1, tzinfo=timezone.utc))
            .sign(key, hashes.SHA256()))
    key_pem = key.private_bytes(serialization.Encoding.PEM,
                                serialization.PrivateFormat.PKCS8,
                                serialization.NoEncryption()).decode()
    cert_pem = cert.public_bytes(serialization.Encoding.PEM).decode()
    return key_pem, cert_pem


def _iso(dt):
    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def build_response(sign_key_pem, sign_cert_pem, *, email, audience=SP, recipient=ACS,
                   not_before=None, not_on_or_after=None, sign=True):
    now = datetime.now(timezone.utc)
    nb = _iso(not_before or now - timedelta(minutes=1))
    na = _iso(not_on_or_after or now + timedelta(minutes=5))
    assertion_xml = (
        '<saml:Assertion xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" '
        'ID="_assert1" Version="2.0" IssueInstant="' + _iso(now) + '">'
        '<saml:Issuer>test-idp</saml:Issuer>'
        '<saml:Subject>'
        '<saml:NameID Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress">'
        + email + '</saml:NameID>'
        '<saml:SubjectConfirmation Method="urn:oasis:names:tc:SAML:2.0:cm:bearer">'
        '<saml:SubjectConfirmationData Recipient="' + recipient + '" NotOnOrAfter="' + na + '"/>'
        '</saml:SubjectConfirmation></saml:Subject>'
        '<saml:Conditions NotBefore="' + nb + '" NotOnOrAfter="' + na + '">'
        '<saml:AudienceRestriction><saml:Audience>' + audience + '</saml:Audience>'
        '</saml:AudienceRestriction></saml:Conditions>'
        '<saml:AuthnStatement AuthnInstant="' + _iso(now) + '">'
        '<saml:AuthnContext><saml:AuthnContextClassRef>'
        'urn:oasis:names:tc:SAML:2.0:ac:classes:PasswordProtectedTransport'
        '</saml:AuthnContextClassRef></saml:AuthnContext></saml:AuthnStatement>'
        '</saml:Assertion>'
    )
    assertion = etree.fromstring(assertion_xml.encode())
    if sign:
        assertion = XMLSigner(c14n_algorithm="http://www.w3.org/2001/10/xml-exc-c14n#").sign(
            assertion, key=sign_key_pem, cert=sign_cert_pem, reference_uri="_assert1",
            id_attribute="ID")
    resp = etree.fromstring(
        ('<samlp:Response xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
         'xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" ID="_resp1" Version="2.0" '
         'IssueInstant="' + _iso(now) + '">'
         '<saml:Issuer>test-idp</saml:Issuer>'
         '<samlp:Status><samlp:StatusCode '
         'Value="urn:oasis:names:tc:SAML:2.0:status:Success"/></samlp:Status>'
         '</samlp:Response>').encode())
    resp.append(assertion)
    return base64.b64encode(etree.tostring(resp)).decode()


IDP_KEY, IDP_CERT = _make_cert()
OTHER_KEY, OTHER_CERT = _make_cert()             # an attacker's key, not the pinned IdP cert

os.environ["DATABASE_URL"] = "sqlite:///./test_saml.db"
os.environ["STORAGE_DIR"] = "./test_storage_saml"
os.environ["AEC_SAML_IDP_ENTITY_ID"] = "test-idp"
os.environ["AEC_SAML_IDP_SSO_URL"] = "https://idp.example.com/sso"
os.environ["AEC_SAML_IDP_CERT"] = IDP_CERT
os.environ["AEC_SAML_SP_ENTITY_ID"] = SP
os.environ["AEC_SAML_ACS_URL"] = ACS
os.environ.pop("AEC_RBAC", None)
for _f in ("./test_saml.db",):
    if os.path.exists(_f):
        os.remove(_f)

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import saml  # noqa: E402
from aec_api.db import SessionLocal  # noqa: E402
from aec_api.main import app  # noqa: E402
from aec_api.models import User  # noqa: E402


def post(saml_response):
    # don't follow the 303 to the SPA root (it 404s under TestClient); we assert on the redirect itself
    return client.post("/auth/saml/acs", data={"SAMLResponse": saml_response}, follow_redirects=False)


with TestClient(app) as client:
    assert saml.is_enabled(), "SAML should be enabled with IdP entity/SSO/cert set"
    # metadata + login initiation are reachable
    assert client.get("/auth/saml/metadata").status_code == 200
    lg = client.get("/auth/saml/login", follow_redirects=False)
    assert lg.status_code == 307 and "SAMLRequest=" in lg.headers["location"], lg.headers
    assert client.get("/auth/providers").json().get("saml") is True

    # --- happy path: correctly signed, in-window, right audience -> session + auto-provision ------
    good = build_response(IDP_KEY, IDP_CERT, email="engineer@corp.com")
    r = post(good)
    assert r.status_code == 303, f"good assertion should log in: {r.status_code} {r.text[:200]}"
    assert "aec-token" in r.cookies or "aec-token" in r.headers.get("set-cookie", ""), r.headers
    with SessionLocal() as db:
        u = db.get(User, "engineer@corp.com")
        assert u and u.provisioned is True and u.email == "engineer@corp.com", u

    # --- attacks: every one must be a 403 --------------------------------------------------------
    # 1) tampered payload — swap the email after signing (digest break)
    tampered = base64.b64encode(
        base64.b64decode(good).replace(b"engineer@corp.com", b"attacker@corp.com")).decode()
    assert post(tampered).status_code == 403, "tampered assertion must be rejected"
    with SessionLocal() as db:
        assert db.get(User, "attacker@corp.com") is None, "tampered identity must never be provisioned"

    # 2) unsigned assertion
    unsigned = build_response(IDP_KEY, IDP_CERT, email="e2@corp.com", sign=False)
    assert post(unsigned).status_code == 403, "unsigned assertion must be rejected"

    # 3) signed by a different key than the pinned IdP cert
    wrong_key = build_response(OTHER_KEY, OTHER_CERT, email="e3@corp.com")
    assert post(wrong_key).status_code == 403, "assertion signed by an untrusted key must be rejected"

    # 4) expired Conditions (valid signature, stale window)
    past = datetime.now(timezone.utc) - timedelta(hours=1)
    expired = build_response(IDP_KEY, IDP_CERT, email="e4@corp.com",
                             not_before=past - timedelta(minutes=5), not_on_or_after=past)
    assert post(expired).status_code == 403, "expired assertion must be rejected"

    # 5) wrong audience
    wrong_aud = build_response(IDP_KEY, IDP_CERT, email="e5@corp.com", audience="some-other-sp")
    assert post(wrong_aud).status_code == 403, "wrong-audience assertion must be rejected"

    # none of the rejected identities were provisioned
    with SessionLocal() as db:
        for bad in ("e2@corp.com", "e3@corp.com", "e4@corp.com", "e5@corp.com"):
            assert db.get(User, bad) is None, f"{bad} must not exist"

print("SAML OK - signed assertion logs in + auto-provisions; tamper/unsigned/wrong-key/expired/wrong-audience all 403")
