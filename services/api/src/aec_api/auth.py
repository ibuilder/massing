"""Minimal optional auth (guide §7/§10). If AEC_API_KEY is set, write endpoints require
`Authorization: Bearer <key>`. Off by default for local dev. Replace with project-scoped
users/roles (viewer/reviewer/editor/admin) backed by your IdP for production."""
from __future__ import annotations

import os

from fastapi import Header, HTTPException

API_KEY = os.environ.get("AEC_API_KEY")


def require_writer(authorization: str | None = Header(default=None)) -> str:
    """Dependency for mutating endpoints. Returns the actor id (or 'dev' when open)."""
    if not API_KEY:
        return "dev"
    if authorization != f"Bearer {API_KEY}":
        raise HTTPException(status_code=401, detail="invalid or missing API key")
    return "api-key"
