"""EVM chain provider — mint release tokens via `MassRelease721` on an Ethereum-compatible network.

Lazy-imports `web3` so deployments that only use the mock provider pay no import cost. Configure with:

  AEC_CHAIN_RPC_URL          JSON-RPC endpoint
  AEC_CHAIN_ID               chain id (integer)
  AEC_CHAIN_CONTRACT         deployed MassRelease721 address
  AEC_CHAIN_MINT_KEY         issuer private key (hex, never logged)
  AEC_CHAIN_DEFAULT_RECIPIENT optional fallback when mint has no recipient
"""
from __future__ import annotations

import os
from typing import Any

from .chain_provider import MintResult, content_hash_to_bytes32, validate_asset_urn, validate_content_hash

RPC_ENV = "AEC_CHAIN_RPC_URL"
CHAIN_ID_ENV = "AEC_CHAIN_ID"
CONTRACT_ENV = "AEC_CHAIN_CONTRACT"
MINT_KEY_ENV = "AEC_CHAIN_MINT_KEY"
DEFAULT_RECIPIENT_ENV = "AEC_CHAIN_DEFAULT_RECIPIENT"

# Minimal ABI — only what the API calls. Source of truth: services/chain/src/MassRelease721.sol
_MASS_RELEASE721_ABI: list[dict[str, Any]] = [
    {
        "type": "function",
        "name": "mintRelease",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "to", "type": "address"},
            {"name": "contentHash", "type": "bytes32"},
            {"name": "assetUrn", "type": "string"},
            {"name": "tokenURI", "type": "string"},
        ],
        "outputs": [{"name": "tokenId", "type": "uint256"}],
    },
    {
        "type": "function",
        "name": "tokenIdForHash",
        "stateMutability": "view",
        "inputs": [{"name": "contentHash", "type": "bytes32"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
]


def _env(name: str) -> str:
    return (os.environ.get(name) or "").strip()


def evm_configured() -> bool:
    return bool(_env(RPC_ENV) and _env(CHAIN_ID_ENV) and _env(CONTRACT_ENV) and _env(MINT_KEY_ENV))


def evm_status() -> dict[str, Any]:
    chain_id_raw = _env(CHAIN_ID_ENV)
    chain_id: int | None = None
    if chain_id_raw.isdigit():
        chain_id = int(chain_id_raw)
    return {
        "configured": evm_configured(),
        "rpc_set": bool(_env(RPC_ENV)),
        "contract": _env(CONTRACT_ENV),
        "chain_id": chain_id,
        "default_recipient": _env(DEFAULT_RECIPIENT_ENV),
    }


def _web3():
    from web3 import Web3

    rpc = _env(RPC_ENV)
    if not rpc:
        raise RuntimeError(f"{RPC_ENV} is required for the evm chain provider")
    w3 = Web3(Web3.HTTPProvider(rpc, request_kwargs={"timeout": 60}))
    if not w3.is_connected():
        raise RuntimeError(f"could not connect to RPC at {RPC_ENV}")
    return w3


def _account(w3):
    key = _env(MINT_KEY_ENV)
    if not key:
        raise RuntimeError(f"{MINT_KEY_ENV} is required for the evm chain provider")
    if not key.startswith("0x"):
        key = "0x" + key
    return w3.eth.account.from_key(key)


def _chain_id() -> int:
    raw = _env(CHAIN_ID_ENV)
    if not raw.isdigit():
        raise RuntimeError(f"{CHAIN_ID_ENV} must be an integer chain id")
    return int(raw)


def _contract_address(w3):
    addr = _env(CONTRACT_ENV)
    if not addr:
        raise RuntimeError(f"{CONTRACT_ENV} is required for the evm chain provider")
    if not w3.is_address(addr):
        raise RuntimeError(f"{CONTRACT_ENV} is not a valid address")
    return w3.to_checksum_address(addr)


def _resolve_recipient(w3, recipient: str) -> str:
    rcpt = (recipient or "").strip() or _env(DEFAULT_RECIPIENT_ENV)
    if not rcpt:
        raise ValueError("recipient is required for evm minting (pass recipient or set "
                         f"{DEFAULT_RECIPIENT_ENV})")
    if not w3.is_address(rcpt):
        raise ValueError(f"invalid recipient address: {rcpt!r}")
    return w3.to_checksum_address(rcpt)


class EvmChainProvider:
    name = "evm"

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
        uri = (metadata_uri or "").strip()
        if not uri:
            raise ValueError("metadata_uri is required for evm minting")

        w3 = _web3()
        acct = _account(w3)
        to = _resolve_recipient(w3, recipient)
        contract = w3.eth.contract(address=_contract_address(w3), abi=_MASS_RELEASE721_ABI)
        digest = content_hash_to_bytes32(content_hash)

        fn = contract.functions.mintRelease(to, digest, asset_urn, uri)
        nonce = w3.eth.get_transaction_count(acct.address)
        tx = fn.build_transaction({
            "from": acct.address,
            "nonce": nonce,
            "chainId": _chain_id(),
        })
        try:
            tx["gas"] = int(w3.eth.estimate_gas(tx) * 1.2)
        except Exception:
            tx["gas"] = 500_000
        if "maxFeePerGas" not in tx and "gasPrice" not in tx:
            latest = w3.eth.get_block("latest")
            base = latest.get("baseFeePerGas")
            if base is not None:
                tx["maxFeePerGas"] = int(base * 2)
                tx["maxPriorityFeePerGas"] = w3.to_wei(1, "gwei")
            else:
                tx["gasPrice"] = w3.eth.gas_price

        signed = acct.sign_transaction(tx)
        tx_hash = w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        if receipt.get("status") != 1:
            raise RuntimeError(f"mint transaction reverted: {tx_hash.hex()}")

        on_chain_id = contract.functions.tokenIdForHash(digest).call()
        if not on_chain_id:
            raise RuntimeError("mint succeeded but tokenIdForHash is zero")

        return MintResult(
            provider=self.name,
            chain_id=_chain_id(),
            contract_address=_contract_address(w3),
            token_id=str(on_chain_id),
            tx_hash=tx_hash.hex(),
            metadata_uri=uri,
            content_hash=content_hash,
        )


def verify_on_chain(content_hash: str) -> dict[str, Any]:
    """Read the on-chain binding for a release hash. Raises if EVM is not configured."""
    validate_content_hash(content_hash)
    w3 = _web3()
    contract = w3.eth.contract(address=_contract_address(w3), abi=_MASS_RELEASE721_ABI)
    digest = content_hash_to_bytes32(content_hash)
    token_id = contract.functions.tokenIdForHash(digest).call()
    return {
        "content_hash": content_hash,
        "chain_id": _chain_id(),
        "contract_address": _contract_address(w3),
        "token_id": str(token_id) if token_id else None,
        "minted": bool(token_id),
    }
