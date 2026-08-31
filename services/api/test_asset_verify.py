"""ASSET-VERIFY — the half a release manifest exists for: someone ELSE can check it.

`asset_rights.py` shipped both halves and only sealing was reachable. Counted against
`services/api/src`, `services/data/src` and `apps/web/src`, excluding the module itself, before this:

    verify_release · verify_signature · verify_content_hash · verify_manifest_hash   0 callers
    public_key_b64 · generate_seed                                                   0 callers
    sign_manifest · build_manifest · new_asset_id                                    1 each

A manifest's whole purpose is that a third party can confirm a release is authentic and unaltered.
Sealing alone produces a file nobody can check — including us. Three things were missing:

1. **Nothing verified a manifest.** Now `POST /asset-rights/verify`.
2. **Nothing published the public key a verifier needs.** `/asset-rights/status` returned `enabled`,
   `signing` and `issuer`; its docstring said "never the key itself", which read as a rule against
   publishing *any* key. `public_key_b64`'s own docstring says the public half is *"safe to publish;
   this is what verifiers need"*, and the same key is embedded in every signed manifest we emit —
   withholding it protected nothing and left a verifier trusting the document's own copy.
3. **Nothing exposed `generate_seed`**, so the *signed* path was unreachable from a clean deployment
   except by minting an Ed25519 seed out of band. Now `python -m aec_api.asset_rights --generate`,
   a command and **not** a route: minting a private key is an operator action at the machine, and no
   request-authorisation gate is worth trusting more than shell access to the host.

**THE DESIGN CORRECTION WORTH KEEPING.** The first plan defaulted `public_key` to this deployment's
key "so `trusted_key` means something". That is wrong, and the matrix below is why: a manifest signed
by anyone else would then be checked against *our* key, fail, and be reported as `signature_ok:
false` — a perfectly valid third-party release described as a bad signature. The key is the caller's
to supply. Omitted, the signature is checked against the key **embedded in the document**, which
proves internal consistency and nothing about authorship — exactly what `trusted_key: false` says.

Run: PYTHONPATH="src:../data/src" ./.venv/bin/python test_asset_verify.py
"""
import os
import subprocess
import sys

os.environ["DATABASE_URL"] = "sqlite:///./test_asset_verify.db"
os.environ.setdefault("STORAGE_DIR", "./test_storage_asset_verify")
os.environ["AEC_ASSET_RIGHTS"] = "1"
os.environ.pop("AEC_RBAC", None)

def _cli(*args: str, **env_over: str) -> subprocess.CompletedProcess:
    """Run the operator command in a subprocess, reading `os.environ` AT CALL TIME.

    It read a snapshot taken at import instead, which is before the seed is set below — so
    `--public-key` ran with no key configured and its refusal branch looked like a broken assertion.
    A fixture that freezes the environment cannot test a tool whose whole job is to read it.
    """
    env = {**os.environ, "PYTHONPATH": os.environ.get("PYTHONPATH", "src:../data/src"), **env_over}
    env = {k: v for k, v in env.items() if v is not None}
    return subprocess.run([sys.executable, "-m", "aec_api.asset_rights", *args],
                          capture_output=True, text=True, env=env)


# The operator command has to run BEFORE the module is imported with a key in the environment.
_gen = _cli("--generate")
os.environ["AEC_ASSET_SIGNING_KEY"] = _gen.stdout.strip()

from fastapi.testclient import TestClient  # noqa: E402

from aec_api import asset_rights as ar  # noqa: E402
from aec_api.main import app  # noqa: E402

_fail = 0


def check(cond, msg):
    """Record one assertion, printing PASS/FAIL, so every check reports rather than the first halting."""
    global _fail
    if not cond:
        _fail += 1
        print(f"FAIL  {msg}")
    else:
        print(f"PASS  {msg}")


client = TestClient(app)


def _manifest(**over):
    content = ar.build_content(model_digest_hash=None,
                               files=[{"logical_path": "project.json", "sha256": "b" * 64, "bytes": 42}],
                               licence=None, mass_format="mass", mass_version=1)
    m = ar.sign_manifest(ar.build_manifest(asset_id=ar.new_asset_id(), content=content, derived=[]))
    m.update(over)
    return m


# --- 1. the operator command ------------------------------------------------------------------------
check(_gen.returncode == 0 and len(_gen.stdout.strip()) > 0, "--generate mints a seed on stdout")
check("PUBLIC key" in _gen.stderr, "--generate explains the public half on stderr, so `--generate > key` "
                                   "captures only the secret and a human still sees what to do")
check(_gen.stdout.strip() not in _gen.stderr, "the seed is NOT echoed into the guidance on stderr")
pub_cli = _cli("--public-key")
check(pub_cli.returncode == 0 and pub_cli.stdout.strip() == ar.public_key_b64(),
      "--public-key prints the configured key's public half")
check(_cli().returncode == 2, "no arguments prints usage and fails (a key tool must not act by default)")
# Positive control on the "no key" branch: without a seed, --public-key must refuse rather than invent.
_nokey = subprocess.run([sys.executable, "-m", "aec_api.asset_rights", "--public-key"],
                        capture_output=True, text=True,
                        env={k: v for k, v in {**os.environ, "PYTHONPATH": os.environ.get("PYTHONPATH", "src:../data/src")}.items()
                             if k != "AEC_ASSET_SIGNING_KEY"})
# Not just "it failed" — a CLEAN refusal. Without the `signing_available()` guard, `public_key_b64`
# raises RuntimeError and the process dies with a traceback: still non-zero, still no stdout, so an
# exit-code assertion alone passes on a crash. The mutation check caught exactly that. What the guard
# buys is an operator being TOLD what to set, so that is what gets asserted.
check(_nokey.returncode == 1 and not _nokey.stdout.strip(),
      "--public-key refuses when no seed is configured, and prints no key")
check("Traceback" not in _nokey.stderr,
      "...and refuses CLEANLY — a traceback is a crash, not a refusal")
check("AEC_ASSET_SIGNING_KEY" in _nokey.stderr and "--generate" in _nokey.stderr,
      "...naming the variable to set and the command that mints one")

# --- 1b. a MALFORMED key is not a usable key ---------------------------------------------------------
# `signing_available()` asked only `bool(env)` — a claim, not a fact — and every consumer trusted it.
# `bundle.py` signs when it is true, so a variable holding anything that is not a 32-byte seed took
# down the WHOLE .mass export from `_private_key`, and publishing the key on /asset-rights/status
# turned the same fault into an unhandled error on the route a client calls to decide whether to
# offer sealing. Found in review of this PR; the export half of it pre-dates this release.
import importlib  # noqa: E402

_real_seed = os.environ["AEC_ASSET_SIGNING_KEY"]
for bad in ("not-a-real-seed", "!!!!", "c2hvcnQ="):          # non-b64, junk, and valid b64 too short
    os.environ["AEC_ASSET_SIGNING_KEY"] = bad
    importlib.reload(ar)
    check(ar.signing_available() is False, f"a malformed seed is not 'available': {bad!r}")
    st_bad = TestClient(app).get("/asset-rights/status")
    check(st_bad.status_code == 200 and st_bad.json()["public_key"] == "" and not st_bad.json()["signing"],
          f"...and /asset-rights/status answers 200 with signing:false rather than erroring: {bad!r}")
    cli_bad = _cli("--public-key")
    check(cli_bad.returncode == 1 and "is set but is not a usable" in cli_bad.stderr,
          f"...and the CLI says SET-BUT-UNUSABLE, not 'not configured': {bad!r}")
os.environ["AEC_ASSET_SIGNING_KEY"] = _real_seed
importlib.reload(ar)
check(ar.signing_available() is True, "positive control: the real seed is still usable after the "
                                      "malformed ones (otherwise the checks above would pass on a "
                                      "function that always answers False)")

# --- 2. the public key is served, the private one is not --------------------------------------------
st = client.get("/asset-rights/status").json()
check(st.get("public_key") == ar.public_key_b64(), "GET /asset-rights/status serves the public key")
check(os.environ["AEC_ASSET_SIGNING_KEY"] not in str(st), "the SEED never appears in the status body")
check({"enabled", "signing", "issuer", "public_key"} <= set(st), f"status keeps its existing keys: {sorted(st)}")

# --- 3. verify, across the three trust cases --------------------------------------------------------
m = _manifest()
r = client.post("/asset-rights/verify", json={"manifest": m})
check(r.status_code == 200 and r.json()["signature_ok"] and not r.json()["trusted_key"],
      "no key supplied -> verified against the EMBEDDED key: self-consistent, trusted_key False")
r = client.post("/asset-rights/verify", json={"manifest": m, "public_key": st["public_key"]})
check(r.status_code == 200 and r.json()["trusted_key"], "the right trusted key -> trusted_key True")

# THE reason public_key is not defaulted to ours. A third party's manifest checked against our key
# reports a valid signature as invalid, so defaulting would make the route lie about other people's
# releases. This asserts the failure mode exists, which is what makes the design choice load-bearing.
other = ar.public_key_b64(ar.generate_seed())
r = client.post("/asset-rights/verify", json={"manifest": m, "public_key": other})
check(r.status_code == 200 and not r.json()["signature_ok"],
      "a DIFFERENT key -> signature_ok False (so defaulting to ours would misreport third-party releases)")

# The footgun the route docstring warns about, asserted so the warning is not just prose: the SAME
# document and the same cryptographic evidence read `trusted_key: false` honestly, and `true` if the
# caller echoes the document's own key back. The API cannot tell those apart — it has no trust anchor
# — which is exactly why trusting a key is the part a verifier must do out of band. Comparing against
# the embedded key would NOT fix this: for a genuine release the trusted key IS the embedded one.
_embedded = m["verification"]["public_key"]
_echoed = client.post("/asset-rights/verify", json={"manifest": m, "public_key": _embedded}).json()
_honest = client.post("/asset-rights/verify", json={"manifest": m}).json()
check(_echoed["trusted_key"] is True and _honest["trusted_key"] is False,
      "echoing the document's own key back flips trusted_key on identical evidence — the documented "
      "limit of what this route can know, pinned so it is not mistaken for a bug later")
check(_echoed["signature_ok"] == _honest["signature_ok"],
      "...and the SIGNATURE finding is identical either way, which is the part that is really proven")

# --- 4. tampering is what the manifest exists to catch -----------------------------------------------
tampered = {**m, "content": {**m["content"], "files": []}}
r = client.post("/asset-rights/verify", json={"manifest": tampered, "public_key": st["public_key"]}).json()
check(not r["content_hash_ok"] and not r["ok"], "altered content fails the content hash")

# --- 5. no vacuous pass ------------------------------------------------------------------------------
# The defect this repository keeps finding is a check that cannot fail. An empty or hash-less manifest
# must not verify, or `ok` would mean "nothing contradicted me" rather than "this is a real release".
for label, junk in [("{}", {}), ("no content", {"manifest_hash": "x"}),
                    ("content, no hashes", {"content": {"files": []}}),
                    ("hashes claimed but wrong", {"content": {"files": []},
                                                  "content_hash": "0" * 64, "manifest_hash": "0" * 64})]:
    got = client.post("/asset-rights/verify", json={"manifest": junk}).json()
    check(got["ok"] is False, f"a degenerate manifest does not verify: {label}")

# --- 6. the routes are REACHABLE, which is the whole item --------------------------------------------
# Asserted by REQUESTING them, not by reading `app.routes` — that list holds 11 entries at import
# because the routers mount lazily, so an "is it in app.routes" check reports every route in this
# service as missing. A 404 is what an unwired route actually does to a caller.
check(client.post("/asset-rights/verify", json={"manifest": {}}).status_code != 404,
      "POST /asset-rights/verify is reachable (not 404)")
check(client.get("/asset-rights/status").status_code != 404,
      "GET /asset-rights/status is still reachable (not 404)")
check(client.post("/asset-rights/no-such-route", json={}).status_code == 404,
      "positive control: a route that does NOT exist really does 404, so the two checks above "
      "are not passing on a server that answers everything")

print()
if _fail:
    raise SystemExit(f"asset_verify: {_fail} check(s) failed")
print("asset_verify: all checks passed — a release can now be checked by whoever receives it: the "
      "public key is published, the manifest can be verified against a caller-supplied key or its "
      "own, tampering fails the content hash, a degenerate manifest never passes, and an operator "
      "has a supported way to mint a signing key without one existing on an HTTP route.")
