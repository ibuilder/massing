"""Object storage abstraction. Local filesystem for dev; swap for MinIO/S3 (boto3) in
prod by implementing the same put/get/path interface (guide §1, §7)."""
from __future__ import annotations

import os
from pathlib import Path

STORAGE_DIR = Path(os.environ.get("STORAGE_DIR", "./storage")).resolve()


def put(key: str, data: bytes) -> str:
    dest = STORAGE_DIR / key
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return key


def get(key: str) -> bytes:
    return (STORAGE_DIR / key).read_bytes()


def path(key: str) -> Path:
    return STORAGE_DIR / key


def exists(key: str) -> bool:
    return (STORAGE_DIR / key).exists()
