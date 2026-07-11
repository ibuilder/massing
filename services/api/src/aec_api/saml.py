"""SAML 2.0 Service Provider (SP) — lets an enterprise IdP (Okta, Azure AD/Entra, OneLogin,
ADFS, Shibboleth) sign users in via SAML in addition to the OAuth providers in oauth.py.

Security model (the assertion is an authentication bearer, so verification is the whole game):
  * The IdP's signing certificate is **pinned** from config — we verify against that cert only,
    never a cert embedded in the message's KeyInfo (which an attacker controls).
  * Identity is read **only from the cryptographically-verified subtree** (`signed_xml`) that
    signxml returns, never from a re-parse of the raw document — this defeats XML Signature
    Wrapping (XSW), the classic SAML break.
  * The signed Assertion's Conditions are enforced: validity window (NotBefore / NotOnOrAfter with
    a small clock-skew allowance) and AudienceRestriction == our SP entityID; the
    SubjectConfirmationData Recipient, when present, must equal our ACS URL.
  * signxml (which uses defused parsing) does the canonicalization + signature + digest checks.

Enabled only when the IdP entityID, SSO URL, and signing cert are all configured; otherwise the
routes report "not configured" (like oauth.is_enabled).
"""
from __future__ import annotations

import base64
import zlib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from . import settings_store

_NS = {
    "samlp": "urn:oasis:names:tc:SAML:2.0:protocol",
    "saml": "urn:oasis:names:tc:SAML:2.0:assertion",
    "md": "urn:oasis:names:tc:SAML:2.0:metadata",
    "ds": "http://www.w3.org/2000/09/xmldsig#",
}
_CLOCK_SKEW = timedelta(minutes=3)          # tolerate small IdP/SP clock drift on Conditions windows


class SamlError(Exception):
    """Any failure to accept a SAML response (bad signature, expired, wrong audience, malformed)."""


@dataclass
class SamlIdentity:
    name_id: str
    email: str | None
    attributes: dict[str, list[str]]


# --- config -----------------------------------------------------------------
def _get(key: str) -> str | None:
    v = settings_store.get(key)
    return v.strip() if v and v.strip() else None


def idp_entity_id() -> str | None:
    return _get("AEC_SAML_IDP_ENTITY_ID")


def idp_sso_url() -> str | None:
    return _get("AEC_SAML_IDP_SSO_URL")


def idp_cert_pem() -> str | None:
    """The IdP signing cert as PEM. Accepts either a full PEM block or a bare base64 body
    (what IdP metadata / admin consoles usually paste)."""
    raw = _get("AEC_SAML_IDP_CERT")
    if not raw:
        return None
    if "BEGIN CERTIFICATE" in raw:
        return raw
    body = "".join(raw.split())
    lines = "\n".join(body[i:i + 64] for i in range(0, len(body), 64))
    return f"-----BEGIN CERTIFICATE-----\n{lines}\n-----END CERTIFICATE-----\n"


def sp_entity_id() -> str:
    return _get("AEC_SAML_SP_ENTITY_ID") or "massing"


def acs_url() -> str | None:
    """Our Assertion Consumer Service URL. Configurable; a router can pass its computed default."""
    return _get("AEC_SAML_ACS_URL")


def is_enabled() -> bool:
    return bool(idp_entity_id() and idp_sso_url() and idp_cert_pem())


# --- SP → IdP: AuthnRequest (HTTP-Redirect binding) -------------------------
def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def build_authn_request(acs: str, request_id: str, issue_instant: datetime) -> str:
    """A minimal, unsigned AuthnRequest XML (SP-signing is optional and most IdPs accept unsigned)."""
    return (
        '<samlp:AuthnRequest xmlns:samlp="urn:oasis:names:tc:SAML:2.0:protocol" '
        'xmlns:saml="urn:oasis:names:tc:SAML:2.0:assertion" '
        f'ID="{request_id}" Version="2.0" IssueInstant="{_iso(issue_instant)}" '
        'ProtocolBinding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST" '
        f'AssertionConsumerServiceURL="{acs}" Destination="{idp_sso_url()}">'
        f'<saml:Issuer>{sp_entity_id()}</saml:Issuer>'
        '<samlp:NameIDPolicy Format="urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress" '
        'AllowCreate="true"/>'
        '</samlp:AuthnRequest>'
    )


def redirect_url(acs: str, request_id: str, issue_instant: datetime, relay_state: str = "") -> str:
    """The IdP SSO URL with the deflated+base64 SAMLRequest (HTTP-Redirect binding, DEFLATE encoding)."""
    xml = build_authn_request(acs, request_id, issue_instant).encode()
    deflated = zlib.compress(xml)[2:-4]                 # raw DEFLATE (strip zlib header + adler32)
    params = {"SAMLRequest": base64.b64encode(deflated).decode()}
    if relay_state:
        params["RelayState"] = relay_state
    sep = "&" if "?" in (idp_sso_url() or "") else "?"
    return f"{idp_sso_url()}{sep}{urlencode(params)}"


def sp_metadata(acs: str) -> str:
    """SP metadata XML for handing to the IdP admin (entityID + the ACS endpoint / POST binding)."""
    return (
        '<?xml version="1.0"?>'
        '<md:EntityDescriptor xmlns:md="urn:oasis:names:tc:SAML:2.0:metadata" '
        f'entityID="{sp_entity_id()}">'
        '<md:SPSSODescriptor AuthnRequestsSigned="false" WantAssertionsSigned="true" '
        'protocolSupportEnumeration="urn:oasis:names:tc:SAML:2.0:protocol">'
        '<md:NameIDFormat>urn:oasis:names:tc:SAML:1.1:nameid-format:emailAddress</md:NameIDFormat>'
        '<md:AssertionConsumerService '
        'Binding="urn:oasis:names:tc:SAML:2.0:bindings:HTTP-POST" '
        f'Location="{acs}" index="0" isDefault="true"/>'
        '</md:SPSSODescriptor></md:EntityDescriptor>'
    )


# --- IdP → SP: verify the SAMLResponse --------------------------------------
def _parse_dt(s: str) -> datetime:
    s = s.strip()
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    dt = datetime.fromisoformat(s)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


def _text(el) -> str | None:
    return el.text.strip() if el is not None and el.text else None


def _find_signed_assertion(signed_xml):
    """From a verified subtree, return the Assertion element (the subtree itself if it *is* the
    Assertion, else the Assertion inside a signed Response). Only the verified tree is ever read."""
    tag = signed_xml.tag
    if tag == "{urn:oasis:names:tc:SAML:2.0:assertion}Assertion":
        return signed_xml
    assertions = signed_xml.findall(".//saml:Assertion", _NS)
    if len(assertions) == 1:
        return assertions[0]
    return None


def verify_response(saml_response_b64: str, acs: str) -> SamlIdentity:
    """Verify a base64 SAMLResponse and return the authenticated identity, or raise SamlError.

    `acs` is our ACS URL (used to check the assertion's Recipient). Verification pins the configured
    IdP cert and reads identity only from the signed subtree (XSW-safe)."""
    if not is_enabled():
        raise SamlError("SAML is not configured")
    try:
        raw = base64.b64decode(saml_response_b64, validate=False)
    except Exception as e:
        raise SamlError("SAMLResponse is not valid base64") from e

    from signxml import SignatureConfiguration, XMLVerifier

    cert = idp_cert_pem()
    try:
        # Pin the IdP cert; SAML references use the `ID` attribute. signxml raises on any failure
        # (bad digest, bad signature, cert mismatch, schema violation).
        results = XMLVerifier().verify(
            raw, x509_cert=cert, id_attribute="ID",
            expect_config=SignatureConfiguration(require_x509=True))
    except Exception as e:                       # noqa: BLE001 — any verify failure = reject
        raise SamlError(f"SAML signature verification failed: {e}") from e

    if not isinstance(results, list):
        results = [results]
    assertion = None
    for r in results:
        assertion = _find_signed_assertion(r.signed_xml)
        if assertion is not None:
            break
    if assertion is None:
        raise SamlError("no signed SAML assertion found (the assertion itself must be signed)")

    _check_conditions(assertion, acs)
    return _identity(assertion)


def _check_conditions(assertion, acs: str) -> None:
    now = _now()
    conditions = assertion.find("saml:Conditions", _NS)
    if conditions is not None:
        nb = conditions.get("NotBefore")
        na = conditions.get("NotOnOrAfter")
        if nb and now + _CLOCK_SKEW < _parse_dt(nb):
            raise SamlError("assertion not yet valid (NotBefore)")
        if na and now - _CLOCK_SKEW >= _parse_dt(na):
            raise SamlError("assertion has expired (NotOnOrAfter)")
        audiences = [_text(a) for a in conditions.findall(".//saml:Audience", _NS)]
        audiences = [a for a in audiences if a]
        if audiences and sp_entity_id() not in audiences:
            raise SamlError(f"assertion audience {audiences} does not include SP {sp_entity_id()!r}")

    # SubjectConfirmationData: Recipient must match our ACS (when present), and its own expiry holds.
    for scd in assertion.findall(".//saml:SubjectConfirmationData", _NS):
        recipient = scd.get("Recipient")
        if recipient and acs and recipient.rstrip("/") != acs.rstrip("/"):
            raise SamlError("SubjectConfirmation Recipient does not match the ACS URL")
        na = scd.get("NotOnOrAfter")
        if na and now - _CLOCK_SKEW >= _parse_dt(na):
            raise SamlError("SubjectConfirmation has expired")


def _identity(assertion) -> SamlIdentity:
    nameid_el = assertion.find("saml:Subject/saml:NameID", _NS)
    name_id = _text(nameid_el)
    if not name_id:
        raise SamlError("assertion has no Subject NameID")

    attrs: dict[str, list[str]] = {}
    for attr in assertion.findall(".//saml:AttributeStatement/saml:Attribute", _NS):
        key = attr.get("Name") or attr.get("FriendlyName")
        if not key:
            continue
        vals = [_text(v) for v in attr.findall("saml:AttributeValue", _NS)]
        attrs[key] = [v for v in vals if v]

    email = None
    fmt = nameid_el.get("Format", "") if nameid_el is not None else ""
    if "emailAddress" in fmt or (name_id and "@" in name_id):
        email = name_id
    for k in ("email", "mail",
              "http://schemas.xmlsoap.org/ws/2005/05/identity/claims/emailaddress",
              "urn:oid:0.9.2342.19200300.100.1.3"):
        if not email and attrs.get(k):
            email = attrs[k][0]
    return SamlIdentity(name_id=name_id, email=email, attributes=attrs)
