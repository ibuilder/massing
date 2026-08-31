"""Asset rights — a signed, deterministic **release manifest** for a project release.

This is the chain-independent core of the asset-rights work: it answers *"is this release
authentic, and is it unaltered?"* with no blockchain, no wallet, and no new dependency. A token, if
one is ever minted, binds to the `content_hash` computed here — so this layer is useful on its own
and is a prerequisite either way. See `docs/internal/asset-rights-nft-design.md` for the study that
produced this scope, including the four things in the incoming brief that did not match this
repository.

**Two hashes, because they answer different questions.**

- `content_hash` is the **identity** of a release: what the release *is*. It covers the model
  digest, the non-derived files, and the licence terms. It deliberately excludes every volatile
  value — timestamps, release ids, signatures, and derived artifacts — so the *same semantic
  release computes the same hash on any machine, in any build, at any time*. That property is the
  entire value of the thing; without it every comparison is a false positive.
- `manifest_hash` covers the whole manifest *except* `verification`, and is what the signature is
  over. It changes when the timestamp or release id changes, which is correct: it identifies this
  *statement about* the release, not the release.

**Derived artifacts are excluded from identity, on purpose.** `geometry/model.frag` is documented in
`docs/mass-format.md` as derived from the IFC and regenerable from it. Hashing it into release
identity would mean a tessellator upgrade changes the release hash while the building is untouched —
exactly the false positive `services/data/src/aec_data/model_digest.py` was built to avoid. Derived
files still travel, in `derived`, where they are recorded but do not contribute to identity.

**The model digest is cited, not reimplemented.** R23-DIGEST already computes a deterministic,
Merkle-shaped hash of an IFC model and already has a test suite that makes the determinism claim
falsifiable. This module takes that value as an input.

**Canonicalisation.** The brief asks for RFC 8785 (JCS). This uses the canonical form already in use
across this repository — sorted keys, `(",", ":")` separators, `ensure_ascii=False`, encoded UTF-8 —
which agrees with JCS on everything except number formatting, where JCS mandates the ECMAScript
algorithm and Python's float repr does not always match it. Rather than depend on that agreement,
**floats are refused outright**: `canonical_bytes` raises on any float anywhere in the object. Every
value in a manifest is a string or an integer, so the divergence cannot arise, and a future JCS
implementation would produce byte-identical output for every manifest this module can build. A
determinism claim that rests on "our floats probably format the same" is not a claim worth making.

**Keys.** Signing uses Ed25519 — asymmetric, so a third party can verify a release with only the
public key. An HMAC over the existing auth secret was the cheaper option and is the wrong one: it
proves authenticity only to whoever already holds the secret, which is precisely not what provenance
means. The private key is read from the environment and is never written to a `.mass`, a manifest, a
log line, or the database. `services/api/test_no_secrets.py` gates the container side of that.
"""
from __future__ import annotations

import base64
import json
import os
import uuid
from datetime import datetime, timezone
from typing import Any

MANIFEST_VERSION = 1

#: URN namespace for the stable, container-carried asset identity.
ASSET_URN_PREFIX = "urn:massing:asset:"
RELEASE_URN_PREFIX = "urn:massing:release:"

#: Env var holding the base64 Ed25519 private seed (32 bytes). Absent = signing unavailable.
SIGNING_KEY_ENV = "AEC_ASSET_SIGNING_KEY"
#: Env var naming the issuer, e.g. "did:web:massing.build".
ISSUER_ENV = "AEC_ASSET_ISSUER"
#: Master feature flag. The whole capability is OFF unless this is explicitly truthy.
ENABLED_ENV = "AEC_ASSET_RIGHTS_ENABLED"

_TRUTHY = {"1", "true", "yes", "on"}


def enabled() -> bool:
    """Whether the asset-rights capability is switched on. Default **off**, per the brief."""
    return (os.environ.get(ENABLED_ENV) or "").strip().lower() in _TRUTHY


def new_asset_id() -> str:
    """Mint a stable asset identity. This identifies the *design lineage*, not a database row."""
    return uuid.uuid4().hex


def asset_urn(asset_id: str) -> str:
    return f"{ASSET_URN_PREFIX}{asset_id}"


def release_urn(release_id: str) -> str:
    return f"{RELEASE_URN_PREFIX}{release_id}"


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# --- canonicalisation ---------------------------------------------------------
class NonCanonicalValue(ValueError):
    """Raised for a value whose canonical encoding is not unambiguous (a float, or a non-JSON type).

    This is a *guard*, not a limitation to work around. If a manifest ever needs a measured
    quantity, it carries it as a pre-rounded string — the same discipline `model_digest.py` applies
    when it rounds before hashing."""


def _reject_floats(obj: Any, path: str = "$") -> None:
    """Walk an object and refuse anything whose canonical form is implementation-dependent.

    `bool` is checked before `int` because `bool` is a subclass of `int` in Python and would
    otherwise pass silently as a number."""
    if obj is None or isinstance(obj, (str, bool, int)):
        return
    if isinstance(obj, float):
        raise NonCanonicalValue(
            f"float at {path}: manifests carry no floats, because the canonical encoding of a "
            "float is not agreed between this implementation and RFC 8785. Pass a pre-rounded "
            "string instead.")
    if isinstance(obj, dict):
        for k, v in obj.items():
            if not isinstance(k, str):
                raise NonCanonicalValue(f"non-string key at {path}: {k!r}")
            _reject_floats(v, f"{path}.{k}")
        return
    if isinstance(obj, (list, tuple)):
        for i, v in enumerate(obj):
            _reject_floats(v, f"{path}[{i}]")
        return
    raise NonCanonicalValue(f"unencodable type at {path}: {type(obj).__name__}")


def canonical_bytes(obj: Any) -> bytes:
    """The canonical UTF-8 encoding of a JSON-able object: sorted keys, no insignificant whitespace.

    Raises `NonCanonicalValue` for any float or non-JSON type — see the module docstring."""
    _reject_floats(obj)
    return json.dumps(obj, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=False).encode("utf-8")


def sha256_hex(data: bytes) -> str:
    import hashlib
    return hashlib.sha256(data).hexdigest()


def hash_object(obj: Any) -> str:
    """`sha256:<lowercase-hex>` over the canonical encoding of `obj`."""
    return f"sha256:{sha256_hex(canonical_bytes(obj))}"


# --- manifest -----------------------------------------------------------------
def build_content(*, model_digest_hash: str | None, files: list[dict],
                  licence: dict | None, mass_format: str, mass_version: int) -> dict:
    """The identity half of a manifest: everything that says what this release **is**.

    `files` entries are `{logical_path, media_type, sha256, bytes}`. They are sorted by
    `logical_path` so that the order a caller happened to walk a directory in cannot change the
    hash. `bytes` is an int; `sha256` is bare lowercase hex.
    """
    norm: list[dict] = []
    for f in files:
        norm.append({
            "logical_path": str(f["logical_path"]),
            "media_type": str(f.get("media_type") or "application/octet-stream"),
            "sha256": str(f["sha256"]).lower(),
            "bytes": int(f["bytes"]),
        })
    norm.sort(key=lambda e: e["logical_path"])
    seen = [e["logical_path"] for e in norm]
    if len(set(seen)) != len(seen):
        # Two entries for one path make the manifest ambiguous about which bytes it attests to.
        raise ValueError("duplicate logical_path in release files")
    return {
        "model_digest": model_digest_hash,
        "files": norm,
        "licence": licence,
        "schema": {"mass_format": mass_format, "mass_version": int(mass_version)},
    }


def build_manifest(*, asset_id: str, content: dict, release_id: str | None = None,
                   created_at: str | None = None, derived: list[dict] | None = None,
                   issuer: str | None = None) -> dict:
    """Assemble a release manifest and compute both hashes.

    `derived` records regenerable artifacts (e.g. `model.frag`). They are listed but excluded from
    `content_hash`, so regenerating one does not change release identity."""
    dnorm: list[dict] = []
    for d in (derived or []):
        dnorm.append({
            "logical_path": str(d["logical_path"]),
            "media_type": str(d.get("media_type") or "application/octet-stream"),
            "sha256": str(d["sha256"]).lower(),
            "bytes": int(d["bytes"]),
            "regenerable_from": str(d.get("regenerable_from") or ""),
        })
    dnorm.sort(key=lambda e: e["logical_path"])

    manifest = {
        "manifest_version": MANIFEST_VERSION,
        "asset_id": asset_urn(asset_id),
        "release_id": release_urn(release_id or uuid.uuid4().hex),
        "created_at": created_at or _now_iso(),
        "issuer": issuer or os.environ.get(ISSUER_ENV) or "",
        "content": content,
        # Recorded, deliberately outside identity. See the module docstring.
        "derived": dnorm,
        "content_hash": hash_object(content),
    }
    manifest["manifest_hash"] = hash_object(
        {k: v for k, v in manifest.items() if k != "manifest_hash"})
    return manifest


def verify_content_hash(manifest: dict) -> bool:
    """Recompute `content_hash` from the manifest's own content and compare."""
    return manifest.get("content_hash") == hash_object(manifest.get("content"))


def verify_manifest_hash(manifest: dict) -> bool:
    """Recompute `manifest_hash`, ignoring `manifest_hash` and `verification`."""
    subject = {k: v for k, v in manifest.items()
               if k not in ("manifest_hash", "verification")}
    return manifest.get("manifest_hash") == hash_object(subject)


# --- signing ------------------------------------------------------------------
def _b64d(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def signing_available() -> bool:
    return bool((os.environ.get(SIGNING_KEY_ENV) or "").strip())


def _private_key():
    from cryptography.hazmat.primitives.asymmetric import ed25519
    raw = (os.environ.get(SIGNING_KEY_ENV) or "").strip()
    if not raw:
        raise RuntimeError(
            f"no signing key: set {SIGNING_KEY_ENV} to a base64url Ed25519 seed (32 bytes). "
            "Releases can still be hashed and verified for integrity without one; they just "
            "cannot be signed.")
    seed = _b64d(raw)
    if len(seed) != 32:
        raise RuntimeError(f"{SIGNING_KEY_ENV} must decode to exactly 32 bytes, got {len(seed)}")
    return ed25519.Ed25519PrivateKey.from_private_bytes(seed)


def generate_seed() -> str:
    """A fresh base64url Ed25519 seed, for operators setting up signing. Never stored by this code."""
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import ed25519
    key = ed25519.Ed25519PrivateKey.generate()
    return _b64e(key.private_bytes(
        encoding=serialization.Encoding.Raw,
        format=serialization.PrivateFormat.Raw,
        encryption_algorithm=serialization.NoEncryption()))


def public_key_b64(seed_b64: str | None = None) -> str:
    """The base64url Ed25519 **public** key — safe to publish; this is what verifiers need."""
    from cryptography.hazmat.primitives import serialization
    key = _private_key() if seed_b64 is None else _key_from_seed(seed_b64)
    return _b64e(key.public_key().public_bytes(
        encoding=serialization.Encoding.Raw, format=serialization.PublicFormat.Raw))


def _key_from_seed(seed_b64: str):
    from cryptography.hazmat.primitives.asymmetric import ed25519
    return ed25519.Ed25519PrivateKey.from_private_bytes(_b64d(seed_b64))


def sign_manifest(manifest: dict, *, seed_b64: str | None = None) -> dict:
    """Return `manifest` with a `verification` block. The signature is over `manifest_hash`.

    Signing does not mutate the input."""
    key = _private_key() if seed_b64 is None else _key_from_seed(seed_b64)
    subject = manifest.get("manifest_hash")
    if not subject:
        raise ValueError("manifest has no manifest_hash to sign")
    sig = key.sign(subject.encode("utf-8"))
    out = dict(manifest)
    out["verification"] = {
        "algorithm": "ed25519",
        "signed_by": manifest.get("issuer") or "",
        "public_key": public_key_b64(seed_b64),
        "signature": _b64e(sig),
    }
    return out


def verify_signature(manifest: dict, *, public_key: str | None = None) -> bool:
    """Verify the signature over `manifest_hash`.

    `public_key` may be supplied by the caller — a verifier who already trusts a key should pass it,
    rather than trusting the one carried in the document, which an attacker who rewrote the manifest
    would simply have replaced too. Falling back to the embedded key proves internal consistency
    only, which is why `verify_release` reports the two separately."""
    from cryptography.exceptions import InvalidSignature
    from cryptography.hazmat.primitives.asymmetric import ed25519
    v = manifest.get("verification") or {}
    if v.get("algorithm") != "ed25519":
        return False
    key_b64 = public_key or v.get("public_key")
    sig_b64 = v.get("signature")
    subject = manifest.get("manifest_hash")
    if not (key_b64 and sig_b64 and subject):
        return False
    try:
        pub = ed25519.Ed25519PublicKey.from_public_bytes(_b64d(key_b64))
        pub.verify(_b64d(sig_b64), subject.encode("utf-8"))
        return True
    except (InvalidSignature, ValueError):
        return False


def verify_release(manifest: dict, *, public_key: str | None = None) -> dict:
    """Full verification, reported as separate findings rather than one boolean.

    A single true/false would collapse "the content was altered" into "the signature is missing",
    and those call for different responses. `trusted_key` is the load-bearing one: it is False when
    the signature only verified against the key the document carried, which proves the document is
    self-consistent and proves nothing about who wrote it."""
    content_ok = verify_content_hash(manifest)
    manifest_ok = verify_manifest_hash(manifest)
    signed = bool(manifest.get("verification"))
    sig_ok = verify_signature(manifest, public_key=public_key) if signed else False
    return {
        "content_hash_ok": content_ok,
        "manifest_hash_ok": manifest_ok,
        "signed": signed,
        "signature_ok": sig_ok,
        "trusted_key": bool(signed and sig_ok and public_key),
        "ok": bool(content_ok and manifest_ok and (sig_ok if signed else True)),
    }


def _main(argv: list[str] | None = None) -> int:
    """Operator entry point: mint a signing key, or show the public half of the configured one.

    `generate_seed` existed with no caller, which meant the **signed** path was unreachable from a
    clean deployment except by generating an Ed25519 seed out of band — the capability shipped
    complete and could not be turned on. This is the missing step, and it is deliberately a command
    rather than a route: minting a private key is an operator action at the machine, and putting it
    behind an HTTP endpoint would make "who may create a signing identity" a question about request
    authorisation. There is no gate here worth trusting more than shell access to the host.

    Prints the seed to stdout and everything else to stderr, so `--generate > key` captures only the
    secret and a human still sees what to do with it.
    """
    import sys
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--generate" in argv:
        seed = generate_seed()
        print(f"# a fresh Ed25519 signing seed. Set it as {SIGNING_KEY_ENV} and keep it secret;\n"
              f"# anyone holding it can sign releases as this deployment. It is not stored here.\n"
              f"# The matching PUBLIC key, which verifiers need and which is safe to publish, is\n"
              f"#   {public_key_b64(seed)}\n"
              f"# and is served on GET /asset-rights/status once the seed is set.",
              file=sys.stderr)
        print(seed)
        return 0
    if "--public-key" in argv:
        if not signing_available():
            print(f"no signing key configured: set {SIGNING_KEY_ENV} (see --generate). Releases are "
                  f"still hashed and tamper-evident without one; they carry no attribution.",
                  file=sys.stderr)
            return 1
        print(public_key_b64())
        return 0
    print(f"usage: python -m aec_api.asset_rights [--generate | --public-key]\n"
          f"  --generate    print a fresh Ed25519 seed for {SIGNING_KEY_ENV} (stdout = the secret)\n"
          f"  --public-key  print the public key of the configured seed, for verifiers\n"
          f"\nsigning is {'AVAILABLE' if signing_available() else 'unavailable'} in this environment.",
          file=sys.stderr)
    return 2


if __name__ == "__main__":
    import sys
    sys.exit(_main())
