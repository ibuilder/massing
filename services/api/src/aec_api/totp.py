"""TOTP (RFC 6238) + HOTP (RFC 4226) multi-factor auth — stdlib only (hmac/hashlib/base64), no deps.

A user enrolls a shared secret (shown as an otpauth:// URI / QR in any authenticator app); at login
they present a 6-digit time-based code. `verify` accepts a small ±window of 30s steps for clock skew.
Recovery codes are one-time backup credentials, stored only as salted hashes.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
import struct
import time

_DIGITS = 6
_STEP = 30            # seconds per TOTP step (RFC 6238 default)
_ALPH = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567"   # RFC 4648 base32 alphabet


def random_secret(nbytes: int = 20) -> str:
    """A fresh base32 TOTP secret (default 160-bit, the RFC-recommended SHA-1 key length)."""
    return base64.b32encode(secrets.token_bytes(nbytes)).decode().rstrip("=")


def _b32decode(secret: str) -> bytes:
    s = secret.strip().replace(" ", "").upper()
    pad = "=" * ((8 - len(s) % 8) % 8)
    return base64.b32decode(s + pad, casefold=True)


def hotp(secret_b32: str, counter: int, digits: int = _DIGITS) -> str:
    """RFC 4226 HMAC-SHA1 one-time password for an explicit counter."""
    mac = hmac.new(_b32decode(secret_b32), struct.pack(">Q", counter), hashlib.sha1).digest()
    off = mac[-1] & 0x0F
    code = (struct.unpack(">I", mac[off:off + 4])[0] & 0x7FFFFFFF) % (10 ** digits)
    return str(code).zfill(digits)


def totp(secret_b32: str, when: float | None = None, step: int = _STEP, digits: int = _DIGITS) -> str:
    """The current time-based OTP for `secret_b32`."""
    when = time.time() if when is None else when
    return hotp(secret_b32, int(when // step), digits)


def verify(secret_b32: str, code: str, window: int = 1, when: float | None = None) -> bool:
    """True if `code` matches the TOTP within ±`window` steps (tolerates modest clock skew).
    Constant-time compare per candidate; any malformed input is a clean False."""
    try:
        code = (code or "").strip().replace(" ", "")
        if not code.isdigit():
            return False
        when = time.time() if when is None else when
        base = int(when // _STEP)
        for delta in range(-window, window + 1):
            counter = base + delta
            if counter < 0:                       # no counter before the epoch (unsigned pack)
                continue
            if hmac.compare_digest(hotp(secret_b32, counter), code.zfill(_DIGITS)):
                return True
        return False
    except Exception:
        return False


def provisioning_uri(secret_b32: str, account: str, issuer: str = "Massing") -> str:
    """otpauth:// URI for authenticator apps / QR codes (RFC / Key-Uri-Format)."""
    from urllib.parse import quote
    label = quote(f"{issuer}:{account}")
    return (f"otpauth://totp/{label}?secret={secret_b32}&issuer={quote(issuer)}"
            f"&algorithm=SHA1&digits={_DIGITS}&period={_STEP}")


# --- recovery (backup) codes --------------------------------------------------
def make_recovery_codes(n: int = 10) -> list[str]:
    """`n` human-readable one-time backup codes (shown once at enrollment)."""
    return ["-".join(secrets.token_hex(2) for _ in range(2)) for _ in range(n)]


def hash_recovery(code: str) -> str:
    """Salted SHA-256 of a recovery code (only the hash is stored)."""
    salt = secrets.token_bytes(8)
    dk = hashlib.sha256(salt + code.strip().lower().encode()).digest()
    return f"{salt.hex()}${dk.hex()}"


def check_recovery(code: str, stored: str) -> bool:
    try:
        salt_hex, dk_hex = stored.split("$")
        dk = hashlib.sha256(bytes.fromhex(salt_hex) + code.strip().lower().encode()).digest()
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False
