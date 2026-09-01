"""IPFS pinning for release NFT metadata — mock and Pinata backends.

The mock backend is deterministic and needs no credentials. Pinata uses `httpx` against the
Pinata v3 JSON pin API when `AEC_IPFS_PINATA_JWT` is set.
"""
from __future__ import annotations

import hashlib
import os
from typing import Any, Protocol, runtime_checkable

from . import asset_rights as ar

PROVIDER_ENV = "AEC_IPFS_PROVIDER"
PINATA_JWT_ENV = "AEC_IPFS_PINATA_JWT"
GATEWAY_ENV = "AEC_IPFS_GATEWAY"


@runtime_checkable
class IpfsStorage(Protocol):
    @property
    def name(self) -> str: ...

    def pin_json(self, obj: dict[str, Any], *, filename: str) -> str:
        """Return an `ipfs://…` URI for the pinned JSON object."""


def configured_provider_name() -> str:
    return (os.environ.get(PROVIDER_ENV) or "mock").strip().lower() or "mock"


def _mock_cid(content: bytes) -> str:
    digest = hashlib.sha256(content).hexdigest()
    return f"bafymock{digest[:52]}"


class MockIpfsStorage:
    name = "mock"

    def pin_json(self, obj: dict[str, Any], *, filename: str) -> str:
        raw = ar.canonical_bytes(obj)
        return f"ipfs://{_mock_cid(raw)}"


class PinataIpfsStorage:
    name = "pinata"

    def pin_json(self, obj: dict[str, Any], *, filename: str) -> str:
        jwt = (os.environ.get(PINATA_JWT_ENV) or "").strip()
        if not jwt:
            raise RuntimeError(f"{PINATA_JWT_ENV} is required for the pinata IPFS provider")
        import httpx

        body = {
            "pinataContent": obj,
            "pinataMetadata": {"name": filename[:255]},
        }
        with httpx.Client(timeout=30.0) as client:
            resp = client.post(
                "https://api.pinata.cloud/pinning/pinJSONToIPFS",
                headers={"Authorization": f"Bearer {jwt}", "Content-Type": "application/json"},
                json=body,
            )
        if resp.status_code >= 400:
            raise RuntimeError(f"Pinata pin failed ({resp.status_code}): {resp.text[:200]}")
        cid = resp.json().get("IpfsHash")
        if not cid:
            raise RuntimeError("Pinata response missing IpfsHash")
        return f"ipfs://{cid}"


def get_storage() -> IpfsStorage:
    name = configured_provider_name()
    if name == "mock":
        return MockIpfsStorage()
    if name == "pinata":
        return PinataIpfsStorage()
    raise RuntimeError(f"unknown IPFS provider {name!r}: use mock or pinata")


def status() -> dict[str, Any]:
    name = configured_provider_name()
    ready = name == "mock" or bool((os.environ.get(PINATA_JWT_ENV) or "").strip())
    return {
        "provider": name,
        "ready": ready,
        "mock": name == "mock",
        "gateway": (os.environ.get(GATEWAY_ENV) or "").strip(),
    }
