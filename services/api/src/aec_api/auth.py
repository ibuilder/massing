"""Authentication: password hashing + signed bearer tokens (stdlib only — no extra deps).

Identity layer under the existing project RBAC: a token says *who* you are (replacing the
dev `X-User` header); per-project authorization still comes from `ProjectMember`. Passwords
are PBKDF2-HMAC-SHA256 salted hashes; tokens are HMAC-SHA256 signed `payload.sig` (JWT-ish,
but dependency-free)."""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time

_PBKDF2_ROUNDS = 200_000
# token signing secret — set AEC_AUTH_SECRET (or AEC_API_KEY) in prod; dev default is insecure
_DEV_SECRET = "dev-insecure-secret"
_SECRET = (os.environ.get("AEC_AUTH_SECRET") or os.environ.get("AEC_API_KEY")
           or _DEV_SECRET).encode()
_TOKEN_TTL = 7 * 24 * 3600   # 7 days


def secret_is_default() -> bool:
    """True when no signing secret is configured (tokens are signed with the public dev default,
    so they're forgeable). Production must set AEC_AUTH_SECRET; main.py refuses to start otherwise."""
    return _SECRET == _DEV_SECRET.encode()


def signing_key() -> bytes:
    """The HMAC key for signed download URLs (shares the auth secret; set AEC_AUTH_SECRET in prod)."""
    return _SECRET


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, _PBKDF2_ROUNDS)
    return f"pbkdf2_sha256${salt.hex()}${dk.hex()}"


# Deny-list of the most common passwords that survive the >=8-char length gate (lower-cased;
# leet/suffix variants collapse via the normalization below). Offline, tiny, no dependency —
# blocks the head of every breach corpus without a wordlist file. (threat-model gap G-5)
_COMMON_PASSWORDS = frozenset({
    "password", "password1", "password123", "passw0rd", "p@ssword", "p@ssw0rd",
    "12345678", "123456789", "1234567890", "123123123", "987654321", "11111111",
    "qwerty123", "qwertyuiop", "1q2w3e4r", "1qaz2wsx", "qazwsx123", "asdfghjkl",
    "iloveyou", "sunshine", "princess", "football", "baseball", "superman", "batman123",
    "trustno1", "letmein1", "welcome1", "welcome123", "admin123", "administrator",
    "changeme", "changeme1", "internet", "computer", "whatever", "monkey123",
    "dragon123", "master123", "shadow123", "michael1", "jennifer", "charlie1",
    "aa123456", "abc12345", "abcd1234", "password!", "password1!", "starwars",
})


def weak_password_reason(password: str, username: str = "") -> str | None:
    """Why a password (already >= 8 chars) is still rejected, or None if acceptable.
    Normalizes case and a trailing punctuation run so 'Password123!' matches 'password123'."""
    p = password.strip().lower()
    stripped = p.rstrip("!@#$%^&*.?")
    if p in _COMMON_PASSWORDS or stripped in _COMMON_PASSWORDS:
        return "password is too common"
    if len(set(p)) <= 2:
        return "password uses too few distinct characters"
    if username and p == username.strip().lower():
        return "password must not equal the username"
    return None


def verify_password(password: str, stored: str) -> bool:
    try:
        _algo, salt_hex, dk_hex = stored.split("$")
        dk = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt_hex), _PBKDF2_ROUNDS)
        return hmac.compare_digest(dk.hex(), dk_hex)
    except Exception:
        return False


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


_RESET_TTL = 3600   # password-reset tokens are short-lived (1 hour)


def create_token(sub: str, ttl: int = _TOKEN_TTL) -> str:
    # `iat` (issued-at) lets the server revoke sessions: a token is rejected when its iat predates
    # the account's token_epoch (bumped on password change / "sign out everywhere"). See rbac.
    now = int(time.time())
    payload = _b64(json.dumps({"sub": sub, "iat": now, "exp": now + ttl}).encode())
    sig = _b64(hmac.new(_SECRET, payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def verify_token_claims(token: str) -> dict | None:
    """Return the verified auth-token claims ({sub, iat, exp}) if the token is a well-signed,
    unexpired *auth* token, else None. Reset tokens (purpose='reset') are rejected so they can't
    be used as bearer tokens. Callers that need session-revocation must read `iat` from here."""
    try:
        payload_b64, sig_b64 = token.split(".")
        expected = _b64(hmac.new(_SECRET, payload_b64.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig_b64, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=="))
        if payload.get("exp", 0) < time.time():
            return None
        if payload.get("purpose") not in (None, "auth"):
            return None
        return payload
    except Exception:
        return None


def verify_token(token: str) -> str | None:
    """Return the subject (username) if the token is a well-signed, unexpired *auth* token.
    Does NOT apply session-revocation (no DB here) — the DB-side epoch check lives in rbac."""
    claims = verify_token_claims(token)
    return claims.get("sub") if claims else None


def _pw_fingerprint(pw_hash: str) -> str:
    """A short, secret-keyed fingerprint of the stored password hash. Embedding it in a reset
    token makes the token single-use: once the password changes, the hash (and fingerprint)
    change, so any outstanding reset token stops validating."""
    return _b64(hmac.new(_SECRET, b"reset:" + pw_hash.encode(), hashlib.sha256).digest())[:16]


def create_reset_token(sub: str, pw_hash: str, ttl: int = _RESET_TTL) -> str:
    payload = _b64(json.dumps({"sub": sub, "exp": int(time.time()) + ttl,
                               "purpose": "reset", "fp": _pw_fingerprint(pw_hash)}).encode())
    sig = _b64(hmac.new(_SECRET, payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


_MFA_TTL = 300   # the MFA login-challenge ticket is short-lived (5 min)


def create_mfa_token(sub: str, ttl: int = _MFA_TTL) -> str:
    """A short-lived 'you passed the password, now prove the second factor' ticket. It is NOT a
    bearer token (purpose='mfa' → rejected by verify_token) — only /auth/mfa/verify accepts it."""
    payload = _b64(json.dumps({"sub": sub, "exp": int(time.time()) + ttl, "purpose": "mfa"}).encode())
    sig = _b64(hmac.new(_SECRET, payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def verify_mfa_token(token: str) -> str | None:
    """Return the subject if `token` is a valid, unexpired MFA-challenge ticket, else None."""
    try:
        payload_b64, sig_b64 = token.split(".")
        expected = _b64(hmac.new(_SECRET, payload_b64.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig_b64, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=="))
        if payload.get("purpose") != "mfa" or payload.get("exp", 0) < time.time():
            return None
        return payload.get("sub")
    except Exception:
        return None


_STEPUP_TTL = 300   # a step-up assertion is short-lived (5 min)


def create_stepup_token(sub: str, act: str, pw_hash: str, ttl: int = _STEPUP_TTL) -> str:
    """A short-lived "a human just re-proved this password" assertion, scoped to ONE action.

    This exists because an ordinary bearer token cannot answer the question that matters for a
    professional seal. A seal is not an authorisation, it is a personal legal attestation that a
    named licensed human was in responsible charge of the work — something a stored credential
    cannot assert, since any process holding the token can replay it. An automation driving this API
    with a user's token would otherwise emit documents bearing that user's seal, and the resulting
    audit row would faithfully record a human act that never happened.

    Three properties make it an assertion about a person rather than a session:

    - `purpose="stepup"` → `verify_token_claims` refuses it as a bearer token, so it cannot be
      escalated into a session even though it is signed with the same key.
    - `act` scopes it to a single operation, so a step-up collected for one action cannot be spent
      on another.
    - `fp` binds it to the current password hash (same trick as `create_reset_token`), so changing
      the password — or "sign out everywhere" — invalidates every outstanding assertion.

    The TTL is deliberately short. This is not a convenience feature; a long-lived step-up is just a
    bearer token with extra steps.
    """
    payload = _b64(json.dumps({"sub": sub, "exp": int(time.time()) + ttl, "purpose": "stepup",
                               "act": act, "fp": _pw_fingerprint(pw_hash),
                               # Identifies THIS assertion so it can be spent exactly once. Without
                               # it the token is only time-bounded, and "a human re-proved this
                               # password recently" is a weaker claim than a per-document one.
                               "jti": secrets.token_urlsafe(12)}).encode())
    sig = _b64(hmac.new(_SECRET, payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def verify_stepup_claims(token: str, act: str, pw_hash: str) -> dict | None:
    """The verified step-up payload (`sub`, `jti`, …), or None.

    **The only step-up verifier.** A second one, "verify_stepup_token", returned just the subject and
    was removed in v0.3.973 with zero callers: identical signature checks, but a caller holding only
    `sub` **cannot spend the `jti`**, so the assertion it verified stayed replayable. Two verifiers
    where one silently drops replay protection is a footgun whether or not anyone has picked it up
    yet — and "it has no callers" is the reason to delete it, not a reason to leave it.

    Returns the whole claim set so the caller can spend the `jti` — which `rbac.consume_stepup` does,
    against the `stepup_spent` table.

    Kept separate rather than changing that function's return type: it is the shape every existing
    caller and test already depends on, and a silent widening is how a boolean check starts reading a
    truthy dict."""
    try:
        payload_b64, sig_b64 = token.split(".")
        expected = _b64(hmac.new(_SECRET, payload_b64.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig_b64, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=="))
        if payload.get("purpose") != "stepup" or payload.get("exp", 0) < time.time():
            return None
        if not hmac.compare_digest(str(payload.get("act") or ""), act):
            return None
        if not hmac.compare_digest(str(payload.get("fp") or ""), _pw_fingerprint(pw_hash)):
            return None
        if not payload.get("sub") or not payload.get("jti"):
            return None
        return payload
    except Exception:
        return None


_STATE_TTL = 600   # OAuth CSRF state is short-lived (10 min)


def create_oauth_state(provider: str) -> str:
    payload = _b64(json.dumps({"sub": provider, "exp": int(time.time()) + _STATE_TTL,
                               "purpose": "oauth"}).encode())
    sig = _b64(hmac.new(_SECRET, payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def seal_pkce(flow_id: str, state: str) -> str:
    """Seal a PKCE **flow id** for the round trip through the identity broker (CLOUD-SSO).

    **What is sealed is an opaque handle, not a credential.** `massing_cloud_auth.verifier_for`
    derives the actual `code_verifier` from this id *and* the server signing key, so the value the
    browser carries reveals nothing and permits nothing on its own. An earlier version sealed the
    verifier itself; see that function for why deriving it is strictly better than sealing it.

    **Neither may travel in `state`.** `state` is echoed by the broker through the user agent, so
    anything inside it is visible to whoever can observe the redirect — and an attacker holding both
    the authorization code and the verifier has exactly what PKCE exists to deny them. This sealed
    blob rides an HttpOnly, SameSite=Lax cookie on **our own** origin and is never sent to the
    broker; only the opaque `state` makes that trip. `state` is bound into the signature, so a seal
    cannot be replayed against a different authorization attempt.
    """
    payload = _b64(json.dumps({"v": flow_id, "st": state, "exp": int(time.time()) + _STATE_TTL,
                               "purpose": "pkce"}).encode())
    sig = _b64(hmac.new(_SECRET, payload.encode(), hashlib.sha256).digest())
    return f"{payload}.{sig}"


def open_pkce(sealed: str, state: str) -> str | None:
    """Return the flow id if `sealed` is a valid, unexpired seal bound to `state`, else None."""
    try:
        payload_b64, sig_b64 = sealed.split(".")
        expected = _b64(hmac.new(_SECRET, payload_b64.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig_b64, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=="))
        if payload.get("purpose") != "pkce" or payload.get("exp", 0) < time.time():
            return None
        # constant-time compare: `state` is attacker-supplied on the callback.
        if not hmac.compare_digest(str(payload.get("st") or ""), state):
            return None
        return payload.get("v")
    except Exception:
        return None


def verify_oauth_state(token: str) -> str | None:
    """Return the provider id if the state is a valid, unexpired oauth state, else None."""
    try:
        payload_b64, sig_b64 = token.split(".")
        expected = _b64(hmac.new(_SECRET, payload_b64.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig_b64, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=="))
        if payload.get("purpose") != "oauth" or payload.get("exp", 0) < time.time():
            return None
        return payload.get("sub")
    except Exception:
        return None


def token_subject(token: str) -> str | None:
    """The 'sub' claim WITHOUT verifying the signature — only to look up the account so its
    current password hash can be checked by verify_reset_token. Never trust this for auth."""
    try:
        return json.loads(base64.urlsafe_b64decode(token.split(".")[0] + "==")).get("sub")
    except Exception:
        return None


def verify_reset_token(token: str, pw_hash: str) -> str | None:
    """Return the subject if `token` is a valid, unexpired, single-use reset token for the
    account whose current password hash is `pw_hash`; else None."""
    try:
        payload_b64, sig_b64 = token.split(".")
        expected = _b64(hmac.new(_SECRET, payload_b64.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(sig_b64, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(payload_b64 + "=="))
        if payload.get("purpose") != "reset" or payload.get("exp", 0) < time.time():
            return None
        if not hmac.compare_digest(payload.get("fp", ""), _pw_fingerprint(pw_hash)):
            return None
        return payload.get("sub")
    except Exception:
        return None


def get_or_create_sso_user(db, username: str, make_user):
    """Find-or-create the local account for an SSO identity. Returns ``(user, created)``.

    **The seeding race, in the one place all three sign-in doors reach it.** OAuth
    (`routers/auth.py`), SAML (`routers/saml.py`) and the massing.cloud broker (`routers/cloud.py`)
    each auto-provision on first sign-in, and each did it the same unguarded way::

        u = db.get(User, email)
        if u is None:
            u = User(username=email, ...)
            db.add(u)

    `User.username` is the PRIMARY KEY, so two concurrent *first* sign-ins for one person — two
    tabs, two devices, a retried callback — both read `None`, both INSERT the same key, and the
    loser's `commit()` raises `IntegrityError`. The person who did nothing wrong gets a **500 on a
    legitimate login**, and a retry then succeeds because the winner's row now exists, which is
    what makes it easy to dismiss as a blip.

    **Seeding is the one moment no row-level mechanism can protect, because there is no row yet** —
    the same sentence `modules._next_ref` carries about its ref counter, and the same fix:
    INSERT inside a SAVEPOINT so the refusal stays local, then re-read and use the winner's row.
    `rbac.consume_stepup` is the third instance of the pattern in this codebase.

    **One helper rather than three copies, deliberately.** The defect this repository keeps finding
    in these three doors is *one rule, applied at some of them* — the `AEC_OAUTH_ALLOWED_DOMAINS`
    check held on four doors and was bypassed by the fifth (PR #339), and this race was present at
    all three. A fourth sign-in path should have to call this, not re-derive it.

    `make_user` is a callable rather than a set of fields because the three doors genuinely differ:
    the password-hash sentinel is per-provider, SAML sets `provisioned=True`, and the cloud door
    computes `role` and `tier` from the broker's claims.
    """
    from .models import User

    return get_or_create_by_pk(db, User, username, make_user)


def get_or_create_by_pk(db, model, pk, make_row):
    """Find-or-create `model` by primary key, surviving a lost seeding race. Returns ``(row, created)``.

    **The idiom, in one place, because this codebase keeps finding it applied to SOME of the sites.**
    `get_or_create_sso_user` was written to stop three sign-in doors re-deriving it — and then the
    massing.cloud callback, having called that helper for its `User`, seeded a `CloudIdentity` four
    lines later with the same unguarded read-decide-insert. Same function, same request, same race,
    one row apart. Extracting it is the only version of the fix that a fifth caller cannot get wrong.

    **Seeding is the one moment no row-level mechanism can protect, because there is no row yet.**
    INSERT inside a SAVEPOINT so the refusal stays local, then re-read and use the winner's row. The
    caller's other staged rows - the audit entry every sign-in door writes - survive, which they do
    not if the IntegrityError reaches the outer transaction and poisons the session.

    `make_row` is a callable rather than a field dict because callers genuinely differ: the
    password-hash sentinel is per-provider, SAML sets `provisioned=True`, and the cloud door
    computes `role` and `tier` from the broker's claims.
    """
    from sqlalchemy.exc import IntegrityError

    row = db.get(model, pk)
    if row is not None:
        return row, False
    try:
        with db.begin_nested():
            row = make_row()
            db.add(row)
            db.flush()
        return row, True
    except IntegrityError:
        # Another writer created it between our read and our insert. The refusal is the database
        # working; the bug was ever treating it as a crash. The savepoint kept it local, so the
        # session is still usable and the caller's other staged rows (the audit entry) survive.
        row = db.get(model, pk)
        if row is None:                     # pragma: no cover - not a seeding collision after all
            raise
        return row, False
