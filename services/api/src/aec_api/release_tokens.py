"""Persist release-token mint records — the off-chain registry for asset-rights mints.

Provenance keys on `asset_id` + `content_hash`, never on `project_id` (regenerated on every
`.mass` import). `project_id` is an optional snapshot of which row triggered the mint.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from . import asset_rights as ar
from . import chain_provider as cp
from . import ipfs_storage as ipfs
from . import release_nft_metadata as rnm
from .models import ReleaseToken


def _bare_asset_id(manifest: dict) -> str:
    urn = str(manifest.get("asset_id") or "")
    prefix = ar.ASSET_URN_PREFIX
    if not urn.startswith(prefix):
        raise HTTPException(400, "manifest.asset_id must be urn:massing:asset:…")
    bare = urn[len(prefix):]
    if not bare:
        raise HTTPException(400, "manifest.asset_id is empty")
    return bare


def _bare_release_id(manifest: dict) -> str:
    urn = str(manifest.get("release_id") or "")
    prefix = ar.RELEASE_URN_PREFIX
    if urn.startswith(prefix):
        return urn[len(prefix):]
    return urn or ""


def _require_valid_manifest(manifest: dict, *, public_key: str | None) -> dict:
    """Run the same checks a verifier would — minting must not proceed on a broken manifest."""
    if not isinstance(manifest, dict):
        raise HTTPException(422, "manifest must be an object")
    rep = ar.verify_release(manifest, public_key=public_key)
    if not rep.get("content_hash_ok"):
        raise HTTPException(400, "manifest content_hash does not match its content")
    if not rep.get("manifest_hash_ok"):
        raise HTTPException(400, "manifest_hash does not match the manifest body")
    content_hash = manifest.get("content_hash")
    if not isinstance(content_hash, str) or not content_hash.startswith("sha256:"):
        raise HTTPException(400, "manifest.content_hash is required")
    try:
        cp.validate_content_hash(content_hash)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return rep


def resolve_metadata_uri(manifest: dict, metadata_uri: str | None) -> str:
    """Return a metadata URI, pinning ERC-721 JSON to IPFS when none is supplied."""
    if (metadata_uri or "").strip():
        return metadata_uri.strip()
    meta = rnm.build_token_metadata(manifest)
    filename = f"massing-release-{manifest.get('release_id', 'unknown')}.json"
    return ipfs.get_storage().pin_json(meta, filename=filename)


def _existing_result(row: ReleaseToken) -> cp.MintResult:
    return cp.MintResult(
        provider=row.provider,
        chain_id=row.chain_id,
        contract_address=row.contract_address,
        token_id=row.token_id,
        tx_hash=row.tx_hash or "",
        metadata_uri=row.metadata_uri or "",
        content_hash=row.content_hash,
    )


def mint_from_manifest(
    db: Session,
    manifest: dict,
    *,
    recipient: str | None,
    metadata_uri: str | None,
    minted_by: str,
    project_id: str | None,
    public_key: str | None,
    pin_metadata: bool = True,
) -> tuple[ReleaseToken, cp.MintResult, bool]:
    """Mint (or return an existing record) for `manifest.content_hash`. Returns (row, result, created)."""
    if not cp.enabled():
        raise HTTPException(403, "chain minting is disabled on this deployment")
    _require_valid_manifest(manifest, public_key=public_key)
    content_hash = str(manifest["content_hash"])

    existing = db.query(ReleaseToken).filter(ReleaseToken.content_hash == content_hash).first()
    if existing:
        return existing, _existing_result(existing), False

    uri = resolve_metadata_uri(manifest, metadata_uri) if pin_metadata else (metadata_uri or "").strip()
    if cp.configured_provider_name() == "evm" and not uri:
        raise HTTPException(400, "metadata_uri is required for evm minting (or enable pin_metadata)")

    try:
        provider = cp.get_provider()
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(503, str(exc)) from exc

    try:
        result = provider.mint_release(
            asset_urn=str(manifest["asset_id"]),
            content_hash=content_hash,
            metadata_uri=uri,
            recipient=recipient or "",
        )
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(502, str(exc)) from exc

    row = ReleaseToken(
        id=uuid.uuid4().hex,
        asset_id=_bare_asset_id(manifest),
        release_id=_bare_release_id(manifest),
        content_hash=content_hash,
        manifest_hash=str(manifest.get("manifest_hash") or ""),
        provider=result.provider,
        chain_id=result.chain_id,
        contract_address=result.contract_address,
        token_id=result.token_id,
        tx_hash=result.tx_hash,
        metadata_uri=result.metadata_uri or None,
        recipient=(recipient or "").strip() or None,
        minted_by=minted_by,
        project_id=project_id,
        status="minted",
    )
    db.add(row)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raced = db.query(ReleaseToken).filter(ReleaseToken.content_hash == content_hash).first()
        if raced:
            return raced, _existing_result(raced), False
        raise
    db.refresh(row)
    return row, result, True


def verify_mint(db: Session, content_hash: str) -> dict[str, Any]:
    """Compare the off-chain registry with the configured chain provider."""
    try:
        cp.validate_content_hash(content_hash)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc

    row = db.query(ReleaseToken).filter(ReleaseToken.content_hash == content_hash).first()
    findings: dict[str, Any] = {
        "content_hash": content_hash,
        "registered": row is not None,
        "registry": row_to_dict(row) if row else None,
    }

    if not cp.enabled():
        findings["chain_check"] = "skipped"
        findings["ok"] = row is not None
        return findings

    try:
        on_chain = cp.verify_binding(content_hash)
    except (RuntimeError, ValueError) as exc:
        findings["chain_check"] = "error"
        findings["chain_error"] = str(exc)
        findings["ok"] = False
        return findings

    findings["on_chain"] = on_chain
    if cp.configured_provider_name() == "evm" and row and on_chain.get("token_id"):
        findings["token_id_match"] = str(row.token_id) == str(on_chain.get("token_id"))
        findings["ok"] = bool(row) and bool(on_chain.get("minted")) and findings["token_id_match"]
    else:
        findings["token_id_match"] = None
        findings["ok"] = row is not None
    findings["chain_check"] = "ok"
    return findings


def row_to_dict(row: ReleaseToken) -> dict[str, Any]:
    return {
        "id": row.id,
        "asset_id": row.asset_id,
        "asset_urn": ar.asset_urn(row.asset_id),
        "release_id": row.release_id,
        "content_hash": row.content_hash,
        "manifest_hash": row.manifest_hash,
        "provider": row.provider,
        "chain_id": row.chain_id,
        "contract_address": row.contract_address,
        "token_id": row.token_id,
        "tx_hash": row.tx_hash,
        "metadata_uri": row.metadata_uri,
        "recipient": row.recipient,
        "minted_by": row.minted_by,
        "project_id": row.project_id,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
    }


def get_by_content_hash(db: Session, content_hash: str) -> ReleaseToken | None:
    try:
        cp.validate_content_hash(content_hash)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    return db.query(ReleaseToken).filter(ReleaseToken.content_hash == content_hash).first()


def list_for_asset(db: Session, asset_id: str) -> list[ReleaseToken]:
    if not asset_id:
        return []
    return (
        db.query(ReleaseToken)
        .filter(ReleaseToken.asset_id == asset_id)
        .order_by(ReleaseToken.created_at.desc())
        .all()
    )
