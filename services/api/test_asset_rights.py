"""ASSET-RIGHTS — the release manifest claims to be deterministic, to exclude volatile and derived
data from identity, and to be signed with a key a third party can check. Each of those is a claim,
so each is made falsifiable here.

Run: PYTHONPATH=src ./.venv/Scripts/python.exe test_asset_rights.py

The determinism tests are modelled on `test_model_digest.py`, for the same reason it gives: anything
that leaks into an identity hash without being part of the release — a timestamp, an id, a
signature, iteration order, a regenerated tessellation — turns every later comparison into a false
positive, and each of those fails silently.

The signing tests exist because "signed" is the word that gets misread. An Ed25519 signature that
verifies against the public key *carried in the same document* proves the document is internally
consistent and proves nothing about who wrote it — an attacker who rewrote the manifest would have
replaced that key too. `verify_release` reports that case as `trusted_key: False`, and the test below
pins the distinction rather than asserting a single boolean.
"""
import os
import sys

os.environ["DATABASE_URL"] = "sqlite:///./asset_rights_test.db"
os.environ["STORAGE_DIR"] = "./test_storage_asset_rights"
os.environ.pop("AEC_RBAC", None)
for _f in ("./asset_rights_test.db",):
    if os.path.exists(_f):
        os.remove(_f)

sys.path.insert(0, "src")

from aec_api import asset_rights as ar  # noqa: E402

FAILED: list[str] = []

#: Every secret this file mints. `check()` scrubs these from anything it prints.
#:
#: This is structural on purpose. `check()` takes a free-form `detail` and prints it on failure, so
#: whether a private key reaches the log depends on which local every future call site happens to
#: pass — and the failing path is exactly the one nobody exercises before committing. On a PUBLIC
#: repository a CI log is public, and a workflow log outlives the run. Registering the secret once,
#: where it is minted, makes the guarantee independent of call-site discipline.
#:
#: Added after CodeQL flagged the `print` below as clear-text logging of sensitive data. No call site
#: actually passed a key, so the alert over-approximated — but the shape it objected to was real:
#: nothing prevented it, and "no current caller does that" is a property of today's code.
SECRETS: list[str] = []


def _scrub(text: str) -> str:
    """Replace any registered secret with a placeholder. Substring, not equality — a secret can be
    embedded in a larger repr (a manifest dict, a request body) rather than passed on its own."""
    for s in SECRETS:
        if s:
            text = text.replace(s, "<redacted-secret>")
    return text


def check(label, ok, detail=""):
    line = f"{'PASS' if ok else 'FAIL'}  {label}"
    if detail and not ok:
        line += " — " + str(detail)
    print(_scrub(line))
    if not ok:
        FAILED.append(label)


def content(*, files=None, digest="sha256:aaa", licence=None):
    return ar.build_content(
        model_digest_hash=digest,
        files=files if files is not None else [
            {"logical_path": "exports/model.ifc", "media_type": "application/x-step",
             "sha256": "AB12", "bytes": 10},
            {"logical_path": "exports/model.ifcjson", "media_type": "application/json",
             "sha256": "cd34", "bytes": 20},
        ],
        licence=licence if licence is not None else {
            "profile": "project-delivery-v1", "terms_hash": "sha256:beef"},
        mass_format="massing.project", mass_version=2)


# --- canonicalisation ---------------------------------------------------------
check("same content hashes identically (two separate constructions)",
      ar.hash_object(content()) == ar.hash_object(content()))

# Key insertion order must not matter: a dict built in a different order is the same object.
a = {"b": 1, "a": {"y": "2", "x": "1"}}
b = {"a": {"x": "1", "y": "2"}, "b": 1}
check("key order does not change the hash", ar.hash_object(a) == ar.hash_object(b))

# File order must not matter — build_content sorts by logical_path.
f1 = [{"logical_path": "exports/a.ifc", "media_type": "m", "sha256": "11", "bytes": 1},
      {"logical_path": "exports/b.ifc", "media_type": "m", "sha256": "22", "bytes": 2}]
check("file order does not change the hash",
      ar.hash_object(content(files=f1)) == ar.hash_object(content(files=list(reversed(f1)))))

check("sha256 values are normalised to lowercase",
      all(e["sha256"] == e["sha256"].lower() for e in content()["files"]))

# Floats are refused rather than silently encoded, because their canonical form is not agreed
# between this implementation and RFC 8785. This is the guard that lets the determinism claim stand.
try:
    ar.canonical_bytes({"x": 1.5})
    check("a float is refused", False, "no exception raised")
except ar.NonCanonicalValue:
    check("a float is refused", True)

try:
    ar.canonical_bytes({"ok": 1, "nested": [{"deep": 2.0}]})
    check("a nested float is refused", False, "no exception raised")
except ar.NonCanonicalValue:
    check("a nested float is refused", True)

# bool is a subclass of int in Python; it must survive rather than be mistaken for a number to reject.
check("bool is accepted (and is not treated as a float)",
      ar.canonical_bytes({"t": True}) == b'{"t":true}')

check("non-ascii is encoded as UTF-8, not escaped",
      ar.canonical_bytes({"k": "café"}) == '{"k":"café"}'.encode())

# --- what identity does and does not include ----------------------------------
base = ar.build_manifest(asset_id="A1", content=content(), release_id="R1",
                         created_at="2026-01-01T00:00:00Z", issuer="did:web:example")

# The whole point of ②/④: volatile facts about the ATTESTATION must not move the identity of the
# RELEASE. Each of these changes the manifest and must leave content_hash alone.
other_time = ar.build_manifest(asset_id="A1", content=content(), release_id="R1",
                               created_at="2099-12-31T23:59:59Z", issuer="did:web:example")
check("a different created_at does not change content_hash",
      base["content_hash"] == other_time["content_hash"])
check("a different created_at DOES change manifest_hash",
      base["manifest_hash"] != other_time["manifest_hash"])

other_rel = ar.build_manifest(asset_id="A1", content=content(), release_id="R2",
                              created_at="2026-01-01T00:00:00Z", issuer="did:web:example")
check("a different release_id does not change content_hash",
      base["content_hash"] == other_rel["content_hash"])

# ④ — a regenerable artifact is recorded but must not enter identity. A tessellator upgrade changes
# these bytes without the building changing; if that moved the release hash, every re-convert would
# read as a new release.
d1 = ar.build_manifest(asset_id="A1", content=content(), release_id="R1",
                       created_at="2026-01-01T00:00:00Z",
                       derived=[{"logical_path": "geometry/model.frag", "media_type": "application/octet-stream",
                                 "sha256": "ff01", "bytes": 99, "regenerable_from": "exports/model.ifc"}])
d2 = ar.build_manifest(asset_id="A1", content=content(), release_id="R1",
                       created_at="2026-01-01T00:00:00Z",
                       derived=[{"logical_path": "geometry/model.frag", "media_type": "application/octet-stream",
                                 "sha256": "ff02", "bytes": 98, "regenerable_from": "exports/model.ifc"}])
check("a changed DERIVED artifact does not change content_hash",
      d1["content_hash"] == d2["content_hash"])
check("a changed derived artifact IS still recorded (it moves manifest_hash)",
      d1["manifest_hash"] != d2["manifest_hash"])

# The other direction — the refusal tests above pass on a hash that never changes at all, so each
# needs its twin proving the hash DOES move when the release really differs.
changed_file = ar.hash_object(content(files=[
    {"logical_path": "exports/model.ifc", "media_type": "application/x-step",
     "sha256": "ffff", "bytes": 10},
    {"logical_path": "exports/model.ifcjson", "media_type": "application/json",
     "sha256": "cd34", "bytes": 20}]))
check("changed file bytes DO change content_hash", changed_file != base["content_hash"])

check("changed file LENGTH changes content_hash",
      ar.hash_object(content(files=[
          {"logical_path": "exports/model.ifc", "media_type": "application/x-step",
           "sha256": "AB12", "bytes": 11},
          {"logical_path": "exports/model.ifcjson", "media_type": "application/json",
           "sha256": "cd34", "bytes": 20}])) != base["content_hash"])

check("changed licence terms DO change content_hash",
      ar.hash_object(content(licence={"profile": "viewer-v1", "terms_hash": "sha256:0000"}))
      != base["content_hash"])

check("a changed model digest DOES change content_hash",
      ar.hash_object(content(digest="sha256:zzz")) != base["content_hash"])

# A manifest that attests to two different sets of bytes for one path is ambiguous about which it
# means, so it is refused at construction rather than hashed into an authoritative-looking value.
try:
    content(files=[{"logical_path": "x.ifc", "media_type": "m", "sha256": "11", "bytes": 1},
                   {"logical_path": "x.ifc", "media_type": "m", "sha256": "22", "bytes": 2}])
    check("duplicate logical_path is refused", False, "no exception raised")
except ValueError:
    check("duplicate logical_path is refused", True)

check("self-verification passes on an untouched manifest",
      ar.verify_content_hash(base) and ar.verify_manifest_hash(base))

# --- tamper detection ---------------------------------------------------------
tampered = dict(base)
tampered["content"] = content(files=[
    {"logical_path": "exports/model.ifc", "media_type": "application/x-step",
     "sha256": "dead", "bytes": 10}])
check("swapped content is detected by content_hash", not ar.verify_content_hash(tampered))

moved = dict(base)
moved["created_at"] = "2030-01-01T00:00:00Z"
check("edited created_at is detected by manifest_hash", not ar.verify_manifest_hash(moved))

# --- signing ------------------------------------------------------------------
seed = ar.generate_seed()
other_seed = ar.generate_seed()
SECRETS.extend((seed, other_seed))          # registered where minted, not where printed
check("a generated seed is 32 bytes", len(ar._b64d(seed)) == 32)
check("two generated seeds differ", seed != other_seed)

signed = ar.sign_manifest(base, seed_b64=seed)
check("signing does not mutate the input", "verification" not in base)
check("signature verifies with the embedded key", ar.verify_signature(signed))
check("signature verifies against the correct explicit key",
      ar.verify_signature(signed, public_key=ar.public_key_b64(seed)))
check("signature FAILS against a different key",
      not ar.verify_signature(signed, public_key=ar.public_key_b64(other_seed)))

# The attack this guards: rewrite the manifest, re-sign with your own key, replace the embedded
# public key. Self-consistent, and worthless. `trusted_key` is the field that says so.
forged = ar.sign_manifest(
    ar.build_manifest(asset_id="A1", content=content(files=[
        {"logical_path": "exports/model.ifc", "media_type": "application/x-step",
         "sha256": "bad0", "bytes": 10}]), release_id="R1",
        created_at="2026-01-01T00:00:00Z", issuer="did:web:example"),
    seed_b64=other_seed)
check("a forged manifest is self-consistent (which is why embedded-key checks are not enough)",
      ar.verify_signature(forged))
check("a forged manifest fails against the TRUSTED key",
      not ar.verify_signature(forged, public_key=ar.public_key_b64(seed)))

rep_untrusted = ar.verify_release(signed)
check("verify_release reports trusted_key False without an explicit key",
      rep_untrusted["signature_ok"] and not rep_untrusted["trusted_key"], rep_untrusted)
rep_trusted = ar.verify_release(signed, public_key=ar.public_key_b64(seed))
check("verify_release reports trusted_key True with the right key",
      rep_trusted["trusted_key"] and rep_trusted["ok"], rep_trusted)
rep_forged = ar.verify_release(forged, public_key=ar.public_key_b64(seed))
check("verify_release rejects the forgery against the trusted key",
      not rep_forged["signature_ok"] and not rep_forged["ok"], rep_forged)

# Tampering after signing must break the signature, not merely the hash.
after = dict(signed)
after["manifest_hash"] = "sha256:" + "0" * 64
check("editing manifest_hash after signing breaks the signature",
      not ar.verify_signature(after, public_key=ar.public_key_b64(seed)))

check("an unsigned manifest is not reported as signed",
      ar.verify_release(base)["signed"] is False)
check("an unsigned but intact manifest still reports ok (integrity without attribution)",
      ar.verify_release(base)["ok"] is True)

# --- feature flag -------------------------------------------------------------
os.environ.pop(ar.ENABLED_ENV, None)
check("the capability is OFF by default", ar.enabled() is False)
os.environ[ar.ENABLED_ENV] = "true"
check("the capability turns on when the flag is set", ar.enabled() is True)
os.environ.pop(ar.ENABLED_ENV, None)

# The signing key must never be readable from a manifest.
blob = ar.canonical_bytes(signed).decode("utf-8")
check("the private seed never appears in a signed manifest", seed not in blob)

# The redaction above is itself a claim, so it is asserted rather than trusted. Both directions:
# a registered secret must vanish even when embedded in a larger string, and ordinary detail must
# survive untouched — a scrubber that ate everything would pass the first half alone.
check("a registered secret is scrubbed from printed detail",
      seed not in _scrub(f"manifest={{'seed': '{seed}'}}")
      and "<redacted-secret>" in _scrub(f"seed={seed}"))
check("scrubbing leaves ordinary detail intact",
      _scrub("content_hash mismatch: sha256:abc != sha256:def")
      == "content_hash mismatch: sha256:abc != sha256:def")


# --- the option belongs to whoever creates the .mass file ---------------------
# Everything below is end-to-end through the real export/import path. The unit tests above prove the
# manifest is internally sound; these prove it describes the archive it actually ships inside, and
# that a container created WITHOUT the option is untouched.
import io as _io  # noqa: E402
import json as _json  # noqa: E402
import zipfile as _zip  # noqa: E402

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import storage  # noqa: E402
from aec_api.main import app  # noqa: E402

BEARER = lambda t: {"Authorization": f"Bearer {t}"}  # noqa: E731


def entries_of(blob):
    z = _zip.ZipFile(_io.BytesIO(blob))
    return z, _json.loads(z.read("manifest.json"))


with TestClient(app) as c:
    c.post("/auth/register", json={"username": "admin", "password": "supersecret"})
    tok = c.post("/auth/login", json={"username": "admin", "password": "supersecret"}).json()["token"]
    pid = c.post("/projects", json={"name": "Rights Source"}).json()["id"]
    # A derived artifact must exist for the derived-exclusion claim to be exercised end-to-end
    # rather than only in theory.
    storage.put(f"{pid}/model.frag", b"FRAGMENT-BYTES-derived-and-regenerable")

    # (1) DEFAULT: nothing asked for -> the container is exactly what it always was.
    os.environ.pop(ar.ENABLED_ENV, None)
    plain = c.get(f"/projects/{pid}/bundle", headers=BEARER(tok)).content
    zp, mp = entries_of(plain)
    check("default export writes no asset_rights.json", "asset_rights.json" not in zp.namelist())
    check("default export reports has_asset_rights False",
          mp.get("has_asset_rights") is False, mp.get("has_asset_rights"))
    check("default export mints NO asset_id (no write on the read path)",
          _json.loads(zp.read("project.json")).get("asset_id") in (None, ""),
          _json.loads(zp.read("project.json")).get("asset_id"))

    # (2) Asked for, but the operator has the capability switched off -> inert, not half-built.
    off = c.get(f"/projects/{pid}/bundle?asset_rights=true", headers=BEARER(tok)).content
    zo, mo = entries_of(off)
    check("opt-in is inert while the capability is disabled",
          "asset_rights.json" not in zo.namelist() and mo.get("has_asset_rights") is False)
    check("a disabled capability still mints no asset_id",
          _json.loads(zo.read("project.json")).get("asset_id") in (None, ""))

    # (2b) Capability ENABLED, but this export did not ask for it. This is the case that actually
    # pins "it is an option": with the flag off, every no-op assertion above passes even if the
    # opt-in were ignored entirely, because the flag alone would suppress it.
    os.environ[ar.ENABLED_ENV] = "true"
    notasked = c.get(f"/projects/{pid}/bundle", headers=BEARER(tok)).content
    zn, mn = entries_of(notasked)
    check("enabled but NOT asked for -> still no asset_rights.json",
          "asset_rights.json" not in zn.namelist() and mn.get("has_asset_rights") is False)
    check("enabled but NOT asked for -> still no asset_id",
          _json.loads(zn.read("project.json")).get("asset_id") in (None, ""),
          _json.loads(zn.read("project.json")).get("asset_id"))

    # (3) Enabled + asked for -> sealed.
    os.environ[ar.ENABLED_ENV] = "true"
    os.environ.pop(ar.SIGNING_KEY_ENV, None)          # no key yet: hashed but unsigned
    sealed = c.get(f"/projects/{pid}/bundle?asset_rights=true", headers=BEARER(tok)).content
    zs, ms = entries_of(sealed)
    check("opting in writes asset_rights.json", "asset_rights.json" in zs.namelist())
    check("the container manifest says has_asset_rights", ms.get("has_asset_rights") is True)
    check("asset_rights.json is listed in the inventory",
          "asset_rights.json" in {e["path"] for e in ms["entries"]})
    rel = _json.loads(zs.read("asset_rights.json"))
    asset = _json.loads(zs.read("project.json")).get("asset_id")
    check("opting in mints the asset_id", bool(asset))
    check("the manifest carries the asset as a URN",
          rel["asset_id"] == ar.asset_urn(asset), rel["asset_id"])
    check("an unsigned sealed container still self-verifies",
          ar.verify_release(rel)["ok"], ar.verify_release(rel))
    check("unsigned means unsigned, not silently signed", ar.verify_release(rel)["signed"] is False)

    # THE END-TO-END CLAIM: every hash in the manifest matches the bytes actually in the archive.
    listed = {f["logical_path"]: f for f in rel["content"]["files"]}
    recomputed_ok = all(
        ar.sha256_hex(zs.read(path)) == f["sha256"] and len(zs.read(path)) == f["bytes"]
        for path, f in listed.items())
    check("every listed hash matches the archive's actual bytes", recomputed_ok, sorted(listed))
    check("the payload it attests to is non-empty", len(listed) >= 1, sorted(listed))

    # The derived tile is recorded, and is NOT part of identity.
    dpaths = {d["logical_path"] for d in rel["derived"]}
    check("the derived tile is recorded under `derived`", "geometry/model.frag" in dpaths, dpaths)
    check("the derived tile is NOT in the identity payload",
          "geometry/model.frag" not in listed, sorted(listed))
    check("the derived tile's hash is real too",
          any(d["sha256"] == ar.sha256_hex(zs.read("geometry/model.frag")) for d in rel["derived"]))

    # Wrapper files describe the container and are regenerated per export; they are deliberately
    # outside the attestation, and saying so is the point — an unstated boundary is the defect.
    check("manifest.json is not claimed as attested payload", "manifest.json" not in listed)
    check("README.txt is not claimed as attested payload", "README.txt" not in listed)

    # TAMPER: rewrite one attested payload entry; the manifest no longer describes the archive.
    victim = sorted(listed)[0]
    tbuf = _io.BytesIO()
    with _zip.ZipFile(tbuf, "w") as out:
        for it in zs.infolist():
            out.writestr(it.filename,
                         b"TAMPERED" if it.filename == victim else zs.read(it.filename))
    zt = _zip.ZipFile(_io.BytesIO(tbuf.getvalue()))
    rt = _json.loads(zt.read("asset_rights.json"))
    rt_listed = {f["logical_path"]: f for f in rt["content"]["files"]}
    check("a tampered payload entry is detected against the manifest",
          ar.sha256_hex(zt.read(victim)) != rt_listed[victim]["sha256"], victim)

    # (4) With a signing key configured, the same export is signed and verifies under the issuer key.
    key = ar.generate_seed()
    SECRETS.append(key)
    os.environ[ar.SIGNING_KEY_ENV] = key
    os.environ[ar.ISSUER_ENV] = "did:web:massing.build"
    signed_blob = c.get(f"/projects/{pid}/bundle?asset_rights=true", headers=BEARER(tok)).content
    zsg, _msg = entries_of(signed_blob)
    rel2 = _json.loads(zsg.read("asset_rights.json"))
    rep = ar.verify_release(rel2, public_key=ar.public_key_b64(key))
    check("a configured key produces a signed container",
          rel2.get("verification", {}).get("algorithm") == "ed25519")
    check("the signed container verifies under the issuer key", rep["ok"] and rep["trusted_key"], rep)
    check("it does NOT verify under a stranger key",
          not ar.verify_release(rel2, public_key=ar.public_key_b64(ar.generate_seed()))["signature_ok"])
    check("the signing seed never reaches the container", key not in signed_blob.decode("latin-1"))
    check("a second opt-in export reuses the same asset_id",
          _json.loads(zsg.read("project.json")).get("asset_id") == asset)

    # (5) The lineage identity survives the round-trip that regenerates the row id.
    r2 = c.post("/projects/import-bundle", headers=BEARER(tok),
                files={"file": ("Rights.mass", signed_blob, "application/zip")},
                data={"name": "Rights Restored"})
    check("a sealed container imports", r2.status_code == 201, r2.text)
    npid = r2.json()["id"]
    check("the project id IS regenerated on import", npid != pid)
    back = c.get(f"/projects/{npid}/bundle?asset_rights=true", headers=BEARER(tok)).content
    zb, _mb = entries_of(back)
    check("the asset_id SURVIVES the round-trip",
          _json.loads(zb.read("project.json")).get("asset_id") == asset,
          (asset, _json.loads(zb.read("project.json")).get("asset_id")))

    # A plain container (no asset_id at all) must still import — the pre-existing-files case.
    r3 = c.post("/projects/import-bundle", headers=BEARER(tok),
                files={"file": ("legacy.mass", plain, "application/zip")},
                data={"name": "Legacy"})
    check("a container with no asset_rights still imports", r3.status_code == 201, r3.text)

    os.environ.pop(ar.ENABLED_ENV, None)
    os.environ.pop(ar.SIGNING_KEY_ENV, None)
    os.environ.pop(ar.ISSUER_ENV, None)

print()
if FAILED:
    print(f"{len(FAILED)} FAILED: {FAILED}")
    raise SystemExit(1)
print("all asset-rights checks passed")
