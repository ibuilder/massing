"""Build ERC-721 token metadata JSON for a sealed release manifest."""
from __future__ import annotations

from typing import Any


def build_token_metadata(manifest: dict) -> dict[str, Any]:
    """Marketplace-compatible metadata pointing at the release identity, not the whole `.mass`."""
    asset_urn = str(manifest.get("asset_id") or "")
    release_urn = str(manifest.get("release_id") or "")
    content_hash = str(manifest.get("content_hash") or "")
    manifest_hash = str(manifest.get("manifest_hash") or "")
    issuer = str(manifest.get("issuer") or "")
    content = manifest.get("content") if isinstance(manifest.get("content"), dict) else {}
    schema = content.get("schema") if isinstance(content.get("schema"), dict) else {}

    short_release = release_urn.rsplit(":", 1)[-1][:12] if release_urn else "release"
    name = f"Massing Release {short_release}"

    attributes: list[dict[str, str]] = [
        {"trait_type": "asset_id", "value": asset_urn},
        {"trait_type": "content_hash", "value": content_hash},
        {"trait_type": "manifest_hash", "value": manifest_hash},
    ]
    if issuer:
        attributes.append({"trait_type": "issuer", "value": issuer})
    if schema.get("mass_format"):
        attributes.append({"trait_type": "mass_format", "value": str(schema["mass_format"])})
    if schema.get("mass_version") is not None:
        attributes.append({"trait_type": "mass_version", "value": str(schema["mass_version"])})

    digest = content.get("model_digest")
    if digest:
        attributes.append({"trait_type": "model_digest", "value": str(digest)})

    return {
        "name": name,
        "description": "Sealed Massing project release bound to a deterministic content hash.",
        "attributes": attributes,
        "external_url": "https://massing.build",
    }
