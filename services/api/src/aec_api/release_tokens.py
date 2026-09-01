"""Persist release-token mint records — the off-chain registry for step 4.

Provenance keys on `asset_id` + `content_hash`, never on `project_id` (regenerated on every
`.mass` import). `project_id` is an optional snapshot of which row triggered the mint.
"""
from __future__ import annotations

import uuid
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import Session

from . import asset_rights as ar
from . import chain_provider as cp
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
    rep = ar.verify_release(manifest, public_key=public_key)
    if not rep.get("content_hash_ok"):
        raise HTTPException(400, "manifest content_hash does not match its content")
    if not rep.get("manifest_hash_ok"):
        raise HTTPException(400, "manifest_hash does not match the manifest body")
    content_hash = manifest.get("content_hash")
    if not isinstance(content_hash, str) or not content_hash.startswith("sha256:"):
        raise HTTPException(400, "manifest.content_hash is required")
    return rep


def mint_from_manifest(
    db: Session,
    manifest: dict,
    *,
    recipient: str | None,
    metadata_uri: str | None,
    minted_by: str,
    project_id: str | None,
    public_key: str | None,
) -> tuple[ReleaseToken, cp.MintResult, bool]:
    """Mint (or return an existing record) for `manifest.content_hash`. Returns (row, result, created)."""
    if not cp.enabled():
        raise HTTPException(403, "chain minting is disabled on this deployment")
    _require_valid_manifest(manifest, public_key=public_key)
    content_hash = str(manifest["content_hash"])
    existing = db.query(ReleaseToken).filter(ReleaseToken.content_hash == content_hash).first()
    if existing:
        result = cp.MintResult(
            provider=existing.provider,
            chain_id=existing.chain_id,
            contract_address=existing.contract_address,
            token_id=existing.token_id,
            tx_hash=existing.tx_hash or "",
            metadata_uri=existing.metadata_uri or "",
            content_hash=existing.content_hash,
        )
        return existing, result, False

    provider = cp.get_provider()
    result = provider.mint_release(
        asset_urn=str(manifest["asset_id"]),
        content_hash=content_hash,
        metadata_uri=metadata_uri or "",
        recipient=recipient or "",
    )
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
    db.commit()
    db.refresh(row)
    return row, result, True


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
    if not content_hash.startswith("sha256:"):
        raise HTTPException(400, "content_hash must be sha256:…")
    return db.query(ReleaseToken).filter(ReleaseToken.content_hash == content_hash).first()


def list_for_asset(db: Session, asset_id: str) -> list[ReleaseToken]:
    return (
        db.query(ReleaseToken)
        .filter(ReleaseToken.asset_id == asset_id)
        .order_by(ReleaseToken.created_at.desc())
        .all()
    )
