"""Chain provider abstraction — asset-rights / NFT work (steps 4–5).

Binds a sealed release manifest's `content_hash` to an on-chain (or mock) token record. The mock
provider is deterministic and needs no network; the evm provider talks to a deployed
`MassRelease721` contract via JSON-RPC.
"""
from __future__ import annotations

import hashlib
import os
import re
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

#: Master feature flag. The whole chain capability is OFF unless this is explicitly truthy.
ENABLED_ENV = "AEC_CHAIN_ENABLED"
#: Which provider backs minting: ``mock`` (default) or ``evm``.
PROVIDER_ENV = "AEC_CHAIN_PROVIDER"

_TRUTHY = {"1", "true", "yes", "on"}
_MOCK_CONTRACT = "mock:MassRelease721"
_MOCK_CHAIN_ID = 0
_CONTENT_HASH_RE = re.compile(r"^sha256:[0-9a-fA-F]{64}$")


@dataclass(frozen=True, slots=True)
class MintResult:
    """What a provider returns after a successful mint (or mock mint)."""
    provider: str
    chain_id: int
    contract_address: str
    token_id: str
    tx_hash: str
    metadata_uri: str
    content_hash: str


@runtime_checkable
class ChainProvider(Protocol):
    """Mint a release token bound to `content_hash`. Real implementations talk to RPC; mock does not."""

    @property
    def name(self) -> str: ...

    def mint_release(
        self,
        *,
        asset_urn: str,
        content_hash: str,
        metadata_uri: str,
        recipient: str,
    ) -> MintResult: ...


def enabled() -> bool:
    """Whether chain minting is switched on. Default **off**, same posture as asset-rights."""
    return (os.environ.get(ENABLED_ENV) or "").strip().lower() in _TRUTHY


def configured_provider_name() -> str:
    raw = (os.environ.get(PROVIDER_ENV) or "mock").strip().lower()
    return raw or "mock"


def validate_content_hash(content_hash: str) -> None:
    if not _CONTENT_HASH_RE.match(content_hash or ""):
        raise ValueError("content_hash must be sha256:<64 lowercase hex digits>")


def validate_asset_urn(asset_urn: str) -> None:
    if not (asset_urn or "").startswith("urn:massing:asset:"):
        raise ValueError("asset_urn must be urn:massing:asset:…")
    if not asset_urn[len("urn:massing:asset:"):]:
        raise ValueError("asset_urn is empty")


def content_hash_to_bytes32(content_hash: str) -> bytes:
    validate_content_hash(content_hash)
    return bytes.fromhex(content_hash.removeprefix("sha256:"))


def _mock_token_id(content_hash: str) -> str:
    digest = hashlib.sha256(content_hash.encode()).hexdigest()
    return str(int(digest[:16], 16))


def _mock_tx_hash(content_hash: str, recipient: str) -> str:
    payload = f"{content_hash}|{recipient}".encode()
    return "mock:0x" + hashlib.sha256(payload).hexdigest()


class MockChainProvider:
    """Deterministic stand-in. Labels every field so it cannot be mistaken for mainnet."""

    name = "mock"

    def mint_release(
        self,
        *,
        asset_urn: str,
        content_hash: str,
        metadata_uri: str,
        recipient: str,
    ) -> MintResult:
        validate_content_hash(content_hash)
        validate_asset_urn(asset_urn)
        rcpt = (recipient or "").strip() or "mock:0x0000000000000000000000000000000000000000"
        uri = (metadata_uri or "").strip() or f"mock:manifest/{content_hash.removeprefix('sha256:')}"
        return MintResult(
            provider=self.name,
            chain_id=_MOCK_CHAIN_ID,
            contract_address=_MOCK_CONTRACT,
            token_id=_mock_token_id(content_hash),
            tx_hash=_mock_tx_hash(content_hash, rcpt),
            metadata_uri=uri,
            content_hash=content_hash,
        )


def get_provider() -> ChainProvider:
    """Resolve the configured provider."""
    name = configured_provider_name()
    if name == "mock":
        return MockChainProvider()
    if name == "evm":
        from . import evm_provider as evm

        if not evm.evm_configured():
            raise RuntimeError(
                "evm chain provider selected but not fully configured — set "
                f"{evm.RPC_ENV}, {evm.CHAIN_ID_ENV}, {evm.CONTRACT_ENV}, and {evm.MINT_KEY_ENV}")
        return evm.EvmChainProvider()
    raise RuntimeError(f"unknown chain provider {name!r}: use mock or evm")


def status() -> dict[str, Any]:
    """Deployment-facing chain capability summary for `/asset-rights/status`."""
    from . import evm_provider as evm
    from . import ipfs_storage as ipfs

    name = configured_provider_name()
    out: dict[str, Any] = {
        "enabled": enabled(),
        "provider": name,
        "mock": name == "mock",
        "ipfs": ipfs.status(),
    }
    if name == "evm":
        out["evm"] = evm.evm_status()
    return out


def verify_binding(content_hash: str) -> dict[str, Any]:
    """Read on-chain (or mock-stand-in) binding for a release hash."""
    validate_content_hash(content_hash)
    name = configured_provider_name()
    if name == "mock":
        return {
            "provider": "mock",
            "content_hash": content_hash,
            "minted": None,
            "note": "mock provider has no on-chain state; use the registry record",
        }
    if name == "evm":
        from . import evm_provider as evm

        rep = evm.verify_on_chain(content_hash)
        rep["provider"] = "evm"
        return rep
    raise RuntimeError(f"unknown chain provider {name!r}")
