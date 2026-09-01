"""Chain provider abstraction — step 4 of asset-rights / NFT work.

Binds a sealed release manifest's `content_hash` to an on-chain (or mock) token record. No RPC,
no wallet, and no new dependency until a real provider is wired in step 5. See
`docs/internal/asset-rights-nft-design.md`.

The mock provider generates deterministic, clearly-labelled stand-ins so the API, database, and
tests can exercise the full mint lifecycle without touching a network.
"""
from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

#: Master feature flag. The whole chain capability is OFF unless this is explicitly truthy.
ENABLED_ENV = "AEC_CHAIN_ENABLED"
#: Which provider backs minting. Only ``mock`` ships today; ``evm`` is reserved for step 5.
PROVIDER_ENV = "AEC_CHAIN_PROVIDER"

_TRUTHY = {"1", "true", "yes", "on"}
_MOCK_CONTRACT = "mock:MassRelease721"
_MOCK_CHAIN_ID = 0


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


def _mock_token_id(content_hash: str) -> str:
    digest = hashlib.sha256(content_hash.encode("utf-8")).hexdigest()
    # Fits uint256 and is stable for the same release identity.
    return str(int(digest[:16], 16))


def _mock_tx_hash(content_hash: str, recipient: str) -> str:
    payload = f"{content_hash}|{recipient}".encode()
    return "mock:0x" + hashlib.sha256(payload).hexdigest()


class MockChainProvider:
    """Deterministic stand-in for step 5. Labels every field so it cannot be mistaken for mainnet."""

    name = "mock"

    def mint_release(
        self,
        *,
        asset_urn: str,
        content_hash: str,
        metadata_uri: str,
        recipient: str,
    ) -> MintResult:
        if not content_hash.startswith("sha256:"):
            raise ValueError("content_hash must be a sha256:… digest")
        if not asset_urn.startswith("urn:massing:asset:"):
            raise ValueError("asset_urn must be urn:massing:asset:…")
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
    """Resolve the configured provider. Raises if chain is enabled but the name is unknown."""
    name = configured_provider_name()
    if name == "mock":
        return MockChainProvider()
    raise RuntimeError(
        f"unknown chain provider {name!r}: only 'mock' is implemented (step 4). "
        "Set AEC_CHAIN_PROVIDER=mock or leave unset.")


def status() -> dict:
    """Deployment-facing chain capability summary for `/asset-rights/status`."""
    return {
        "enabled": enabled(),
        "provider": configured_provider_name(),
        "mock": configured_provider_name() == "mock",
    }
