"""PDF digital signatures (PAdES) via pyHanko — certificate-based, tamper-evident signing of our
generated documents (Bluebeam's model: PKCS#12 / Adobe-style signatures).

A signer is loaded from a configured PKCS#12 (ESIGN_P12 + ESIGN_P12_PASS) for production, or a
self-signed signer is generated once and cached under the storage dir for offline/self-hosted use
(an *advanced* signature — tamper-evident + self-validating, but not chained to a public CA / not a
*qualified* signature; see docs/esign-options.md). Electronic (typed) signatures remain the simple
path; this adds the cryptographic option.
"""
from __future__ import annotations

import io
import os
from pathlib import Path
from typing import Any

_P12_PASS = b"aec-bim-platform"
_signer_cache: Any = None


def _keys_dir() -> Path:
    d = Path(os.environ.get("STORAGE_DIR", ".")) / "keys"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _generate_self_signed_p12() -> bytes:
    """Create a self-signed RSA signer cert + key, serialized as PKCS#12 (cached on disk)."""
    import datetime
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.hazmat.primitives.serialization import BestAvailableEncryption, pkcs12
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Massing Signer"),
                      x509.NameAttribute(NameOID.ORGANIZATION_NAME, "Massing")])
    now = datetime.datetime.now(datetime.timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(key.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - datetime.timedelta(days=1))
            .not_valid_after(now + datetime.timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .sign(key, hashes.SHA256()))
    return pkcs12.serialize_key_and_certificates(b"aec-signer", key, cert, None,
                                                 BestAvailableEncryption(_P12_PASS))


def _p12_path() -> tuple[str, bytes]:
    """(pkcs12 file path, passphrase) — configured signer if present, else the cached self-signed one."""
    configured = os.environ.get("ESIGN_P12")
    if configured and Path(configured).exists():
        return configured, os.environ.get("ESIGN_P12_PASS", "").encode()
    path = _keys_dir() / "signer.p12"
    if not path.exists():
        path.write_bytes(_generate_self_signed_p12())
    return str(path), _P12_PASS


def is_configured() -> bool:
    """Digital signing is always available (self-signed fallback); True iff a *configured* cert is set."""
    p = os.environ.get("ESIGN_P12")
    return bool(p and Path(p).exists())


def status() -> dict[str, Any]:
    return {
        "available": True,
        "configured_cert": is_configured(),
        "kind": "configured" if is_configured() else "self-signed",
        "note": ("PAdES digital signatures are applied with your configured certificate."
                 if is_configured() else
                 "PAdES digital signatures use a self-signed platform certificate (tamper-evident; "
                 "set ESIGN_P12 to a PKCS#12 to sign with your own / a CA-issued certificate)."),
    }


def _signer():
    global _signer_cache
    if _signer_cache is None:
        from pyhanko.sign import signers
        path, passphrase = _p12_path()
        _signer_cache = signers.SimpleSigner.load_pkcs12(path, passphrase=passphrase or None)
    return _signer_cache


def digitally_sign(pdf_bytes: bytes, reason: str = "Approved", name: str = "") -> bytes:
    """Apply an invisible PAdES digital signature to a PDF, returning the signed bytes."""
    from pyhanko.pdf_utils.incremental_writer import IncrementalPdfFileWriter
    from pyhanko.sign import fields, signers

    w = IncrementalPdfFileWriter(io.BytesIO(pdf_bytes))
    meta = signers.PdfSignatureMetadata(
        field_name="AECSignature",
        reason=reason,
        location="Massing",
        name=name or None,
        subfilter=fields.SigSeedSubFilter.PADES,
    )
    out = io.BytesIO()
    signers.sign_pdf(w, meta, signer=_signer(), output=out)
    return out.getvalue()


def signer_fingerprint() -> str:
    """SHA-256 fingerprint of the signing certificate (recorded on the record for the audit trail)."""
    import hashlib
    cert = _signer().signing_cert
    der = cert.dump() if hasattr(cert, "dump") else bytes(cert)
    return hashlib.sha256(der).hexdigest()[:32]
