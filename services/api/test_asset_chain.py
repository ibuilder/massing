"""ASSET-CHAIN — step 4: provider abstraction + mock mint registry, no RPC.

Run: cd services/api && PYTHONPATH=src:../data/src python3 test_asset_chain.py
"""
from __future__ import annotations

import io
import json
import os
import sys
import zipfile

os.environ["DATABASE_URL"] = "sqlite:///./asset_chain_test.db"
os.environ["STORAGE_DIR"] = "./test_storage_asset_chain"
os.environ.pop("AEC_RBAC", None)
for _f in ("./asset_chain_test.db",):
    if os.path.exists(_f):
        os.remove(_f)

sys.path.insert(0, "src")

from aec_api import asset_rights as ar  # noqa: E402
from aec_api import chain_provider as cp  # noqa: E402
from aec_api import release_tokens as rt  # noqa: E402
from aec_api.main import app  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

FAILED: list[str] = []


def check(label, ok, detail=""):
    line = f"{'PASS' if ok else 'FAIL'}  {label}"
    if detail and not ok:
        line += " — " + str(detail)
    print(line)
    if not ok:
        FAILED.append(label)


def _manifest(*, asset="abc123", rel="rel1", digest="sha256:aaa"):
    content = ar.build_content(
        model_digest_hash=digest,
        files=[{"logical_path": "project.json", "media_type": "application/json",
                "sha256": "ab12", "bytes": 4}],
        licence={"profile": "project-delivery-v1", "terms_hash": "sha256:beef"},
        mass_format="massing.project", mass_version=2,
    )
    return ar.build_manifest(asset_id=asset, content=content, release_id=rel)


# --- chain_provider unit ------------------------------------------------------
os.environ.pop(cp.ENABLED_ENV, None)
check("chain disabled by default", not cp.enabled())

os.environ[cp.ENABLED_ENV] = "true"
check("chain enabled when env set", cp.enabled())
check("default provider is mock", cp.configured_provider_name() == "mock")

mock = cp.MockChainProvider()
m1 = _manifest()
r1 = mock.mint_release(
    asset_urn=m1["asset_id"],
    content_hash=m1["content_hash"],
    metadata_uri="ipfs://bafytest",
    recipient="0xRecipient1",
)
r2 = mock.mint_release(
    asset_urn=m1["asset_id"],
    content_hash=m1["content_hash"],
    metadata_uri="ipfs://bafytest",
    recipient="0xRecipient1",
)
check("mock token_id is deterministic", r1.token_id == r2.token_id, (r1.token_id, r2.token_id))
check("mock tx_hash is deterministic", r1.tx_hash == r2.tx_hash)
check("mock labels contract", r1.contract_address.startswith("mock:"))
check("mock chain_id is zero", r1.chain_id == 0)

other = _manifest(rel="rel2", digest="sha256:bbb")
r3 = mock.mint_release(
    asset_urn=other["asset_id"],
    content_hash=other["content_hash"],
    metadata_uri="",
    recipient="",
)
check("different content_hash yields different token_id", r1.token_id != r3.token_id)

try:
    mock.mint_release(asset_urn="bad", content_hash=m1["content_hash"],
                     metadata_uri="", recipient="")
    check("reject bad asset_urn", False)
except ValueError:
    check("reject bad asset_urn", True)

# --- API integration ----------------------------------------------------------
BEARER = lambda t: {"Authorization": f"Bearer {t}"}  # noqa: E731

with TestClient(app) as c:
    c.post("/auth/register", json={"username": "admin", "password": "supersecret"})
    tok = c.post("/auth/login", json={"username": "admin", "password": "supersecret"}).json()["token"]
    pid = c.post("/projects", json={"name": "Chain Source"}).json()["id"]

    os.environ.pop(cp.ENABLED_ENV, None)
    st = c.get("/asset-rights/status", headers=BEARER(tok)).json()
    check("status reports chain.enabled false by default", st.get("chain", {}).get("enabled") is False)

    blocked = c.post("/asset-rights/mint", json={"manifest": _manifest()}, headers=BEARER(tok))
    check("mint 403 while chain disabled", blocked.status_code == 403)

    os.environ[cp.ENABLED_ENV] = "true"
    st2 = c.get("/asset-rights/status", headers=BEARER(tok)).json()
    check("status reports chain.enabled true when configured", st2["chain"]["enabled"] is True)
    check("status reports mock provider", st2["chain"]["provider"] == "mock" and st2["chain"]["mock"] is True)

    man = _manifest()

    os.environ[ar.ENABLED_ENV] = "true"
    bad = c.post("/asset-rights/mint", json={"manifest": {"content_hash": "sha256:dead"}}, headers=BEARER(tok))
    check("mint rejects broken manifest", bad.status_code == 400)

    mint1 = c.post(
        "/asset-rights/mint",
        json={"manifest": man, "recipient": "0xabc", "metadata_uri": "ipfs://meta", "project_id": pid},
        headers=BEARER(tok),
    )
    check("mint succeeds", mint1.status_code == 200, mint1.text)
    body1 = mint1.json()
    check("first mint created=true", body1.get("created") is True)
    check("mint stores content_hash", body1["mint"]["content_hash"] == man["content_hash"])
    check("mint records mock provider", body1["chain"]["provider"] == "mock")
    check("mint returns token_id", bool(body1["chain"]["token_id"]))

    mint2 = c.post("/asset-rights/mint", json={"manifest": man}, headers=BEARER(tok))
    body2 = mint2.json()
    check("second mint is idempotent", body2.get("created") is False)
    check("idempotent mint same row id", body1["mint"]["id"] == body2["mint"]["id"])

    lookup = c.get(f"/asset-rights/mints?content_hash={man['content_hash']}", headers=BEARER(tok))
    check("lookup by content_hash", lookup.status_code == 200 and lookup.json()["id"] == body1["mint"]["id"])

    missing = c.get("/asset-rights/mints?content_hash=sha256:0000000000000000000000000000000000000000000000000000000000000000",
                    headers=BEARER(tok))
    check("lookup 404 when absent", missing.status_code == 404)

    # Project-scoped list requires asset_id on the project.
    os.environ.pop(ar.SIGNING_KEY_ENV, None)
    sealed = c.get(f"/projects/{pid}/bundle?asset_rights=true", headers=BEARER(tok)).content
    zp = zipfile.ZipFile(io.BytesIO(sealed))
    rel = json.loads(zp.read("asset_rights.json"))
    asset = json.loads(zp.read("project.json"))["asset_id"]
    c.post("/asset-rights/mint", json={"manifest": rel, "project_id": pid}, headers=BEARER(tok))
    listed = c.get(f"/projects/{pid}/asset-rights/mints", headers=BEARER(tok)).json()
    check("project list includes asset_id", listed["asset_id"] == asset)
    check("project list has at least one mint", len(listed["mints"]) >= 1)

    empty_pid = c.post("/projects", json={"name": "No Asset"}).json()["id"]
    empty = c.get(f"/projects/{empty_pid}/asset-rights/mints", headers=BEARER(tok)).json()
    check("project without asset_id returns empty list", empty["mints"] == [] and empty["asset_id"] is None)

# --- release_tokens service (direct) ------------------------------------------
from aec_api.db import SessionLocal  # noqa: E402

with SessionLocal() as db:
    man3 = _manifest(asset="direct1", rel="r-direct", digest="sha256:service-direct")
    row, res, created = rt.mint_from_manifest(
        db, man3, recipient="0x1", metadata_uri="mock://x", minted_by="tester", project_id=None, public_key=None,
    )
    check("service mint created", created and row.content_hash == man3["content_hash"])
    again, _, created2 = rt.mint_from_manifest(
        db, man3, recipient="0x2", metadata_uri="", minted_by="tester", project_id=None, public_key=None,
    )
    check("service mint idempotent", not created2 and again.id == row.id)

print()
if FAILED:
    print(f"test_asset_chain FAILED ({len(FAILED)}):", ", ".join(FAILED))
    sys.exit(1)
print("test_asset_chain OK")
